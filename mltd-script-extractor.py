import argparse
import json
import logging
import pathlib
import os
import re

p = argparse.ArgumentParser(
    prog='mltd-script-extractor',
    description='Convert MLTD script/text data into a human readable transcript',
)
p.add_argument(
    'src_dir',
    help='directory containing commu .txt and .json files to parse (assumes files are paired like foo_jp.gtx.txt and foo.json)'
    )
# TODO: implement
# p.add_argument(
#     '-p', '--prefix',
#     help="only parse .txt/.json files starting with this prefix (useful when dealing with a directory containing multiple commus)",
#     )
# TODO: implement
# p.add_argument(
#     '-f', '--output-format',
#     default='',
#     help='How resulting transcript will be formatted (default: %(default)s)',
#     metavar='FORMAT'
#     )
p.add_argument(
    '-o', '--output-dir',
    default='transcribed',
    help="Directory to save transcript to (default: %(default)s)",
    metavar='DIR'
    )
p.add_argument(
    '-c', '--cm-gtx',
    default='CM_jp.gtx.txt',
    help='Name of common strings file (default: %(default)s)',
    metavar='CM_FILE'
    )
p.add_argument(
    '-n', '--names-file',
    default='character_names.json',
    help='Name of character display name cache file (default: %(default)s)',
    metavar='NAME_FILE'
    )
p.add_argument(
    '-r', '--force-regen-names',
    action='store_true',
    help='Force regeneration of character display name cache file'
    )
p.add_argument(
    '--only-regen-names',
    action='store_true',
    help='Only generate the character display name cache file from CM file, do nothing else (implies --force-regen-names)'
    )

args = p.parse_args()

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

# shamelessly lifted from https://stackoverflow.com/questions/3862010/is-there-a-generator-version-of-string-split-in-python
def splitStr(string, sep='\\s+'):
    # warning: does not yet work if sep is a lookahead like `(?=b)`
    if sep=='':
        return (c for c in string)
    else:
        return (_.group(1) for _ in re.finditer(f'(?:^|{sep})((?:(?!{sep}).)*)', string, flags=re.DOTALL))
    
def generateNameCache(source_filename=args.cm_gtx, destination_filename=args.names_file):
    logging.info(f'reading {source_filename}...')

    with open(source_filename, 'r', encoding='utf8') as f:
        common_strings = splitStr(f.read(), sep='\\|')

    cm_count = 0
    display_char_count = 0
    display_chars = dict()

    while (token := next(common_strings, None)) is not None:
        cm_count += 1
        if token.startswith('display_character_'):
            display_char_count += 1
            (id, name) = token.split('^')
            display_chars.update({id: name})

    logging.info(f'found {display_char_count} display_character entries in {cm_count} strings!')
    logging.info(f'writing to {destination_filename}...')

    with open(destination_filename, 'w', encoding='utf8') as f:
        json.dump(display_chars, f, ensure_ascii=False, indent=4)


### IT BEGINS
if args.only_regen_names:
    generateNameCache()
    logging.info('--only-regen-names specified, exiting...')
    exit()

### setting up name lookup dictionary
if os.path.isfile(args.names_file):
    if args.force_regen_names:
        logging.info(f'overwriting existing name cache at {args.names_file}!')
        generateNameCache()
    else:
        logging.info(f'name cache already found at {args.names_file}, using...')
else:
    logging.info(f'no name cache file found, generating...')
    generateNameCache()

with open(args.names_file, 'r', encoding='utf8') as f:
    names = json.load(f)

logging.debug(f'found {len(names)} names!')

### flip through source directory
json_files = []
txt_files = []

logging.info(f'checking {args.src_dir} for commu data...')
src_dir = os.fsencode(args.src_dir)
for file in os.listdir(src_dir):
    filename = os.fsdecode(file)

    if filename.endswith(".json"):
        json_files.append(filename)
        continue

    if filename.endswith(".txt"):
        txt_files.append(filename)
        continue

logging.debug(f'found {len(json_files)} .json files and {len(txt_files)} .txt files!')
json_files.sort()
txt_files.sort()
chapters = list(zip(json_files, txt_files))
logging.debug(f'json_files: {json_files}')
logging.debug(f'txt_files: {txt_files}')
logging.debug(f'merged chapter list: {chapters}')

# take the first 3 segments, which is sufficient for events and main commus
commu_id = '_'.join(json_files[0].split('_')[0:3])
all_chapters = []

for i, chap in enumerate(chapters):
    chapter_id_quick = chap[0].replace('.json','')
    chapter_id = None # actual "real" chapter ID, just in case it ever differs from the standard file naming convention
    logging.info(f'({i+1}/{len(chapters)}) working through chapter {chapter_id_quick}...')

    events = []
    gtx_lines = {}
    chapter_output = {
        'id': chapter_id_quick,
        'title': None,
        'lines': []
    }

    # read through commu json and filter for only actor_text (and select1) events
    with open(os.path.join(args.src_dir, chap[0]), 'r', encoding='utf-8-sig') as f:
        all_events = json.load(f)
        chapter_id = all_events['header']['title'] # fetch the "real" name, just in case
        chapter_output.update({'id': chapter_id})
        events = list(filter(lambda e: e['command'] == "actor_text", all_events['datas']['CutRecord']))
        button_events = list(filter(lambda e: e['command'] == "select1", all_events['datas']['Scenario']))

        logging.debug(f'  found {len(events)} actor_text events in .json!')
        logging.debug(f'  + found {len(button_events)} select1 buttons in .json!')
    
    # open up commu text data and filter out _title and _synopsis events
    with open(os.path.join(args.src_dir, chap[1]), 'r', encoding='utf8') as f:
        all_lines = splitStr(f.read(), sep='\\|')
        line_count = 0

        while (token := next(all_lines, None)) is not None:
            (id, text) = token.split('^')
            
            if id.endswith('_title'):
                chapter_output.update({'title': text})
                logging.info(f'  chapter title: {text}')
                continue
            elif id.endswith('_synopsis'):
                continue
            elif id.endswith('_null') and text == 'テキスト無し':
                logging.warning(f'  skipping {id}, null and textless')
                continue
            else:
                line_count += 1
                gtx_lines.update({id: text})

        logging.debug(f'  found {line_count} lines in text data!')
        # logging.debug(f'gtx_lines {gtx_lines}')

    # run through actor_text events and tie it all together
    #   notable args for actor_text events:
    #   - arg1 is the 1000, 1001, etc ID used to refer to this specific line of text
    #   - arg5 is the display_character item to use (not to be confused with arg4, which is the actual character speaking) (...or null)
    #   - arg6 is the ID to pull from the .gtx file
    #   - arg7 is the .acb to pull arg8's voice track from (typically either the current commu chapter, or se_system)
    #   - arg8 is the audio to play from arg7, such as telop_loop for P's signature sound, or the name of a voice track in the commu's .acb file
    for e in events:
        char_name = None
        gtx_id = e['arg6']

        # special case for null lines that have survived (typically for things like "the next day..." or "30 minutes later...")
        if e['arg4'] == 'null' and e['arg5'] == 'null':
            char_name = '---'
            logging.debug(f'  line {e["arg1"]} has null arg4 and arg5, assigning "---" speaker name!')
            logging.debug(f'    text: "{gtx_lines[gtx_id]}"')
        elif e['command'] == 'select1':
            char_name = '[button]'
            logging.debug(f'  line {e["arg1"]} is a button, assigning "[button]" speaker name!')
            logging.debug(f'    button text: "{gtx_lines[gtx_id]}"')
        else:
            char_id = f'display_character_{e["arg5"]}'
            if char_id not in names:
                char_id = f'display_character_{e["arg4"]}'
                logging.warning(f'  could not find "{e["arg5"]}" in name cache, falling back to "{e["arg4"]}"...')
                if char_id not in names:
                    logging.warning(f'  COULD NOT FIND "{e["arg4"]}" IN NAME CACHE, SKIPPING LINE')
                    continue
        
        if char_name is None:
            char_name = names[char_id]
            logging.debug(f'  looking up "{char_id}" in name cache, found "{char_name}"!')
        
        # logging.debug(f'  parsing event, spoken by {char_name}, gtx_id {gtx_id}')
        line = {
            'line_id': int(e['arg1']),
            'speaker': char_name,
            'text': gtx_lines[gtx_id]
        }
        chapter_output['lines'].append(line)
        logging.debug(f'  added line {line["line_id"]} to {chapter_id}!')
    chapter_output['lines'] = sorted(chapter_output['lines'], key=lambda d: d['line_id'])

    # insert button events into chapter wherever they should be
    #   we use an amended version of the arg1 value to determine what line IDs it should be nestled between
    #   and then scan through the existing (actor_text) event list until we find the right place
    # notable args for select1 events:
    #   - arg1 is the line identifier found in the accompanying .gtx file
    #     - this is different from actor_text events, where arg1 is only the 1000, 1001, etc ID,
    #       while arg6 is the full .gtx identifier
    #   - arg2 is presumably the next (short) ID to jump to when selected, prepended by an asterisk (ie: "*2000")
    for b in button_events:
        button_id = int(b['arg1'].rsplit('_', 1)[1])
        gtx_id = b['arg1']
        found = False
        
        target_index = None

        logging.debug(f'  finding place for button {b["arg1"]}...')
        for index, text_event in enumerate(chapter_output['lines']):
            # skip very first event, since we want to check 2 elements at once
            if index == 0:
                continue

            prev_event = chapter_output['lines'][index-1]
            prev_id = prev_event['line_id']
            next_id = text_event['line_id']
            # logging.debug(f'    checking between text events {prev_id} and {next_id}...')
            # logging.debug(f'      PREV {prev_id} < {button_id} ? {prev_id < button_id}! // NEXT {button_id} < {next_id} ? {button_id < next_id}!')
            if prev_id < button_id and button_id < next_id:
                logging.debug(f'    found place for button {button_id} between text events {prev_id} and {next_id}!')
                found = True
                target_index = index
                break
        
        if found:
            logging.debug(f'  inserting button {button_id} at position {target_index}...')
            line = {
                'line_id': button_id,
                'speaker': "[button]",
                'text': gtx_lines[gtx_id]
            }
            chapter_output['lines'].insert(index, line)
        else:
            logging.warning(f'  found no suitable position for button {b["arg1"]}!')


    all_chapters.append(chapter_output)
    logging.debug('  chapter complete!')

logging.info('---------------------------------------')

output_filename = os.path.join(args.output_dir, commu_id + ".json")
pathlib.Path(args.output_dir).mkdir(parents=True, exist_ok=True)
with open(output_filename, 'w', encoding='utf8') as f:
    logging.info(f'all chapters complete, saving to {output_filename}...')
    json.dump(all_chapters, f, ensure_ascii=False, indent=4)

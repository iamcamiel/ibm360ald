"""Check the delivered A1 set and consolidated machine reference."""
from pathlib import Path
import json,collections
root=Path(__file__).resolve().parents[2]
out=root/'ALD_Visual_Transcriptions/A1 Socket Listing'
inventory=json.loads((out/'Inventory.json').read_text(encoding='utf-8'))
reference=json.loads((out/'Socket reference.json').read_text(encoding='utf-8'))
expected={Path(scan['file']).stem for scan in inventory['scans']}
delivered=set(reference['delivered_pages'])
assert expected==delivered,(expected-delivered,delivered-expected)
assert len(reference['delivered_pages'])==len(delivered)
allowed=set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ─│┌┐└┘┼◇◺+-✲.�\n')
glyph_errors=[];divider_errors=[];markers=0
for stem in sorted(expected):
 path=out/(stem+'.txt');text=path.read_text(encoding='utf-8')
 assert text.strip(),path
 markers+=text.count('�')
 if invalid:=set(text)-allowed:glyph_errors.append({'file':path.name,'characters':sorted(invalid)})
 lines=text.splitlines()
 counts=collections.Counter(i for line in lines for i,ch in enumerate(line) if ch=='│')
 dividers=[i for i,count in counts.items() if count>len(lines)*.5]
 assert len(dividers)>=6,(path.name,dividers)
 for column in dividers:
  rows=[i for i,line in enumerate(lines) if len(line)>column and line[column]=='│']
  for row in range(min(rows),max(rows)+1):
   if len(lines[row])<=column or lines[row][column]!='│':divider_errors.append({'file':path.name,'row':row+1,'column':column+1})
assert not glyph_errors,glyph_errors
assert not divider_errors,divider_errors
assert all(link['parent_section_index'] is not None for link in reference['continuation_links'])
unreadable=json.loads((out/'Unreadable print.json').read_text(encoding='utf-8'))
assert markers==unreadable['marker_count'],(markers,unreadable['marker_count'])
by_stem={Path(scan['file']).stem:scan for scan in inventory['scans']}
for marker in unreadable['markers']:
 scan=by_stem[marker['source_listing']]
 assert marker['previous_scan']==scan['previous_scan'] and marker['next_scan']==scan['next_scan']
result={'status':'Passed','reviewed_source_scan_count':len(delivered),'text_file_count':len(delivered),'socket_section_count':len(reference['records']),'linked_continuation_count':len(reference['continuation_links']),'unsupported_character_count':0,'interrupted_divider_count':0,'unreadable_character_count':markers,'unreadable_location_count':unreadable['location_count'],'unreadable_scan_count':len({m['source_listing'] for m in unreadable['markers']}),'printed_source_discrepancies':'Retained literally and recorded in Review notes.json; this validation does not assert that original printed references are internally consistent.'}
(out/'Validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
guide=[
'A1 SOCKET LISTING - READING AND REFERENCE GUIDE','',
f"All {len(delivered)} source scans have visually reviewed UTF-8 text files. Use a monospaced font such as JuliaMono and disable word wrapping. The files retain seven source columns, boxed titles in the last column and vertical page identifiers alongside the title boxes.",'',
'Unclear printed characters use U+FFFD, �. Unreadable print.txt gives their text locations and the preceding and following A1 scans in the original scan order. Unreadable print.json gives the same information in machine-readable form. Review notes.json includes native-source evidence, possible reconstructions and printed inconsistencies. Original scans are unchanged.','',
'Socket reference.json retains raw source sections and joins explicitly identified continuation fragments into logical_records. Where a transcription stores a complete semantic record in a continuation fragment, printed_lines preserves the actual source fragment. Duplicate semantic entries are counted once in the logical reference.','',
'ALD references.json is indexed by ALD page identifier and provides card portions and connector pins, with board/socket information and source_listings provenance. References containing � are uncertain and must be excluded from exact page comparisons. Printed references to pages absent from the scan collection are retained when the native scan confirms them.','',
'Validation.json records coverage, character-set, divider-continuity, continuation-link and unreadable-neighbor checks. Plug-list socket sets and totals were checked for individual deliveries. Source discrepancies remain in the files and notes; they are not silently reconciled.','',
f"Remaining unreadable print: {markers} characters in {unreadable['location_count']} locations across {result['unreadable_scan_count']} scans.",
]
(out/'Reading guide.txt').write_text('\n'.join(guide)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))

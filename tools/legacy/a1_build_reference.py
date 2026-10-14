"""Combine reviewed A1 deliveries; retain source values and uncertainty markers."""
from pathlib import Path
import json,re,collections
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing'
inventory=json.loads((OUT/'Inventory.json').read_text(encoding='utf-8'))
scans={Path(r['file']).stem:r for r in inventory['scans']}
records=[];notes=[];references=collections.defaultdict(list);issues=[];pages=[]
documents=[(file,json.loads(file.read_text(encoding='utf-8'))) for file in sorted(OUT.glob('*SOCKET LISTING.json'))]
for file in sorted(OUT.glob('*BOARD*.json')):
 b=json.loads(file.read_text(encoding='utf-8'))
 if 'socket_records' not in b:continue
 for page in b.get('pages',[]):
  listing_page=page.split('-')[-1];sections=[r for r in b['socket_records'] if r.get('listing_page')==listing_page]
  target=OUT/(page+' SOCKET LISTING.json')
  if target.exists():continue
  stem=target.stem
  documents.append((target,{'board':b['board'],'status':'Source-reviewed board delivery' if page in b.get('source_reviewed_pages',[]) or sections and all(s.get('source_reviewed') for s in sections) else 'Unreviewed board delivery',
    'source':scans.get(stem,{}).get('source'),'records':sections,'notes':[n for n in b.get('uncertainties',[]) if n.get('page')==page or page in n.get('source','') or not n.get('page') and not n.get('source')],
    'board_notes':b.get('notes',[])}))
for file,d in documents:
 stem=file.stem
 source_scan=scans.get(stem,{})
 board=d.get('board',d.get('footer',{}).get('board'))
 sections=d.get('records',d.get('sections',d.get('sockets',[])))
 accepted=bool('review' in d.get('status','').lower() and 'unreview' not in d.get('status','').lower())
 if not accepted:issues.append({'file':file.name,'issue':'No source-review status; excluded from reference'});continue
 pages.append(stem)
 for section in sections:
  sockets=section.get('occupied_sockets',section.get('sockets',[section.get('socket')]));sockets=[s for s in sockets if s]
  r={'board':section.get('board',board),'sockets':sockets,'kind':section.get('kind'),
     'part_number':section.get('part_number'),'card_type':section.get('card_type'),'references':[],
     'pins':[],'unused_portions':section.get('unused_portions',[]),'unused_pins':section.get('unused_pins',[]),
     'source_listing':stem,'source':d.get('source') or source_scan.get('source'),'source_column':section.get('source_column'),
     'source_y':section.get('source_y'),'source_row':section.get('source_row'),
     'wire_code':section.get('wire_code',section.get('printed_code')),'connector_listing':section.get('connector_listing'),
     'destination':section.get('destination',section.get('cable_destination',section.get('goes_to'))),
     'continues_from_page':section.get('continues_from_page',section.get('continues_listing_page')),'continues_socket':section.get('continues_socket'),
     'continues_source_column':section.get('continues_source_column'),
     'printed_pin_socket':section.get('printed_pin_socket')}
  if 'printed_lines' in section:r['printed_lines']=section['printed_lines']
  for ref in section.get('references',[]):
   page=ref.get('ALD_page',ref.get('ald_page'));portions=ref.get('printed_portions',ref.get('portions',[]))
   r['references'].append({'ALD_page':page,'printed_portions':portions})
   if page:
    for portion in portions:
     references[page].append({'kind':'card portion','board':r['board'],'sockets':sockets,'part_number':r['part_number'],
                             'card_type':r['card_type'],'portion':portion,'source_listing':stem})
  for pin in section.get('pins',section.get('pin_references',section.get('pin_rows',[]))):
   ref=pin.get('ALD_reference',pin.get('reference'));connector=pin.get('socket',pin.get('connector',pin.get('printed_socket',section.get('printed_pin_socket'))))
   if connector is None and len(sockets)==1:connector=sockets[0]
   normalized={'connector':connector,'pin':pin.get('pin'),'ALD_reference':ref};r['pins'].append(normalized)
   if ref:
    page=pin.get('ald_page',pin.get('ALD_page')) or ref[:5];references[page].append({'kind':'connector pin','board':r['board'],'sockets':sockets,
             'connector':connector,'pin':pin.get('pin'),'ALD_reference':ref,'source_listing':stem})
  pn,typ=r['part_number'],r['card_type']
  if pn and typ and '�' not in pn+typ and pn[-4:]!=typ:issues.append({'file':file.name,'sockets':sockets,'issue':'Part-number suffix differs from printed card type','part_number':pn,'card_type':typ})
  records.append(r)
 localnotes=list(d.get('review_notes',d.get('notes',[])))+list(d.get('unreadable_entries',[]))+list(d.get('board_notes',[]))
 for flag in ['missing_continuation','missing_plug_list']:
  if d.get(flag):localnotes.append({'note':flag.replace('_',' ')+' in available source scans'})
 for note in localnotes:
  if isinstance(note,str):note={'note':note}
  notes.append({'source_listing':stem,'source':d.get('source') or source_scan.get('source'),'previous_scan':source_scan.get('previous_scan'),
                'next_scan':source_scan.get('next_scan'),**note})
 if stem in scans:
  scans[stem]['review_status']=d['status'];scans[stem]['text_file_present']=(OUT/(stem+'.txt')).exists()
  scans[stem]['unreadable_character_count']=(OUT/(stem+'.txt')).read_text(encoding='utf-8').count('�') if (OUT/(stem+'.txt')).exists() else None
socket_index=collections.defaultdict(lambda:collections.defaultdict(list))
for i,r in enumerate(records):
 for socket in r['sockets']:socket_index[r['board']][socket].append(i)
continuations=[];linked=collections.defaultdict(list)
for i,r in enumerate(records):
 if 'continuation' not in (r['kind'] or '').lower():continue
 source_page=r['continues_from_page']
 if source_page:
  source_prefix=r['source_listing'][:5]+'-'+source_page if source_page in ['01','02'] else source_page
  source_stem=source_prefix+' SOCKET LISTING'
 elif r['continues_socket']:
  source_stem=r['source_listing']
  if r['source_column']==1 and '-02 ' in source_stem:source_stem=source_stem.replace('-02 ','-01 ',1)
 else:continue
 if source_stem not in pages and r['source_listing'][:5]+' SOCKET LISTING' in pages:source_stem=r['source_listing'][:5]+' SOCKET LISTING'
 matches=[j for j,candidate in enumerate(records) if j!=i and candidate['board']==r['board'] and candidate['source_listing']==source_stem
          and 'continuation' not in (candidate['kind'] or '').lower() and set(r['sockets']) & set(candidate['sockets'])]
 if r['continues_source_column'] is not None:matches=[j for j in matches if records[j]['source_column']==r['continues_source_column']]
 if len(matches)>1 and r['pins']:
  connector_matches=[j for j in matches if (records[j]['kind'] or '').lower() in ['connector','conn']]
  if len(connector_matches)==1:matches=connector_matches
 target=matches[0] if len(matches)==1 else None
 continuations.append({'section_index':i,'parent_section_index':target,'status':'Explicit printed continuation linked' if target is not None else 'Parent cannot be identified uniquely; raw fragment retained'})
 if target is not None:linked[target].append(i)
logical_records=[]
linked_fragments={i for fragments in linked.values() for i in fragments}
for i,r in enumerate(records):
 if i in linked_fragments:continue
 merged={**r,'source_section_indices':[i]+linked.get(i,[])}
 for field in ['references','pins','unused_portions','unused_pins']:
  seen=set();cells=[]
  for j in merged['source_section_indices']:
   for cell in records[j][field]:
    key=json.dumps(cell,sort_keys=True,ensure_ascii=False)
    if key not in seen:seen.add(key);cells.append(cell)
  merged[field]=cells
 for field in ['part_number','card_type','destination','wire_code']:
  if not merged.get(field):
   values={records[j][field] for j in merged['source_section_indices'] if records[j].get(field)}
   if len(values)==1:merged[field]=values.pop()
 logical_records.append(merged)
references=collections.defaultdict(list);reference_keys={}
def index_ref(page,entry):
 provenance=entry.pop('source_listings')
 key=(page,json.dumps(entry,sort_keys=True,ensure_ascii=False))
 if key not in reference_keys:
  entry['source_listings']=list(provenance);entry['source_listing']=provenance[0]
  reference_keys[key]=entry;references[page].append(entry)
 else:
  for source in provenance:
   if source not in reference_keys[key]['source_listings']:reference_keys[key]['source_listings'].append(source)
for record in logical_records:
 provenance=list(dict.fromkeys(records[i]['source_listing'] for i in record['source_section_indices']))
 for ref in record['references']:
  if ref['ALD_page']:
   for portion in ref['printed_portions']:
    index_ref(ref['ALD_page'],{'kind':'card portion','board':record['board'],'sockets':record['sockets'],'part_number':record['part_number'],'card_type':record['card_type'],'portion':portion,'source_listings':provenance})
 for pin in record['pins']:
  if pin['ALD_reference']:
   index_ref(pin['ALD_reference'][:5],{'kind':'connector pin','board':record['board'],'sockets':record['sockets'],**pin,'source_listings':provenance})
complete=len(set(pages))==len(scans) and set(pages)==set(scans)
result={'status':'Complete reference: all source scans delivered and visually reviewed; uncertain print and source discrepancies retained' if complete else 'Partial reference: contains only delivered, source-reviewed pages','total_source_scans':len(scans),
        'delivered_reviewed_scan_count':len(pages),'delivered_pages':pages,'records':records,
        'socket_section_index':dict(socket_index),'continuation_links':continuations,'logical_records':logical_records,
        'continuation_note':'Raw sections remain separate. Logical records join only explicitly identified continuation fragments; all fields retain original printed values.'}
(OUT/'Socket reference.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'ALD references.json').write_text(json.dumps({'status':result['status'],'coverage':len(pages),'ALD_pages':dict(sorted(references.items()))},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'Review notes.json').write_text(json.dumps({'status':('Complete' if complete else 'Partial')+' report; source neighbors are original scan-order neighbors','notes':notes,'machine_checks':issues},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
unresolved=[]
for stem in sorted(set(pages)):
 txt=OUT/(stem+'.txt')
 if not txt.exists():continue
 scan=scans.get(stem,{})
 for row,line in enumerate(txt.read_text(encoding='utf-8').splitlines(),1):
  for match in re.finditer('�+',line):
   col=match.start()
   unresolved.append({'source_listing':stem,'text_row':row,'text_column':col+1,'character_count':len(match.group()),'context':line[max(0,col-18):match.end()+19].strip(),'previous_scan':scan.get('previous_scan'),'next_scan':scan.get('next_scan')})
(OUT/'Unreadable print.json').write_text(json.dumps({'status':result['status'],'replacement_character':'�','marker_count':sum(m['character_count'] for m in unresolved),'location_count':len(unresolved),'markers':unresolved},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
report=['A1 socket listings - unreadable print','',result['status'],'','Each entry gives a 1-based text row and column. Scan neighbors follow the original scanning order.','Probable reconstructions and source discrepancies are recorded separately in Review notes.json.','']
for item in unresolved:
 report.append(f"{item['source_listing']} - row {item['text_row']}, column {item['text_column']}: {item['context']}")
 report.append('  Before: '+str(item['previous_scan'] or 'No earlier scan in the A1 listing set'))
 report.append('  After: '+str(item['next_scan'] or 'No later scan in the A1 listing set'))
 report.append('')
(OUT/'Unreadable print.txt').write_text('\n'.join(report)+'\n',encoding='utf-8')
(OUT/'Inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(len(pages),'of',len(scans),'scans integrated;',len(records),'socket sections;',len(references),'referenced ALD pages;',len(issues),'machine-check issues.')

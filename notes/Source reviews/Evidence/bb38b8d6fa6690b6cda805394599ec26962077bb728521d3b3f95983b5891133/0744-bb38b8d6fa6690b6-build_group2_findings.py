"""Combine recorded native visual decisions with exact private correction plans."""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,re
BASE=Path(__file__).resolve().parent;OUT=BASE/'Group 2 review';ROOT=Path('D:/Github/IBM360')
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(v,m):
 if not v:raise ValueError(m)
def esc(key):return str(key).replace('~','~0').replace('/','~1')
def walk(v,p=''):
 if isinstance(v,dict):
  for k,x in v.items():yield from walk(x,p+'/'+esc(k))
 elif isinstance(v,list):
  for i,x in enumerate(v):yield from walk(x,p+'/'+str(i))
 else:yield p,v
def newlabel(value,old,new):
 return re.sub(r'(?<![A-Z])'+re.escape(old)+r'(?!\d)',lambda _:new,value)
def main():
 q=read(BASE/'Group 2 requests.json');decisions=read(OUT/'Visual decisions.json');crops={c['case_id']:c for c in read(OUT/'Crop bindings.json')['cases']}
 cases=[];pagecache={};allpatches={};allcells={};issues=[]
 for page in q['pages']:
  modelpath=Path(page['model']['path']);textpath=Path(page['text']['path']);need(sha(modelpath)==page['model']['sha256'],'Changed model '+page['page']);need(sha(textpath)==page['text']['sha256'],'Changed text '+page['page'])
  model=read(modelpath);rows=textpath.read_text('utf-8-sig').splitlines();pagecache[page['page']]=model
  for case in page['cases']:
   cid=case['case_id'];need(cid in decisions,'Missing native visual decision '+cid);decision=decisions[cid]
   status='confident';proposed=decision;note='Native source block and flagged contact visually inspected; damaged letter resolves to the proposed physical bank.'
   if decision.startswith('uncertain:'):
    status='uncertain';proposed=decision.split(':',1)[1];note='Native block and target contact located. The surviving glyph is insufficient for a confident correction; proposed contact is a best guess only.'
   elif decision.startswith('printed:'):
    status='extractioncontextissue';proposed=decision.split(':',1)[1];note='Native scan genuinely prints this G/J contact. Preserve the pin; audit single-card/SLT-width classification is the issue, not the letter.'
   old=case['audit_flag']['physical_contact'];pin=case['pin'];node=case['node'];base=case['audit_flag']['node_pointer']+'/pins/'+str(case['audit_flag']['pin_index'])
   crop=crops[cid];need(sha(crop['crop']['path'])==crop['crop']['sha256'],'Changed source crop '+cid)
   patches=[];cells=[];caseissues=[];refchanges={}
   if status=='confident':
    for field,value in pin.items():
     if not isinstance(value,str)or field not in('pin','physical_pin','reference','printed_annotation','label','pin_label','contact','printed_pin'):continue
     new=newlabel(value,old,proposed)
     if new!=value:
      patch={'op':'replace','pointer':base+'/'+esc(field),'before':value,'after':new};patches.append(patch)
      if field=='reference':refchanges[value]=new
    # Only exact current references owned by this pin are propagated. Never
    # globally replace an unqualified contact or historical review material.
    for collection in('nets','wire_paths','junctions','printed_labels','unjoined_crossings'):
     for pointer,value in walk(model.get(collection,[]),'/'+collection):
      if not isinstance(value,str):continue
      changed=value
      for prior,fresh in refchanges.items():changed=re.sub(r'(?<![A-Za-z0-9_])'+re.escape(prior)+r'(?![A-Za-z0-9_])',lambda _:fresh,changed)
      if changed!=value:patches.append({'op':'replace','pointer':pointer,'before':value,'after':changed,'proof':'Exact full reference bound to the flagged node/pin'})
    row=pin.get('row',node['row']+3);column=node['column'];line=rows[row]
    lo=max(0,column-10)if pin.get('side')=='input'else max(0,column+7)
    hi=column+1 if pin.get('side')=='input'else min(len(line),column+22)
    matches=[m.start()+lo for m in re.finditer(re.escape(old),line[lo:hi])]
    correct=[m.start()+lo for m in re.finditer(re.escape(proposed),line[lo:hi])]
    if len(matches)==1:
     start=matches[0]
     for offset,(before,after)in enumerate(zip(old,proposed)):
      if before!=after:cells.append({'row':row,'column':start+offset,'before':before,'after':after})
    elif len(matches)==0 and correct:note+=' Current TXT already has the corrected contact; JSON-only repair.'
    else:caseissues.append({'kind':'text_pin_span_requires_review','row':row,'span':[lo,hi],'literal':line[lo:hi],'old_matches':matches,'correct_matches':correct})
    if not patches:caseissues.append({'kind':'no_active_pin_patch','pin_pointer':base})
   if cid=='pin-0126':note+=' Root independently viewed this crop and confirmed the complete B03 reading; both the invalid letter and numeric mirror are corrected, within the flagged-label scope.'
   if cid=='pin-0010':note+=' Existing K border control is retained separately; only the following physical-contact label changes.'
   if cid=='pin-0001':note+=' The genuine G12 contact is also present on the matching7063S24 MA221 scan. Resolve C→G, then retain the module-width/technology issue separately rather than forcing a B/D contact.'
   full=str(pin.get('pin')or old);observed=newlabel(full,old,proposed)
   result={'case_id':cid,'page':page['page'],'scan_id':page['scan_id'],'status':status,
    'node_id':node.get('id'),'node_pointer':case['audit_flag']['node_pointer'],'pin_index':int(case['audit_flag']['pin_index']),
    'side':pin.get('side'),'card_portion':node.get('printed_card_portion'),'circuit':node.get('unit'),
    'original_contact':old,'observed_contact':proposed if status!='uncertain'else None,'proposed_contact':proposed,
    'original_pin_label':full,'observed_pin_label':observed if status!='uncertain'else None,'best_guess':proposed if status=='uncertain'else None,
    'preserved_pin_context':{k:v for k,v in pin.items()if k in('triangle','border_marker','border_glyph','printed_control_prefix','printed_asterisk','printed_annotation','point','row','side')},
    'source':crop['source'],'source_crop':crop['crop'],'crop_calibration':crop['calibration'],
    'model':page['model'],'text':page['text'],'working_text':page['working_text'],
    'text_edits':cells,'json_patches':patches,'note':note,'planning_issues':caseissues,'source_changes_applied':False}
   cases.append(result)
   for p in patches:
    key=(str(modelpath),p['pointer'])
    if key in allpatches:need(allpatches[key]['before']==p['before']and allpatches[key]['after']==p['after'],'Conflicting JSON patches '+str(key))
    allpatches[key]=p
   for cell in cells:
    key=(str(textpath),cell['row'],cell['column'])
    if key in allcells:need(allcells[key]==cell,'Conflicting TXT cells '+str(key))
    allcells[key]=cell
   if caseissues:issues.append({'case_id':cid,'issues':caseissues})
 counts={status:sum(c['status']==status for c in cases)for status in sorted({c['status']for c in cases})}
 report={'schema':'private-native-pin-letter-findings-v1','group':2,'created_utc':datetime.now(timezone.utc).isoformat(),
  'source_changes_applied':False,'requests':{'path':str(BASE/'Group 2 requests.json'),'sha256':sha(BASE/'Group 2 requests.json')},
  'visual_decisions':{'path':str(OUT/'Visual decisions.json'),'sha256':sha(OUT/'Visual decisions.json')},
  'review_tool':{'path':str(Path(__file__).resolve()),'sha256':sha(__file__)},'count':len(cases),'pages':len(q['pages']),
  'status_counts':counts,'unique_txt_cells':len(allcells),'unique_json_patches':len(allpatches),'planning_issues':issues,'cases':cases}
 (OUT/'Findings.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
 with(OUT/'Findings.csv').open('w',encoding='utf-8-sig',newline='')as f:
  writer=csv.DictWriter(f,fieldnames=['case_id','page','node_id','card_portion','original_contact','observed_contact','proposed_contact','status','text_cell_count','json_patch_count','planning_issues','crop']);writer.writeheader()
  for c in cases:writer.writerow({k:c.get(k)for k in ['case_id','page','node_id','card_portion','original_contact','observed_contact','proposed_contact','status']}|{'text_cell_count':len(c['text_edits']),'json_patch_count':len(c['json_patches']),'planning_issues':json.dumps(c['planning_issues']),'crop':c['source_crop']['path']})
 print(json.dumps({'count':len(cases),'status_counts':counts,'unique_txt_cells':len(allcells),'unique_json_patches':len(allpatches),'planning_issues':issues},indent=2))
if __name__=='__main__':main()

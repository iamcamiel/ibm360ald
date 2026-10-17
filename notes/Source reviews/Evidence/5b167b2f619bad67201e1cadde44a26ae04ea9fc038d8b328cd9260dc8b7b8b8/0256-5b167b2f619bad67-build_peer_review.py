"""Independent complete Group 2 proposal; no canonical source writes."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
from datetime import datetime,timezone
import json,hashlib,re,csv
from PIL import Image,ImageChops
BASE=Path(__file__).resolve().parents[1];HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def esc(s):return str(s).replace('~','~0').replace('/','~1')
def ptr(o,p):
 parts=[x.replace('~1','/').replace('~0','~')for x in p.strip('/').split('/')]
 for k in parts[:-1]:o=o[int(k)]if isinstance(o,list)else o[k]
 return o,int(parts[-1])if isinstance(o,list)else parts[-1]
checks=0
def check(v,why):
 global checks
 checks+=1
 if not v:raise AssertionError(why)
frozen=BASE/'Group 2 review/Findings.json';original=read(frozen)
check(sha(frozen)=='9b0757a45c96b424673786b68443067614fe073e3d046bbb8626bd9dd0dd4124','Frozen findings hash')
requests=read(BASE/'Group 2 requests.json');lookup={c['case_id']:(p,c)for p in requests['pages']for c in p['cases']}
check(set(lookup)=={f['case_id']for f in original['cases']},'Exact 210-case coverage')
witnesses=read(HERE/'Current native witness bindings.json')['witnesses']+read(HERE/'Additional native witness bindings.json')['witnesses']
witness_by={(w['page'],w['node_id']):w for w in witnesses}
overrides={
 'pin-0243':('D11','Damaged RR081 output N11✲ resolves to D11✲. Current native FC001 AT has the same 0412B1/U55AC portion and clear D11✲ output.',('FC001','AT')),
 'pin-0385':('B10','AP001 input preserves control prefix 2. Current native AP021 AL shows the same 3312A1/T06AA input B10 and output B10✲.',('AP021','AL')),
 'pin-0495':('D07','FA531 AF damaged C07-shaped letter is D07; same-page native AK has identical 3808B1/U03AF with clear 3D07 input. Prefix 3 remains separate.',('FA531','AK')),
 'pin-0562':('B04','KC021 P04-shaped contact has a lost lower B bow and open 0. Native AP395 AV 0458A5/U03AE clearly reads B04; source digit remains 0, not 2.',('AP395','AV')),
 'pin-0473':('B10','CT021 J10T-shaped output has worn B arcs. Native AP741 BR 0141A3/U03AE clearly reads B10, matching current 94 same-portion B10 outputs. Preserve T.',('AP741','BR')),
 'pin-0353':('D02','RT775 AV output visibly has rounded D02 outline. Native BF051 AM 3330AF/U03AE independently has clear D02; original B02 proposal is rejected.',('BF051','AM')),
}
models={};texts={};sourcehash={};sourceimages={};crops_seen=set();ops={};cells={};final=[];case_changes=[]
for p in requests['pages']:
 check(sha(p['model']['path'])==p['model']['sha256'],'model epoch '+p['page'])
 check(sha(p['text']['path'])==p['text']['sha256'],'TXT epoch '+p['page'])
 models[p['page']]=read(p['model']['path']);texts[p['page']]=Path(p['text']['path']).read_text('utf-8-sig').splitlines()
for oldf in original['cases']:
 f=deepcopy(oldf);p,c=lookup[f['case_id']];cid=f['case_id'];node=c['node'];pin=c['pin'];model=models[f['page']]
 for b in [f['source'],f['source_crop']]:
  path=b['path']
  if path not in sourcehash:sourcehash[path]=sha(path)
  check(sourcehash[path]==b['sha256'],'source/crop binding '+cid)
 sp=f['source']['path'];cp=f['source_crop']['path']
 if sp not in sourceimages:sourceimages={sp:Image.open(sp).convert('RGB')}
 crop=Image.open(cp).convert('RGB');box=f['source_crop']['box']
 check(ImageChops.difference(sourceimages[sp].crop(box),crop).getbbox()is None,'native crop exact pixels '+cid)
 crops_seen.add(cid)
 if cid in overrides:
  proposed,note,key=overrides[cid];w=witness_by[key]
  for b in [w['model'],w['source'],w['crop']]:check(sha(b['path'])==b['sha256'],'witness current binding '+cid)
  with Image.open(w['source']['path'])as im:
   check(ImageChops.difference(im.convert('RGB').crop(w['crop']['box']),Image.open(w['crop']['path']).convert('RGB')).getbbox()is None,'witness pixels '+cid)
  check(any(proposed in str(x.get('pin',''))for x in w['node'].get('pins',[])),'witness current model pin '+cid)
  f.update(status='confident',observed_contact=proposed,proposed_contact=proposed,best_guess=None,note=note)
  f['observed_pin_label']=f['original_pin_label'].replace(f['original_contact'],proposed,1)
  f['independent_native_witness']=deepcopy(w)
  f['peer_override']={'prior_status':oldf['status'],'prior_proposed_contact':oldf['proposed_contact'],'complete_replacement_proposal':True}
  case_changes.append(cid)
 # Independently reconstruct every current-field proposal, including complete
 # exact pin references in all active connection collections and coordinate keys.
 patches=[];edits=[];refchanges={};old=f['original_contact'];new=f['proposed_contact'];base=f['node_pointer']+'/pins/'+str(f['pin_index'])
 def add(pointer,before,after,op='replace',reason='Native contact restoration'):
  if op!='replace'or before!=after:patches.append(dict(op=op,pointer=pointer,before=before,after=after,proof=reason))
 def relabel(s):return re.sub(r'(?<![A-Z])'+re.escape(old)+r'(?!\d)',lambda _:new,s)
 if f['status']=='confident':
  for field,value in pin.items():
   if field not in('pin','physical_pin','reference','printed_annotation','label','pin_label','contact','printed_pin')or not isinstance(value,str):continue
   fresh=relabel(value)
   if fresh!=value:
    add(base+'/'+esc(field),value,fresh)
    if field=='reference':refchanges[value]=fresh
  def activewalk(v,path):
   if isinstance(v,dict):
    for k,x in v.items():
     if any(s in str(k).lower()for s in('review_note','history','provenance','source_evidence','evidence_')):continue
     if k in refchanges:
      check(refchanges[k]not in v,'reference key collision '+cid)
      add(path+'/'+esc(k),x,None,'remove','Exact current coordinate-key rename; coordinates unchanged')
      add(path+'/'+esc(refchanges[k]),None,x,'add','Exact current coordinate-key rename; coordinates unchanged')
     activewalk(x,path+'/'+esc(k))
   elif isinstance(v,list):
    for i,x in enumerate(v):activewalk(x,path+'/'+str(i))
   elif isinstance(v,str):
    fresh=v
    for a,b in refchanges.items():fresh=re.sub(r'(?<![A-Za-z0-9_])'+re.escape(a)+r'(?![A-Za-z0-9_])',lambda _:b,fresh)
    if fresh!=v:add(path,v,fresh,reason='Exact full current reference owned by this node/pin')
  for collection in('nets','wire_paths','wires','connections','signals','pin_connections','junctions','printed_labels','unjoined_crossings'):
   if collection in model:activewalk(model[collection],'/'+collection)
  for ni,n in enumerate(model.get('nodes',[])):
   for pi,other in enumerate(n.get('pins',[])):
    if '/nodes/'+str(ni)+'/pins/'+str(pi)==base:continue
    for key in('reference','net','source','target'):
     if other.get(key)in refchanges:add('/nodes/'+str(ni)+'/pins/'+str(pi)+'/'+key,other[key],refchanges[other[key]],reason='Exact current endpoint copy')
  row=pin.get('absolute_row',pin.get('row',node['row']+3));line=texts[f['page']][row];col=node['column'];right=pin.get('border_side')=='right'or pin.get('side')=='output'
  lo=max(0,col+7)if right else max(0,col-12);hi=min(len(line),col+22)if right else col+1
  hits=[m.start()+lo for m in re.finditer(re.escape(old),line[lo:hi])];fresh=[m.start()+lo for m in re.finditer(re.escape(new),line[lo:hi])]
  if len(hits)==1:
   start=hits[0]
   for j,(a,b)in enumerate(zip(old,new)):
    if a!=b:edits.append(dict(row=row,column=start+j,before=a,after=b))
  else:check(not hits and len(fresh)==1,'unique own TXT span '+cid)
  check(bool(patches),'active pin patch '+cid)
 f['text_edits']=edits;f['json_patches']=patches;f['planning_issues']=[];f['peer_reviewed']=True
 for a in patches:
  key=(f['page'],a['pointer']);ident={k:a[k]for k in('op','before','after')}
  check(key not in ops or ops[key]==ident,'conflicting current pointer '+cid);ops[key]=ident
 for a in edits:
  key=(f['page'],a['row'],a['column']);ident=(a['before'],a['after'])
  check(key not in cells or cells[key]==ident,'conflicting TXT cell '+cid);cells[key]=ident
 final.append(f)
# Replay all independent proposals against exact current files, without writing.
for page,model in models.items():
 candidate=deepcopy(model)
 for (p,pointer),op in ops.items():
  if p!=page:continue
  target,key=ptr(candidate,pointer)
  if op['op']=='add':check(key not in target,'add preimage '+pointer);target[key]=op['after']
  elif op['op']=='remove':check(target[key]==op['before'],'remove preimage '+pointer);del target[key]
  else:check(target[key]==op['before'],'replace preimage '+pointer);target[key]=op['after']
 for (p,r,c),(before,after)in cells.items():
  if p==page:check(texts[page][r][c]==before,'TXT preimage '+str((page,r,c)))
 for f in final:
  if f['page']!=page or f['status']!='confident':continue
  target,key=ptr(candidate,f['node_pointer']+'/pins/'+str(f['pin_index'])+'/pin')
  check(f['proposed_contact']in target[key],'candidate physical label '+f['case_id'])
 check(candidate.get('review_notes')==model.get('review_notes'),'historical review_notes unchanged '+page)
counts=dict(Counter(f['status']for f in final));out=deepcopy(original)
out.update(schema='private-native-pin-letter-peer-reviewed-findings-v1',created_utc=datetime.now(timezone.utc).isoformat(),prepared_findings=bind(frozen),requests=bind(BASE/'Group 2 requests.json'),independent_review_tool=bind(__file__),peer_override_cases=case_changes,status_counts=counts,unique_txt_cells=len(cells),unique_json_patches=len(ops),cases=final,planning_issues=[],independent_review_checks=checks,all_native_cases_viewed=210,source_changes_applied=False)
op=BASE/'Group 2 review/Peer-reviewed findings.json';op.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')
report={'schema':'independent-native-group-peer-review-v1','group':2,'source_changes_applied':False,'prepared_findings':bind(frozen),'peer_reviewed_findings':bind(op),'checks_passed':checks,'visual_coverage':210,'status_counts':counts,'overrides':case_changes,'unique_txt_cells':len(cells),'unique_json_patches':len(ops),'blocking_issues':[],'notes':['All 210 target native crops were visually inspected in readable montages before this mechanical verification.','Four uncertain cases resolved with current source-bound native witnesses. CT021 and RT775 original confident choices revised based on fresh source and same-portion native witnesses.','Five genuine G/J contacts remain unchanged; width/module-context concerns stay separate.','Independent mechanical checks bind source epochs and exact native RGB crop pixels, reconstruct and replay active proposals, preserve historical observations and layout geometry.']}
(HERE/'Independent peer review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
with (BASE/'Group 2 review/Peer-reviewed findings.csv').open('w',newline='',encoding='utf-8-sig')as f:
 keys=['case_id','page','node_id','card_portion','original_contact','proposed_contact','status'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:c.get(k)for k in keys}for c in final)
print(json.dumps(report,indent=2))

"""Cumulative literal and owned-reference propagation only, no new readings."""
from pathlib import Path
from copy import deepcopy
from collections import defaultdict
from datetime import datetime,timezone
import json,hashlib,sys
BASE=Path(__file__).resolve().parents[1];HERE=Path(__file__).resolve().parent
sys.path.insert(0,'D:/Github/IBM360/ibm360ald/tools/reviews')
from source_review_guards import validate_pin_edits
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def parent(o,p):
 a=[s.replace('~1','/').replace('~0','~')for s in p.strip('/').split('/')]
 for k in a[:-1]:o=o[int(k)]if isinstance(o,list)else o[k]
 return o,int(a[-1])if isinstance(o,list)else a[-1]
checks=0
def need(v,m):
 global checks
 checks+=1
 if not v:raise AssertionError(m)
selection=BASE/'Final reviewed selection v2.json';s=read(selection);lookup={c['case_id']:(p,c)for g in(1,2,3)for p in read(BASE/f'Group {g} requests.json')['pages']for c in p['cases']};final={}
for g in s['groups']:
 need(sha(g['findings']['path'])==g['findings']['sha256'],'Frozen final peer')
 d=read(g['findings']['path'])
 for f in d.get('cases',d.get('findings',[])):final[f['case_id']]=(g['findings'],f)
prior=HERE/'All active pin mirrors addendum v3.json';doc=read(prior);cases=deepcopy(doc['cases']);caseby={c['case_id']:c for c in cases};census_path=HERE/'All stale active references.json';census=read(census_path);need(sha(census['manifest']['path'])==census['manifest']['sha256'],'Bound stage epoch')
for finding in census['issues']:
 cid=finding['case_id'];b,f=final[cid];p,c=lookup[cid];need(f['status'].startswith(('confident','resolved')),'Already settled')
 if cid not in caseby:
  record={'case_id':cid,'page':p['page'],'status':'resolved_active_label_mirror','source_final_findings':b,'source_final_case_id':cid,'model':p['model'],'text':p['text'],'source':f.get('source'),'native_crop':f.get('native_crop',f.get('source_crop')),'already_accepted_contact':f['proposed_contact'],'text_edits':[],'json_patches':[],'no_new_visual_decision':True};cases.append(record);caseby[cid]=record
 record=caseby[cid]
 if finding['kind']=='stale_coordinate_key':
  ops=[dict(op='remove',pointer=finding['pointer'],before=finding['before'],after=None),dict(op='add',pointer=finding['new_pointer'],before=None,after=finding['after'])]
 else:ops=[dict(op='replace',pointer=finding['pointer'],before=finding['before'],after=finding['after'])]
 for op in ops:op['reason']='Exact owned qualified reference propagation. Coordinate payload and wire geometry retained.';record['json_patches'].append(op)
 record.setdefault('qualified_reference_bindings',[]).append({'old_reference':finding['old_reference'],'new_reference':finding['new_reference']})
# Independently replay complete per-page base + addendum operations on current
# original models, detecting collisions and requiring unchanged coordinate payload.
for page in sorted({c['page']for c in cases}):
 pf=next(p for p,c in lookup.values()if p['page']==page);need(sha(pf['model']['path'])==pf['model']['sha256'],'Current model preimage');model=read(pf['model']['path']);candidate=deepcopy(model);ops={}
 for b,f in final.values():
  if f['page']!=page:continue
  for a in f.get('json_patches',[]):
   a=dict(a);a['pointer']=a.get('pointer',a.get('path'));ops[a['pointer']]=a
 for case in cases:
  if case['page']!=page:continue
  for a in case['json_patches']:need(a['pointer']not in ops,'Omitted mirror only, no overriding base patch');ops[a['pointer']]=a
 for a in ops.values():
  t,k=parent(candidate,a['pointer']);op=a.get('op','replace')
  if op=='remove':need(t[k]==a['before'],'Exact coordinate key preimage');del t[k]
  elif op=='add':need(k not in t,'New reference key absent');t[k]=deepcopy(a['after'])
  else:need(t[k]==a['before'],'Exact current field preimage');t[k]=a['after']
 need(not validate_pin_edits(model,candidate,{'json_patches':list(ops.values()),'evidence':[c['native_crop']for c in cases if c['page']==page]}),'Pin annotation guard')
 for case in cases:
  if case['page']!=page:continue
  for link in [case['model'],case['text'],case['native_crop']]:need(sha(link['path'])==link['sha256'],'Immutable source-case binding')
doc.update(created_utc=datetime.now(timezone.utc).isoformat(),review_tool=bind(__file__),superseded_addendum=bind(prior),reference_census=bind(census_path),case_count=len(cases),additional_json_patches=sum(len(c['json_patches'])for c in cases),cases=cases,checks_passed=checks)
out=HERE/'Complete active pin mirrors and references addendum v4.json';need(not out.exists(),'Immutable new output');out.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps({'addendum':bind(out),'case_count':len(cases),'additional_json_patches':doc['additional_json_patches'],'checks_passed':checks},indent=2))

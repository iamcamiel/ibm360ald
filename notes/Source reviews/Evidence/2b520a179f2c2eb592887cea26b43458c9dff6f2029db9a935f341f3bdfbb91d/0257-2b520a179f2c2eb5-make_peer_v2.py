"""Keep printed annotation on pin labels; bare physical_pin is a mirror."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
from datetime import datetime,timezone
import json,hashlib,sys,re
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
src=BASE/'Group 2 review/Peer-reviewed findings.json';doc=read(src)
assert sha(src)=='89e40e7dcfdb636ca530f42b5c0681d356a50b0a506e0b18474ccf464dbda577'
q=read(BASE/'Group 2 requests.json');look={c['case_id']:(p,c)for p in q['pages']for c in p['cases']}
revisions=[];changes={};checks=0
for f in doc['cases']:
 if f['status']!='confident':continue
 p,c=look[f['case_id']];base=f['node_pointer']+'/pins/'+str(f['pin_index']);old=f['original_contact'];new=f['proposed_contact'];pin=c['pin']
 for patch in f['json_patches']:
  if patch['pointer']==base+'/physical_pin'and patch['after']!=new:
   revisions.append({'case_id':f['case_id'],'pointer':patch['pointer'],'prior_proposal_after':patch['after'],'final_after':new,'source_preimage':patch['before']});patch['after']=new;patch['proof']='Bare physical-contact mirror; printed control prefix/suffix remain on pin label and annotation fields.'
 if isinstance(pin.get('printed_label'),str):
  fresh=re.sub(r'(?<![A-Z])'+re.escape(old)+r'(?!\d)',lambda _:new,pin['printed_label'])
  if fresh!=pin['printed_label']and not any(a['pointer']==base+'/printed_label'for a in f['json_patches']):
   f['json_patches'].append(dict(op='replace',pointer=base+'/printed_label',before=pin['printed_label'],after=fresh,proof='Complete active printed label mirror; preserve printed annotation.'));revisions.append({'case_id':f['case_id'],'pointer':base+'/printed_label','final_after':fresh})
 for a in f['json_patches']:
  key=(f['page'],a['pointer']);assert key not in changes or all(changes[key].get(k)==a.get(k)for k in('op','before','after'));changes[key]=a
for p in q['pages']:
 model=read(p['model']['path']);assert sha(p['model']['path'])==p['model']['sha256'];candidate=deepcopy(model);ops=[a for(page,_),a in changes.items()if page==p['page']]
 for a in ops:
  t,k=parent(candidate,a['pointer']);operation=a['op']
  if operation=='add':assert k not in t;t[k]=a['after']
  elif operation=='remove':assert t[k]==a['before'];del t[k]
  else:assert t[k]==a['before'];t[k]=a['after']
  checks+=1
 issues=validate_pin_edits(model,candidate,{'json_patches':ops,'evidence':[{'source_native_crops':True}]});assert not issues,(p['page'],issues);checks+=1
out=BASE/'Group 2 review/Peer-reviewed findings v2.json';doc.update(peer_predecessor=bind(src),independent_review_tool_v2=bind(__file__),physical_mirror_scope_revisions=revisions,created_utc=datetime.now(timezone.utc).isoformat(),unique_json_patches=len(changes),additional_guard_checks=checks)
out.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n','utf-8')
report=read(HERE/'Independent peer review.json');report.update(peer_reviewed_findings=bind(out),prior_peer_reviewed_findings=bind(src),additional_guard_checks=checks,guard_tool=bind(Path('D:/Github/IBM360/ibm360ald/tools/reviews/source_review_guards.py')),physical_mirror_scope_revisions=revisions,checks_passed=report['checks_passed']+checks,review_tool_v2=bind(__file__),unique_json_patches=len(changes))
(HERE/'Independent peer review v2.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
print(json.dumps(report,indent=2))

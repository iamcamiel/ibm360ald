"""Bind and recheck supplemental current-source proof without changing findings."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
import json
BASE=Path(__file__).resolve().parent;REPO=Path('D:/Github/IBM360/ibm360ald');OUT=BASE/'Group 3 review/Independent peer review'
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def digest(p):return sha256(Path(p).read_bytes()).hexdigest()
def get(v,p):
 for k in p.strip('/').split('/'):v=v[int(k)]if isinstance(v,list)else v[k]
 return v
finalpath=BASE/'Group 3 review/Group3 Peer-reviewed findings.json';final=read(finalpath)
crosspath=BASE/'Proposed contact current-source cross-check.json';cross={c['case_id']:c for c in read(crosspath)['cases']}
proofcases=[];checks=0;cache={}
for case in final['cases']:
 proofs=case.get('current_source_witnesses',[])
 if case['case_id']in('pin-0400','pin-0436','pin-0437'):proofs=cross[case['case_id']]['candidate_proofs'][case['proposed_contact']]
 if not proofs:continue
 for proof in proofs:
  p=Path(proof['model_path']);p=p if p.is_absolute()else REPO/p
  if str(p)not in cache:cache[str(p)]=(read(p),digest(p))
  doc,actual=cache[str(p)];assert actual==proof['model_sha256'];checks+=1
  node=get(doc,proof['node_pointer']);pin=node['pins'][proof['pin_index']]
  assert pin.get('pin',pin.get('printed_pin'))==proof['literal_pin'];checks+=1
  assert str(node.get('card_type'))+str(node.get('portion'))==proof['card_portion'];checks+=1
  assert str(node.get('unit',node.get('circuit',node.get('technology','')))).strip()==proof['circuit'];checks+=1
  assert pin['side']==case['side'];checks+=1
 proofcases.append({'case_id':case['case_id'],'proposed_contact':case['proposed_contact'],'proofs':proofs})
report={'schema':'independent-current-pin-witness-verification-v1','created_utc':datetime.now(timezone.utc).isoformat(),'source_changes_applied':False,'peer_findings':{'path':str(finalpath),'sha256':digest(finalpath)},'proposal_source':{'path':str(crosspath),'sha256':digest(crosspath)},'checks_passed':checks,'failure_count':0,'cases':proofcases}
p=OUT/'Current witness verification.json';p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
print(json.dumps({'path':str(p),'sha256':digest(p),'checks_passed':checks,'cases':len(proofcases)},indent=2))

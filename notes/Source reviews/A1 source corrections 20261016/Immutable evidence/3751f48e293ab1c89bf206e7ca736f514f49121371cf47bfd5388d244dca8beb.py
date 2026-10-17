"""Recover one stale shared-auxiliary hash, without new visual acceptance."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import argparse,json,hashlib,os,tempfile
H=Path(__file__).resolve().parent
PROOF_SHA='80f6b76d48a772deb313c1ca57ab077d600bce8a70eef4c4aa8d7a9db0cbb9e6'
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def need(v,m):
 if not v:raise ValueError(m)
def checked(b):
 p=Path(b.get('path',b.get('file','')));need(sha(p)==b['sha256'],'Stale proof binding: '+str(p));return p
def replace_value(d,ptr,before,after):
 ks=ptr.strip('/').split('/');v=d
 for k in ks[:-1]:v=v[int(k)]if isinstance(v,list)else v[k]
 need(v[ks[-1]]==before,'Reviewed field predecessor differs');v[ks[-1]]=after
def prepare():
 pp=H/'Verification.json';need(sha(pp)==PROOF_SHA,'Frozen proof changed');proof=read(pp);snap=H/'Preparation adapter snapshot.json';need(sha(snap)==proof['original_adapter']['sha256'],'Preparation adapter snapshot differs');old_item=proof['unchanged_page_acceptance_item'];auth=proof['successor_authority']
 for b in auth.values():checked(b)
 acceptance=read(auth['independent_acceptance']['path']);publication=read(auth['actual_publication']['path']);need(acceptance['passed']and acceptance['independent_review']and not acceptance['failures'],'Actual independent acceptance failed');checked(acceptance['batch_manifest']);checked(acceptance['source_stage_review']);need(publication['passed']and publication['published'],'Actual publication failed');checked(publication['manifest']);checked(publication['independent_acceptance'])
 need(publication['manifest']==auth['accepted_batch'],'Publication binds wrong batch');need(publication['independent_acceptance']==auth['independent_acceptance'],'Publication binds wrong independent authority')
 for b in [old_item['source'],old_item['owner_receipt'],old_item['independent_audit'],*old_item['current_quartet'].values(),old_item['current_auxiliary_existing_data'][1]]:checked(b)
 transitions=proof['shared_auxiliary_transitions'];need(len(transitions)==2,'Working/repository auxiliary mirrors required')
 for t in transitions:
  before=read(checked(t['before']));after=read(checked(t['candidate']));need(sha(t['target'])==t['candidate']['sha256'],'Current auxiliary is not exact accepted V4 candidate');expected=deepcopy(before);need(len(t['changes'])==3,'Exactly three V4 page01 changes required')
  for c in t['changes']:
   i=int(c['pointer'].split('/')[2]);need(before['socket_records'][i]['listing_page']=='01','Changed shared row is not page01');replace_value(expected,c['pointer'],c['before'],c['after'])
  need(expected==after,'Additional auxiliary semantic change');need([x for x in before['socket_records']if x['listing_page']=='02']==[x for x in after['socket_records']if x['listing_page']=='02'],'Page02 socket records changed')
 adapter=Path(proof['original_adapter']['path']);raw=adapter.read_bytes();doc=json.loads(raw);matches=[i for i,item in enumerate(doc['pages'])if item.get('page')=='A1251-02'];need(len(matches)==1,'Unique exact page02 adapter item required');i=matches[0];need(doc['pages'][i]==old_item,'Exact page02 predecessor item changed');before=transitions[0]['before']['sha256'];after=transitions[0]['candidate']['sha256'];need(old_item['current_auxiliary_existing_data'][0]['sha256']==before,'Stale predecessor differs');need(raw.count(before.encode())==1,'Old hash must occur once for byte-minimal guarded substitution');candidate=raw.replace(before.encode(),after.encode(),1);expected=deepcopy(doc);expected['pages'][i]['current_auxiliary_existing_data'][0]['sha256']=after;need(json.loads(candidate)==expected,'Adapter change exceeds one declared hash');return proof,adapter,raw,candidate,i
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--publish',action='store_true');args=ap.parse_args();proof,adapter,before,after,i=prepare();summary={'passed':True,'preflight_only':not args.publish,'page':'A1251-02','adapter_item_index':i,'adapter_preimage_sha256':hashlib.sha256(before).hexdigest(),'adapter_candidate_sha256':hashlib.sha256(after).hexdigest(),'exact_pointer':f'/pages/{i}/current_auxiliary_existing_data/0/sha256','new_visual_acceptance':False,'source_files_modified':False}
 if not args.publish:print(json.dumps(summary,indent=2));return
 out=H/'Publication';need(not out.exists(),'Preserve an existing publication/recovery attempt');out.mkdir();(out/'Before adapter.json').write_bytes(before);(out/'After adapter candidate.json').write_bytes(after);intent={**summary,'proof':bind(H/'Verification.json'),'publication_helper':bind(Path(__file__)),'actual_immediate_adapter_predecessor':bind(out/'Before adapter.json'),'actual_candidate':bind(out/'After adapter candidate.json'),'existing_V4_authority':proof['successor_authority'],'unchanged_page02_item_acceptance':proof['unchanged_page_acceptance_item']};(out/'Intent.json').write_text(json.dumps(intent,indent=2)+'\n','utf-8');need(prepare()[2]==before,'Adapter changed during guarded preparation');written=False
 try:
  fd,temp=tempfile.mkstemp(prefix=adapter.name+'.',suffix='.tmp',dir=adapter.parent)
  with os.fdopen(fd,'wb')as f:f.write(after);f.flush();os.fsync(f.fileno())
  need(adapter.read_bytes()==before,'Adapter predecessor drifted before atomic replacement');os.replace(temp,adapter);written=True;need(adapter.read_bytes()==after,'Published bytes differ');actual=read(adapter);expected=read(out/'Before adapter.json');expected['pages'][i]['current_auxiliary_existing_data'][0]['sha256']=proof['shared_auxiliary_transitions'][0]['candidate']['sha256'];need(actual==expected,'Published adapter differs outside exact hash')
  receipt={**summary,'preflight_only':False,'published':True,'completed_utc':datetime.now(timezone.utc).isoformat(),'intent':bind(out/'Intent.json'),'prior_adapter':bind(out/'Before adapter.json'),'current_adapter':bind(adapter),'exact_existing_V4_authority':proof['successor_authority'],'original_visual_acceptance_retained':True,'all_other_adapter_items_and_fields_unchanged':True,'rollback_performed':False};(out/'Publication receipt.json').write_text(json.dumps(receipt,indent=2)+'\n','utf-8');print(json.dumps(receipt,indent=2))
 except Exception:
  if written and adapter.read_bytes()==after:adapter.write_bytes(before)
  raise
if __name__=='__main__':main()

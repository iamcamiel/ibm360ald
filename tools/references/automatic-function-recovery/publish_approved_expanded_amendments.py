"""Guarded canonical publication only after independent candidate AND layout acceptance."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,sys
sys.dont_write_bytecode=True
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';REF=Path('D:/Reference Materials/IBM 360/IBM_360_ALD');BASE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def check(b):assert sha(b['path'])==b['sha256'],b['path']
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--application-manifest',required=True,type=Path);ap.add_argument('--application-audit',required=True,type=Path);ap.add_argument('--publish',action='store_true');args=ap.parse_args()
 app=read(args.application_manifest);audit=read(args.application_audit);receipt=args.application_manifest.parent/'Approved unreadable function canonical publication receipt.json'
 assert args.application_manifest.resolve().is_relative_to(BASE/'expanded-applications') and not receipt.exists()
 assert audit.get('passed') and not audit.get('failures') and not audit.get('visual_review_pending',False)
 bound=audit.get('application_manifest',audit.get('manifest'));assert bound and bound['sha256']==sha(args.application_manifest)
 candidate_audit=read(app['independent_candidate_audit']['path']);assert candidate_audit.get('passed') and not candidate_audit.get('failures')
 assert candidate_audit.get('candidate_manifest',candidate_audit.get('manifest'))['sha256']==app['candidate_manifest']['sha256']
 fields=[f for p in app['pages'] for f in p['function_fields']];ids=[f['candidate_id'] for f in fields]
 held=app.get('held_candidates',[]);held_ids=[r['candidate_id'] for r in held]
 assert len(ids)==len(set(ids)) and not set(ids)&set(held_ids) and sorted(ids+held_ids)==sorted(candidate_audit['approved_candidate_ids'])
 assert sorted(ids)==sorted(audit['approved_candidate_ids'])
 assert sorted(held_ids)==sorted(audit.get('held_candidate_ids',[]))
 for b in app['protected_inputs']+[app['candidate_manifest'],app['independent_candidate_audit'],app['authority'],app['preparation_helper']]:check(b)
 for b in app['snapshot_inputs']:check(b)
 destinations=[]
 for page in app['pages']:
  check(page['source']);check(page['frozen_original_source']);check(page['prior_review_record'])
  for field in page['function_fields']:
   for witness in field['witness_source_model_text_bindings']:
    for kind,base in (('model',REPO),('text',REPO),('original',REF)):
     b=witness[kind];assert sha(base/b['path'])==b['sha256'],'Witness changed: '+b['path']
  assert page['source']['sha256']==page['frozen_original_source']['sha256']
  assert page['exact_meaningful_cell_changes']==[c for f in page['function_fields'] for c in f['exact_meaningful_cell_changes']]
  assert all(c['before']=='�' and len(c['after'])==1 and c['after'] not in '�\r\n' for c in page['exact_meaningful_cell_changes'])
  for key,b in page['canonical_quartet'].items():
   check(b);check(page['before_quartet'][key]);check(page['candidate_quartet'][key]);assert b['sha256']==page['before_quartet'][key]['sha256']
   path=Path(b['path']).resolve();assert path.is_relative_to(ROOT) and not path.is_relative_to(REPO) and not path.is_relative_to(BASE/'expanded-applications');destinations.append(path)
 assert len(destinations)==len(set(destinations))==4*len(app['pages'])
 if not args.publish:print(json.dumps({'preflight_passed':True,'counts':app['counts'],'canonical_writes':0}));return
 app_binding=bind(args.application_manifest);audit_binding=bind(args.application_audit);published=[]
 for page in app['pages']:
  for key,b in page['canonical_quartet'].items():
   dest=Path(b['path']);check(b);stage=dest.with_name(dest.name+'.approved-unreadable-stage');assert not stage.exists();stage.write_bytes(Path(page['candidate_quartet'][key]['path']).read_bytes());assert sha(stage)==page['candidate_quartet'][key]['sha256'];check(b);os.replace(stage,dest)
  current={k:bind(b['path']) for k,b in page['canonical_quartet'].items()};assert all(current[k]['sha256']==v['sha256'] for k,v in page['candidate_quartet'].items())
  published.append({'page':page['page'],'source_scan_id':page['source_scan_id'],'source':page['source'],'before_quartet':page['before_quartet'],'current_quartet':current,'independently_reviewed_candidate_quartet':page['candidate_quartet'],'independent_candidate_audit':audit_binding,'prior_review_record':page['prior_review_record'],'function_fields':page['function_fields'],'exact_meaningful_cell_changes':page['exact_meaningful_cell_changes'],'allowed_active_semantic_changes':page['allowed_active_semantic_changes'],'trailing_space_padding':0,'current_bytes_equal_independently_reviewed_candidates':True})
 for b in app['protected_inputs']+[app_binding,audit_binding]:check(b)
 for page in app['pages']:check(page['source'])
 result={'created_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'failures':[],'manifest':app_binding,'independent_audit':audit_binding,'candidate_manifest':app['candidate_manifest'],'independent_candidate_approval':app['independent_candidate_audit'],'authority':app['authority'],'publication_helper':bind(Path(__file__)),'pages':published,'counts':app['counts'],'history_key':app['history_key'],'held_candidates':held,'validation_report':app['validation_report'],'repository_mirror_performed':False,'original_TIFFs_unchanged':True,'readable_character_changes':0,'geometric_and_routing_changes':0,'derived_values_eligible_as_future_native_witnesses':False}
 receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'receipt':bind(receipt),'counts':app['counts']}))
if __name__=='__main__':main()

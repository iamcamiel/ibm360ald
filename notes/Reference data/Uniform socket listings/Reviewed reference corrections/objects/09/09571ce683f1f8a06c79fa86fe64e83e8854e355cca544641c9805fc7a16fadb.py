"""Guarded source publication after independent acceptance; defaults to preflight.

No acceptance is generated. Original scans and historical proofs are read-only.
The --publish switch is for the coordinating parent after reviewing this script.
"""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import argparse,csv,hashlib,importlib.util,io,json,os,shutil,subprocess,sys

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).resolve().parent
MANIFEST=HERE/'Batch manifest.json';PREPARED=HERE/'Prepared page stages.json'
AUDIT=ROOT/'tmp/ald-text/ald/repository-export'
ADAPTER=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json'
REGISTRY=AUDIT/'A1 table application registry.json';SOURCE=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(Path(p).read_bytes())}
def check(v,m):
 if not v:raise ValueError(m)
def checked(link):
 p=Path(link['path']);check(p.is_file() and sha(p.read_bytes())==link['sha256'],'Stale binding '+str(p));return p
def module(p,name):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def atomic(p,raw):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.socket-reference-tmp')
 check(not tmp.exists(),'Unowned temporary file '+str(tmp));tmp.write_bytes(raw);os.replace(tmp,p)
def run(args,path):
 proc=subprocess.run([sys.executable,'-X','utf8',*map(str,args)],cwd=ROOT,capture_output=True,text=True)
 path.write_text(proc.stdout+proc.stderr,encoding='utf-8');check(proc.returncode==0,'Child verification failed '+str(path))

def main():
 cli=argparse.ArgumentParser();cli.add_argument('--acceptance',type=Path,required=True);cli.add_argument('--publish',action='store_true');args=cli.parse_args()
 batch=load(MANIFEST);prepared=load(PREPARED);acceptance=load(args.acceptance)
 check(acceptance.get('schema')=='socket-reference-batch-independent-acceptance-v1' and acceptance.get('passed') is True and acceptance.get('independent_review') is True and not acceptance.get('failures'),'Independent acceptance did not pass')
 check(checked(acceptance['batch_manifest']).resolve()==MANIFEST.resolve(),'Acceptance binds another batch')
 actual={str(checked(x).resolve()):x['sha256'] for x in acceptance['accepted_page_stages']}
 expected={str(checked(x).resolve()):x['sha256'] for x in prepared['page_stages']}
 check(actual==expected and len(actual)==14,'Independent acceptance must bind exact fourteen page stages')
 for x in batch['source_bindings']:
  checked({'path':str(REPO/x['path']),'sha256':x['sha256']})
 checked(batch['predecessor_adapter']);checked(batch['registry_predecessor'])
 for x in batch['metadata_preimages']+batch['uniform_preimages']:checked(x)
 targets={}
 for f in [*batch['files'],*batch['tool_candidates']]:
  target=Path(f['target']).resolve();check(target.is_relative_to(ROOT) and not target.is_relative_to(SOURCE) and target.suffix.lower()not in{'.tif','.tiff'},'Target outside accepted write scope')
  check(str(target)not in targets,'Duplicate batch target '+str(target));targets[str(target)]=f
  checked(f['candidate'])
  if f.get('before'):
   before=checked(f['before']).read_bytes();check(target.is_file() and target.read_bytes()==before,'Live preimage differs '+str(target))
  else:check(not target.exists(),'New target already exists '+str(target))
 for p in actual:
  stage=load(p)
  for key in ['source','human_authority','source_crop','predecessor_acceptance','historical_repository_acceptance']:checked(stage[key])
  for crop in stage.get('source_crops',[]):checked(crop)
 # The independent peer must bind the guard candidates it reviewed, not merely source cells.
 peer_bound={str(Path(x['path']).resolve()):x['sha256'] for x in acceptance.get('candidate_bindings',[])}
 for f in batch['tool_candidates']:
  c=f['candidate'];check(peer_bound.get(str(Path(c['path']).resolve()))==c['sha256'],'Guard candidate lacks independent acceptance binding')
 report={'schema':'socket-reference-batch-publication-v1','passed':True,'published':False,'manifest':bind(MANIFEST),'independent_acceptance':bind(args.acceptance),'planned_targets':len(targets),'source_pages':14,'reviewed_aliases':22,'source_tokens':62,'source_cells':63,'unrelated_adapter_items_preserved':True,'original_scans_modified':False,'historical_acceptance_modified':False,'publication_script':bind(__file__),'rollback_scope':'Source, data, metadata, adapter/registry and page-publication targets; transient read-only export plan and verification logs remain diagnostic.','transient_export_plan_rolled_back':False}
 if not args.publish:print(json.dumps(report,indent=2));return
 publication=HERE/'Publication';check(not publication.exists(),'Publication output already exists; do not replay')
 publication.mkdir();backups={};written=[]
 frozen={str(Path(x['path']).resolve()):x['sha256']for x in batch['metadata_preimages']+batch['uniform_preimages']}
 def save_write(path,raw):
  path=Path(path).resolve();key=str(path)
  check(path.is_relative_to(ROOT) and not path.is_relative_to(SOURCE),'Write scope escaped')
  if key not in backups:
   old=path.read_bytes() if path.exists() else None;backups[key]=old
   if key in frozen:check(old is not None and sha(old)==frozen[key],'Frozen metadata/uniform preimage changed '+key)
   if old is not None:
    backup=publication/'Predecessors'/path.relative_to(ROOT);backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(old)
  else:old=path.read_bytes() if path.exists() else None
  if old==raw:return
  atomic(path,raw);written.append(key)
 try:
  # Recheck every target before the first write, then again immediately at its write.
  for key,f in targets.items():
   target=Path(key);before=checked(f['before']).read_bytes() if f.get('before')else None
   check((target.read_bytes()if target.exists()else None)==before,'Concurrent target change '+key)
  for key,f in targets.items():
   target=Path(key);before=checked(f['before']).read_bytes() if f.get('before')else None
   check((target.read_bytes()if target.exists()else None)==before,'Concurrent target change '+key)
   save_write(target,checked(f['candidate']).read_bytes())
  app=module(REPO/'tools/reviews/register_a1_application.py','published_socket_registration')
  adapter=load(ADAPTER);registry=load(REGISTRY);old_adapter=deepcopy(adapter);old_registry=deepcopy(registry);page_publications=[]
  for stage_link in prepared['page_stages']:
   stage_path=checked(stage_link);stage=load(stage_path);out=publication/'Pages'/stage['page']/'Publication receipt.json'
   record={'schema':app.PUBLICATION_SCHEMA,'passed':True,'failures':[],'manifest':bind(stage_path),'independent_acceptance':bind(args.acceptance),'source':stage['source'],'published_targets':[bind(f['target']) for f in stage['files']],'batch_manifest':bind(MANIFEST),'source_or_table_writes_guarded':True}
   save_write(out,enc(record));page_publications.append(bind(out))
   adapter,registry,item=app.prepare(stage_path,out,args.acceptance,ADAPTER,REGISTRY,ROOT,ROOT/'ALD_Visual_Transcriptions',SOURCE,adapter_document=adapter,registry_document=registry)
  touched={str(Path(p['working_txt']['path']).resolve())for p in batch['pages']}
  check([x for x in old_adapter['pages']if app.target_of(x)not in touched]==[x for x in adapter['pages']if app.target_of(x)not in touched],'Unrelated adapter item changed')
  check([x for x in old_registry['entries']if x['target']not in touched]==[x for x in registry['entries']if x['target']not in touched],'Unrelated registry entry changed')
  checked(batch['predecessor_adapter']);checked(batch['registry_predecessor'])
  app.validate_registered_applications(REGISTRY,ADAPTER,ROOT,ROOT/'ALD_Visual_Transcriptions',SOURCE,adapter=adapter,registry=registry)
  save_write(ADAPTER,enc(adapter));save_write(REGISTRY,enc(registry));app.validate_registered_applications(REGISTRY,ADAPTER,ROOT,ROOT/'ALD_Visual_Transcriptions',SOURCE)
  # Refresh read-only plan. No full export is invoked.
  run([AUDIT/'export_reviewed.py'],publication/'Read-only export plan.txt')
  plan=load(AUDIT/'export plan.json');check(not plan['conflicts'],'Fresh reviewed plan has conflicts')
  ids={str(p['scan_id'])for p in batch['pages']};chosen=[x for x in plan['exported']if str(x['source_scan_id'])in ids]
  check(len(chosen)==14,'Fresh export plan does not accept all corrected pages')
  exporter=module(AUDIT/'export_reviewed.py','published_socket_exporter')
  rows=list(csv.DictReader(io.StringIO((SOURCE/'ALD Scan Order.csv').read_text('utf-8-sig'))));byid={str(r['id']):i for i,r in enumerate(rows)}
  for item in chosen:
   text=Path(item['transcription_source']);destination=Path(item['destination']);check(text.read_bytes()==destination.read_bytes() and sha(text.read_bytes())==item['text_sha256'],'Accepted text hash differs')
   i=byid[str(item['source_scan_id'])];row=rows[i];metadata_path,meta=exporter.companion_metadata(text)
   note=exporter.note_content(Path(row['newpath']),text,meta,row,rows[i-1]['newname']if i else'',rows[i+1]['newname']if i+1<len(rows)else'',item['review_record'])
   check(sha(note)==item['notes_sha256'],'Export notes differ from plan');save_write(Path(item['notes_destination']),note)
   record_path=REPO/'notes/A1 Socket Listing'/(text.stem+' review record.json');record=load(record_path)
   record.update(text_sha256=item['text_sha256'],acceptance_record=item['review_record'])
   if metadata_path:
    record.update(working_metadata_source=str(metadata_path),working_metadata_sha256=sha(metadata_path.read_bytes()),review_metadata_snapshot=meta)
   record['reviewed_socket_reference_corrections']={'source_cells':next(p['exact_meaningful_cell_changes']for p in batch['pages']if str(p['scan_id'])==str(item['source_scan_id'])),'batch_manifest':bind(MANIFEST),'independent_acceptance':bind(args.acceptance)}
   save_write(record_path,enc(record))
  content_path=REPO/'notes/Content data manifest.json';content=load(content_path);revised=[]
  changed_json={Path(k).relative_to(REPO).as_posix()for k,f in targets.items()if Path(k).is_relative_to(REPO/'json')}
  for item in content['files']:
   if item['path']in changed_json:item['sha256']=sha((REPO/item['path']).read_bytes());content['managed_files'][item['path']]=item['sha256'];revised.append(item['path'])
  check(set(revised)==changed_json,'Changed JSON omitted from content manifest')
  content['updated_utc']=datetime.now(timezone.utc).isoformat();save_write(content_path,enc(content))
  last_path=AUDIT/'last export manifest.json';provenance=REPO/'notes/Reviewed export provenance.json'
  check(last_path.read_bytes()==provenance.read_bytes(),'Export/provenance baselines diverged')
  last=load(last_path);keep=[x for x in last['exported']if str(x['source_scan_id'])not in ids]
  for item in chosen:
   indices=[i for i,x in enumerate(last['exported'])if str(x['source_scan_id'])==str(item['source_scan_id'])];check(len(indices)==1,'Duplicate/missing predecessor export');last['exported'][indices[0]]=item
   last['managed_files'][item['destination']]=item['text_sha256'];last['managed_files'][item['notes_destination']]=item['notes_sha256']
  check(keep==[x for x in last['exported']if str(x['source_scan_id'])not in ids],'Unrelated export entries changed')
  if 'reviewed_plan_sha256'in last:last['reviewed_plan_sha256']=sha((AUDIT/'export plan.json').read_bytes())
  last['updated_utc']=datetime.now(timezone.utc).isoformat();save_write(last_path,enc(last));save_write(provenance,enc(last))
  # Rebuild the additive uniform dataset against the now-current accepted source hashes.
  uniform_manifest=REPO/'notes/Socket listings uniform/Build manifest.json';old_uniform=load(uniform_manifest)
  uniform_stage=publication/'Uniform dataset';run([REPO/'tools/references/build_uniform_socket_listings.py','--repo',REPO,'--output',uniform_stage],publication/'Uniform rebuild.txt')
  run([REPO/'tools/references/verify_uniform_socket_listings.py','--repo',REPO,'--dataset',uniform_stage,'--report',publication/'Uniform stage independent verification.json'],publication/'Uniform stage verification.txt')
  new_uniform=load(uniform_stage/'notes/Socket listings uniform/Build manifest.json')
  check(new_uniform['counts']==old_uniform['counts'],'Reference corrections unexpectedly change uniform record counts')
  check({x['path']for x in new_uniform['files']}=={x['path']for x in old_uniform['files']},'Uniform output inventory changed')
  for x in new_uniform['files']:save_write(REPO/x['path'],(uniform_stage/x['path']).read_bytes())
  save_write(uniform_manifest,(uniform_stage/'notes/Socket listings uniform/Build manifest.json').read_bytes())
  run([REPO/'tools/references/verify_uniform_socket_listings.py','--repo',REPO,'--report',publication/'Published uniform independent verification.json'],publication/'Published uniform verification.txt')
  # Finally confirm source cells, page registration and read-only export eligibility.
  app.validate_registered_applications(REGISTRY,ADAPTER,ROOT,ROOT/'ALD_Visual_Transcriptions',SOURCE)
  run([AUDIT/'export_reviewed.py'],publication/'Final read-only export plan.txt')
  final_plan=load(AUDIT/'export plan.json');check(not final_plan['conflicts'],'Final export plan conflicts')
  check(len([x for x in final_plan['exported']if str(x['source_scan_id'])in ids])==14,'Final accepted page coverage differs')
  for key,f in targets.items():check(Path(key).read_bytes()==checked(f['candidate']).read_bytes(),'Published candidate changed '+key)
  report.update(published=True,completed_utc=datetime.now(timezone.utc).isoformat(),page_publications=page_publications,adapter=bind(ADAPTER),registry=bind(REGISTRY),provenance=bind(provenance),content_manifest=bind(content_path),uniform_manifest=bind(uniform_manifest),uniform_verification=bind(publication/'Published uniform independent verification.json'),written_targets=[{'path':p,'before_sha256':sha(backups[p])if backups[p]is not None else None,'after_sha256':sha(Path(p).read_bytes())}for p in dict.fromkeys(written)],repository_inventory_refresh_required=True)
  atomic(publication/'Publication receipt.json',enc(report));print(json.dumps({'passed':True,'published':True,'receipt':str(publication/'Publication receipt.json'),'changed_targets':len(set(written))}))
 except BaseException as e:
  for key in reversed(list(dict.fromkeys(written))):
   old=backups[key];path=Path(key)
   if old is None:path.unlink(missing_ok=True)
   else:atomic(path,old)
  report.update(passed=False,published=False,error=str(e),rolled_back=True,rollback_verified=all((Path(p).read_bytes()if Path(p).exists()else None)==raw for p,raw in backups.items()))
  atomic(publication/'Publication receipt.json',enc(report));raise

if __name__=='__main__':main()

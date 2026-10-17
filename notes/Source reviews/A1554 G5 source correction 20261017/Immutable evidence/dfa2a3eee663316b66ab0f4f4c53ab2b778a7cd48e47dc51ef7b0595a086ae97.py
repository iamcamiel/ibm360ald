"""Prepare a bounded portable A1554 proof payload privately, without publication."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';BASE=Path(__file__).parent;STAGE=BASE/'A1554 G5 source correction stage v3';PUB=STAGE/'Publication';DEST='notes/Source reviews/A1554 G5 source correction 20261017'
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def need(x,m):
 if not x:raise ValueError(m)
def at(d,p):
 for k in p.strip('/').split('/'):d=d[int(k)]if isinstance(d,list)else d[k]
 return d
def main():
 out=BASE/'A1554 portable proof preparation';need(not out.exists(),'Fresh private preparation required');receipt_path=PUB/'Publication receipt.json';receipt=read(receipt_path);need(receipt.get('passed')is True and receipt.get('published')is True and not receipt.get('rolled_back'),'Actual successful publication required');scope_path=BASE/'Independent published A1554 exact scope verification.json';scope=read(scope_path);need(scope.get('passed')is True and scope['publication_receipt']==bind(receipt_path),'Independent published-scope verification missing/stale');stage=read(STAGE/'Stage manifest.json');payload=out/'payload';objects=payload/'Immutable evidence';objects.mkdir(parents=True);copies={};mapping=[];external=[];inputs={};plans=[]
 def add(path,role,expected=None,original=None):
  path=Path(path).resolve();need(path.is_file(),'Missing proof '+str(path));b=bind(path);need(expected is None or b['sha256']==expected,'Stale proof '+str(path));inputs[str(path)]=b['sha256']
  if path.suffix.lower()in{'.tif','.tiff'}:external.append({'original_path':str(path),'sha256':b['sha256'],'role':role,'policy':'External original TIFF; not copied'});return
  digest=b['sha256']
  if digest not in copies:
   name=digest+path.suffix.lower();dest=objects/name;dest.write_bytes(path.read_bytes());need(bind(dest)['sha256']==digest,'Copied proof differs');relative=DEST+'/Immutable evidence/'+name;copies[digest]={'path':relative,'prepared_file':str(dest),'sha256':digest,'bytes':dest.stat().st_size,'role':role}
  mapping.append({'original_path':original or str(path),'snapshot_path':str(path),'sha256':digest,'portable_path':copies[digest]['path'],'role':role})
 def link(b,role):
  p=Path(b['path']);p=p if p.is_absolute()else ROOT/p
  if p.is_file()and bind(p)['sha256']==b['sha256']:add(p,role,b['sha256']);return
  saved=PUB/'Predecessors'/p.relative_to(ROOT)if p.is_relative_to(ROOT)else None
  if saved and saved.is_file()and bind(saved)['sha256']==b['sha256']:add(saved,role,b['sha256'],original=str(p));return
  external.append({'original_path':str(p),'sha256':b['sha256'],'role':role,'policy':'Historical or externally retained binding; current path superseded or not copied. No replacement proof invented.'})
 explicit=['Stage manifest.json','Independent publication acceptance.json','Independent registration contract verification.json','Mechanical exact scope verification.json','Historical repository proof.json','Predecessor application proof.json','Resolution authority.json','Preparation assertions.json','V2 candidate identity and schema repair verification.json']
 for name in explicit:add(STAGE/name,'Original immutable stage/review authority')
 for name in ['Publication receipt.json','Page publication receipt.json','Read-only export plan.txt']:add(PUB/name,'Actual immutable publication outcome')
 for p in [Path(__file__),scope_path,BASE/'verify_A1554_published_scope_independent.py']:add(p,'Independent post-publication scope/helper')
 for key in ['human_authority','source_crop','predecessor_acceptance','historical_repository_acceptance','preparation_script','font','registration_helper','predecessor_adapter','registry_predecessor','source']:
  if isinstance(stage.get(key),dict):link(stage[key],key)
 for b in stage.get('source_crops',[]):link(b,'Native source crop')
 link(receipt['publication_script'],'Exact publication helper')
 changes={x['target']:x['changes']for x in stage['json_mirror_changes']};witnesses=[]
 for f in stage['files']:
  for label in ['before','candidate']:
   b=f.get(label)
   if not b:continue
   p=Path(b['path']);need(bind(p)['sha256']==b['sha256'],'Stage input changed')
   if f['role']=='current auxiliary reference mirror':
    external.append({'original_path':str(p),'sha256':b['sha256'],'role':f['role']+' '+label,'policy':'Large shared JSON stays private; exact patches and physical-owner witnesses preserved'})
   else:add(p,'Exact source '+label+' '+f['role'],b['sha256'])
  if f['target']in changes:
   before=read(f['before']['path']);after=read(f['candidate']['path']);owners={}
   for c in changes[f['target']]:
    parts=c['pointer'].strip('/').split('/');count=3 if parts[0]=='ALD_pages'else 2;pointer='/'+'/'.join(parts[:count]);owners[pointer]={'pointer':pointer,'before':at(before,pointer),'after':at(after,pointer)}
   witnesses.append({'target':f['target'],'before':f['before'],'after':f['candidate'],'exact_patches':changes[f['target']],'source_bound_owners':list(owners.values())})
 # Snapshot all actual mutable publication metadata immediately, explicitly.
 source_targets={f['target']for f in stage['files']}
 for item in receipt['written_targets']:
  p=Path(item['path']);need(bind(p)['sha256']==item['after_sha256'],'Post-publication target moved before snapshot');old=PUB/'Predecessors'/p.relative_to(ROOT)
  if str(p)not in source_targets:
   add(p,'Immediate published metadata/registration postimage',item['after_sha256'])
   if item['before_sha256']is not None:add(old,'Exact immediate metadata/registration predecessor',item['before_sha256'],original=str(p))
 def emit(name,doc,role):
  p=payload/name;p.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n','utf-8');plans.append({'path':DEST+'/'+name,'prepared_file':str(p),'sha256':bind(p)['sha256'],'bytes':p.stat().st_size,'role':role})
 emit('Exact scoped JSON witnesses.json',{'derived_index_not_acceptance':True,'source_stage':bind(STAGE/'Stage manifest.json'),'exact_meaningful_cell_changes':stage['exact_meaningful_cell_changes'],'shared_JSON_and_page_witnesses':witnesses},'Exact source/JSON change index')
 emit('Evidence map.json',{'schema':'portable-A1554-source-proof-map-v1','source_publication':bind(receipt_path),'independent_acceptance':receipt['independent_acceptance'],'no_new_acceptance_created':True,'original_receipt_bytes_rewritten':False,'original_TIFFs_copied':0,'mappings':mapping,'external_bindings':external},'Original-to-portable mapping')
 p=payload/'README.txt';p.write_text('A1554-01 G5 source correction — 2026-10-17\n\nNative review and accepted source publication correct part 5800519/type0519 to 5800514/type0514 at board02E-E4 socketG5. Exactly two TXT cells and their declared active JSON mirrors changed.\n\nOriginal stages, independent acceptances, source authority, native crops and actual publication/registration epoch snapshots are preserved byte for byte. The evidence map resolves copied content-addressed files without rewriting historical paths inside receipts. This bundle creates no new acceptance.\n\nOriginal TIFFs remain externally hash-bound. Large shared reference JSON preimages remain private; exact patches and complete minimal physical-owner before/after witnesses are indexed separately. Canonical source outputs remain distinct from evidence snapshots.\n','utf-8');plans.append({'path':DEST+'/README.txt','prepared_file':str(p),'sha256':bind(p)['sha256'],'bytes':p.stat().st_size,'role':'Reader guide'})
 plans=list(copies.values())+plans
 for path,digest in inputs.items():need(bind(path)['sha256']==digest,'Input epoch moved during preparation')
 for x in plans:need(not(REPO/x['path']).exists(),'Portable target collision');need(bind(x['prepared_file'])['sha256']==x['sha256'],'Prepared object changed')
 manifest={'schema':'private-A1554-portable-proof-publication-plan-v1','prepared_only':True,'repository_writes':False,'publication_requires_root_cue':True,'destination':DEST,'source_receipt':bind(receipt_path),'independent_scope_verification':bind(scope_path),'inputs':[{'path':p,'sha256':h}for p,h in inputs.items()],'files':plans,'file_count':len(plans),'total_bytes':sum(x['bytes']for x in plans)};path=out/'Portable proof preparation manifest.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(bind(path),indent=2))
if __name__=='__main__':main()

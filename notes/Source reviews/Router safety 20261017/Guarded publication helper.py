"""Private exact four-file router release; no generation, source or inventory writes."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os

BASE=Path(__file__).resolve().parent
REPO=Path('D:/Github/IBM360/ibm360ald')
PREFIX='notes/Source reviews/Router safety 20261017'
TARGETS={
 'tools/card_ald/render_composite_card.py':BASE/'Independent diagnostics/Combined candidate v4/render_composite_card.py',
 'tools/card_ald/test_prepare_robustness.py':BASE/'Independent diagnostics/test_prepare_robustness.py',
 'tools/card_ald/test_router_safety.py':BASE/'Release candidate/test_router_safety.py',
 'tools/card_ald/README.txt':BASE/'Release candidate/README.txt'}
PROTECTED=BASE/'Protected source and published output inputs.json'

def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def need(v,m):
 if not v:raise ValueError(m)
def put(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def checked(b):
 p=Path(b['path']);need(p.is_file() and sha(p)==b['sha256'],'Changed bound file '+str(p));return p
def current(p):return sha(p)if Path(p).is_file()else None
def atomic(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.router-release-tmp')
 need(not tmp.exists(),'Unexpected temporary file '+str(tmp))
 created=False
 try:
  with tmp.open('xb')as f:
   created=True
   f.write(data);f.flush();os.fsync(f.fileno())
  os.replace(tmp,p)
 finally:
  if created and tmp.exists():tmp.unlink()

def protected_check(binding,changed=None):
 d=read(checked(binding));changed=changed or {};counts={}
 folders={'ALD text':('ALD','.txt'),'published JSON':('json','.json'),'published card text':('Card-ALD','.txt'),'card tools':('tools/card_ald','.py')}
 for group,items in d['files'].items():
  for b in items:
   p=Path(b['path']);rel=p.relative_to(REPO).as_posix();expected=changed.get(rel,b['sha256']);need(current(p)==expected,'Protected file drift '+rel)
  if group in folders:
   folder,suffix=folders[group];actual={str(p.resolve())for p in (REPO/folder).rglob('*'+suffix)};expected={str(Path(b['path']).resolve())for b in items}
   expected.update(str((REPO/r).resolve())for r,h in changed.items()if r.startswith(folder+'/')and r.endswith(suffix))
   need(actual==expected,'Protected tree membership drift '+group)
  counts[group]=len(items)
 need(all(p.suffix=='.txt'for p in(REPO/'Card-ALD').rglob('*')if p.is_file()),'Unexpected unbound published card file type')
 return counts

def prepare(out):
 out=Path(out).resolve();need(out.is_relative_to(BASE)and not out.exists(),'New private release folder required')
 protected=bind(PROTECTED);counts=protected_check(protected);need(not(REPO/PREFIX).exists(),'Proof namespace must be new')
 need(sha(TARGETS['tools/card_ald/render_composite_card.py'])=='a9aa540cf6ce8b6106dd7db1aefd3c6c9e7e84a96b633a2b9ff7d8da33efcccf','Wrong frozen renderer')
 need(sha(TARGETS['tools/card_ald/test_prepare_robustness.py'])=='efc1bdb2d9e760c0da495e7b0266c55968fd67c4dbd88db4f013278d34ce0b11','Wrong frozen prepare test')
 out.mkdir();records=[];proof=[]
 for rel,src in TARGETS.items():
  source=bind(src);dest=REPO/rel;old=current(dest);candidate=out/'Candidates'/Path(rel).name;candidate.parent.mkdir(exist_ok=True);candidate.write_bytes(src.read_bytes());before=None
  if old is not None:
   saved=out/'Predecessors'/Path(rel).name;saved.parent.mkdir(exist_ok=True);saved.write_bytes(dest.read_bytes());before=bind(saved)
   proof.append({'path':PREFIX+'/Predecessor tools/'+dest.name,'source':before})
  records.append({'path':rel,'before_sha256':old,'predecessor':before,'candidate':bind(candidate),'original_candidate':source})
  proof.append({'path':PREFIX+'/Accepted tools/'+dest.name,'source':bind(candidate)})
 explicit=[('Protected source and published output inputs.json',PROTECTED),
           ('Author tool preparation.json',BASE/'Independent diagnostics/Prepare robustness tool preparation.json'),
           ('Downstream integration mixed result.json',BASE/'Independent diagnostics/Final v4 downstream integration/Integration verification.json'),
           ('0479 deferred source conversion failure.txt',BASE/'Independent diagnostics/Final v4 downstream integration/0479 failure traceback.txt'),
           ('Final selected routing-only trials.json',BASE/'Independent diagnostics/Final v4 frozen routing-only selected trials.json'),
           ('Reviewed geometry integration check.json',BASE/'Root reviewed geometry integration check.json'),
           ('Portable prepare fixture results.txt',BASE/'Independent diagnostics/Portable prepare fixtures candidate v4.txt'),
           ('Human answers source corrections deferred.json',BASE.parent/'prefix0-parser-corrected-20261017/Recovered mixed-port source crops/Human review answers.json'),
           ('Guarded publication helper.py',Path(__file__))]
 for rel,src in explicit:
  original=bind(src);saved=out/'Evidence'/rel;saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(src.read_bytes());proof.append({'path':PREFIX+'/'+rel,'source':bind(saved),'original':original})
 manifest={'schema':'private-four-file-router-release-v1','created_utc':datetime.now(timezone.utc).isoformat(),'repo':str(REPO),'proof_prefix':PREFIX,
           'protected_inputs':protected,'protected_counts':counts,'records':records,'proof_files':proof,'publication_helper':bind(__file__),
           'inventory_before':bind(REPO/'notes/Repository records manifest.json'),'acceptance_required':True,
           'no_source_or_card_output_writes':True,'no_generation_or_rerun':True,'internal_net_assembly_held':True,
           'runtime_proof_names':['Release manifest.json','Independent acceptance.json','Publication receipt.json']}
 put(out/'Release manifest.json',manifest);validate(out/'Release manifest.json');print(json.dumps({'prepared':True,'manifest':bind(out/'Release manifest.json'),'code_targets':4,'static_proof_files':len(proof),'protected_counts':counts},indent=2))

def validate(path):
 m=read(path);need(m.get('schema')=='private-four-file-router-release-v1'and m.get('repo')==str(REPO),'Release schema/repository')
 checked(m['publication_helper']);need(m['publication_helper']==bind(__file__),'Wrong publisher bytes')
 need(m['proof_prefix']==PREFIX and {x['path']for x in m['records']}==set(TARGETS)and len(m['records'])==4,'Four-target scope changed')
 protected_check(m['protected_inputs']);checked(m['inventory_before']);need(not(REPO/PREFIX).exists(),'Proof namespace already exists')
 seen=set()
 for c in m['records']:
  need(current(REPO/c['path'])==c['before_sha256'],'Code target preimage changed '+c['path']);checked(c['candidate']);checked(c['original_candidate'])
  need(c['candidate']['sha256']==c['original_candidate']['sha256'],'Candidate/source differs')
  if c['before_sha256']is not None:need(checked(c['predecessor']).read_bytes()==(REPO/c['path']).read_bytes(),'Predecessor preservation')
  else:need(c['predecessor']is None,'Invented predecessor')
 for p in m['proof_files']:
  rel=p['path'];need(rel.startswith(PREFIX+'/')and rel not in seen and '..'not in Path(rel).parts,'Proof target scope');seen.add(rel);checked(p['source'])
  if 'original'in p:checked(p['original'])
  need(not(REPO/rel).exists(),'New proof target exists '+rel)
 return m

def accept(path,ap,ah):
 need(sha(ap)==ah,'Exact independent acceptance hash required');a=read(ap)
 need(a.get('passed')is True and a.get('independent_review')is True and a.get('failures')==[],'Passed independent review required')
 need(a.get('release_manifest')==bind(path),'Acceptance must bind this exact release manifest')
 m=read(path);bindings={(str(Path(x['path']).resolve()),x['sha256'])for x in a.get('candidate_bindings',[])}
 for c in m['records']:
  x=c['original_candidate'];need((str(Path(x['path']).resolve()),x['sha256'])in bindings,'Acceptance missing exact target candidate '+c['path'])
 return a

def publish(path,ap,ah,write):
 path=Path(path).resolve();ap=Path(ap).resolve();m=validate(path);accept(path,ap,ah)
 preflight={'schema':'private-router-release-preflight-v1','passed':True,'manifest':bind(path),'independent_acceptance':bind(ap),'protected_counts':m['protected_counts'],'code_targets':4,'static_proof_files':len(m['proof_files']),'no_write':not write}
 if not write:print(json.dumps(preflight,indent=2));return
 receipt=path.parent/'Publication receipt.json';completion=path.parent/'Proof publication receipt.json';need(not receipt.exists()and not completion.exists(),'Publication receipt already exists')
 writes=[];done=[]
 for c in m['records']:writes.append((c['path'],c['before_sha256'],checked(c['candidate']).read_bytes(),c['predecessor'],'Accepted router tool/test/documentation'))
 for p in m['proof_files']:writes.append((p['path'],None,checked(p['source']).read_bytes(),None,'Bounded immutable router proof'))
 writes.extend([(PREFIX+'/Release manifest.json',None,path.read_bytes(),None,'Exact release manifest copy'),(PREFIX+'/Independent acceptance.json',None,ap.read_bytes(),None,'Exact independent acceptance copy')])
 try:
  # Recheck every preimage immediately before the first mutation.
  validate(path);accept(path,ap,ah)
  for rel,before,data,old,role in writes:
   target=REPO/rel;need(current(target)==before,'Target changed before write '+rel);atomic(target,data);after=hashlib.sha256(data).hexdigest();done.append({'path':rel,'before_sha256':before,'after_sha256':after,'role':role,'predecessor':old});need(sha(target)==after,'Written byte check')
  changed={c['path']:c['candidate']['sha256']for c in m['records']};protected_check(m['protected_inputs'],changed);checked(m['inventory_before'])
  pub={'schema':'guarded-four-file-router-tool-publication-v1','passed':True,'published':True,'created_utc':datetime.now(timezone.utc).isoformat(),'manifest':bind(path),'independent_acceptance':bind(ap),'changes':done,'source_writes':0,'published_card_output_writes':0,'inventory_writes':0,'internal_net_assembly_held':True,'no_card_rerun':True,'rollback_required':False}
  put(receipt,pub);rel=PREFIX+'/Publication receipt.json';need(not(REPO/rel).exists(),'Publication proof collision');atomic(REPO/rel,receipt.read_bytes());done.append({'path':rel,'before_sha256':None,'after_sha256':sha(receipt),'role':'Exact router publication receipt copy','predecessor':None})
  for c in done:need(sha(REPO/c['path'])==c['after_sha256'],'Final target recheck '+c['path'])
  protected_check(m['protected_inputs'],changed);checked(m['inventory_before'])
  put(completion,{'schema':'bounded-router-proof-publication-v1','passed':True,'published':True,'publication_receipt':bind(receipt),'manifest':bind(path),'independent_acceptance':bind(ap),'changes':done,'source_writes':0,'card_output_writes':0,'inventory_writes':0})
  print(json.dumps({'passed':True,'publication_receipt':bind(receipt),'proof_receipt':bind(completion),'files_written':len(done)},indent=2))
 except Exception as exc:
  rollback=[]
  for c in reversed(done):
   target=REPO/c['path']
   if current(target)!=c['after_sha256']:raise RuntimeError('Rollback refused because target drifted: '+c['path'])from exc
   if c['before_sha256']is None:target.unlink()
   else:atomic(target,checked(c['predecessor']).read_bytes())
   rollback.append(c['path'])
  # Only empty directories created by this bounded proof publication are removed.
  prefix=REPO/PREFIX
  if prefix.exists():
   for p in sorted((x for x in prefix.rglob('*')if x.is_dir()),key=lambda x:len(x.parts),reverse=True):
    if not any(p.iterdir()):p.rmdir()
   if not any(prefix.iterdir()):prefix.rmdir()
  protected_check(m['protected_inputs']);checked(m['inventory_before']);put(path.parent/'Failed publication diagnostic.json',{'passed':False,'error':repr(exc),'rollback_paths':rollback,'source_data_rollback_verified':True,'historical_private_receipts_retained':True});raise

if __name__=='__main__':
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='mode',required=True);a=s.add_parser('prepare');a.add_argument('--output',type=Path,required=True);a=s.add_parser('publish');a.add_argument('--manifest',type=Path,required=True);a.add_argument('--acceptance',type=Path,required=True);a.add_argument('--acceptance-sha256',required=True);a.add_argument('--write',action='store_true');a=p.parse_args()
 if a.mode=='prepare':prepare(a.output)
 else:publish(a.manifest,a.acceptance,a.acceptance_sha256,a.write)

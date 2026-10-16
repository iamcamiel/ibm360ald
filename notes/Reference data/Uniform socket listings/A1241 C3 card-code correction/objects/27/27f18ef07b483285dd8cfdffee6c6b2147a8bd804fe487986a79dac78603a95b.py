"""Preserve exact A1241 review and publication evidence; no TIFF copies."""
from pathlib import Path
from collections import deque
from datetime import datetime,timezone
import hashlib,json
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).resolve().parent
TOOLS=ROOT/'tmp/ald-text/ald/socket-ald-audit';DEST=REPO/'notes/Reference data/Uniform socket listings/A1241 C3 card-code correction'
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(Path(p).read_bytes())}
def need(v,m):
 if not v:raise ValueError(m)
def links(v):
 if isinstance(v,dict):
  if isinstance(v.get('sha256'),str)and isinstance(v.get('path',v.get('file')),str):yield {'path':v.get('path',v.get('file')),'sha256':v['sha256']}
  for x in v.values():yield from links(x)
 elif isinstance(v,list):
  for x in v:yield from links(x)
publication=read(HERE/'Publication/Publication receipt.json');need(publication.get('passed')is True and publication.get('published')is True,'Publication not complete')
stage=read(HERE/'Stage manifest.json');peer=read(HERE/'Independent acceptance.json');need(not DEST.exists(),'Proof destination already exists')
seeds={HERE/'Stage manifest.json',HERE/'Independent acceptance.json',HERE/'Independent review.py',HERE/'Independent scope tests.txt',HERE/'Mechanical verification.json',HERE/'Preparation assertions.json',HERE/'Publication/Publication receipt.json',HERE/'Publication/Page publication receipt.json',HERE/'Publication/Read-only export plan.txt',HERE/'Verify published scope.py',HERE/'Published scope verification.json',Path(__file__)}
for name in ['prepare_a1241_addendum.py','publish_a1241_addendum.py','verify_a1241_preparation.py','test_a1241_addendum_scope.py']:seeds.add(TOOLS/name)
for f in stage['files']:seeds|={Path(f['before']['path']),Path(f['candidate']['path'])}
for x in publication['written_targets']:
 p=Path(x['path']);need(sha(p.read_bytes())==x['after_sha256'],'Publication target changed before snapshot '+str(p));seeds.add(p)
for p in(HERE/'Publication/Predecessors').rglob('*'):
 if p.is_file():seeds.add(p)
for x in peer.get('candidate_bindings',[]):
 p=Path(x['path'])
 if p.suffix.lower()not in{'.tif','.tiff'}and(p.is_relative_to(HERE)or p in seeds):seeds.add(p)
prior_map=REPO/'notes/Reference data/Uniform socket listings/Reviewed reference corrections/Portable proof mapping.json';prior=read(prior_map)
prior_objects={x['sha256']:(prior_map.parent/x['path']).relative_to(REPO).as_posix()for x in prior['objects']}
queue=deque((p,None)for p in sorted(seeds));seen=set();objects={};mapped={};external=[];pending=[];missing=[]
DEST.mkdir(parents=True)
while queue:
 p,expected=queue.popleft();p=Path(p).resolve();key=(str(p),expected)
 if key in seen:continue
 seen.add(key)
 if p.suffix.lower()in{'.tif','.tiff'}:external.append({'original_path':str(p),'sha256':expected,'reason':'Original TIFF retained only in reference archive'});continue
 if not p.is_file():missing.append({'original_path':str(p),'sha256':expected});continue
 raw=p.read_bytes();digest=sha(raw)
 if expected and digest!=expected:pending.append({'original_path':str(p),'sha256':expected});continue
 if digest not in objects:
  suffix=p.suffix.lower()if p.suffix.lower()in{'.json','.py','.txt','.png','.csv'}else'.bin';relative='objects/'+digest[:2]+'/'+digest+suffix;dest=DEST/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);objects[digest]=relative
 mapped[(str(p),digest)]={'original_path':str(p),'sha256':digest,'object':objects[digest]}
 if p.suffix.lower()=='.json':
  try:document=json.loads(raw.decode('utf-8-sig'))
  except(ValueError,UnicodeError):continue
  for link in links(document):
   q=Path(link['path'])
   if not q.is_absolute():pending.append({'original_path':link['path'],'sha256':link['sha256']});continue
   if q.suffix.lower()in{'.tif','.tiff'}:external.append({'original_path':str(q),'sha256':link['sha256'],'reason':'Original TIFF retained only in reference archive'})
   elif q.is_relative_to(HERE)or q in seeds or q.name.startswith('A1241-01 C3 '):queue.append((q,link['sha256']))
   else:pending.append({'original_path':str(q),'sha256':link['sha256']})
for x in pending:
 key=(x['original_path'],x['sha256'])
 if x['sha256']in objects:mapped[key]={**x,'object':objects[x['sha256']]}
 elif x['sha256']in prior_objects:mapped[key]={**x,'repository_path':prior_objects[x['sha256']],'reason':'Exact immutable V4 proof object already retained'}
 else:external.append({**x,'reason':'Explicit historical/canonical binding retained without mutation'})
for x in mapped.values():
 p=DEST/x['object']if'object'in x else REPO/x['repository_path'];need(sha(p.read_bytes())==x['sha256'],'Portable proof digest differs')
mapping={'schema':'a1241-card-code-portable-proof-v1','passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'source_publication':bind(HERE/'Publication/Publication receipt.json'),'independent_acceptance':bind(HERE/'Independent acceptance.json'),'page':'A1241-01','board':'02B-D1','sockets':['C3'],'source_cells':2,'json_fields':36,'post_publication_targets_snapshotted':len(publication['written_targets']),'original_tiffs_copied':0,'direct_human_glyph_answer_claimed':False,'reading':'Native review:5803388 3388','mapping':list(mapped.values()),'objects':[{'sha256':h,'path':r}for h,r in sorted(objects.items())],'external_bindings':external,'missing_paths':missing,'immutable_review_bytes_rewritten':False}
need(not missing,'Missing seeded proof artifacts')
path=DEST/'Portable proof mapping.json';path.write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(DEST/'README.txt').write_text('A1241-01 SOCKET C3 CARD-CODE CORRECTION\n\nNative review reads5803388 3388. Two digit cells and36 active part/type\nfields changed at the same physical site02B-D1 C3. No page references,\nportions, buckets or historical acceptance data were changed.\n\nThe mapping preserves all exact before/candidate/review and post-publication\nmetadata bytes. Original absolute strings remain untouched inside immutable\nobjects. Some immutable V4 proof objects are reused by repository path/hash.\nOriginal TIFFs remain external archive references; no scans are duplicated.\n',encoding='utf-8')
print(json.dumps({'passed':True,'destination':str(DEST),'objects':len(objects),'resolved_bindings':len(mapped),'post_targets':len(publication['written_targets']),'missing_paths':len(missing),'mapping':bind(path)}))

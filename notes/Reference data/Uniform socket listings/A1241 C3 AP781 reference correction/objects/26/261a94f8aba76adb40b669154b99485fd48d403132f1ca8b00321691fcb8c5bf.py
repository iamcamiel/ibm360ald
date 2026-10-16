"""Preserve exact A1241 AP781 review and publication evidence; no TIFF copies."""
from pathlib import Path
from collections import deque
from datetime import datetime,timezone
import hashlib,json
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).resolve().parent
TOOLS=ROOT/'tmp/ald-text/ald/socket-ald-audit';DEST=REPO/'notes/Reference data/Uniform socket listings/A1241 C3 AP781 reference correction'
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
seeds={HERE/'Stage manifest.json',HERE/'Independent acceptance.json',HERE/'Publication/Publication receipt.json',HERE/'Publication/Page publication receipt.json',HERE/'Publication/Read-only export plan.txt',HERE/'Verify published scope.py',HERE/'Published scope verification.json',Path(__file__)}
for name in ['prepare_a1241_reference_addendum.py','publish_single_table_addendum.py','test_a1241_reference_scope.py','independently_review_a1241_reference.py']:seeds.add(TOOLS/name)
seeds.update(p for p in HERE.iterdir() if p.is_file() and p.suffix.lower() in {'.py','.json','.txt','.png'})
for f in stage['files']:
 seeds.add(Path(f['candidate']['path']))
 if f.get('before'):seeds.add(Path(f['before']['path']))
for x in publication['written_targets']:
 p=Path(x['path']);need(sha(p.read_bytes())==x['after_sha256'],'Publication target changed before snapshot '+str(p));seeds.add(p)
for p in(HERE/'Publication/Predecessors').rglob('*'):
 if p.is_file():seeds.add(p)
for x in peer.get('candidate_bindings',[]):
 p=Path(x['path'])
 if p.suffix.lower()not in{'.tif','.tiff'}and(p.is_relative_to(HERE)or p in seeds):seeds.add(p)
prior_objects={}
for prior_map in sorted((REPO/'notes/Reference data/Uniform socket listings').rglob('Portable proof mapping.json')):
 if prior_map.parent==DEST:continue
 prior=read(prior_map)
 for x in prior['objects']:prior_objects[x['sha256']]=(prior_map.parent/x['path']).relative_to(REPO).as_posix()
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
 elif x['sha256']in prior_objects:mapped[key]={**x,'repository_path':prior_objects[x['sha256']],'reason':'Exact immutable prior proof object already retained'}
 else:external.append({**x,'reason':'Explicit historical/canonical binding retained without mutation'})
for x in mapped.values():
 p=DEST/x['object']if'object'in x else REPO/x['repository_path'];need(sha(p.read_bytes())==x['sha256'],'Portable proof digest differs')
mapping={'schema':'a1241-ap781-reference-portable-proof-v1','passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'source_publication':bind(HERE/'Publication/Publication receipt.json'),'independent_acceptance':bind(HERE/'Independent acceptance.json'),'page':'A1241-01','board':'02B-D1','sockets':['C3'],'source_cells':1,'json_operations':8,'post_publication_targets_snapshotted':len(publication['written_targets']),'original_tiffs_copied':0,'direct_human_glyph_answer_claimed':False,'reading':'Independent native reviewers agree: AP781 F1 H1','mapping':list(mapped.values()),'objects':[{'sha256':h,'path':r}for h,r in sorted(objects.items())],'external_bindings':external,'missing_paths':missing,'immutable_review_bytes_rewritten':False}
need(not missing,'Missing seeded proof artifacts')
path=DEST/'Portable proof mapping.json';path.write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(DEST/'README.txt').write_text('A1241-01 SOCKET C3 F1/H1 PAGE-REFERENCE CORRECTION\n\nIndependent native reviewers read AP781 F1 H1. One source cell changes\nAP741 to AP781. Only same-card F1/H1 reference groups and exact index\nmemberships change. Previously accepted5803388 3388 is retained.\n\nExact before/candidate/review and post-publication metadata bytes are retained.\nOriginal TIFF files remain external archive references and are not copied.\n',encoding='utf-8')
print(json.dumps({'passed':True,'destination':str(DEST),'objects':len(objects),'resolved_bindings':len(mapped),'post_targets':len(publication['written_targets']),'missing_paths':len(missing),'mapping':bind(path)}))

"""Preserve immutable review/publication bytes with a content-addressed map.

Copies no TIFFs. Absolute paths inside old proof bytes are not rewritten.
The map resolves their path/hash pairs to the copied object or canonical file.
"""
from pathlib import Path
from collections import deque
from datetime import datetime,timezone
import hashlib,json

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).resolve().parent
DEST=REPO/'notes/Reference data/Uniform socket listings/Reviewed reference corrections'
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(Path(p).read_bytes())}
def need(v,m):
 if not v:raise ValueError(m)
def links(v):
 if isinstance(v,dict):
  if isinstance(v.get('sha256'),str) and isinstance(v.get('path',v.get('file')),str):yield {'path':v.get('path',v.get('file')),'sha256':v['sha256']}
  for x in v.values():yield from links(x)
 elif isinstance(v,list):
  for x in v:yield from links(x)

receipt=HERE/'Publication/Publication receipt.json';published=read(receipt)
need(published.get('passed')is True and published.get('published')is True,'Publication did not pass')
need(not DEST.exists(),'Portable proof destination already exists')
batch=read(HERE/'Batch manifest.json');prepared=read(HERE/'Prepared page stages.json');peer=read(HERE/'Independent batch acceptance.json')
seeds={receipt,HERE/'Batch manifest.json',HERE/'Prepared page stages.json',HERE/'Independent batch acceptance.json',HERE/'publish_batch.py',HERE/'preserve_proof.py',HERE/'prepare_application.py',HERE/'validate_preparation.py',HERE/'Preparation mechanical assertions.json',HERE/'source/prepare.py',HERE/'source/Stage manifest.json'}
for f in batch['files']+batch['tool_candidates']:
 for key in ['before','candidate']:
  if f.get(key):seeds.add(Path(f[key]['path']))
for s in prepared['page_stages']:seeds.add(Path(s['path']))
for p in published['page_publications']:seeds.add(Path(p['path']))
for name in ['Read-only export plan.txt','Final read-only export plan.txt','Uniform rebuild.txt','Uniform stage independent verification.json','Uniform stage verification.txt','Published uniform independent verification.json','Published uniform verification.txt']:
 p=HERE/'Publication'/name
 if p.exists():seeds.add(p)
for p in (HERE/'tools').glob('test_*.py'):seeds.add(p)
for f in batch['authority_records']:
 finding=f['finding']
 for c in finding.get('crops',[])+finding.get('native_crops',[]):
  crop=c.get('crop',c)
  if 'path'in crop:seeds.add(Path(crop['path']))
 # Preserve the direct human statement separately from native AI readings.
 if finding.get('human_correction_binding'):seeds.add(Path(finding['human_correction_binding']['path']))
seeds.add(Path(batch['reviewed_findings']['path']))
written={Path(x['path']).resolve()for x in published['written_targets']}
for p in (HERE/'Publication/Predecessors').rglob('*'):
 if p.is_file()and (ROOT/p.relative_to(HERE/'Publication/Predecessors')).resolve()in written:seeds.add(p)
queue=deque((p,None)for p in sorted(seeds));seen=set();objects={};mapping=[];external=[];unresolved=[]
DEST.mkdir(parents=True)
while queue:
 p,expected=queue.popleft();p=Path(p).resolve();key=(str(p),expected)
 if key in seen:continue
 seen.add(key)
 if p.suffix.lower()in{'.tif','.tiff'}:
  external.append({'original_path':str(p),'sha256':expected,'reason':'Original TIFF remains in reference archive; never duplicated'});continue
 if not p.exists():
  unresolved.append({'original_path':str(p),'sha256':expected,'reason':'Referenced path missing; retained as historical binding'});continue
 raw=p.read_bytes();digest=sha(raw)
 if expected is not None and digest!=expected:
  # Old target bindings resolve later to an exact predecessor object by hash.
  mapping.append({'original_path':str(p),'sha256':expected,'object_by_sha256':expected,'current_path_has_successor':True});continue
 if digest not in objects:
  suffix=p.suffix.lower()if p.suffix.lower()in{'.json','.py','.png','.txt','.csv'}else'.bin';relative='objects/'+digest[:2]+'/'+digest+suffix;out=DEST/relative;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw);objects[digest]=relative
 mapping.append({'original_path':str(p),'sha256':digest,'object':objects[digest]})
 if p.suffix.lower()=='.json':
  try:document=json.loads(raw.decode('utf-8-sig'))
  except(ValueError,UnicodeError):continue
  for link in links(document):
   lp=Path(link['path'])
   if not lp.is_absolute():
    canonical=REPO/lp
    if canonical.is_file()and sha(canonical.read_bytes())==link['sha256']:external.append({'original_path':link['path'],'sha256':link['sha256'],'repository_path':canonical.relative_to(REPO).as_posix(),'reason':'Canonical source/tool already retained in repository'})
    else:mapping.append({'original_path':link['path'],'sha256':link['sha256'],'object_by_sha256':link['sha256'],'historical_relative_binding':True})
   elif lp.suffix.lower()in{'.tif','.tiff'}:external.append({'original_path':str(lp),'sha256':link['sha256'],'reason':'Original TIFF remains in reference archive; never duplicated'})
   elif lp.is_relative_to(HERE)or lp in seeds:queue.append((lp,link['sha256']))
   elif lp.is_relative_to(REPO)and lp.is_file()and sha(lp.read_bytes())==link['sha256']:
    external.append({'original_path':str(lp),'sha256':link['sha256'],'repository_path':lp.relative_to(REPO).as_posix(),'reason':'Canonical file already retained in repository'})
   else:
    # Exact before/candidate objects were seeded, so these aliases can be resolved by digest.
    mapping.append({'original_path':str(lp),'sha256':link['sha256'],'object_by_sha256':link['sha256'],'historical_binding':True})
resolved=[]
for item in mapping:
 if 'object_by_sha256'in item:
  digest=item.pop('object_by_sha256')
  if digest in objects:item['object']=objects[digest];resolved.append(item)
  else:external.append({**item,'reason':'Historical external or immutable canonical binding; not recopied'})
 else:resolved.append(item)
unique={(m['original_path'],m['sha256']):m for m in resolved}
for m in unique.values():need(sha((DEST/m['object']).read_bytes())==m['sha256'],'Portable copied object differs')
proof={'schema':'reviewed-socket-reference-portable-proof-v1','created_utc':datetime.now(timezone.utc).isoformat(),'publication':bind(receipt),'original_tiffs_copied':0,'source_pages':14,'resolved_reference_aliases':22,'source_tokens':62,'source_cells':63,'direct_human_readings':['AP413 -> AP433','RA907 -> RB907'],'other_readings':'Native source inspection with exact card/site/portion support; the four RU readings retain their worn-stroke qualifications.','held_out':'RF091 -> RF081 remains excluded pending human review.','mapping':list(unique.values()),'objects':[{'sha256':h,'path':rel}for h,rel in sorted(objects.items())],'external_bindings':external,'unresolved_paths':unresolved,'immutable_bytes_rewritten':False,'portable_resolution':'Resolve each original path plus SHA256 through mapping; object bytes preserve original JSON and all historical absolute strings. Canonical repository references and original TIFF archive bindings remain explicit.'}
(DEST/'Portable proof mapping.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(DEST/'README.txt').write_text('REVIEWED SOCKET-LISTING REFERENCE CORRECTIONS\n\n14 scans, 22 page-code readings, 62 tokens and 63 changed text cells.\nAP413 -> AP433 and RA907 -> RB907 are direct human readings.\nThe remaining readings come from native inspection and cross-reference checks.\nRF091 remains held and is not changed.\n\nPortable proof mapping.json resolves original path/hash pairs to immutable\ncontent-addressed objects. Review records are copied byte for byte, retaining\ntheir historical absolute paths. TIFFs are represented only by archive path\nand hash; no original scans are duplicated.\n',encoding='utf-8')
print(json.dumps({'destination':str(DEST),'objects':len(objects),'resolved_bindings':len(unique),'unresolved_paths':len(unresolved),'original_tiffs_copied':0,'mapping':bind(DEST/'Portable proof mapping.json')}))

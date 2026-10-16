"""Snapshot every guarded publication target before later source batches run."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent;REPO=Path('D:/Github/IBM360/ibm360ald');DEST=REPO/'notes/Reference data/Uniform socket listings/Reviewed reference corrections'
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(b):return hashlib.sha256(b).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(Path(p).read_bytes())}
def need(v,m):
 if not v:raise ValueError(m)
publication=read(HERE/'Publication/Publication receipt.json');need(publication['passed']and publication['published'],'Publication not passed')
mapping_path=DEST/'Portable proof mapping.json';previous=mapping_path.read_bytes();proof=read(mapping_path)
objects={x['sha256']:x['path']for x in proof['objects']};mapping={(x['original_path'],x['sha256']):x for x in proof['mapping']}
def store(p,expected=None):
 p=Path(p).resolve();need(p.suffix.lower()not in{'.tif','.tiff'},'TIFF copying is forbidden')
 raw=p.read_bytes();digest=sha(raw);need(expected is None or digest==expected,'Post-publication target changed '+str(p))
 if digest not in objects:
  suffix=p.suffix.lower()if p.suffix.lower()in{'.json','.png','.txt','.py','.csv'}else'.bin';relative='objects/'+digest[:2]+'/'+digest+suffix;dest=DEST/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);objects[digest]=relative
 mapping[(str(p),digest)]={'original_path':str(p),'sha256':digest,'object':objects[digest],'post_publication_snapshot':True}
for x in publication['written_targets']:store(x['path'],x['after_sha256'])
store(__file__)
# Preserve the first immutable collector's map before extending this index.
old_digest=sha(previous);old_relative='objects/'+old_digest[:2]+'/'+old_digest+'.json';(DEST/old_relative).parent.mkdir(parents=True,exist_ok=True);(DEST/old_relative).write_bytes(previous);objects[old_digest]=old_relative
proof['previous_mapping_object']={'sha256':old_digest,'path':old_relative}
external=[]
for item in proof['external_bindings']:
 if item.get('sha256')in objects and Path(item['original_path']).suffix.lower()not in{'.tif','.tiff'}:
  key=(item['original_path'],item['sha256']);mapping.setdefault(key,{'original_path':item['original_path'],'sha256':item['sha256'],'object':objects[item['sha256']]})
 else:external.append(item)
for m in mapping.values():need(sha((DEST/m['object']).read_bytes())==m['sha256'],'Copied proof bytes differ')
proof.update(mapping=list(mapping.values()),objects=[{'sha256':h,'path':p}for h,p in sorted(objects.items())],external_bindings=external,post_publication_targets_snapshotted=len(publication['written_targets']),post_publication_snapshot_utc=datetime.now(timezone.utc).isoformat(),all_mutable_publication_targets_preserved=True)
mapping_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
receipt={'schema':'socket-reference-portable-post-publication-snapshot-v1','passed':True,'source_publication':bind(HERE/'Publication/Publication receipt.json'),'portable_mapping':bind(mapping_path),'snapshotted_targets':len(publication['written_targets']),'objects':len(objects),'resolved_bindings':len(mapping),'original_tiffs_copied':0,'created_utc':datetime.now(timezone.utc).isoformat()}
(DEST/'Snapshot receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt))

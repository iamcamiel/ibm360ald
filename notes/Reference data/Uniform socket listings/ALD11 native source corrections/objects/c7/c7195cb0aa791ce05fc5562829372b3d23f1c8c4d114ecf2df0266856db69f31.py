"""Retain immediate post-import ALD11 metadata and its accepted source proofs."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald'
HERE=ROOT/'tmp/ald-text/ald/socket-ald-audit/native-eleven-ald-review'
DEST=REPO/'notes/Reference data/Uniform socket listings/ALD11 native source corrections'
def need(v,m):
 if not v:raise ValueError(m)
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(Path(p).read_bytes())}
def main():
 receipt_path=HERE/'Execution step 05.txt';receipt=read(receipt_path)
 need(receipt['schema']=='accepted-source-review-import-receipt-v1'and receipt['passed']is True,'Import has not passed')
 pages=['AP639','AP781','AP813','CS011','DS131'];need(sorted(x['page']for x in receipt['pages'])==pages,'Wrong imported page scope')
 need(receipt['source_or_scan_writes']==0 and not DEST.exists(),'Unexpected source writes or existing proof directory')
 seeds={Path(__file__).resolve(),ROOT/'tmp/ald-text/ald/socket-ald-audit/execute_ald11_plan.py'}
 seeds.update(p for p in HERE.rglob('*')if p.is_file()and '__pycache__'not in p.parts)
 for item in receipt['mutations']:
  path=Path(item['path']);need(sha(path.read_bytes())==item['after_sha256'],'Current imported target changed: '+str(path));seeds.add(path)
 registry=ROOT/'tmp/ald-text/ald/repository-export/Source review successor registry.json';seeds.add(registry)
 for page in receipt['pages']:
  for path in page['targets'].values():seeds.add(Path(path))
 objects={};mapping=[];DEST.mkdir(parents=True)
 for path in sorted(seeds):
  need(path.suffix.lower()not in('.tif','.tiff'),'Original scan copy prohibited')
  data=path.read_bytes();digest=sha(data)
  if digest not in objects:
   suffix=path.suffix.lower()if path.suffix.lower()in('.json','.py','.txt','.png','.csv')else'.bin'
   relative='objects/'+digest[:2]+'/'+digest+suffix;target=DEST/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);objects[digest]=relative
  mapping.append({'original_path':str(path.resolve()),'sha256':digest,'object':objects[digest]})
 for item in mapping:need(sha((DEST/item['object']).read_bytes())==item['sha256'],'Portable object differs')
 output={'schema':'ald-native-eleven-portable-proof-v1','passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),
  'pages':pages,'reviewed_nodes':11,'changed_source_characters':3,'import_receipt':bind(receipt_path),
  'source_publication':bind(HERE/'stage/publication.json'),'independent_acceptance':bind(HERE/'Independent acceptance.json'),
  'post_publication_targets_snapshotted':len(receipt['mutations']),'original_tiffs_copied':0,'mapping':mapping,
  'objects':[{'sha256':digest,'path':relative}for digest,relative in sorted(objects.items())],
  'scope':'Immediate accepted ALD11 source/import evidence and exact current post-import metadata. K border controls remain printed and are represented separately from card portions.'}
 path=DEST/'Portable proof mapping.json';path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'passed':True,'mapping':bind(path),'objects':len(objects),'bindings':len(mapping),'post_targets':len(receipt['mutations'])},indent=2))
if __name__=='__main__':main()

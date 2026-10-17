"""Read-only actual-publication scope verification; never creates acceptance."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';BASE=Path(__file__).parent;STAGE=BASE/'A1554 G5 source correction stage v3';PUB=STAGE/'Publication';checks=0
def need(x,m):
 global checks
 checks+=1
 if not x:raise ValueError(m)
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def checked(b):
 p=Path(b['path']);need(bind(p)['sha256']==b['sha256'],'Stale proof '+str(p));return p
def saved(p):return PUB/'Predecessors'/Path(p).resolve().relative_to(ROOT)
def patch(d,p,v):
 keys=p.strip('/').split('/');obj=d
 for k in keys[:-1]:obj=obj[int(k)]if isinstance(obj,list)else obj[k]
 k=keys[-1];obj[int(k)if isinstance(obj,list)else k]=v
def at(d,p):
 for k in p.strip('/').split('/'):d=d[int(k)]if isinstance(d,list)else d[k]
 return d
def main():
 receipt_path=PUB/'Publication receipt.json';need(receipt_path.is_file(),'Final publication receipt not yet present; no completion claim');receipt=read(receipt_path);need(receipt.get('passed')is True and receipt.get('published')is True and not receipt.get('rolled_back'),'Actual successful publication required');stage_path=checked(receipt['manifest']);stage=read(stage_path);acceptance_path=checked(receipt['independent_acceptance']);acceptance=read(acceptance_path);need(acceptance.get('passed')is True and acceptance.get('independent_review')is True and not acceptance.get('failures')and acceptance['manifest_sha256']==bind(stage_path)['sha256'],'Independent stage acceptance mismatch')
 need(stage['page']=='A1554-01'and stage['board']=='02E-E4'and stage['source_scan_id']=='35','Wrong source page');checked(stage['source']);need(len(stage['files'])==10,'Unexpected source target count');need(stage['exact_meaningful_cell_changes']==[{'row':11,'column':229,'before':'9','after':'4'},{'row':11,'column':234,'before':'9','after':'4'}],'Wrong source cells')
 for f in stage['files']:
  need(Path(f['target']).read_bytes()==checked(f['candidate']).read_bytes(),'Published source differs '+f['target']);before=checked(f['before'])if f.get('before')else None;after=checked(f['candidate'])
  if before is not None and before.suffix=='.txt'and f['role'].endswith('TXT'):
   a=before.read_text('utf-8-sig').splitlines();b=after.read_text('utf-8-sig').splitlines();need(len(a)==len(b),'TXT row count changed');delta=[]
   for row,(x,y)in enumerate(zip(a,b)):
    need(len(x)==len(y),'TXT row width changed')
    for col,(u,v)in enumerate(zip(x,y)):
     if u!=v:delta.append({'row':row,'column':col,'before':u,'after':v})
   need(delta==stage['exact_meaningful_cell_changes'],'TXT changes exceed two cells')
 for item in stage['json_mirror_changes']:
  f=next(f for f in stage['files']if f['target']==item['target']);expected=read(checked(f['before']))
  for p in item['changes']:need(at(expected,p['pointer'])==p['before'],'JSON patch predecessor mismatch');patch(expected,p['pointer'],p['after'])
  need(expected==read(f['target']),'JSON has undeclared changes')
 target=next(f['target']for f in stage['files']if f['role']=='working accepted TXT')
 adapter=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json';registry=ROOT/'tmp/ald-text/ald/repository-export/A1 table application registry.json'
 oldpath=saved(adapter);need(bind(oldpath)['sha256']==stage['predecessor_adapter']['sha256'],'Adapter predecessor snapshot mismatch');old=read(oldpath);new=read(adapter)
 def adapter_target(x):
  q=x.get('current_quartet',{});texts=[v['path']for v in q.values()if isinstance(v,dict)and str(v.get('path','')).endswith('.txt')and not str(v.get('path','')).endswith(' review notes.txt')]
  return str(Path(texts[0]).resolve())if len(texts)==1 else None
 norm=str(Path(target).resolve());need([x for x in old['pages']if adapter_target(x)!=norm]==[x for x in new['pages']if adapter_target(x)!=norm],'Unrelated adapter items changed')
 oldpath=saved(registry);need(bind(oldpath)['sha256']==stage['registry_predecessor']['sha256'],'Registry predecessor snapshot mismatch');old=read(oldpath);new=read(registry);need([x for x in old['entries']if str(Path(x['target']).resolve())!=norm]==[x for x in new['entries']if str(Path(x['target']).resolve())!=norm],'Unrelated registry entries changed')
 provenance=REPO/'notes/Reviewed export provenance.json';last=ROOT/'tmp/ald-text/ald/repository-export/last export manifest.json';need(provenance.read_bytes()==last.read_bytes(),'Repository/export provenance differs');old=read(saved(provenance));new=read(provenance);need([x for x in old['exported']if str(x['source_scan_id'])!='35']==[x for x in new['exported']if str(x['source_scan_id'])!='35'],'Unrelated accepted export entry changed');entry=next(x for x in new['exported']if str(x['source_scan_id'])=='35');need(bind(entry['destination'])['sha256']==entry['text_sha256']==bind(target)['sha256'],'Published accepted TXT hash differs');need(bind(entry['notes_destination'])['sha256']==entry['notes_sha256'],'Published accepted note hash differs');reviewpath=Path(entry['review_record']);reviewpath=reviewpath if reviewpath.is_absolute()else ROOT/reviewpath;need(reviewpath.is_file(),'Missing source review record')
 changed={entry['destination']:entry['text_sha256'],entry['notes_destination']:entry['notes_sha256']};expected=deepcopy(old['managed_files']);expected.update(changed);need(expected==new['managed_files'],'Unrelated managed export ownership changed')
 content=REPO/'notes/Content data manifest.json';old=read(saved(content));new=read(content);allowed={Path(f['target']).relative_to(REPO).as_posix():bind(f['target'])['sha256']for f in stage['files']if Path(f['target']).is_relative_to(REPO/'json')};expected=deepcopy(old)
 for f in expected['files']:
  if f['path']in allowed:f['sha256']=allowed[f['path']]
 expected['managed_files'].update(allowed);expected['updated_utc']=new['updated_utc'];need(expected==new,'Content manifest has unrelated changes')
 for r in receipt['written_targets']:
  need(bind(r['path'])['sha256']==r['after_sha256'],'Current receipt target hash changed');p=saved(r['path'])
  if r['before_sha256']is not None:need(p.is_file()and bind(p)['sha256']==r['before_sha256'],'Missing immediate publication predecessor')
 result={'schema':'independent-published-A1554-exact-scope-verification-v1','passed':True,'independent_review':True,'created_utc':datetime.now(timezone.utc).isoformat(),'checks':checks,'publication_receipt':bind(receipt_path),'manifest':bind(stage_path),'acceptance':bind(acceptance_path),'source_targets':10,'TXT_cells':2,'unrelated_adapter_registry_export_content_changes':0,'source_writes':False,'reviewer_tool':bind(__file__)};output=BASE/'Independent published A1554 exact scope verification.json';need(not output.exists(),'Preserve prior verification');output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(bind(output),indent=2))
if __name__=='__main__':main()

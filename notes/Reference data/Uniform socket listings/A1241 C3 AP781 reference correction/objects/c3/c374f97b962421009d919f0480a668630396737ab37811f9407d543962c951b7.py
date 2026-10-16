"""Check actual scoped metadata deltas after guarded A1241 publication."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).resolve().parent;P=HERE/'Publication'
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def before(p):return read(P/'Predecessors'/Path(p).relative_to(ROOT))
checks=[]
def need(v,m):
 if not v:raise ValueError(m)
 checks.append(m)
receipt=read(P/'Publication receipt.json');need(receipt['passed']and receipt['published']and not receipt.get('rolled_back'),'Guarded publication passed without rollback')
target=str((ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing/A1241-01 SOCKET LISTING.txt').resolve())
adapter=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json';registry=ROOT/'tmp/ald-text/ald/repository-export/A1 table application registry.json'
old,new=before(adapter),read(adapter)
def at(x):return str(Path(x.get('current_quartet',{}).get('txt',{}).get('path','')).resolve())
need([x for x in old['pages']if at(x)!=target]==[x for x in new['pages']if at(x)!=target],'Every unrelated adapter item unchanged')
need(len([x for x in new['pages']if at(x)==target])==1,'Exactly one current A1241 adapter item')
old,new=before(registry),read(registry);need([x for x in old['entries']if x['target']!=target]==[x for x in new['entries']if x['target']!=target],'Every unrelated registry item unchanged')
last=ROOT/'tmp/ald-text/ald/repository-export/last export manifest.json';provenance=REPO/'notes/Reviewed export provenance.json';old,new=before(last),read(last)
need([x for x in old['exported']if str(x['source_scan_id'])!='126']==[x for x in new['exported']if str(x['source_scan_id'])!='126'],'Every other export entry unchanged')
need(last.read_bytes()==provenance.read_bytes(),'Last export and repository provenance agree')
changed_json={Path(x['target']).relative_to(REPO).as_posix()for x in read(HERE/'Stage manifest.json')['files']if Path(x['target']).is_relative_to(REPO/'json')}
content=REPO/'notes/Content data manifest.json';old,new=before(content),read(content)
need([x for x in old['files']if x['path']not in changed_json]==[x for x in new['files']if x['path']not in changed_json],'Every unrelated content entry unchanged')
need({k:v for k,v in old['managed_files'].items()if k not in changed_json}=={k:v for k,v in new['managed_files'].items()if k not in changed_json},'Every unrelated managed content hash unchanged')
for x in new['files']:
 if x['path']in changed_json:need(sha(REPO/x['path'])==x['sha256']==new['managed_files'][x['path']],'Current changed JSON hash correct '+x['path'])
for x in receipt['written_targets']:need(sha(x['path'])==x['after_sha256'],'Exact post-publication target '+x['path'])
report={'schema':'a1241-ap781-published-scope-verification-v1','passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'checks':checks,'checks_completed':len(checks),'only_source_scan_id':'126','uniform_rebuild_deferred':True,'source_or_metadata_writes':False}
(HERE/'Published scope verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':True,'checks':len(checks),'only_source_scan_id':'126'}))

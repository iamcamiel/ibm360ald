"""Guarded single-page socket-table publication; preflight is the default.

Requires an independently supplied acceptance. No acceptance is generated, and
no original scan, historical proof or unrelated source record is modified.
Uniform dataset rebuilding is deliberately deferred until all accepted source
and metadata releases in the coordinator's transaction have finished.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse, csv, hashlib, importlib.util, io, json, os, subprocess, sys

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald'
OUT=ROOT/'tmp/ald-text/ald/uniform-socket-listings/source-review/A1241-C3-3388-addendum'
AUDIT=ROOT/'tmp/ald-text/ald/repository-export';MANIFEST=OUT/'Stage manifest.json'
ADAPTER=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json'
REGISTRY=AUDIT/'A1 table application registry.json';SOURCE=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')

def need(v,m):
    if not v:raise ValueError(m)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(Path(p).read_bytes())}
def checked(link):
    path=Path(link['path']).resolve();need(path.is_file()and sha(path.read_bytes())==link['sha256'],'Stale binding: '+str(path));return path
def module(p,name):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def atomic(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.a1241-addendum-tmp')
    need(not temp.exists(),'Existing temporary file: '+str(temp));temp.write_bytes(raw);os.replace(temp,path)

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--acceptance',required=True,type=Path);cli.add_argument('--publish',action='store_true');args=cli.parse_args()
    stage=read(MANIFEST);acceptance=read(args.acceptance)
    need(acceptance.get('schema')=='socket-table-literal-correction-independent-acceptance-v1'
         and acceptance.get('independent_review') is True and acceptance.get('passed') is True
         and not acceptance.get('failures') and acceptance.get('manifest_sha256')==sha(MANIFEST.read_bytes()),'Independent acceptance does not bind this passing exact table stage')
    checked(stage['registration_helper']);app=module(REPO/'tools/reviews/register_a1_application.py','a1241_published_table_helper')
    need(stage['artifact_schema']==app.TABLE_QUARTET_SCHEMA and stage['model_schema']=='socket-page-records-v1','Actual table schema differs')
    for key in ('source','human_authority','source_crop','predecessor_acceptance','historical_repository_acceptance','preparation_script','font','predecessor_adapter','registry_predecessor'):
        checked(stage[key])
    for link in stage['metadata_preimages']:checked(link)
    targets={}
    for record in stage['files']:
        target=Path(record['target']).resolve();need(target.is_relative_to(ROOT)and target.suffix.lower()not in{'.tif','.tiff'},'Target outside writable source scope')
        need(str(target)not in targets,'Duplicate target');need(target.read_bytes()==checked(record['before']).read_bytes(),'Live source preimage differs: '+str(target));checked(record['candidate']);targets[str(target)]=record
    report={'schema':'a1-card-code-addendum-publication-v1','passed':True,'published':False,'manifest':bind(MANIFEST),
        'independent_acceptance':bind(args.acceptance),'planned_source_targets':len(targets),'original_scan_writes':0,
        'uniform_rebuild_deferred':True,'repository_inventory_refresh_required':True,'publication_script':bind(__file__)}
    if not args.publish:print(json.dumps(report,indent=2));return
    publication=OUT/'Publication';need(not publication.exists(),'Publication already exists; preserve its outcome and do not replay');publication.mkdir()
    backups={};written=[];frozen={str(Path(x['path']).resolve()):x['sha256']for x in stage['metadata_preimages']}
    def write(path,raw):
        path=Path(path).resolve();key=str(path);need(path.is_relative_to(ROOT)and not path.is_relative_to(SOURCE),'Write scope escaped')
        if key not in backups:
            old=path.read_bytes()if path.exists()else None;backups[key]=old
            if key in frozen:need(old is not None and sha(old)==frozen[key],'Frozen metadata preimage changed')
            if old is not None:
                saved=publication/'Predecessors'/path.relative_to(ROOT);saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(old)
        if path.is_file()and path.read_bytes()==raw:return
        atomic(path,raw);written.append(key)
    try:
        # Recheck all source preimages before the first mutation.
        for key,record in targets.items():need(Path(key).read_bytes()==checked(record['before']).read_bytes(),'Concurrent source change')
        for key,record in targets.items():
            need(Path(key).read_bytes()==checked(record['before']).read_bytes(),'Concurrent source change at write');write(key,checked(record['candidate']).read_bytes())
        page_receipt=publication/'Page publication receipt.json'
        pub={'schema':app.PUBLICATION_SCHEMA,'passed':True,'failures':[],'manifest':bind(MANIFEST),'independent_acceptance':bind(args.acceptance),
             'source':stage['source'],'published_targets':[bind(record['target'])for record in stage['files']]}
        write(page_receipt,enc(pub))
        old_adapter=read(ADAPTER);old_registry=read(REGISTRY)
        adapter,registry,item=app.prepare(MANIFEST,page_receipt,args.acceptance,ADAPTER,REGISTRY,ROOT,ROOT/'ALD_Visual_Transcriptions',SOURCE)
        app.validate_registered_applications(REGISTRY,ADAPTER,ROOT,ROOT/'ALD_Visual_Transcriptions',SOURCE,adapter=adapter,registry=registry)
        target=str(Path(next(r['target']for r in stage['files']if r['role']=='working accepted TXT')).resolve())
        need([x for x in old_adapter['pages']if app.target_of(x)!=target]==[x for x in adapter['pages']if app.target_of(x)!=target],'Unrelated adapter items changed')
        need([x for x in old_registry['entries']if x['target']!=target]==[x for x in registry['entries']if x['target']!=target],'Unrelated registry entries changed')
        checked(stage['predecessor_adapter']);checked(stage['registry_predecessor'])
        write(ADAPTER,enc(adapter));write(REGISTRY,enc(registry));app.validate_registered_applications(REGISTRY,ADAPTER,ROOT,ROOT/'ALD_Visual_Transcriptions',SOURCE)
        process=subprocess.run([sys.executable,'-X','utf8',str(AUDIT/'export_reviewed.py')],cwd=ROOT,capture_output=True,text=True)
        (publication/'Read-only export plan.txt').write_text(process.stdout+process.stderr,encoding='utf-8')
        need(process.returncode==0,'Read-only export plan failed')
        plan=read(AUDIT/'export plan.json');need(not plan['conflicts'],'Export plan has conflicts')
        matches=[x for x in plan['exported']if str(x['source_scan_id'])=='126'];need(len(matches)==1,'Corrected table is not independently accepted by exporter');entry=matches[0]
        need(Path(entry['destination']).read_bytes()==Path(entry['transcription_source']).read_bytes(),'Repository/current TXT differs')
        exporter=module(AUDIT/'export_reviewed.py','a1241_scoped_exporter')
        catalogue=list(csv.DictReader(io.StringIO((SOURCE/'ALD Scan Order.csv').read_text(encoding='utf-8-sig'))));i=next(i for i,row in enumerate(catalogue)if str(row['id'])=='126');row=catalogue[i]
        metadata_path,meta=exporter.companion_metadata(Path(entry['transcription_source']))
        note=exporter.note_content(Path(row['newpath']),Path(entry['transcription_source']),meta,row,catalogue[i-1]['newname']if i else'',catalogue[i+1]['newname']if i+1<len(catalogue)else'',entry['review_record'])
        need(sha(note)==entry['notes_sha256'],'Fresh exported notes do not match plan');write(entry['notes_destination'],note)
        record_path=REPO/'notes/A1 Socket Listing/A1241-01 SOCKET LISTING review record.json';record=read(record_path)
        record.update(text_sha256=entry['text_sha256'],acceptance_record=entry['review_record'],working_metadata_source=str(metadata_path),working_metadata_sha256=sha(Path(metadata_path).read_bytes()),review_metadata_snapshot=meta)
        record['reviewed_socket_card_code_correction']={'source_cells':stage['exact_meaningful_cell_changes'],'manifest':bind(MANIFEST),'independent_acceptance':bind(args.acceptance)};write(record_path,enc(record))
        content_path=REPO/'notes/Content data manifest.json';content=read(content_path)
        changed_json={Path(path).relative_to(REPO).as_posix()for path in targets if Path(path).is_relative_to(REPO/'json')};seen=set()
        for value in content['files']:
            if value['path']in changed_json:
                value['sha256']=sha((REPO/value['path']).read_bytes());content['managed_files'][value['path']]=value['sha256'];seen.add(value['path'])
        need(seen==changed_json,'Current JSON content inventory omitted a changed target');content['updated_utc']=datetime.now(timezone.utc).isoformat();write(content_path,enc(content))
        last_path=AUDIT/'last export manifest.json';provenance=REPO/'notes/Reviewed export provenance.json';need(last_path.read_bytes()==provenance.read_bytes(),'Export/provenance baselines differ')
        last=read(last_path);other=[x for x in last['exported']if str(x['source_scan_id'])!='126'];positions=[i for i,x in enumerate(last['exported'])if str(x['source_scan_id'])=='126'];need(len(positions)==1,'Ambiguous predecessor scan identity')
        last['exported'][positions[0]]=entry;last['managed_files'][entry['destination']]=entry['text_sha256'];last['managed_files'][entry['notes_destination']]=entry['notes_sha256']
        need(other==[x for x in last['exported']if str(x['source_scan_id'])!='126'],'Unrelated export entry changed')
        if 'reviewed_plan_sha256'in last:last['reviewed_plan_sha256']=sha((AUDIT/'export plan.json').read_bytes())
        last['updated_utc']=datetime.now(timezone.utc).isoformat();write(last_path,enc(last));write(provenance,enc(last))
        for key,record in targets.items():need(Path(key).read_bytes()==checked(record['candidate']).read_bytes(),'Candidate changed after publication')
        app.validate_registered_applications(REGISTRY,ADAPTER,ROOT,ROOT/'ALD_Visual_Transcriptions',SOURCE)
        report.update(published=True,completed_utc=datetime.now(timezone.utc).isoformat(),page_publication=bind(page_receipt),adapter=bind(ADAPTER),registry=bind(REGISTRY),content_manifest=bind(content_path),provenance=bind(provenance),
            written_targets=[{'path':path,'before_sha256':sha(backups[path])if backups[path]is not None else None,'after_sha256':sha(Path(path).read_bytes())}for path in dict.fromkeys(written)])
        atomic(publication/'Publication receipt.json',enc(report));print(json.dumps({'passed':True,'published':True,'receipt':str(publication/'Publication receipt.json'),'uniform_rebuild_deferred':True}))
    except BaseException as error:
        for key in reversed(list(dict.fromkeys(written))):
            if backups[key]is None:Path(key).unlink(missing_ok=True)
            else:atomic(key,backups[key])
        report.update(passed=False,published=False,error=str(error),rolled_back=True,
            rollback_verified=all((Path(p).read_bytes()if Path(p).exists()else None)==raw for p,raw in backups.items()))
        atomic(publication/'Publication receipt.json',enc(report));raise

if __name__=='__main__':main()

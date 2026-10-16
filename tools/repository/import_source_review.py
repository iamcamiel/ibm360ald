"""Mirror accepted source-review successors without scanning the ALD archive.

Default is a dry run. --write performs one guarded, rollback-capable transaction
for the registry's selected pages, their provenance, and the reviewed baselines.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reviews'))
import source_review as sr
import successor_registry as registry_api

ROOT = Path(__file__).resolve().parents[2]


def digest(raw):return sha256(raw).hexdigest()
def encode(data):return (json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def read(raw):return json.loads(raw.decode('utf-8-sig'))
def require(ok,message):
    if not ok:raise ValueError(message)


def load_exporter(workspace):
    path=Path(workspace)/'tmp/ald-text/ald/repository-export/export_reviewed.py'
    spec=importlib.util.spec_from_file_location('scoped_source_export_notes',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module,path


def build_plan(registry, workspace, repo, exports, source_root, pages=None):
    """Return a public plan and private byte replacements; perform no writes."""
    registry,workspace,repo,exports,source_root=map(lambda p:Path(p).resolve(),(registry,workspace,repo,exports,source_root))
    require(repo.is_relative_to(workspace),'Repository must be inside workspace')
    guards={};updates={};roles={}
    def capture(path,expected=None):
        path=Path(path).resolve();raw=path.read_bytes() if path.is_file() else None
        if expected is not None:require(raw is not None and digest(raw)==expected,'Stale binding: '+str(path))
        signature=None if raw is None else digest(raw)
        require(path not in guards or guards[path]==signature,'Input changed while preparing: '+str(path))
        guards[path]=signature
        return raw
    def put(path,raw,role):
        path=Path(path).resolve();require(path.is_relative_to(workspace),'Write outside workspace')
        capture(path)
        require(path not in updates or updates[path]==raw,'Conflicting planned target: '+str(path))
        updates[path]=raw;roles[path]=role
    def preserve(link):
        path=Path(link['path']).resolve();raw=capture(path,link['sha256'])
        target=repo/'notes/Source reviews/Evidence'/link['sha256']/path.name
        existing=capture(target)
        require(existing in (None,raw),'Immutable preservation collision')
        put(target,raw,'Immutable accepted source-review evidence')
        return {'path':target.relative_to(repo).as_posix(),'sha256':link['sha256']}
    verified=registry_api.accepted_successors(registry,workspace,exports,source_root)
    require(verified.get('passed') is True,'Successor registry did not validate')
    registry_raw=capture(registry,verified['registry']['sha256']);registry_doc=read(registry_raw)
    current=verified['records']
    if pages is not None:
        wanted=set(pages);current=[r for r in current if r['page'] in wanted]
        require(wanted=={r['page'] for r in current},'Requested page is not an accepted current successor')
    require(current,'No accepted pages selected')
    require(len({r['page'] for r in current})==len(current),'Ambiguous page identity in registry')
    audit=workspace/'tmp/ald-text/ald/repository-export'
    exporter,exporter_path=load_exporter(workspace);capture(exporter_path)
    exporter.SOURCE=source_root
    catalogue_raw=capture(source_root/'ALD Scan Order.csv')
    catalogue=list(csv.DictReader(io.StringIO(catalogue_raw.decode('utf-8-sig'))))
    baseline_paths=[audit/'export plan.json',audit/'last export manifest.json']
    baselines=[read(capture(p)) for p in baseline_paths]
    for doc in baselines:
        require(not doc.get('export_in_progress') and not doc.get('conflicts'),'Export baseline is incomplete or conflicted')
    content_path=repo/'notes/Content data manifest.json';content=read(capture(content_path))
    records_path=repo/'notes/Repository records manifest.json';records=read(capture(records_path))
    original_content=deepcopy(content);original_records=deepcopy(records)
    content_entries={e['path']:e for e in content['files']};record_entries={e['path']:e for e in records['files']}
    # Recover every exact accepted state on each registered target chain. This
    # permits a bounded mirror to catch up across several accepted successors.
    states={}
    for release in registry_doc['releases']:
        pubpath=Path(release['publication']['path']);pub=read(capture(pubpath,release['publication']['sha256']))
        manifest_link=pub['manifest'];manifest=read(capture(manifest_link['path'],manifest_link['sha256']))
        for rec in manifest['records']:
            target=str(Path(rec['prior_quartet']['txt']['path']).resolve())
            for group,snapshot_group in (('prior_quartet','before_saved'),('staged_quartet','staged_quartet')):
                states.setdefault(target,[]).append({**{k:v['sha256'] for k,v in rec[group].items()},'_snapshots':rec[snapshot_group]})
    preserved=[preserve(link) for link in verified['preservation_files']]
    summaries=[]
    for item in current:
        page=item['page'];selected=[]
        capture(item['source']['path'],item['source']['sha256'])
        for doc in baselines:
            hits=[e for e in doc['exported'] if e['page']==page and Path(e['transcription_source']).resolve()==Path(item['text_path']).resolve()]
            require(len(hits)==1,'Missing/ambiguous accepted baseline page: '+page);selected.append(hits[0])
        first=selected[0]
        require(sr.json_equal(first,selected[1]),'Export plan and mirrored baseline disagree: '+page)
        require((source_root/first['source_relative']).resolve()==Path(item['source_path']).resolve(),'Source identity differs from baseline: '+page)
        require(Path(first['destination']).resolve().is_relative_to(repo/'ALD'),'Baseline TXT target is outside ALD')
        relative=Path(first['source_relative']).parent
        text_name=Path(first['destination']).name
        paths={'txt':Path(first['destination']).resolve(),'notes':Path(first['notes_destination']).resolve(),
               'json':repo/'json'/relative/Path(text_name).with_suffix('.json').name,
               'preview':repo/'notes'/relative/Path(item['current_quartet']['preview']['path']).name}
        require(paths['notes'].is_relative_to(repo/'notes'),'Notes target outside notes')
        old_hashes={};new_hashes={}
        for kind,path in paths.items():
            raw=capture(path);old_hashes[kind]=digest(raw) if raw is not None else None
            source=item['current_quartet'][kind];new=capture(source['path'],source['sha256']);new_hashes[kind]=source['sha256']
            if kind in ('txt','notes'):
                expected=first['text_sha256' if kind=='txt' else 'notes_sha256']
                require(old_hashes[kind]==expected,'Repository '+kind+' differs from export baseline: '+page)
                require(baselines[0].get('managed_files',{}).get(str(path))==expected,'TXT/notes ownership baseline missing: '+page)
            if kind=='json':
                entry=content_entries.get(path.relative_to(repo).as_posix())
                require(entry and entry['role']=='Published page content model' and entry['sha256']==old_hashes[kind], 'Content baseline differs: '+page)
                require(content.get('managed_files',{}).get(entry['path'])==old_hashes[kind],'Content managed hash differs: '+page)
            key=path.relative_to(repo).as_posix();owned=record_entries.get(key)
            if raw is not None:require(owned and owned['sha256']==old_hashes[kind],'Repository integrity ownership differs: '+key)
            put(path,new,'Accepted source-review current '+kind)
        rows=[(i,row) for i,row in enumerate(catalogue) if Path(row['newpath']).resolve()==Path(item['source_path']).resolve()]
        require(len(rows)==1,'Missing/ambiguous original catalogue row: '+page)
        ordinal,row=rows[0];previous=catalogue[ordinal-1]['newname'] if ordinal else '(none)'
        following=catalogue[ordinal+1]['newname'] if ordinal+1<len(catalogue) else '(none)'
        matched=[]
        for state in states.get(item['text_path'],[]):
            if old_hashes['txt']!=state['txt'] or old_hashes['json']!=state['json'] or old_hashes['preview'] not in (None,state['preview']):continue
            links=state['_snapshots']
            old_meta=read(capture(links['json']['path'],links['json']['sha256']))
            capture(links['txt']['path'],links['txt']['sha256']);capture(links['notes']['path'],links['notes']['sha256'])
            expected=exporter.note_content(Path(item['source_path']),Path(links['txt']['path']),old_meta,row,previous,following,first['review_record'])
            if digest(expected)==old_hashes['notes']:matched.append(state)
        require(matched,'Repository quartet/exported notes are not one exact accepted chain state: '+page)
        current_meta=read(capture(item['current_quartet']['json']['path'],item['current_quartet']['json']['sha256']))
        wrapped_notes=exporter.note_content(Path(item['source_path']),Path(item['text_path']),current_meta,row,previous,following,item['receipt'])
        updates[paths['notes']]=wrapped_notes;new_hashes['notes']=digest(wrapped_notes)
        prior_review=Path(first['review_record']);prior_review=prior_review if prior_review.is_absolute() else workspace/prior_review
        raw=capture(prior_review);require(raw is not None,'Historical acceptance missing: '+page)
        prior_link={'path':str(prior_review.resolve()),'sha256':digest(raw)};prior_preserved=preserve(prior_link)
        pointer={'schema':'source-review-repository-current-v1','page':page,'source':item['source'],
                 'publication':item['publication'],'manifest':item['manifest'],'independent_acceptance':item['independent_acceptance'],
                 'registry':verified['registry'],'preserved_predecessor_review':prior_preserved,
                 'current_repository_quartet':{k:{'path':p.relative_to(repo).as_posix(),'sha256':new_hashes[k]} for k,p in paths.items()}}
        pointer_path=repo/'notes'/relative/(Path(text_name).stem+' source review current.json')
        old_pointer=capture(pointer_path)
        if old_pointer is not None:
            owner=record_entries.get(pointer_path.relative_to(repo).as_posix())
            require(owner and owner['sha256']==digest(old_pointer),'Current review pointer differs from managed inventory')
            prior=read(old_pointer);require(prior.get('schema')==pointer['schema'] and prior.get('page')==page,'Unrelated current-review pointer')
            if prior.get('publication')!=item['publication'] or prior.get('registry')!=verified['registry']:
                preserve({'path':str(pointer_path),'sha256':digest(old_pointer)})
        if old_pointer is not None and prior.get('publication')==item['publication'] and prior.get('registry')==verified['registry']:
            require(prior.get('current_repository_quartet')==pointer['current_repository_quartet'],'Current-review pointer quartet differs')
            pointer=prior
        put(pointer_path,encode(pointer),'Current accepted source-review pointer; predecessor acceptance retained')
        for entry in selected:
            entry.update(text_sha256=new_hashes['txt'],notes_sha256=new_hashes['notes'],review_record=item['receipt'])
        for doc in baselines:
            for kind in ('txt','notes'):doc['managed_files'][str(paths[kind])]=new_hashes[kind]
        entry=content_entries[paths['json'].relative_to(repo).as_posix()]
        entry.update(source=item['current_quartet']['json']['path'],sha256=new_hashes['json'])
        content['managed_files'][entry['path']]=new_hashes['json']
        summaries.append({'page':page,'release_id':item['release_id'],'before':old_hashes,'after':new_hashes,
                          'targets':{k:str(v) for k,v in paths.items()}})
    stamp=datetime.now(timezone.utc).isoformat()
    if content!=original_content:content['updated_utc']=stamp
    put(content_path,encode(content),'Scoped current-content manifest update')
    for doc in baselines:
        trace={'registry_sha256':verified['registry']['sha256'],'pages':sorted(x['page'] for x in current)}
        if trace not in doc.setdefault('scoped_source_review_imports',[]):doc['scoped_source_review_imports'].append(trace)
    plan_raw=encode(baselines[0]);put(baseline_paths[0],plan_raw,'Scoped reviewed export plan update')
    baselines[1]['reviewed_plan_sha256']=digest(plan_raw)
    last_raw=encode(baselines[1]);put(baseline_paths[1],last_raw,'Scoped mirrored export baseline update')
    provenance_path=repo/'notes/Reviewed export provenance.json'
    provenance_raw=capture(provenance_path)
    require(provenance_raw is not None and digest(provenance_raw)==guards[baseline_paths[1]],'Reviewed export provenance differs from baseline')
    put(provenance_path,last_raw,'Scoped reviewed export provenance update')
    # Add/refresh only planned repository files; no filesystem walk or unrelated
    # ownership reset. The records manifest never inventories its own bytes.
    for path,raw in list(updates.items()):
        if path.is_relative_to(repo):
            key=path.relative_to(repo).as_posix();entry=record_entries.get(key)
            if entry is None:
                entry={'path':key};records['files'].append(entry);record_entries[key]=entry
            entry.update(sha256=digest(raw),role=roles[path])
    if records!=original_records:records['updated_utc']=stamp
    put(records_path,encode(records),'Scoped repository integrity manifest update')
    changed={p:raw for p,raw in updates.items() if guards[p] != digest(raw)}
    report={'schema':'accepted-source-review-import-plan-v1','registry':verified['registry'],'pages':summaries,
            'checked_files':len(guards),'planned_writes':len(changed),'source_or_scan_writes':0,
            'mutations':[{'path':str(p),'before_sha256':guards[p],'after_sha256':digest(raw),'role':roles[p]} for p,raw in changed.items()]}
    return report,changed,guards


def apply_plan(report,changes,guards,history):
    """Guard all inputs once, then atomically replace or roll back every target."""
    history=Path(history).resolve();require(not history.exists(),'Import history already exists')
    for path,expected in guards.items():
        current=digest(path.read_bytes()) if path.is_file() else None
        require(current==expected,'Input changed after dry run: '+str(path))
    history.mkdir(parents=True)
    originals={p:p.read_bytes() if p.exists() else None for p in changes}
    for index,(path,raw) in enumerate(originals.items()):
        if raw is not None:sr.atomic_write(history/f'{index:04d}-before.bin',raw)
    sr.atomic_write(history/'plan.json',encode(report))
    written=[]
    try:
        for path,raw in changes.items():
            written.append(path);sr.atomic_write(path,raw)
        for path,raw in changes.items():require(path.read_bytes()==raw,'Mirror verification failed')
        receipt={**report,'schema':'accepted-source-review-import-receipt-v1','passed':True,'written_files':len(written)}
        sr.atomic_write(history/'receipt.json',encode(receipt))
    except BaseException:
        for path in reversed(written):
            raw=originals[path]
            if raw is None:path.unlink(missing_ok=True)
            elif not path.is_file() or path.read_bytes()!=raw:sr.atomic_write(path,raw)
        raise
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('registry',type=Path);parser.add_argument('--workspace',type=Path,default=ROOT.parent)
    parser.add_argument('--repo',type=Path,default=ROOT);parser.add_argument('--exports',type=Path)
    parser.add_argument('--source-root',type=Path,default=Path('D:/Reference Materials/IBM 360/IBM_360_ALD'))
    parser.add_argument('--pages',nargs='+');parser.add_argument('--write',action='store_true')
    parser.add_argument('--plan-output',type=Path)
    args=parser.parse_args();exports=args.exports or args.workspace/'ALD_Visual_Transcriptions'
    report,changes,guards=build_plan(args.registry,args.workspace,args.repo,exports,args.source_root,args.pages)
    if args.plan_output:
        output=args.plan_output.resolve()
        require(not any(output.is_relative_to(Path(root).resolve()) for root in (args.repo,exports,args.source_root)),'Dry-run plan cannot overwrite source/repository trees')
        sr.atomic_write(output,encode(report))
    if args.write:
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        with sr.locked(args.workspace/'tmp/ald-text/ald/repository-export/Source review mirror.lock'):
            report=apply_plan(report,changes,guards,args.workspace/'tmp/ald-text/ald/repository-export/Source review mirror history'/stamp)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()

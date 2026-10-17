"""Guard a verified current-catalog rebuild, including retired misread types."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,sys
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald'
REL='notes/Card types current/Build manifest.json'
PREFIXES=('json/Card types current/','csv/Card types current/','notes/Card types current/')

def read(path):return json.loads(Path(path).read_text('utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bind(path):return {'path':str(Path(path).resolve()),'sha256':sha(Path(path).read_bytes())}
def enc(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def need(ok,message):
    if not ok:raise ValueError(message)
def checked(link):
    path=Path(link['path']);need(bind(path)==link,'Stale binding: '+str(path));return path
def allowed(relative):
    if not isinstance(relative,str) or '\\' in relative:return False
    path=Path(relative)
    if not relative.startswith(PREFIXES) or len(path.parts)!=3 or '..' in path.parts or path.is_absolute() or path.as_posix()!=relative:return False
    target=(REPO/path).resolve()
    return target.is_relative_to(REPO.resolve()) and target.relative_to(REPO.resolve()).as_posix().startswith(PREFIXES)

def private(path):
    path=Path(path).resolve()
    return path.is_relative_to(ROOT.resolve()) and not path.is_relative_to(REPO.resolve())

def inventory(manifest,manifest_digest):
    files=manifest['files'];need(len({f['path'] for f in files})==len(files),'Duplicate catalog inventory path')
    need(all(allowed(f['path']) and re.fullmatch('[0-9a-f]{64}',str(f['sha256'])) for f in files),'Invalid catalog inventory path/hash')
    need(REL not in {f['path'] for f in files},'Catalog inventory must not recursively list its own manifest')
    return {**{f['path']:f['sha256'] for f in files},REL:manifest_digest}
def atomic(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.catalog-refresh-tmp')
    created=False
    try:
        with temporary.open('xb') as stream:
            created=True;stream.write(raw)
        os.replace(temporary,path)
    finally:
        if created:temporary.unlink(missing_ok=True)
def run(argv,log):
    result=subprocess.run([sys.executable,'-X','utf8',*map(str,argv)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    log.write_text(result.stdout+result.stderr,'utf-8');need(result.returncode==0,'Catalog build/verification failed: '+str(log))
    return json.loads(result.stdout)
def namespace():
    # Nested notes are pre-existing provenance, never current generator outputs.
    # Nested JSON/CSV remain visible here so an unowned file rejects the refresh.
    return {path.relative_to(REPO).as_posix() for prefix in PREFIXES for path in (REPO/prefix).rglob('*')
            if path.is_file() and not(prefix=='notes/Card types current/' and len(path.relative_to(REPO).parts)>3)}

def protected_history():
    branch=REPO/'notes/Card types current';result=[]
    need(branch.resolve().is_relative_to(REPO.resolve()),'Protected history root escaped repository')
    for path in sorted(branch.rglob('*')):
        if not path.is_file() or len(path.relative_to(REPO).parts)<=3:continue
        need(path.resolve().is_relative_to(branch.resolve()),'Protected history file escaped its exact namespace')
        result.append({'relative':path.relative_to(REPO).as_posix(),**bind(path)})
    return result

def check_protected_history(expected):
    need(expected==protected_history(),'Protected nested history inventory or bytes changed')

def consumed_sources(fresh):
    """Bind actual page inputs and supplemental models selected by the builder.

    Page paths/hashes come from the candidate's explicit source_pages binding.
    The builder additionally reads the content manifest's accepted-existing-model
    role; its exact listed paths are used, with no inferred A1 directory names.
    """
    sources={}
    def add(relative,digest):
        path=REPO/relative
        need(not Path(relative).is_absolute() and '..' not in Path(relative).parts and path.resolve().is_relative_to(REPO.resolve()),'Source input outside repository')
        need(relative not in sources or sources[relative]==digest,'Conflicting catalog source binding')
        need(bind(path)['sha256']==digest,'Catalog source input differs: '+relative);sources[relative]=digest
    for text,entry in fresh['source_pages'].items():
        add(text,entry['text_sha256']);add(entry['model'],entry['model_sha256'])
    content=read(REPO/'notes/Content data manifest.json')
    for entry in content['files']:
        if entry['role']=='Accepted existing A1 board model or source-column table':add(entry['path'],entry['sha256'])
    return [bind(REPO/path) for path in sorted(sources)]

def prepare(output):
    output=Path(output).resolve();need(private(output) and not output.exists(),'Use a new private output directory')
    protected=protected_history()
    old=read(REPO/REL);owned=inventory(old,bind(REPO/REL)['sha256'])
    need(namespace()==set(owned),'Current catalog namespace differs from owned inventory')
    for relative,digest in owned.items():need(allowed(relative) and bind(REPO/relative)['sha256']==digest,'Current catalog predecessor differs')
    output.mkdir(parents=True);candidate=output/'Candidate';before=output/'Predecessors'
    builder=REPO/'tools/references/build_current_card_catalog.py';verifier=REPO/'tools/references/verify_current_card_catalog.py'
    run([builder,'--repo',REPO,'--output',candidate],output/'Build.txt')
    verified=run([verifier,'--repo',REPO,'--catalog',candidate],output/'Independent verification.txt');need(verified.get('passed') is True,'Candidate verification did not pass')
    fresh=read(candidate/REL);new=inventory(fresh,bind(candidate/REL)['sha256'])
    need(all(allowed(relative) for relative in new),'Candidate output escaped catalog namespaces')
    records=[]
    for relative in sorted(set(owned)|set(new)):
        target=REPO/relative;old_binding=None;candidate_binding=None
        if relative in owned:
            need(bind(target)['sha256']==owned[relative],'Predecessor changed during build')
            saved=before/relative;saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(target.read_bytes());old_binding=bind(saved)
        else:need(not target.exists(),'Unowned new catalog target exists')
        if relative in new:
            candidate_binding=bind(candidate/relative);need(candidate_binding['sha256']==new[relative],'Candidate inventory differs')
        records.append({'relative':relative,'before':old_binding,'candidate':candidate_binding})
    source_bindings=[bind(REPO/'notes/Reviewed export provenance.json'),bind(REPO/'notes/Content data manifest.json')]
    need(fresh['source_binding']['reviewed_export_provenance_sha256']==source_bindings[0]['sha256'] and fresh['source_binding']['content_data_manifest_sha256']==source_bindings[1]['sha256'],'Candidate source epoch differs')
    manifest={'schema':'guarded-current-card-catalog-refresh-v1','created_utc':datetime.now(timezone.utc).isoformat(),'records':records,
              'inputs':source_bindings+consumed_sources(fresh)+[{'path':x['path'],'sha256':x['sha256']} for x in protected]+[bind(builder),bind(verifier),bind(__file__)],
              'protected_nested_notes_history':protected,
              'old_manifest_sha256':owned[REL],'new_manifest_sha256':new[REL],
              'candidate_verification':verified,'card_types':fresh['card_types'],'counts':fresh['counts'],
              'source_writes':0,'published':False}
    check_protected_history(protected)
    atomic(output/'Refresh manifest.json',enc(manifest));print(json.dumps({'prepared':True,'card_types':fresh['card_types'],'retired':len(set(owned)-set(new)),'protected_history_files':len(protected),'manifest':bind(output/'Refresh manifest.json')}))

def publish(manifest_path):
    manifest_path=Path(manifest_path).resolve();folder=manifest_path.parent
    need(private(manifest_path) and manifest_path.name=='Refresh manifest.json','Use an exact prepared private refresh manifest')
    manifest=read(manifest_path)
    need(manifest['schema']=='guarded-current-card-catalog-refresh-v1','Unsupported catalog refresh')
    need(all(re.fullmatch('[0-9a-f]{64}',str(manifest[k])) for k in ['old_manifest_sha256','new_manifest_sha256']),'Invalid catalog epoch hash')
    protected=manifest['protected_nested_notes_history'];check_protected_history(protected)
    receipt_path=folder/'Publication receipt.json';need(not receipt_path.exists(),'Publication already recorded')
    for link in manifest['inputs']:checked(link)
    history=REPO/'notes/Source reviews/Current card catalog predecessors'/manifest['old_manifest_sha256']
    proof=REPO/'notes/Source reviews/Current card catalog successors'/manifest['new_manifest_sha256']
    need(not proof.exists(),'Candidate catalog epoch already has a publication proof')
    records=manifest['records'];need(len({r['relative'] for r in records})==len(records),'Duplicate refresh target')
    old_manifest=folder/'Predecessors'/REL;fresh_manifest=folder/'Candidate'/REL
    need(sha(old_manifest.read_bytes())==manifest['old_manifest_sha256'] and sha(fresh_manifest.read_bytes())==manifest['new_manifest_sha256'],'Prepared catalog manifest epoch differs')
    old_inventory=inventory(read(old_manifest),manifest['old_manifest_sha256']);new_inventory=inventory(read(fresh_manifest),manifest['new_manifest_sha256'])
    need({r['relative'] for r in records}==set(old_inventory)|set(new_inventory),'Refresh targets differ from exact old/new inventories')
    for r in records:
        rel=r['relative'];need(allowed(rel),'Write escaped catalog namespaces')
        for key,branch,expected in [('before','Predecessors',old_inventory),('candidate','Candidate',new_inventory)]:
            need(bool(r[key])==(rel in expected),'Refresh record presence differs from inventory')
            if r[key]:need(Path(r[key]['path']).resolve()==(folder/branch/rel).resolve() and private(r[key]['path']) and r[key]['sha256']==expected[rel],'Prepared file escaped its exact private inventory binding')
    owned={r['relative'] for r in records if r['before']}
    need(namespace()==owned,'Predecessor catalog namespace changed')
    for record in records:
        target=REPO/record['relative'];need(allowed(record['relative']),'Write escaped catalog namespaces')
        current=target.read_bytes() if target.exists() else None
        need(current==(checked(record['before']).read_bytes() if record['before'] else None),'Current catalog preimage differs')
        if record['candidate']:checked(record['candidate'])
    need(manifest['candidate_verification'].get('passed') is True,'Prepared candidate was not verified')
    reverified=run([REPO/'tools/references/verify_current_card_catalog.py','--repo',REPO,'--catalog',folder/'Candidate'],folder/'Publication candidate verification.txt')
    need(reverified.get('passed') is True,'Publication candidate verification did not pass')
    actual_sources=consumed_sources(read(fresh_manifest))
    required_inputs=actual_sources+[{'path':x['path'],'sha256':x['sha256']} for x in protected]+[bind(REPO/'notes/Reviewed export provenance.json'),bind(REPO/'notes/Content data manifest.json'),bind(REPO/'tools/references/build_current_card_catalog.py'),bind(REPO/'tools/references/verify_current_card_catalog.py'),bind(__file__)]
    need(len(manifest['inputs'])==len(required_inputs) and {(x['path'],x['sha256']) for x in manifest['inputs']}=={(x['path'],x['sha256']) for x in required_inputs},'Prepared source/tool binding inventory differs from complete actual inputs')
    for link in actual_sources:checked(link)
    for link in manifest['inputs']:checked(link)
    changed=[];proof_paths=[];receipt_written=False
    try:
        for record in records:
            target=REPO/record['relative'];old=checked(record['before']).read_bytes() if record['before'] else None
            new=checked(record['candidate']).read_bytes() if record['candidate'] else None
            if old==new:continue
            if old is not None:
                saved=history/record['relative'];need(not saved.exists() or saved.read_bytes()==old,'Historical catalog collision')
                if not saved.exists():atomic(saved,old)
            changed.append(record)
            if new is None:target.unlink()
            else:atomic(target,new)
        result=run([REPO/'tools/references/verify_current_card_catalog.py','--repo',REPO,'--catalog',REPO],folder/'Published verification.txt')
        need(result.get('passed') is True,'Published catalog verification failed')
        for link in manifest['inputs']:checked(link)
        check_protected_history(protected)
        need(namespace()=={r['relative'] for r in records if r['candidate']},'Published catalog namespace differs')
        receipt={'schema':'guarded-current-card-catalog-publication-v1','passed':True,'completed_utc':datetime.now(timezone.utc).isoformat(),
                 'manifest':bind(manifest_path),'verification':result,'source_writes':0,
                 'changes':[{'path':r['relative'],'before_sha256':r['before']['sha256'] if r['before'] else None,'after_sha256':r['candidate']['sha256'] if r['candidate'] else None} for r in changed],
                 'predecessors':str(history),'protected_nested_notes_history':protected,'protected_history_unchanged':True,'repository_inventory_refresh_required':True}
        proof.mkdir(parents=True)
        for name,raw in [('Refresh manifest.json',manifest_path.read_bytes()),('Published verification.txt',(folder/'Published verification.txt').read_bytes()),('Publication receipt.json',enc(receipt))]:
            path=proof/name;atomic(path,raw);proof_paths.append(path)
        atomic(receipt_path,enc(receipt));receipt_written=True;print(json.dumps({'passed':True,'changed':len(changed),'receipt':bind(receipt_path)}))
    except BaseException as original:
        rollback_failures=[]
        for record in reversed(changed):
            target=REPO/record['relative']
            try:
                if record['before']:atomic(target,checked(record['before']).read_bytes())
                elif target.exists():target.unlink()
            except BaseException as exc:rollback_failures.append(str(target)+': '+str(exc))
        for path in proof_paths:path.unlink(missing_ok=True)
        if receipt_written:receipt_path.unlink(missing_ok=True)
        if proof.exists() and not any(proof.iterdir()):proof.rmdir()
        try:check_protected_history(protected)
        except BaseException as exc:rollback_failures.append('Protected history: '+str(exc))
        if rollback_failures:raise RuntimeError('Catalog refresh failed and rollback needs attention: '+repr(rollback_failures)) from original
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('prepare').add_argument('--output',required=True,type=Path)
    sub.add_parser('publish').add_argument('manifest',type=Path)
    args=parser.parse_args()
    if args.command=='prepare':prepare(args.output)
    else:publish(args.manifest)

"""Build/verify a new uniform candidate, then guard an existing-namespace refresh.

Original scans, accepted ALD text, legacy models and their provenance are read
only. Publishing replaces only the preexisting uniform dataset paths and writes
the requested portable verification proof. Full private predecessors support
rollback; this does not invoke the original first-publication helper.
"""
from datetime import datetime,timezone
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys
from A1554_uniform_release_guard import check_release, verify_semantic_delta

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald'
BUILD=REPO/'tools/references/build_uniform_socket_listings.py'
VERIFY=REPO/'tools/references/verify_uniform_socket_listings.py'
REL='notes/Socket listings uniform/Build manifest.json'
PROOF=REPO/'notes/Reference data/Uniform socket listings/A1554 G5 correction epoch 20261017'
PREFIXES=('json/Socket listings uniform/','csv/Socket listings uniform/','notes/Socket listings uniform/')

def need(v,m):
    if not v:raise ValueError(m)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(Path(p).read_bytes())}
def checked(link):
    path=Path(link['path']).resolve();need(path.is_file()and sha(path.read_bytes())==link['sha256'],'Stale binding: '+str(path));return path
def enc(v):return(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def atomic(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.uniform-refresh-tmp')
    created=False
    try:
        # Exclusive creation protects an unowned preexisting file, including
        # a race after a separate exists() check. Clean up only our own temp.
        try:
            stream=temp.open('xb')
        except FileExistsError as error:
            raise ValueError('Unowned temporary file: '+str(temp)) from error
        created=True
        with stream:stream.write(raw)
        os.replace(temp,path)
    finally:
        if created:temp.unlink(missing_ok=True)
def allowed(relative):
    return isinstance(relative,str)and relative.startswith(PREFIXES)and'..'not in Path(relative).parts and not Path(relative).is_absolute()
def run(args,log):
    process=subprocess.run([sys.executable,'-X','utf8',*map(str,args)],cwd=ROOT,capture_output=True,text=True)
    log.write_text(process.stdout+process.stderr,encoding='utf-8');need(process.returncode==0,'Verification/build failed; see '+str(log))

def prepare(output, release_receipt):
    output=Path(output).resolve();need(output.is_relative_to(ROOT)and not output.is_relative_to(REPO)and not output.exists(),'Use a NEW private output directory')
    old_path=REPO/REL;old_raw=old_path.read_bytes();old=read(old_path)
    links={x['path']:x['sha256']for x in old['files']}
    need(len(links)==len(old['files'])and all(allowed(x)for x in links),'Invalid prior namespace inventory')
    need(REL not in links,'Build manifest unexpectedly self-inventoried');links[REL]=sha(old_raw)
    actual={p.relative_to(REPO).as_posix()for prefix in PREFIXES for p in (REPO/prefix).rglob('*')if p.is_file()}
    need(actual==set(links),'Unowned or missing uniform namespace files')
    for relative,expected in links.items():need(sha((REPO/relative).read_bytes())==expected,'Owned predecessor differs: '+relative)
    release=check_release(release_receipt)
    output.mkdir(parents=True);candidate=output/'Candidate dataset';before=output/'Predecessor dataset'
    atomic(output/'Accepted A1554 source release guard.json',enc(release))
    for relative in links:
        saved=before/relative;saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes((REPO/relative).read_bytes())
    run([BUILD,'--repo',REPO,'--output',candidate],output/'Candidate build.txt')
    run([VERIFY,'--repo',REPO,'--dataset',candidate,'--report',output/'Candidate independent verification.json'],output/'Candidate verifier.txt')
    fresh=read(candidate/REL);verification=read(output/'Candidate independent verification.json')
    need(verification['passed']is True and not verification['failures'],'Independent verification failed')
    need(fresh['counts']==old['counts'],'Source identity correction changed structural counts')
    semantic=verify_semantic_delta(before/'json/Socket listings uniform/Socket listings.json',candidate/'json/Socket listings uniform/Socket listings.json')
    atomic(output/'Exact uniform semantic delta.json',enc(semantic))
    new={x['path']:x['sha256']for x in fresh['files']};new[REL]=sha((candidate/REL).read_bytes())
    need(set(new)==set(links),'Uniform output inventory changed')
    records=[]
    for relative,expected in sorted(links.items()):
        need(allowed(relative),'Derived target escaped namespace')
        need(sha((REPO/relative).read_bytes())==expected,'Live predecessor changed during build')
        records.append({'relative':relative,'target':str(REPO/relative),'before':bind(before/relative),'candidate':bind(candidate/relative)})
    inputs=[{'path':str(REPO/x['path']),'sha256':x['sha256']}for x in fresh['inputs']]
    inputs += [bind(VERIFY),bind(Path(__file__)),*release['inputs']]
    inputs=list({(x['path'],x['sha256']):x for x in inputs}.values())
    for link in inputs:checked(link)
    manifest={'schema':'guarded-existing-uniform-A1554-count-preserving-refresh-v1','created_utc':datetime.now(timezone.utc).isoformat(),'published':False,
        'source_writes':0,'legacy_model_writes':0,'original_scan_writes':0,'records':records,'counts':fresh['counts'],
        'inputs':inputs,'candidate_verification':bind(output/'Candidate independent verification.json'),
        'predecessor_build_manifest':bind(before/REL),'current_candidate_build_manifest':bind(candidate/REL),
        'source_release_guard':bind(output/'Accepted A1554 source release guard.json'),
        'source_release_receipt':bind(release_receipt),'predecessor_counts':old['counts'],
        'exact_semantic_delta':bind(output/'Exact uniform semantic delta.json'),
        'portable_proof_target':str(PROOF),'changed_files':sum(r['before']['sha256']!=r['candidate']['sha256']for r in records)}
    atomic(output/'Refresh manifest.json',enc(manifest))
    return{'passed':True,'published':False,'manifest':bind(output/'Refresh manifest.json'),'counts':fresh['counts'],'existing_paths':len(records),'changed_files':manifest['changed_files']}

def publish(manifest_path):
    manifest_path=Path(manifest_path).resolve();folder=manifest_path.parent;manifest=read(manifest_path)
    need(manifest['schema']=='guarded-existing-uniform-A1554-count-preserving-refresh-v1','Unsupported refresh schema')
    need(Path(manifest['portable_proof_target']).resolve()==PROOF.resolve(),'Portable proof target changed')
    need(not(folder/'Publication receipt.json').exists()and not PROOF.exists(),'Refresh/proof already published; do not replay')
    checked(manifest['candidate_verification']);checked(manifest['predecessor_build_manifest']);checked(manifest['current_candidate_build_manifest'])
    for link in manifest['inputs']:checked(link)
    frozen_release=read(checked(manifest['source_release_guard']))
    live_release=check_release(checked(manifest['source_release_receipt']))
    need(live_release==frozen_release,'Accepted source release or current postimages changed')
    checked(manifest['exact_semantic_delta'])
    live_semantic=verify_semantic_delta(folder/'Predecessor dataset/json/Socket listings uniform/Socket listings.json',folder/'Candidate dataset/json/Socket listings uniform/Socket listings.json')
    need(live_semantic==read(checked(manifest['exact_semantic_delta'])),'Semantic delta changed')
    need(manifest['counts']==manifest['predecessor_counts'],'Uniform structural counts changed')
    actual={p.relative_to(REPO).as_posix()for prefix in PREFIXES for p in (REPO/prefix).rglob('*')if p.is_file()}
    need(actual=={r['relative']for r in manifest['records']},'Unowned or missing uniform namespace files at publication')
    targets=set()
    for record in manifest['records']:
        relative=record['relative'];target=Path(record['target']).resolve();need(allowed(relative)and target==(REPO/relative).resolve(),'Target escaped existing namespace')
        need(target not in targets,'Duplicate refresh target');targets.add(target)
        checked(record['before']);checked(record['candidate']);need(target.read_bytes()==checked(record['before']).read_bytes(),'Current predecessor changed')
    written=[];proof_written=[]
    try:
        for record in manifest['records']:
            target=Path(record['target']);old=checked(record['before']).read_bytes();new=checked(record['candidate']).read_bytes()
            need(target.read_bytes()==old,'Concurrent namespace change')
            if old!=new:atomic(target,new);written.append(record)
        # Check the actual published namespace against independent source spans.
        run([VERIFY,'--repo',REPO,'--report',folder/'Published independent verification.json'],folder/'Published verifier.txt')
        published=read(folder/'Published independent verification.json');need(published['passed']is True and not published['failures'],'Published independent verification failed')
        for link in manifest['inputs']:checked(link)
        for record in manifest['records']:need(Path(record['target']).read_bytes()==checked(record['candidate']).read_bytes(),'Published output differs from verified candidate')
        receipt={'schema':'guarded-existing-uniform-A1554-count-preserving-publication-v1','passed':True,'published':True,
            'completed_utc':datetime.now(timezone.utc).isoformat(),'manifest':bind(manifest_path),'counts':manifest['counts'],
            'candidate_verification':manifest['candidate_verification'],'published_verification':bind(folder/'Published independent verification.json'),
            'current_build_manifest':bind(REPO/REL),'source_epoch_inputs':manifest['inputs'],
            'source_release_guard':manifest['source_release_guard'],'source_release_receipt':manifest['source_release_receipt'],
            'exact_semantic_delta':manifest['exact_semantic_delta'],
            'predecessor_counts':manifest['predecessor_counts'],
            'existing_paths':len(manifest['records']),'written_paths':len(written),'source_writes':0,'legacy_model_writes':0,'original_scan_writes':0,
            'private_predecessors':str(folder/'Predecessor dataset'),'repository_inventory_refresh_required':True}
        # Keep compact portable proof with the complete immutable source epoch.
        # Large duplicate predecessor/candidate datasets remain private.
        PROOF.mkdir(parents=True)
        def preserve(source,relative):
            source=Path(source);dest=PROOF/relative;need(not dest.exists(),'Portable proof collision')
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read_bytes());proof_written.append(dest)
            return{'path':dest.relative_to(REPO).as_posix(),'sha256':sha(dest.read_bytes()),'original_path':str(source.resolve())}
        proof=[]
        for source,name in [(checked(manifest['predecessor_build_manifest']),'Predecessor build manifest.json'),
                            (REPO/REL,'Current build manifest.json'),
                            (checked(manifest['candidate_verification']),'Candidate independent verification.json'),
                            (folder/'Published independent verification.json','Published independent verification.json'),
                            (checked(manifest['source_release_guard']),'Accepted A1554 source release guard.json'),
                            (checked(manifest['exact_semantic_delta']),'Exact uniform semantic delta.json'),
                            (Path(__file__),'refresh_uniform_after_A1554.py')]:
            proof.append(preserve(source,Path(name)))
        for link in manifest['inputs']:
            source=checked(link)
            if source.is_relative_to(REPO):relative=Path('Final input snapshots')/source.relative_to(REPO)
            else:relative=Path('Final input snapshots/tools')/source.name
            destination=PROOF/relative
            if destination.exists():
                need(destination.is_file()and destination.read_bytes()==source.read_bytes(),
                     'Portable input snapshot basename collision: '+str(relative))
            else:proof.append(preserve(source,relative))
        portable_plan={'schema':'portable-existing-uniform-refresh-hash-plan-v1','counts':manifest['counts'],
            'files':[{'path':r['relative'],'before_sha256':r['before']['sha256'],'after_sha256':r['candidate']['sha256']}for r in manifest['records']],
            'scope':'Only existing uniform namespace paths. Full private preimages retain rollback data; this portable plan preserves their exact before/after identities.'}
        path=PROOF/'Guarded namespace hash plan.json';atomic(path,enc(portable_plan));proof_written.append(path)
        proof.append({'path':path.relative_to(REPO).as_posix(),'sha256':sha(path.read_bytes())})
        receipt['portable_evidence']=proof
        portable_receipt=PROOF/'Current build receipt.json';atomic(portable_receipt,enc(receipt));proof_written.append(portable_receipt)
        atomic(folder/'Publication receipt.json',enc(receipt))
        return{'passed':True,'published':True,'receipt':bind(folder/'Publication receipt.json'),'portable_receipt':bind(portable_receipt),'source_epoch_stable':True,'counts':manifest['counts']}
    except BaseException as error:
        for record in reversed(written):atomic(record['target'],checked(record['before']).read_bytes())
        for path in reversed(proof_written):path.unlink(missing_ok=True)
        # Empty directories may remain; never recursively remove a computed tree.
        rollback=all(Path(r['target']).read_bytes()==checked(r['before']).read_bytes()for r in manifest['records'])
        atomic(folder/'Failed publication receipt.json',enc({'passed':False,'published':False,'error':str(error),'rolled_back':rollback}))
        raise

def main():
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('prepare');p.add_argument('--output',type=Path,required=True);p.add_argument('--source-release-receipt',type=Path,required=True)
    p=commands.add_parser('publish');p.add_argument('manifest',type=Path)
    args=parser.parse_args();result=prepare(args.output,args.source_release_receipt)if args.command=='prepare'else publish(args.manifest)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()

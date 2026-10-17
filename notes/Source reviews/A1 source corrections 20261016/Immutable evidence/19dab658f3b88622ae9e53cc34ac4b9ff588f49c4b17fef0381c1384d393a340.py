"""Prepare compact portable proof files privately; never write the repository."""
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import argparse,hashlib,json,copy
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).parent
DEST='notes/Source reviews/A1 source corrections 20261016'

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def ptr(doc,p):
    if not p:return doc
    for k in p.strip('/').split('/'):
        k=k.replace('~1','/').replace('~0','~');doc=doc[int(k)] if isinstance(doc,list) else doc[k]
    return doc
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True,type=Path);args=ap.parse_args();out=args.output.resolve()
    assert out.is_relative_to(ROOT) and not out.is_relative_to(REPO) and not out.exists(),'Use a fresh private output directory'
    ba=ROOT/'tmp/ald-text/ald/uniform-socket-listings/source-review/A1231-A1232-BA-portion-corrections'
    config=[('A1122 identity',HERE/'A1 source stages/A1122-01-v2'),('A1344 identity',HERE/'A1 source stages/A1344-01'),('A1251 shared auxiliary recovery',HERE/'A1251-02 auxiliary rebind'),('BA portions',ba)]
    receipts={name:read(folder/'Publication/Publication receipt.json') for name,folder in config}
    assert all(r.get('passed') is True and r.get('published') is True for r in receipts.values()),'Every release must have an actual final published receipt'
    out.mkdir(parents=True);payload=out/'payload';payload.mkdir();objects=payload/'Immutable evidence';objects.mkdir()
    inputs={};copied={};references=[];proposed=[];notes=[];change_sets={};canonical=[]
    # Reuse exact immutable evidence already in notes instead of copying fonts,
    # receipts or crops again. Only size-matching candidates are hashed.
    bysize=defaultdict(list)
    for p in (REPO/'notes').rglob('*'):
        if p.is_file() and p.suffix.lower() not in {'.tif','.tiff'}:bysize[p.stat().st_size].append(p)
    digestcache={};reused={}
    def digest(p):
        p=Path(p).resolve()
        if p not in digestcache:digestcache[p]=sha(p)
        return digestcache[p]
    def add(p,role,release,expected=None):
        p=Path(p).resolve();assert p.is_file(),str(p)
        digest_value=sha(p);assert expected is None or digest_value==expected,'Immutable input differs '+str(p)
        inputs[p]=digest_value
        if p.suffix.lower() in {'.tif','.tiff'}:
            references.append(dict(path=str(p),sha256=digest_value,role=role,release=release,disposition='external_original_TIFF_not_copied'));return
        if digest_value not in copied and digest_value not in reused:
            existing=next((q for q in bysize.get(p.stat().st_size,[]) if digest(q)==digest_value),None)
            if existing:
                reused[digest_value]={'repository_path':existing.relative_to(REPO).as_posix(),'sha256':digest_value,'bytes':p.stat().st_size}
            else:
                name=digest_value+p.suffix.lower();target=objects/name;target.write_bytes(p.read_bytes());assert sha(target)==digest_value
                relative=DEST+'/Immutable evidence/'+name
                copied[digest_value]={'relative':relative,'private_path':str(target),'sha256':digest_value,'bytes':p.stat().st_size}
                proposed.append(dict(path=relative,prepared_file=str(target),sha256=digest_value,bytes=p.stat().st_size,kind='copied_immutable_evidence',role=role))
        references.append(dict(original_path=str(p),sha256=digest_value,role=role,release=release,
                               portable_path=(copied.get(digest_value) or reused[digest_value]).get('relative',(copied.get(digest_value) or reused[digest_value]).get('repository_path')),
                               disposition='copied_byte_for_byte' if digest_value in copied else 'reuse_existing_identical_repository_evidence'))
    def addlink(link,role,release):
        p=Path(link['path']);p=p if p.is_absolute() else ROOT/p
        if p.exists() and sha(p)==link['sha256']:add(p,role,release,link['sha256'])
        else:references.append(dict(original_path=str(p),sha256=link['sha256'],role=role,release=release,disposition='historical_binding_path_now_superseded; identify_by_hash'))
    def keepmetadata(p,role,release):
        add(p,role,release)
        doc=read(p)
        # Preserve the useful selected provenance graph, not every data preimage.
        for key in ['preparation_script','publication_script','registration_helper','reviewer','reviewer_program','full_independent_review','human_authority','predecessor_acceptance','predecessor_application_snapshot','historical_repository_acceptance','coordinator_native_readings','pin_publication_verification','active_entry_helper','native_proposals']:
            link=doc.get(key)
            if isinstance(link,dict) and 'path' in link and 'sha256' in link:addlink(link,key,release)
        for key in ['reviewers','source_crops','evidence']:
            for link in doc.get(key,[]) if isinstance(doc.get(key,[]),list) else []:
                if isinstance(link,dict) and 'path' in link and 'sha256' in link:
                    if key=='source_crops' or Path(link['path']).suffix.lower() in {'.py','.png','.jpg','.jpeg'}:addlink(link,key,release)
        if isinstance(doc.get('font'),dict):addlink(doc['font'],'rendering font binding',release)
        if isinstance(doc.get('source'),dict):
            # Hash was accepted by the copied independent review; no TIFF copied.
            references.append(dict(original_path=doc['source']['path'],sha256=doc['source']['sha256'],role='original TIFF source',release=release,disposition='external_original_TIFF_not_copied'))
        return doc
    def owners(doc,path):
        parts=path.strip('/').split('/')
        if parts[0] in {'records','logical_records','socket_records','sections','sockets'} and len(parts)>=2:base='/'+parts[0]+'/'+parts[1]
        elif parts[0]=='ALD_pages' and len(parts)>=3:base='/'+parts[0]+'/'+parts[1]+'/'+parts[2]
        else:return None
        try:return dict(pointer=base,value=ptr(doc,base))
        except (KeyError,IndexError):return dict(pointer=base,value=None)
    def stagechanges(name,stage):
        summary={'stage_manifest_sha256':sha(stage),'exact_file_deltas':[],'native_TIFF_bindings':[]}
        doc=keepmetadata(stage,'immutable source correction stage',name)
        if doc.get('source'):summary['native_TIFF_bindings'].append(doc['source'])
        for f in doc.get('files',[]):
            rec={'target':f['target'],'role':f['role'],'before_sha256':f['before']['sha256'] if f['before'] else None,'after_sha256':f['candidate']['sha256'],'exact_changes':f['changes']}
            old=Path(f['before']['path']) if f['before'] else None;new=Path(f['candidate']['path'])
            assert sha(new)==f['candidate']['sha256']
            inputs[new.resolve()]=f['candidate']['sha256']
            if old:assert sha(old)==f['before']['sha256'];inputs[old.resolve()]=f['before']['sha256']
            if f['role'] in {'working accepted TXT','repository accepted TXT','current accepted socket table model','successor columns proof'}:
                if old:add(old,'exact page/columns predecessor snapshot',name,f['before']['sha256'])
                add(new,'exact page/columns corrected snapshot',name,f['candidate']['sha256'])
            elif f['role']=='current auxiliary reference mirror':
                # Exact patch records plus minimal full physical owners permit a
                # portable review without copying many-MB shared reference files.
                beforedoc=read(old);afterdoc=read(new);witnesses={}
                for change in f['changes']:
                    path=change.get('pointer',change.get('path'));a=owners(beforedoc,path);z=owners(afterdoc,path)
                    key=(a or z or {}).get('pointer',path)
                    witnesses[key]={'before':a,'after':z}
                rec['scoped_JSON_owner_witnesses']=list(witnesses.values())
                rec['shared_full_preimages_copied']=False
            else:
                references.append(dict(original_path=str(new),sha256=f['candidate']['sha256'],role=f['role'],release=name,disposition='bound_full_preview_or_notes_snapshot_not_duplicated'))
            summary['exact_file_deltas'].append(rec)
        return summary
    for name,folder in config:
        pub=folder/'Publication/Publication receipt.json';keepmetadata(pub,'actual immutable publication receipt',name)
        receipt=receipts[name]
        changes=receipt.get('written_targets',receipt.get('published_targets',[]))
        for item in changes:
            path=Path(item.get('path',item.get('target','')))
            if not str(path):continue
            expected=item.get('after_sha256',item.get('sha256'))
            canonical.append(dict(release=name,path=str(path),publication_epoch_sha256=expected,
                                  repository_path=path.resolve().relative_to(REPO).as_posix() if path.resolve().is_relative_to(REPO) else None,
                                  current_sha256=sha(path) if path.is_file() else None,
                                  status='matches_publication_epoch' if path.is_file() and sha(path)==expected else 'superseded_or_external_current_state',
                                  copied_as_evidence=False))
        if name in {'A1122 identity','A1344 identity'}:
            change_sets[name]=stagechanges(name,folder/'Stage manifest.json')
            for filename in ['Independent publication acceptance.json','Independent stage acceptance.json','Resolution authority.json','Predecessor application proof.json','Historical repository proof.json','Preparation assertions.json']:
                p=folder/filename
                if p.exists():keepmetadata(p,filename,name)
            keepmetadata(folder/'Publication/Page publication receipt.json','actual immutable page publication receipt',name)
        elif name=='A1251 shared auxiliary recovery':
            change_sets[name]=keepmetadata(folder/'Repair plan.json','exact metadata-only recovery plan',name)
            keepmetadata(folder/'Verification.json','existing-authority recovery proof, not new visual acceptance',name)
            keepmetadata(folder/'Publication/Intent.json','actual recovery publication intent',name)
            for filename in ['Before adapter.json','After adapter candidate.json']:add(folder/'Publication'/filename,'exact adapter epoch snapshot',name)
            for key,link in receipt['exact_existing_V4_authority'].items():addlink(link,'historical original V4 '+key,name)
            add(folder/'publish_auxiliary_rebind.py','recovery helper snapshot',name)
            link=receipt['current_adapter'];path=Path(link['path'])
            canonical.append(dict(release=name,path=str(path),publication_epoch_sha256=receipt['adapter_candidate_sha256'],repository_path=None,
                                  current_sha256=sha(path),status='matches_publication_epoch' if sha(path)==receipt['adapter_candidate_sha256'] else 'superseded_metadata_adapter_epoch',
                                  output_kind='metadata-only existing-authority hash rebind; no source text or new visual acceptance',copied_as_evidence=False))
        else:
            batch=keepmetadata(folder/'Batch manifest.json','immutable BA batch stage',name)
            keepmetadata(folder/'Independent acceptance.json','actual independent BA batch acceptance',name)
            keepmetadata(folder/'Prepared page stages.json','exact BA page-stage inventory',name)
            keepmetadata(folder/'Mechanical scope verification.json','preparer scope evidence, not independent acceptance',name)
            for link in read(folder/'Prepared page stages.json')['page_stages']:
                p=Path(link['path']);change_sets[name+' '+p.parent.name]=stagechanges(name,p)
                for filename in ['Historical repository proof.json','Predecessor application item.json']:
                    q=p.parent/filename
                    if q.exists():add(q,'historical predecessor proof copy',name)
            # Global shared auxiliary deltas are in the batch, not its five-file
            # page stages. Keep their exact patch and owner witnesses as well.
            change_sets[name+' complete batch']=stagechanges(name,folder/'Batch manifest.json')
            for link in batch.get('preserved_column_proofs',[]):addlink(link,'unchanged original column proof',name)
            for link in receipt['page_publications']:addlink(link,'actual immutable BA page publication receipt',name)
    # Preserve superseded A1122 preparation transparently; it was never accepted.
    old=HERE/'A1 source stages/A1122-01/Stage manifest.json'
    if old.exists():add(old,'superseded private preparation; not an acceptance or publication','A1122 identity')
    add(__file__,'portable evidence preparation helper snapshot','bundle preparation')
    generated=[]
    def emit(name,value,role):
        p=payload/name;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        rec=dict(path=DEST+'/'+name,prepared_file=str(p),sha256=sha(p),bytes=p.stat().st_size,kind='derived_evidence_index',role=role)
        proposed.append(rec);generated.append(rec);return rec
    emit('Exact scoped change witnesses.json',{'schema':'portable-scoped-change-witness-index-v1','derived_not_acceptance':True,'release_change_sets':change_sets},'exact declared changes and minimal physical record witnesses')
    emit('Canonical publication outputs.json',{'schema':'historical-publication-output-index-v1','canonical_outputs_are_not_evidence_copies':True,'records':canonical},'actual canonical publication epoch outputs, separate from copied proof')
    emit('Evidence map.json',{'schema':'portable-immutable-evidence-map-v1','original_bytes_unchanged':True,'new_acceptance_created':False,'proposed_repository_destination':DEST,
                             'copied_immutable_objects':[{k:v for k,v in x.items() if k!='private_path'} for x in copied.values()],'existing_identical_repository_evidence':list(reused.values()),'original_reference_mapping':references,
                             'external_policy':'Original TIFFs and large shared JSON preimages are hash-bound and intentionally not copied. Native crops, original stage change lists, and minimal source-bound owner witnesses are preserved. Historical original absolute paths inside copied receipts remain untouched.'},'immutable original-to-portable evidence mapping')
    readme=payload/'README.md'
    readme.write_text('# A1 source correction evidence — 2026-10-16\n\nThis is a compact evidence snapshot for A1122 identity, A1344 identities, the A1251-02 shared auxiliary binding recovery, and A1231/A1232 BA portions. It creates no new acceptance and publishes no transcription changes.\n\nOriginal stages, independent acceptances, publication receipts and helper snapshots are preserved byte for byte in content-addressed objects. `Evidence map.json` maps historical paths and hashes to these copies or already-existing identical repository evidence. Absolute paths inside immutable original receipts are retained.\n\n`Exact scoped change witnesses.json` is a derived index of the original exact TXT/JSON changes, with compact physical-record witnesses instead of giant shared-reference preimages. Native TIFF crops are retained; original TIFFs remain externally bound by their original hashes.\n\n`Canonical publication outputs.json` separately lists actual canonical outputs at each publication epoch. A copied receipt or evidence object is not a canonical transcription. Shared files may have later accepted successors; that distinction is recorded without rewriting historical receipts. The A1251 recovery explicitly reused existing authority and made no new visual acceptance or source-text correction.\n\nAll original reviewed column arrays and original historical receipts remain unchanged. Corrected BA tokens retain the following genuine BB token. No content, provenance or repository inventory manifest is modified by preparing this bundle.\n',encoding='utf-8')
    proposed.append(dict(path=DEST+'/README.md',prepared_file=str(readme),sha256=sha(readme),bytes=readme.stat().st_size,kind='derived_explanation',role='reader guide and evidence/canonical distinction'))
    emit('Bundle inventory.json',{'schema':'portable-A1-evidence-bundle-inventory-v1','self_excluded':True,'prepared_only':True,'no_new_acceptance_or_source_publication':True,
                                  'builder':bind(__file__),'publication_receipts':[bind(folder/'Publication/Publication receipt.json') for _,folder in config],
                                  'files':[{k:v for k,v in x.items() if k!='prepared_file'} for x in proposed]},'portable hash inventory of every other bundle file')
    for path,expected in inputs.items():assert sha(path)==expected,'Input epoch changed during private bundle preparation '+str(path)
    for rec in proposed:
        assert sha(rec['prepared_file'])==rec['sha256']
        target=(REPO/rec['path']).resolve();assert target.is_relative_to(REPO/DEST) and not target.exists(),'Proposed evidence target already exists'
    assert len({r['path'] for r in proposed})==len(proposed)
    manifest={'schema':'private-portable-A1-evidence-publication-proposal-v1','created_utc':datetime.now(timezone.utc).isoformat(),'repository':str(REPO),'proposed_destination':DEST,
              'prepared_only':True,'repository_writes':0,'content_provenance_inventory_writes':0,'new_acceptance_created':False,
              'builder':bind(__file__),'release_receipts':[bind(folder/'Publication/Publication receipt.json') for _,folder in config],
              'files':proposed,'file_count':len(proposed),'total_proposed_bytes':sum(r['bytes'] for r in proposed),'immutable_objects_copied':len(copied),'identical_existing_objects_reused':len(reused),
              'original_input_bindings':[dict(path=str(p),sha256=h) for p,h in sorted(inputs.items(),key=lambda x:str(x[0]))],
              'publication_not_performed':True,'scope':'Only the exact listed new proof files are proposed; all existing canonical source/data/metadata files remain untouched.'}
    mp=out/'Proposed repository files.json';mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'prepared':True,'manifest':bind(mp),'files':len(proposed),'bytes':manifest['total_proposed_bytes'],'reused':len(reused),'repository_writes':0},indent=2))
if __name__=='__main__':main()

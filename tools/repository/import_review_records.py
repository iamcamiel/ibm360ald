"""Preserve review/provenance records and reusable historical tool sources.

Reads the coordinator's reviewed-export snapshot; never changes working files.
Run with --write to publish. Diagram content JSON/CSV is a separate import.
"""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import ast
import hashlib
import json


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def immutable_chain_binding(link, workspace):
    """Resolve legacy relative receipt links against their declared workspace.

    Coordinator audit links predate absolute-path normalization. Their tmp/...
    paths are workspace-relative, regardless of the importer's launch directory.
    No alternate-path search or hash exception is allowed.
    """
    workspace=Path(workspace).resolve()
    declared=Path(link['file'])
    assert declared.is_absolute() or not declared.drive, 'Drive-relative receipt path is ambiguous'
    source=(declared if declared.is_absolute() else workspace/declared).resolve()
    assert source.is_relative_to(workspace), source
    raw=source.read_bytes()
    assert digest(raw)==link['sha256'], source
    return source,raw


def current_review_supersedes_historical_target(workspace, page_name, target):
    """Check that a later, reviewed export accounts for a changed live quartet file."""
    workspace=Path(workspace).resolve();target=Path(target).resolve()
    plan=read_json(workspace/'tmp/ald-text/ald/repository-export/export plan.json')
    assert plan['conflicts']==[]
    entries=[x for x in plan['exported'] if x['page']==page_name]
    assert len(entries)==1,page_name
    entry=entries[0]
    audit=read_json(workspace/entry['review_record'])
    records=[x for x in audit['pages'] if x['page']==page_name and x.get('eligible')]
    assert len(records)==1,page_name
    current=records[0]['current_quartet']
    assert any(Path(value['path']).resolve()==target and value['sha256']==digest(target.read_bytes())
               for value in current.values()),target
    assert Path(entry['transcription_source']).resolve()==Path(current['txt']['path']).resolve()
    assert entry['text_sha256']==current['txt']['sha256']
    repo_text=Path(entry['destination'])
    assert repo_text.is_file() and digest(repo_text.read_bytes())==entry['text_sha256']
    return True


def companion(text):
    key = text.name.split(' ', 1)[0]
    for path in [text.with_suffix('.json'),
                 text.with_name(text.stem+' verification.json'),
                 text.with_name(key+' verification.json'),
                 text.with_name(key+' review.json')]:
        if path.is_file():
            return path
    return None


def automatic_function_recovery_keepers(workspace):
    """Keep exact accepted inference history separate from native observations."""
    base=workspace/'tmp/ald-text/ald/card-type-database/function-unreadable-resolution-v1'
    stage=base/'expanded-applications/2c3919e8676d5858-accepted-review-v2'
    receipt_path=stage/'Approved unreadable function canonical publication receipt.json'
    if not receipt_path.is_file():return []
    def checked(b):
        p=Path(b.get('path',b.get('file','')))
        assert p.is_file() and digest(p.read_bytes())==b['sha256'],str(p)
        return p
    assert digest(receipt_path.read_bytes())=='c57ebebdb8a70a39162363d826bd9ed2ba4f6e9d6d10956c81722f6917078974'
    receipt=read_json(receipt_path);assert receipt['passed'] is True and not receipt.get('failures')
    manifest=checked(receipt['manifest']);peer=checked(receipt['independent_audit'])
    assert digest(manifest.read_bytes())=='cbd5f512cedea4b09134ea97cfbb2d931f7a4afd4eb29f0f9ec57915106b4dab'
    assert digest(peer.read_bytes())=='3717f829206a121367ed9af860ebe9e50a86caecba568ad92d61091134907039'
    acceptance=read_json(peer);assert acceptance['passed'] is True and not acceptance.get('failures') and acceptance['visual_review_pending'] is False
    assert checked(acceptance['manifest'])==checked(acceptance['application_manifest'])==manifest
    assert len(receipt['pages'])==61 and len(acceptance['approved_candidate_ids'])==112 and not acceptance['held_candidate_ids']
    assert receipt['derived_values_eligible_as_future_native_witnesses'] is False
    keeper=Path('notes/Card types/Automatic function recoveries/V10 expanded unique fit')
    files=[]
    for folder,label in [(stage,'Application'),(base/'independent-review','Independent review'),(base/'expanded-shape-takeover-v1/v10-accepted-readonly','Frozen V10 candidates')]:
        for source in sorted(folder.rglob('*')):
            if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
                files.append((source,keeper/label/source.relative_to(folder)))
    for name in ['Classifier extraction verification.json','Expanded V9 script inspection.json','Automatic recovery integration preparation plan.json']:
        source=base/'expanded-shape-takeover-v1'/name
        if source.is_file():files.append((source,keeper/'Derivation proof'/source.name))
    authority=workspace/'tmp/ald-text/ald/card-type-database/function-review-batch-8'
    for name in ['Direct human batch8 answers.json','Direct human automatic unreadable label recovery authorization.json']:
        files.append((authority/name,keeper/'Authority'/name))
    reviews=workspace/'tmp/ald-text/ald/repository-export/independent-human-function-integration-review'
    for name in ['Automatic function recovery preparation checks.json','Automatic function recovery integration guard review.json']:
        source=reviews/name
        if source.is_file():files.append((source,keeper/'Integration checks'/name))
    for source in [base/'expanded-shape-takeover-v1/derive_expanded_candidates.py',base/'prepare_approved_expanded_amendments.py',base/'publish_approved_expanded_amendments.py',workspace/'tmp/ald-text/ald/repository-export/bind_automatic_function_recoveries.py']:
        files.append((source,Path('tools/references/automatic-function-recovery')/source.name))
    return files


def H_rule_function_keepers(workspace):
    """Preserve the compact accepted64-field proof without per-page receipt copies."""
    base=workspace/'tmp/ald-text/ald/card-type-database/function-H-review-v1'
    receipt_path=base/'application-unified64-v3/Unified H rule canonical publication receipt.json'
    if not receipt_path.is_file():return []
    def checked(b):
        p=Path(b.get('path',b.get('file','')))
        assert p.is_file() and digest(p.read_bytes())==b['sha256'],str(p)
        return p
    assert digest(receipt_path.read_bytes())=='d4ac76fd0b3abb6018c89bfa3841660a30f97cc553247e5a8448fc6036b3497f'
    receipt=read_json(receipt_path);assert receipt['passed'] is True and not receipt['failures']
    manifest_path=checked(receipt['manifest']);peer_path=checked(receipt['independent_audit'])
    assert digest(manifest_path.read_bytes())=='a66c6e3145609d4ae0c5ff3996e40fdb8a593dbb100b1e369943ff86fcd14e1f'
    assert digest(peer_path.read_bytes())=='3ec19ece8c388cf9d0f949f00b45f9c48e42c22dae161157ba5596c17f160fbd'
    peer=read_json(peer_path);app=read_json(manifest_path)
    assert peer['passed'] is True and not peer['failures'] and peer['visual_review_pending'] is False
    assert checked(peer['manifest'])==checked(peer['application_manifest'])==manifest_path
    assert len(receipt['pages'])==33 and len(peer['approved_candidate_ids'])==64 and not peer['held_candidate_ids']
    assert receipt['new_independent_native_witnesses_created'] is False
    keeper=Path('notes/Card types/H function rules/Unified 64 correction');files={}
    def add(source,destination):
        source=source.resolve();key=destination.as_posix()
        if key in files:assert digest(files[key][0].read_bytes())==digest(source.read_bytes())
        files[key]=(source,destination)
    for source in base.glob('*.json'):
        add(source,keeper/'Authority and review history'/source.name)
    for source in manifest_path.parent.glob('*.json'):
        add(source,keeper/'Application'/source.name)
    # Historical v2 JSON remains evidence, but its retired duplicate paths are
    # not live requirements. V3 points at retained equal-SHA prior originals.
    old=base/'application-unified64-v2/Private unified H rule application manifest.json'
    add(old,keeper/'Application history/v2 manifest.json')
    for source in sorted((base/'independent-inventory').rglob('*')):
        if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
            add(source,keeper/'Independent review'/source.relative_to(base/'independent-inventory'))
    for page in app['pages']:
        folder=page['page']+'-'+str(page['source_scan_id'])
        for kind,group in [('before','before_quartet'),('candidate','candidate_quartet')]:
            for b in page[group].values():
                source=checked(b);add(source,keeper/'Page quartets'/folder/kind/source.name)
        guard=checked(page['immutable_original_source_guard']);add(guard,keeper/'Page quartets'/folder/'before'/guard.name)
        prior=checked(page['prior_review_record'])
        existing_112_keeper=workspace/'ibm360ald/notes/Card types/Automatic function recoveries/V10 expanded unique fit/Automatic unreadable function recovery current audit.json'
        if prior.name=='Automatic unreadable function recovery current audit.json' and existing_112_keeper.is_file():
            # This exact full prior112 record already has a retained keeper.
            # Preserve its binding in the compact manifest, not another15MB copy.
            assert digest(existing_112_keeper.read_bytes())==page['prior_review_record']['sha256']
        else:
            add(prior,keeper/'Prior review records'/page['prior_review_record']['sha256']/prior.name)
    for sheet in app['contact_sheets']:
        source=checked(sheet['image']);add(source,keeper/'Contact sheets'/source.name)
    for b in app['snapshot_inputs']:
        source=checked(b);add(source,keeper/'Immutable input receipts'/source.name)
    regression=workspace/'tmp/ald-text/ald/repository-export/independent-human-function-integration-review/H function rule integration guard review.json'
    if regression.is_file():add(regression,keeper/'Integration checks'/regression.name)
    for source in [base/'review_unreadable_H_ambiguities.py',base/'build_unified_H_rule_inventory.py',base/'stage_unified_H_rule_application.py',base/'prepare_compact_v3.py',base/'publish_unified_H_rule_application.py',workspace/'tmp/ald-text/ald/repository-export/bind_H_rule_function_corrections.py']:
        add(source,Path('tools/references/H-function-rule-recovery')/source.name)
    return list(files.values())


def native_three_correction_keepers(workspace):
    """Retain the exact three-page native-source correction and independent gate."""
    base=workspace/'tmp/ald-text/ald/card-type-database/native-three-review'
    manifest_path=base/'unified-stage/Unified native three correction manifest.json'
    audit_path=base/'independent-review/Independent three native corrections acceptance.json'
    publication_path=base/'unified-stage/Unified native three publication receipt.json'
    binder_path=workspace/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Native three source corrections current audit.json'
    if not publication_path.is_file():return []
    frozen={
        manifest_path:'726a8926ab81dc7d1ea1f0fde9272b82198e47a1c94a5fc938273138e267bf5b',
        audit_path:'9ff7d60e334dd2cf04d1ee86fc080f111c28ee4ffe785683f8db1907890d9deb',
        publication_path:'da36314bd4e296b0c8ea6473afe93b6f9e51a7ccd6af9e074860f419393a962f',
    }
    for source,expected in frozen.items():
        assert source.is_file() and digest(source.read_bytes())==expected,str(source)
    manifest=read_json(manifest_path);audit=read_json(audit_path);publication=read_json(publication_path);binder=read_json(binder_path)
    assert audit['passed'] is True and audit['failures']==[] and binder['passed'] is True and binder['failures']==[]
    assert audit['manifest']['sha256']==publication['manifest']['sha256']==frozen[manifest_path]
    assert publication['independent_audit']['sha256']==frozen[audit_path]
    assert binder['manifest']['sha256']==frozen[manifest_path] and binder['publication']['sha256']==frozen[publication_path]
    assert binder['independent_audit']['sha256']==frozen[audit_path]
    assert publication['quartet_files']==12 and publication['repository_writes']==0 and publication['original_scan_writes']==0
    assert len(manifest['pages'])==3 and {p['page'] for p in manifest['pages']}=={'PX311','KU641','AP743'}
    assert len(binder['pages'])==3 and {p['page'] for p in binder['pages']}=={'PX311','KU641','AP743'}
    keeper=Path('notes/Card types/Native source corrections/Three page source review');files={}
    def add(source,destination):
        source=Path(source).resolve();assert source.is_file() and source.is_relative_to(workspace)
        key=destination.as_posix();raw=source.read_bytes()
        if key in files:assert digest(files[key][0].read_bytes())==digest(raw)
        files[key]=(source,destination)
    def checked(binding):
        source=Path(binding.get('path',binding.get('file','')))
        assert source.is_file() and digest(source.read_bytes())==binding['sha256'],str(source)
        return source
    def checked_published_target(binding,page_name):
        """Accept a historical publication target only through the current reviewed export."""
        source=Path(binding.get('path',binding.get('file','')))
        assert source.is_file(),str(source)
        current_hash=digest(source.read_bytes())
        if current_hash==binding['sha256']:return source
        plan=read_json(workspace/'tmp/ald-text/ald/repository-export/export plan.json')
        assert plan['conflicts']==[]
        exported=[x for x in plan['exported'] if x['page']==page_name]
        assert len(exported)==1,page_name
        entry=exported[0]
        current_audit=read_json(workspace/entry['review_record'])
        accepted=[x for x in current_audit['pages'] if x['page']==page_name and x.get('eligible')]
        assert len(accepted)==1,page_name
        assert any(Path(value['path']).resolve()==source.resolve() and value['sha256']==current_hash
                   for value in accepted[0]['current_quartet'].values()),str(source)
        assert Path(entry['transcription_source']).resolve()==Path(accepted[0]['current_quartet']['txt']['path']).resolve()
        assert entry['text_sha256']==accepted[0]['current_quartet']['txt']['sha256']
        return source
    for source in [manifest_path,audit_path,publication_path,binder_path]:add(source,keeper/'Core'/source.name)
    for source in [base/'unified_native_three.py',base/'independent-review/independent_three_review.py',base/'independent-review/make_preview_contact.py',workspace/'tmp/ald-text/ald/repository-export/bind_native_three_corrections.py']:
        add(source,Path('tools/references/native-three-source-corrections')/source.name)
    contact=base/'independent-review/Three page preview before-after contact.png'
    assert digest(contact.read_bytes())=='f65dd984de3dbc42f8d4009825d6aa91bf5df808ea7373ee8751ea9cc08e5753'
    add(contact,keeper/'Independent review'/contact.name)
    for page in manifest['pages']:
        name=page['page'];source=checked(page['evidence']);add(source,keeper/'Native evidence'/name/source.name)
        crop=next(x['native_three_crop'] for x in binder['pages'] if x['page']==name)
        crop_path=checked(crop);add(crop_path,keeper/'Native evidence'/name/crop_path.name)
        original=checked(page['source'])
        assert original.resolve().is_relative_to(Path('D:/Reference Materials/IBM 360/IBM_360_ALD').resolve())
        for group in ['before_quartet','candidate_quartet']:
            for binding in page[group].values():
                path=checked(binding);add(path,keeper/'Page quartets'/name/group/path.name)
        for binding in page['candidate_quartet'].values():
            target=next(x for x in publication['canonical_destinations'] if x['sha256']==binding['sha256'])
            assert checked_published_target(target,name).resolve().is_relative_to((workspace/'ALD_Visual_Transcriptions').resolve())
    v13=base/'v13-builder';release=v13/'Final native three finding release.json'
    if release.is_file():
        assert digest(release.read_bytes())=='31c97212e9e0ecc6423d14b633cd43e412acadb3c2abe5e05babc4b350c1c994'
        final=read_json(release)
        assert final['schema_version']=='card-db-native-three-release-v1'
        assert final['review_sha256']==digest((workspace/'ibm360ald/notes/Card types/Independent OH OK and triangle native review.json').read_bytes())
        for binding,expected in [('stage_manifest',frozen[manifest_path]),('independent_acceptance',frozen[audit_path]),('publication_receipt',frozen[publication_path])]:
            assert final[binding]['sha256']==expected
            checked(final[binding])
        assert len(final['releases'])==3 and {r['page'] for r in final['releases']}=={'PX311','KU641','AP743'}
        for item in final['releases']:
            page=next(p for p in manifest['pages'] if p['page']==item['page'])
            assert item['scan_id']==str(page['scan_id']) and item['original_TIFF_sha256']==page['source']['sha256']
            assert item['accepted_text_sha256']==page['candidate_quartet']['txt']['sha256']
            assert item['accepted_model_sha256']==page['candidate_quartet']['json']['sha256']
        builder=v13/'build_card_type_database.py'
        invocation=v13/'Private V13 build invocation.json'
        assert digest(builder.read_bytes())=='bc73037e31effa9931b976d301da4b891bce41092212a854d2a744d740a4ccca'
        assert digest(invocation.read_bytes())=='6e413cca76c861a149c390a963290ffacaad7c4080aa47e3fdb8b30ddb71fe41'
        for source in [release,builder,invocation]:
            add(source,keeper/'V13 release'/source.name)
    return list(files.values())


def eleven_function_correction_keepers(workspace):
    """Preserve eleven current native/human function corrections and their gate."""
    base=workspace/'tmp/ald-text/ald/card-type-database/v13-next-review'
    manifest_path=base/'eleven-page-private-stage/Eleven native and human function correction manifest.json'
    native_path=base/'V13 seven source-bound function correction candidates.json'
    human_path=base/'V13 four direct-human function corrections and DT001 comparison.json'
    audit_path=base/'Independent eleven native and human function corrections acceptance.json'
    publication_path=base/'eleven-page-private-stage/Eleven canonical publication receipt.json'
    binder_path=workspace/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Eleven function corrections current audit.json'
    if not publication_path.is_file():return []
    frozen={
        manifest_path:'9bdeb975f0a457bdbd98e37d6bb162bba754f12074dc820d09b858be8f6c028f',
        native_path:'7f12522b6e83348a529646ff01c5f683a633b59c2f53af35e008c46c0ba42d52',
        human_path:'f7ac879f867147fd9553587e8ca99db293c5a3f3eb8ea00813cd1f2a4f41014f',
        audit_path:'aa8d69862b3e6a86179a2df96b7971d99faeb43b56ae3c2137607cb70628f81a',
        publication_path:'dfc760aca5398e959faec09fbb74127d1ba8310bd51200b2e65e7fc278d22ec7',
    }
    for source,expected in frozen.items():
        assert source.is_file() and digest(source.read_bytes())==expected,str(source)
    manifest=read_json(manifest_path);audit=read_json(audit_path)
    publication=read_json(publication_path);binder=read_json(binder_path)
    assert audit['passed'] is True and audit['failures']==[] and audit['visual_review_pending'] is False
    assert binder['passed'] is True and binder['failures']==[]
    assert audit['manifest']['sha256']==publication['manifest']['sha256']==frozen[manifest_path]
    assert publication['independent_audit']['sha256']==frozen[audit_path]
    assert binder['manifest']['sha256']==frozen[manifest_path]
    assert binder['publication']['sha256']==frozen[publication_path]
    assert binder['independent_audit']['sha256']==frozen[audit_path]
    assert publication['canonical_quartet_files']==44 and len(publication['canonical_destinations'])==44
    assert publication['repository_writes']==publication['original_scan_writes']==0
    native_pages={'AP737','AP181','RQ683','KU601','RQ781','MC371','AP441'}
    human_pages={'AP531','XM181','AS201','AP313'}
    assert {p['page'] for p in manifest['pages']}==native_pages|human_pages
    assert len(binder['pages'])==11 and {p['page'] for p in binder['pages']}==native_pages|human_pages
    assert manifest['direct_human_authority']==read_json(human_path)['direct_human_authority']
    assert manifest['confirmed_no_change']['page']=='DT001' and manifest['confirmed_no_change']['current_function']=='A'
    keeper=Path('notes/Card types/Function source corrections/Eleven page source review');files={}
    def add(source,destination):
        source=Path(source).resolve();assert source.is_file() and source.is_relative_to(workspace)
        key=destination.as_posix();raw=source.read_bytes()
        if key in files:assert digest(files[key][0].read_bytes())==digest(raw)
        files[key]=(source,destination)
    def checked(binding):
        source=Path(binding.get('path',binding.get('file',''))).resolve()
        assert source.is_file() and digest(source.read_bytes())==binding['sha256'],str(source)
        return source
    semantics_path=base/'0143 human semantics provenance.json'
    semantics=read_json(semantics_path)
    assert semantics['schema']=='card-type-0143-human-semantics-authority-v1'
    assert semantics['confirmed_page']=='DT001' and semantics['literal_page_correction'] is None
    assert semantics['raw_statement'].startswith('in 0143, the C1-C2-C3 parts form a group')
    assert semantics['selected_answer']=='Yes, DT001 switches them (recommended)'
    for source in [manifest_path,native_path,human_path,audit_path,publication_path,binder_path,semantics_path]:
        add(source,keeper/'Core'/source.name)
    for source in [base/'stage_seven.py',base/'stage_eleven.py',base/'publish_eleven.py',
                   base/'audit_eleven_independent.py',
                   workspace/'tmp/ald-text/ald/repository-export/bind_eleven_function_corrections.py']:
        add(source,Path('tools/references/eleven-function-source-corrections')/source.name)
    audited={x['page']:x for x in audit['reviewed_pages']}
    published={str(Path(x['path']).resolve()):x['sha256'] for x in publication['canonical_destinations']}
    assert len(published)==44 and set(audited)==native_pages|human_pages
    for page in manifest['pages']:
        name=page['page'];review=audited[name]
        assert page['authority_kind']==review['authority_kind']==('native' if name in native_pages else 'direct-human')
        original=checked(page['source'])
        assert original.is_relative_to(Path('D:/Reference Materials/IBM 360/IBM_360_ALD').resolve())
        for key in ('source_crop','broad_context_crop'):
            source=checked(page[key]);add(source,keeper/'Native evidence'/name/source.name)
        for group in ('before_quartet','candidate_quartet'):
            for binding in page[group].values():
                source=checked(binding);add(source,keeper/'Page quartets'/name/group/source.name)
        for kind,binding in page['candidate_quartet'].items():
            target=Path(page['canonical_quartet'][kind]['path']).resolve()
            assert target.is_relative_to((workspace/'ALD_Visual_Transcriptions').resolve())
            assert target.is_file() and binding['sha256']==published[str(target)]
            if digest(target.read_bytes())!=binding['sha256']:
                assert current_review_supersedes_historical_target(workspace,name,target)
        record=next(x for x in binder['pages'] if x['page']==name)
        assert record['current_quartet']['txt']['sha256']==page['candidate_quartet']['txt']['sha256']
        assert record['source']['sha256']==page['source']['sha256']
        assert checked(record['eleven_authority_record']) in {native_path.resolve(),human_path.resolve()}
    human=read_json(human_path)
    comparison=human['matching_OR_example_for_DT001']
    assert comparison['page']=='DT011' and comparison['printed_function']=='OR'
    dt011_crop=checked(comparison['source_crop'])
    add(dt011_crop,keeper/'Native evidence'/'DT011 comparison'/dt011_crop.name)
    v14_release=base/'v14-builder/Final eleven function finding release.json'
    if v14_release.is_file():
        assert digest(v14_release.read_bytes())=='bfa9c1a5a289335eabcc04f02441841f92e18dfa0f8178b3eeb5c13b0798b26e'
        release=read_json(v14_release)
        assert release['schema_version']=='card-db-eleven-function-release-v1'
        assert release['stage_manifest']['sha256']==frozen[manifest_path]
        assert release['independent_acceptance']['sha256']==frozen[audit_path]
        assert release['publication_receipt']['sha256']==frozen[publication_path]
        assert release['native_candidate_record']['sha256']==frozen[native_path]
        assert release['human_candidate_record']['sha256']==frozen[human_path]
        assert release['direct_human_authority']==human['direct_human_authority']
        assert len(release['releases'])==11 and {x['page'] for x in release['releases']}==native_pages|human_pages
        add(v14_release,keeper/'V14 release'/v14_release.name)
    return list(files.values())


def sparse_shape_review_keepers(workspace):
    """Retain the 17 native-crop comparisons and the AP041 K4/K6/K8 repair.

    The original TIFFs remain in the reference archive.  Their hashes are
    recorded in these receipts; only derivative crops and review records are
    imported into the repository.
    """
    base=workspace/'tmp/ald-text/ald/card-type-database/sparse-shape-review'
    verdict_path=base/'Human review of 17 sparse shape cases.json'
    gallery_path=base/'All 17 source-crop evidence.json'
    ap=base/'ap041-k8'
    candidate_path=ap/'AP041 three-way portion correction candidate.json'
    manifest_path=ap/'three-way-private-stage/AP041 three-way private stage manifest.json'
    acceptance_path=ap/'AP041 independent three-way private-stage acceptance.json'
    publication_path=ap/'AP041 three-way canonical publication receipt.json'
    frozen={
        verdict_path:'de8bd7edd9ee7762d036db7203f61dad8a263bfeeda233c6d7ffe4131f08be81',
        gallery_path:'dd49d41d43b5d2ba702e40118e35aa6b1587f665193cadc991796fa59744c013',
        candidate_path:'af84b44ae4450f8a8acb7e96d7da5af9dbe2e081ea10dc0def6e5e24631568b6',
        manifest_path:'6f75210fd899c41065e1334d32687d1d8aa6770fa843ec69278ba6a1865ae60a',
        acceptance_path:'6c1fe94f5fc8230e3e1a73520a5725911a8d033835419b3bd6f03afb0278d977',
        publication_path:'80afb1f7abc05f17dd2ea04367b37cc9b71ba4f47a6e5b8768bc40482a8df629',
    }
    for source,expected in frozen.items():
        assert source.is_file() and digest(source.read_bytes())==expected,str(source)
    verdict, gallery=read_json(verdict_path),read_json(gallery_path)
    candidate,manifest=read_json(candidate_path),read_json(manifest_path)
    acceptance,publication=read_json(acceptance_path),read_json(publication_path)
    assert verdict['schema_version']=='ald-sparse-function-shape-human-review-v1'
    assert len(gallery['cases'])==17 and [x['index'] for x in gallery['cases']]==list(range(1,18))
    assert verdict['interpretation']['review_after_corrected_crop']==[]
    assert set(verdict['interpretation']['accepted_as_legitimate_different_shape'])=={
        '0141C3','0141D3','0143D1','0412G1','0486C1','0488B2','0490K1',
        '0497A2','0500A2','0505B3','0505B4','0512G1','3161B1','3311C4',
        '3365A1','8005B5'}
    assert verdict['interpretation']['native_recheck_card_portion']==['4633K4']
    assert candidate['source_tiff']['sha256']==manifest['original_tiff']['sha256']==publication['source_tiff']['sha256']
    original=Path(publication['source_tiff']['path']).resolve()
    assert original.suffix.lower() in {'.tif','.tiff'} and original.is_file()
    assert digest(original.read_bytes())==publication['source_tiff']['sha256']
    assert acceptance['status']=='PASS' and not acceptance['failures']
    assert publication['stage']['sha256']==frozen[manifest_path]
    assert publication['independent_acceptance']['sha256']==frozen[acceptance_path]
    assert manifest['source_candidate']['sha256']==frozen[candidate_path]
    assert {x['artifact'] for x in publication['canonical_destinations']}=={'txt','json','notes','preview'}
    for item in publication['canonical_destinations']:
        current=Path(item['path']).resolve()
        assert current.is_relative_to(workspace) and digest(current.read_bytes())==item['sha256']
    assert len(manifest['text_edits'])==3 and len(manifest['model_edits'])==9
    assert {x['node'] for x in manifest['text_edits']}=={'AS','AU','BB'}
    keeper=Path('notes/Card types/Sparse shape review/Seventeen native comparisons')
    ap_keeper=Path('notes/Card types/Sparse shape review/AP041 three-way portion correction')
    files={}
    def add(source,destination):
        source=Path(source).resolve()
        assert source.is_file() and source.is_relative_to(workspace),str(source)
        assert source.suffix.lower() not in {'.tif','.tiff'},str(source)
        key=destination.as_posix()
        if key in files:assert digest(files[key][0].read_bytes())==digest(source.read_bytes()),key
        files[key]=(source,destination)
    def checked(binding):
        source=Path(binding['path']).resolve()
        assert source.is_file() and digest(source.read_bytes())==binding['sha256'],str(source)
        return source
    for source in [verdict_path,gallery_path,base/'All 17 function-shape source crops.html']:
        add(source,keeper/source.name)
    for case in gallery['cases']:
        assert len(case['flagged'])==2 and case['normal_has_same_shape'] is False
        for item in [*case['flagged'],case['normal']]:
            crop=(base/item['crop']).resolve()
            assert crop.is_relative_to(base.resolve()) and digest(crop.read_bytes())==item['crop_sha256']
            assert crop.suffix.lower()=='.png' and Path(item['source_TIFF']).suffix.lower() in {'.tif','.tiff'}
            add(crop,keeper/item['crop'])
    # Retain the comparison sheets shown to the user, as well as their exact
    # crop bindings.  The corrected KD101 crop is required by gallery case 8.
    for folder in ['agent1','agent2','agent3']:
        for source in sorted((base/folder).glob('*')):
            if source.is_file() and source.suffix.lower() in {'.png','.json'}:
                add(source,keeper/folder/source.name)
    for source in [candidate_path,manifest_path,acceptance_path,publication_path]:
        add(source,ap_keeper/'Core'/source.name)
    for group in ['before_quartet','candidate_quartet']:
        for binding in manifest[group].values():
            source=checked(binding)
            add(source,ap_keeper/'Page quartets'/group/source.name)
    for binding in manifest['native_crops']+[manifest['comparison']]:
        source=checked(binding)
        add(source,ap_keeper/'Native evidence'/source.name)
    for source in sorted(ap.glob('*.png')):
        add(source,ap_keeper/'Native evidence'/source.name)
    for source in [ap/'stage_ap041_threeway.py',ap/'audit_ap041_threeway.py',
                   ap/'publish_ap041_threeway.py',ap/'build_current_ap041_audit.py',
                   base/'make_gallery.py']:
        add(source,Path('tools/references/sparse-shape-and-ap041-review')/source.name)
    audit_path=workspace/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP041 three-way portion current audit.json'
    if audit_path.is_file():
        audit=read_json(audit_path)
        assert audit['passed'] is True and not audit['failures'] and len(audit['pages'])==1
        page=audit['pages'][0]
        assert page['page']=='AP041' and page['eligible'] is True
        assert page['source']['sha256']==publication['source_tiff']['sha256']
        assert page['owner_receipt']['sha256']==frozen[publication_path]
        for kind,binding in manifest['candidate_quartet'].items():
            assert page['current_quartet'][kind]['sha256']==binding['sha256']
        add(audit_path,ap_keeper/'Core'/audit_path.name)
    return list(files.values())


def retired_kt_fact_keepers(workspace):
    """Archive three historical companions without restoring active content."""
    path = workspace/'tmp/ald-text/ald/card-type-database/function-review-batch-7/application/Retired KT source facts/Retired KT source facts receipt.json'
    if not path.is_file():
        return []
    assert digest(path.read_bytes()) == '7b7132908bfd1ffca3164cc3541892f38783332056d04ad4d107699339c9cc32'
    receipt = read_json(path)
    assert receipt['passed'] is True and not receipt['failures']
    assert {r['page'] for r in receipt['retirements']} == {'KT701','KT721','KT731'}
    assert len(receipt['retirements']) == 3

    def checked(binding):
        file = Path(binding['path'])
        assert file.is_file() and digest(file.read_bytes()) == binding['sha256'], str(file)
        return file

    before_path = checked(receipt['before_content_manifest'])
    after_path = checked(receipt['after_content_manifest'])
    before = {r['path']:r for r in read_json(before_path)['files']}
    after = {r['path']:r for r in read_json(after_path)['files']}
    expected = {'json/KT Indicator Rollers and Scan Bus/'+page+' source facts.json'
                for page in ['KT701','KT721','KT731']}
    assert set(before)-set(after) == expected and not set(after)-set(before)
    assert receipt['counts'] == {'before_content_records':len(before),
                                'after_content_records':len(after),
                                'removed_companions':3,'added_records':0,
                                'primary_page_models_retained':3}
    recovery = read_json(checked(receipt['KT_recovery_acceptance']))
    assert recovery['passed'] is True and recovery['published'] is True
    recovery = {r['page']:r for r in recovery['acceptance_receipts'] if r['passed'] is True}
    publication = read_json(checked(receipt['batch7_publication']))
    assert publication['passed'] is True and not publication.get('failures')
    publication = {r['page']:r for r in publication['pages']}
    files = [path,before_path,after_path]
    for item in receipt['retirements']:
        page = item['page']; old = recovery[page]; accepted = publication[page]
        relative = item['retired_relative_path']
        assert relative == 'json/KT Indicator Rollers and Scan Bus/'+page+' source facts.json'
        assert item['original_content_record'] == before[relative]
        facts = checked(item['preserved_facts'])
        assert facts.resolve().is_relative_to((workspace/'tmp/ald-text/ald/repository-export/held accepted snapshots/content-20261014T202147005112Z').resolve())
        assert facts.name == page+' source facts.json'
        assert item['preserved_facts']['sha256'] == before[relative]['sha256'] == old['accepted_hashes']['facts_sha256']
        assert item['old_accepted_text_sha256'] == old['accepted_hashes']['text_sha256'] == accepted['before_quartet']['txt']['sha256']
        assert item['batch7_current_text_at_retirement'] == accepted['current_quartet']['txt']
        assert item['batch7_current_text_at_retirement']['sha256'] != item['old_accepted_text_sha256']
        assert item['frozen_batch7_accepted_text'] == accepted['independently_reviewed_candidate_quartet']['txt']
        checked(item['frozen_batch7_accepted_text'])
        assert item['frozen_batch7_accepted_primary_model'] == accepted['independently_reviewed_candidate_quartet']['json']
        checked(item['frozen_batch7_accepted_primary_model'])
        primary = item['primary_page_model_present_at_retirement']
        relative_primary = Path(primary['path']).relative_to(workspace/'ibm360ald').as_posix()
        assert relative_primary in after and after[relative_primary]['role'] == 'Published page content model'
        assert primary['sha256'] == after[relative_primary]['sha256'] == item['frozen_batch7_accepted_primary_model']['sha256']
        assert item['original_TIFF'] == accepted['source']
        assert Path(item['original_TIFF']['path']).resolve() == Path(old['source_tiff']).resolve()
        assert item['original_TIFF']['sha256'] == old['source_sha256']
        checked(item['original_TIFF'])
        assert item['original_TIFF_unchanged'] is True and item['owner_source_facts_unchanged_at_retirement'] is True
        files.append(facts)
    assert len({f.name for f in files}) == 6
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path,
                        default=Path(__file__).resolve().parents[3])
    parser.add_argument('--reference', type=Path,
                        default=Path('D:/Reference Materials/IBM 360/IBM_360_ALD'))
    parser.add_argument('--repo', type=Path,
                        default=Path(__file__).resolve().parents[2])
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    repo, workspace = args.repo.resolve(), args.workspace.resolve()
    assert (repo/'.git').is_dir(), 'Choose the ALD repository'
    exports = workspace/'ALD_Visual_Transcriptions'
    audit = workspace/'tmp/ald-text/ald/repository-export'
    manifest_raw = (audit/'last export manifest.json').read_bytes()
    exported = json.loads(manifest_raw)
    assert not exported.get('export_in_progress'), 'Wait for the text export'
    folders = {path.name for path in args.reference.iterdir() if path.is_dir()}
    by_family = {name[:2]: name for name in folders}
    planned = {}

    def add(destination, raw, source, role):
        destination = destination.resolve()
        assert destination.is_relative_to(repo)
        relative = destination.relative_to(repo).as_posix()
        item = {'path': relative, 'sha256': digest(raw),
                'source': str(source), 'role': role, '_raw': raw}
        if relative in planned:
            assert planned[relative]['sha256'] == item['sha256'], relative
        planned[relative] = item

    def copy(source, destination, role):
        add(destination, source.read_bytes(), source, role)

    # Keep original identities/order and current approved grid/glyph policies.
    copy(args.reference/'ALD Scan Order.csv', repo/'notes/ALD Scan Order.csv',
         'Original scan order and current TIFF filename catalogue')
    shared = {
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/OR function human correction current audit.json':
            'Manual verification/OR function human correction current audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/CA211 human primary function correction current audit.json':
            'Card types/Function correction history/CA211 human primary function correction current audit.json',
        'tmp/ald-text/ald/card-type-database/Direct human CA211 AK function correction.json':
            'Card types/Direct human CA211 AK function correction.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/R TU human function correction current audit.json':
            'Card types/Function correction history/R TU human function correction current audit.json',
        'tmp/ald-text/ald/card-type-database/Direct human R TU function correction.json':
            'Card types/Direct human R TU function correction.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Returned function answers current audit.json':
            'Card types/Function review answers/Returned function answers current audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Function review batch 2 current audit.json':
            'Card types/Function review answers/Batch 2/Function review batch 2 current audit.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-2/Direct human answers 1-4.json':
            'Card types/Function review answers/Batch 2/Direct human answers 1-4.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-2/Direct human answers 5-10.json':
            'Card types/Function review answers/Batch 2/Direct human answers 5-10.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-2/Effective human answers 1-10.json':
            'Card types/Function review answers/Batch 2/Effective human answers 1-10.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-2/Second ten function review questions.json':
            'Card types/Function review answers/Batch 2/Second ten function review questions.json',
        'tmp/ald-text/ald/repository-export/independent-human-function-integration-review/Function batch 2 integration guard review.json':
            'Card types/Function review answers/Batch 2/Integration guard review.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Function review batch 3 current audit.json':
            'Card types/Function review answers/Batch3/Function review batch 3 current audit.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-3/Direct human batch3 answers.json':
            'Card types/Function review answers/Batch3/Direct human batch3 answers.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-3/Third ten function review questions.json':
            'Card types/Function review answers/Batch3/Third ten function review questions.json',
        'tmp/ald-text/ald/repository-export/independent-human-function-integration-review/Function batch 3 integration guard review.json':
            'Card types/Function review answers/Batch3/Integration guard review.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Function review batch 4 current audit.json':
            'Card types/Function review answers/Batch4/Function review batch 4 current audit.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-4/Direct human batch4 answers.json':
            'Card types/Function review answers/Batch4/Direct human batch4 answers.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-4/Fourth ten function review questions.json':
            'Card types/Function review answers/Batch4/Fourth ten function review questions.json',
        'tmp/ald-text/ald/repository-export/independent-human-function-integration-review/Function batch 4 integration guard review.json':
            'Card types/Function review answers/Batch4/Integration guard review.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Function review batch 5 current audit.json':
            'Card types/Function review answers/Batch5/Function review batch 5 current audit.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-5/Direct human batch5 answers.json':
            'Card types/Function review answers/Batch5/Direct human batch5 answers.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-5/Fifth ten function review questions.json':
            'Card types/Function review answers/Batch5/Fifth ten function review questions.json',
        'tmp/ald-text/ald/repository-export/independent-human-function-integration-review/Function batch 5 integration guard review.json':
            'Card types/Function review answers/Batch5/Integration guard review.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Function review batch 6 current audit.json':
            'Card types/Function review answers/Batch6/Function review batch 6 current audit.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-6/Direct human batch6 answers.json':
            'Card types/Function review answers/Batch6/Direct human batch6 answers.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-6/Sixth ten function review questions.json':
            'Card types/Function review answers/Batch6/Sixth ten function review questions.json',
        'tmp/ald-text/ald/repository-export/independent-human-function-integration-review/Function batch 6 integration guard review.json':
            'Card types/Function review answers/Batch6/Integration guard review.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Function review batch 7 current audit.json':
            'Card types/Function review answers/Batch7/Function review batch 7 current audit.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-7/Direct human batch7 answers.json':
            'Card types/Function review answers/Batch7/Direct human batch7 answers.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-7/Seventh ten function review questions.json':
            'Card types/Function review answers/Batch7/Seventh ten function review questions.json',
        'tmp/ald-text/ald/repository-export/independent-human-function-integration-review/Function batch 7 integration guard review.json':
            'Card types/Function review answers/Batch7/Integration guard review.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-7/application/Retired KT source facts/Retirement keeper guard review.json':
            'Card types/Function review answers/Batch7/Retired KT source facts/Retirement keeper guard review.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Function review batch 8 current audit.json':
            'Card types/Function review answers/Batch8/Function review batch 8 current audit.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-8/Direct human batch8 answers.json':
            'Card types/Function review answers/Batch8/Direct human batch8 answers.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-8/Direct human automatic unreadable label recovery authorization.json':
            'Card types/Function review answers/Batch8/Direct human automatic unreadable label recovery authorization.json',
        'tmp/ald-text/ald/card-type-database/function-review-batch-8/Eighth ten function review questions.json':
            'Card types/Function review answers/Batch8/Eighth ten function review questions.json',
        'tmp/ald-text/ald/repository-export/independent-human-function-integration-review/Function batch 8 integration guard review.json':
            'Card types/Function review answers/Batch8/Integration guard review.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Automatic unreadable function recovery current audit.json':
            'Card types/Automatic function recoveries/V10 expanded unique fit/Automatic unreadable function recovery current audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/H function port rule current audit.json':
            'Card types/H function rules/Unified 64 correction/H function port rule current audit.json',
        'tmp/ald-text/ald/card-type-database/function-review-answers-v1/Direct human function review answers.json':
            'Card types/Function review answers/Direct human function review answers.json',
        'tmp/ald-text/ald/card-type-database/function-review-answers-v1/Direct human correction to returned function answers.json':
            'Card types/Function review answers/Direct human correction to returned function answers.json',
        'tmp/ald-text/ald/card-type-database/function-review-answers-v1/Effective human function review answers.json':
            'Card types/Function review answers/Effective human function review answers.json',
        'tmp/ald-text/ald/card-type-database/function-review-answers-v1/Returned workbook/ALD function shape review v1.xlsx':
            'Card types/Function review answers/Returned workbook/ALD function shape review v1.xlsx',
        'outputs/01a12afd-f7e4-7a21-aa71-cbee821ab67d/ALD function shape review v1.xlsx':
            'Card types/Function review answers/Issued workbook/ALD function shape review v1.xlsx',
        'tmp/ald-text/ald/card-type-database/shape-review-workbook-v1/First ten rare function review questions current.json':
            'Card types/Function review answers/Issued questions snapshot.json',
        'tmp/ald-text/ald/repository-export/independent-human-function-integration-review/Returned function answer integration guard review.json':
            'Card types/Function review answers/Integration guard review.json',
        'tmp/ald-text/ald/repository-export/independent-human-function-integration-review/R TU integration guard review.json':
            'Card types/Function correction history/R TU integration guard review.json',
        'tmp/ald-text/ald/card-type-database/Direct human card-type observations.json':
            'Card types/Direct human card-type observations.json',
        'tmp/ald-text/ald/card-type-database/Direct human OR function correction.json':
            'Card types/Direct human OR function correction.json',
        'tmp/ald-text/ald/card-type-database/Direct human additional function corrections.json':
            'Card types/Direct human additional function corrections.json',
        'tmp/ald-text/ald/card-type-database/Direct human function whitespace and R TO corrections.json':
            'Card types/Direct human function whitespace and R TO corrections.json',
        'tmp/ald-text/ald/ap3/root/Combined human function batches final exact audit.json':
            'AP Parallel Adder/Human function correction history/Combined human function batches final exact audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json':
            'Manual verification/Recorded and recovered UTF8 application current audit.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet-v5/Workbook binding manifest v5.json':
            'Manual verification/Workbook binding manifest v5.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet-v5/Workbook independent audit v5.json':
            'Manual verification/Workbook independent audit v5.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet-v5/Post-v5 recorded answers.json':
            'Manual verification/Post-v5 recorded answers.json',
        'tmp/ald-text/ald/repository-export/independent-human-function-integration-review/Independent integration guard review.json':
            'Card types/Function correction history/Independent integration guard review.json',
        'outputs/01a12afd-f7e4-7a21-aa71-cbee821ab67d/ALD manual verification questions v5.xlsx':
            'Manual verification/ALD manual verification questions v5.xlsx',
        'tmp/ald-text/ald/Parallel until complete coordination broadcast.json':
            'Parallel until complete coordination broadcast.json',
        'tmp/ald-text/ald/repository-export/Coordinator source review holds.json':
            'Coordinator source review holds.json',
        'tmp/ald-text/ald/repository-export/Coordinator transcription scope exclusions.json':
            'Coordinator transcription scope exclusions.json',
        'tmp/ald-text/ald/repository-export/ED direct human scope exclusion verified.json':
            'ED ROS Diagrams, Drivers/ED direct human scope exclusion verified.json',
        'tmp/ald-text/ald/filename-corrections/ED000-01 DT to ED folder move audit.json':
            'ED ROS Diagrams, Drivers/ED000-01 DT to ED folder move audit.json',
        'tmp/ald-text/rt/root/AR KU handoff.json':
            'RT T Register/AR KU half-workload handoff.json',
        'tmp/ald-text/ald/repository-export/ZA corrected source review hold release.json':
            'ZA Programmed Grounds/ZA corrected source review hold release.json',
        'tmp/ald-text/ald/repository-export/XM905 corrected source review hold release.json':
            'XM Mixer/XM905 corrected source review hold release.json',
        'tmp/ald-text/ls/physical-copy-2026-10-13/Frozen physical copy publication receipts.json':
            'LS LS Bus/Frozen physical copy publication receipts.json',
        'tmp/ald-text/ls/physical-copy-2026-10-13/Before physical copy snapshot receipt.json':
            'LS LS Bus/Before physical copy snapshot receipt.json',
        'tmp/ald-text/ls/workbook-46e7d24ea74f/Before returned workbook snapshot receipt.json':
            'LS LS Bus/Before returned workbook snapshot receipt.json',
        'tmp/ald-text/ls/workbook-46e7d24ea74f/Frozen workbook publication receipts.json':
            'LS LS Bus/Historical returned workbook publication receipts.json',
        'tmp/ald-text/ls/source-derived-2026-10-13/Before source-derived recovery snapshot receipt.json':
            'LS LS Bus/Before source-derived recovery snapshot receipt.json',
        'tmp/ald-text/ls/source-derived-2026-10-13/Frozen source-derived publication receipts.json':
            'LS LS Bus/Frozen source-derived publication receipts.json',
        'tmp/ald-text/ald/manual-verification/received/2026-10-13-46e7d24ea74f/Answer receipt.json':
            'Manual verification/2026-10-13 returned workbook answer receipt.json',
        'tmp/ald-text/ald/manual-verification/received/2026-10-13-46e7d24ea74f/Returned question workbook.xlsx':
            'Manual verification/2026-10-13 returned question workbook.xlsx',
        'tmp/ald-text/ald/manual-verification/received/2026-10-14-5796f6dd2e40/Answer receipt.json':
            'Manual verification/2026-10-14 returned V4 answer receipt.json',
        'tmp/ald-text/ald/manual-verification/received/2026-10-14-5796f6dd2e40/Returned question workbook.xlsx':
            'Manual verification/2026-10-14 returned V4 question workbook.xlsx',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook binding manifest v2.json':
            'Manual verification/Workbook binding manifest v2.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Question recovery decisions v2.json':
            'Manual verification/Question recovery decisions v2.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook validation v2.json':
            'Manual verification/Workbook validation v2.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook decision partition validation v2.json':
            'Manual verification/Workbook decision partition validation v2.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook delivery receipt v2.json':
            'Manual verification/Workbook delivery receipt v2.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook binding manifest v3.json':
            'Manual verification/Workbook binding manifest v3.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook binding manifest v4.json':
            'Manual verification/Workbook binding manifest v4.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v4/WA140 WA150 corrected reference recoveries.json':
            'A1 Socket Listing/WA140 WA150 corrected reference recoveries.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v4/Pending inventory after V4.json':
            'Manual verification/Pending inventory after V4.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v4/C2A endpoint prefix direct human correction.json':
            'Manual verification/C2A endpoint prefix direct human correction.json',
        'tmp/ald-text/ald/manual-verification/socket-function-recovery-v1/Direct human socket function instructions.json':
            'Manual verification/Socket function reference checks/Direct human socket function instructions.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/C2A human correction current audit.json':
            'Manual verification/C2A human correction current audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP001 human socket correction current audit.json':
            'AP Parallel Adder/AP001 human socket correction current audit.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook reconciliation audit v4.json':
            'Manual verification/Workbook reconciliation audit v4.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook independent audit v4.json':
            'Manual verification/Workbook independent audit v4.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook validation v4.json':
            'Manual verification/Workbook validation v4.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook delivery receipt v4.json':
            'Manual verification/Workbook delivery receipt v4.json',
        'outputs/01a12afd-f7e4-7a21-aa71-cbee821ab67d/ALD manual verification questions v4.xlsx':
            'Manual verification/ALD manual verification questions v4.xlsx',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Question recovery decisions v3.json':
            'Manual verification/Question recovery decisions v3.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook validation v3.json':
            'Manual verification/Workbook validation v3.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook decision partition validation v3.json':
            'Manual verification/Workbook decision partition validation v3.json',
        'tmp/ald-text/ald/manual-verification/spreadsheet/Workbook delivery receipt v3.json':
            'Manual verification/Workbook delivery receipt v3.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Human J6 reference reading receipt.json':
            'Manual verification/Human J6 reference reading receipt.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Contextual independent cross-review v3.json':
            'Manual verification/Contextual independent cross-review v3.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/A1 contextual recovery candidates v3.json':
            'Manual verification/A1 contextual recovery candidates v3.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Non-A1 contextual recovery candidates v3.json':
            'Manual verification/Non-A1 contextual recovery candidates v3.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Source-derived acceptance adapter audit.json':
            'Manual verification/Source-derived acceptance adapter audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Supplementary source-derived acceptance adapter audit.json':
            'Manual verification/Supplementary source-derived acceptance adapter audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Next source-derived acceptance adapter audit.json':
            'Manual verification/Next source-derived acceptance adapter audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/WA accepted current audit.json':
            'Manual verification/WA accepted current audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/V3 current publication audit.json':
            'Manual verification/V3 current publication audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/KT V2 unchanged current rebind audit.json':
            'Manual verification/KT V2 unchanged current rebind audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/WA final current audit.json':
            'Manual verification/WA final current audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/WA301 current authority audit.json':
            'Manual verification/WA301 current authority audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/WA glyph and footer current audit.json':
            'Manual verification/WA glyph and footer current audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/FX RT V3 current publication audit.json':
            'Manual verification/FX RT V3 current publication audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/FX RT V3 unchanged Next RT binding audit.json':
            'RT T Register/FX RT V3 unchanged Next RT binding audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Human WA recurring glyph reading receipt.json':
            'WA Cable Routing/Human WA recurring glyph reading receipt.json',
        'tmp/ald-text/recovery-v3/Source derived independent reviews.json':
            'Manual verification/FX RT V3 source-derived independent reviews.json',
        'tmp/ald-text/recovery-v3/Published FX RT V3 family receipt.json':
            'Manual verification/Published FX RT V3 family receipt.json',
        'tmp/ald-text/recovery-v3/Completed V3 repository mirror receipt.json':
            'Manual verification/Completed FX RT V3 repository mirror receipt.json',
        'tmp/ald-text/recovery-v3/rt/Deferred RT381 source discrepancies.json':
            'RT T Register/Deferred RT381 source discrepancies.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/RT381 pending next-inventory reopenings.json':
            'RT T Register/RT381 pending next-inventory reopenings.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/WA verified human glyph closure.json':
            'WA Cable Routing/WA verified human glyph closure.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted XM015 questions.json':
            'XM Mixer/Pending newly accepted XM015 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP751 AP762 AP763 questions.json':
            'AP Parallel Adder/Pending newly accepted AP751 AP762 AP763 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted XM012 AP752 AP611 questions.json':
            'Manual verification/Pending newly accepted XM012 AP752 AP611 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted XM013 questions.json':
            'XM Mixer/Pending newly accepted XM013 questions.json',
        'tmp/ald-text/xm/XM final coverage audit.json':
            'XM Mixer/XM final coverage audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/XM completed repository mirror receipt.json':
            'XM Mixer/XM completed repository mirror receipt.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted XM017 questions.json':
            'XM Mixer/Pending newly accepted XM017 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP761 AP772 AP771 questions.json':
            'AP Parallel Adder/Pending newly accepted AP761 AP772 AP771 questions.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP accepted parity caption corrections audit.json':
            'AP Parallel Adder/AP accepted parity caption corrections audit.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP621 AP631 AP633 AP634 AP773 AP781 AP782 questions.json':
            'AP Parallel Adder/Pending newly accepted AP621 AP631 AP633 AP634 AP773 AP781 AP782 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted RX001 RX002 RX051 RX081 questions.json':
            'RX ROS Address Register/Pending newly accepted RX001 RX002 RX051 RX081 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP782 AP781 AQ4 reference recovery.json':
            'AP Parallel Adder/AP782 AP781 AQ4 reference recovery.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX101 coordinator mirror audit.json':
            'RX ROS Address Register/RX101 coordinator mirror audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX003 coordinator mirror audit.json':
            'RX ROS Address Register/RX003 coordinator mirror audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX091 coordinator source review audit.json':
            'RX ROS Address Register/RX091 superseded caption source review audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX091 comparative native diamond audit.json':
            'RX ROS Address Register/RX091 comparative native diamond audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX091 coordinator mirror audit.json':
            'RX ROS Address Register/RX091 coordinator mirror audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX completed repository mirror receipt.json':
            'RX ROS Address Register/RX completed repository mirror receipt.json',
        'tmp/ald-text/ald/repository-export/RX091 native diamond source review hold release.json':
            'RX ROS Address Register/RX091 native diamond source review hold release.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP783 AP791 AP792 questions.json':
            'AP Parallel Adder/Pending newly accepted AP783 AP791 AP792 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP791 independent readable peer recoveries.json':
            'AP Parallel Adder/AP791 independent readable peer recoveries.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP637 AP639 questions.json':
            'AP Parallel Adder/Pending newly accepted AP637 AP639 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP637 AP639 independent readable source recoveries.json':
            'AP Parallel Adder/AP637 AP639 independent readable source recoveries.json',
        'tmp/ald-text/ald/grid-verification/AP635 direct human approval verified.json':
            'AP Parallel Adder/AP635 direct human approval verified.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP635 coordinator mirror readiness audit.json':
            'AP Parallel Adder/AP635 coordinator mirror readiness audit.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP001 AP291 corrected current coordinator audit.json':
            'AP Parallel Adder/AP001 AP291 corrected current coordinator audit.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP793 questions.json':
            'AP Parallel Adder/Pending newly accepted AP793 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP793 tentative physical-card cross-reference support.json':
            'AP Parallel Adder/AP793 tentative physical-card cross-reference support.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP793 AP801 AP811 AP813 coordinator mirror audit.json':
            'AP Parallel Adder/AP793 AP801 AP811 AP813 coordinator mirror audit.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP801 AP811 AP813 questions.json':
            'AP Parallel Adder/Pending newly accepted AP801 AP811 AP813 questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP801 AP811 AP813 independent recovery evidence.json':
            'AP Parallel Adder/AP801 AP811 AP813 independent recovery evidence.json',
        'tmp/ald-text/ald/repository-export/AP001 AP291 native literal source review findings.json':
            'AP Parallel Adder/AP001 AP291 native literal source review findings.json',
        'tmp/ald-text/ald/repository-export/AP001 native literal source review hold release.json':
            'AP Parallel Adder/AP001 native literal source review hold release.json',
        'tmp/ald-text/ald/repository-export/AP291 native literal source review hold release.json':
            'AP Parallel Adder/AP291 native literal source review hold release.json',
        'tmp/ald-text/ald/repository-export/AP001 literal correction release frozen audit.json':
            'AP Parallel Adder/AP001 literal correction release frozen audit.json',
        'tmp/ald-text/ald/repository-export/AP291 literal correction release frozen audit.json':
            'AP Parallel Adder/AP291 literal correction release frozen audit.json',
        'tmp/ald-text/ald/manual-verification/ap3-ap793-source-filename-correction/AP793 executed source filename correction receipt.json':
            'AP Parallel Adder/AP795 to AP793 source filename correction receipt.json',
        'tmp/ald-text/ald/manual-verification/ap3-ap793-source-filename-correction/AP793 prepared source filename correction.json':
            'AP Parallel Adder/AP795 to AP793 prepared source filename correction.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/AP795 AP793 independent source identity proof.json':
            'AP Parallel Adder/AP795 AP793 independent source identity proof.json',
        'tmp/ald-text/ald/wa_root/glyph_corner_correction/SE-DE glyph resolution receipt.json':
            'WA Cable Routing/SE-DE glyph resolution receipt.json',
        'tmp/ald-text/ald/wa_root/WA160_footer_recheck/final_public_review_WA160.json':
            'WA Cable Routing/WA160 corrected current native and preview review.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending inventory after V3.json':
            'Manual verification/Pending inventory after V3.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/WA conditional pending questions.json':
            'WA Cable Routing/WA conditional pending questions.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/WA pending review notes.json':
            'WA Cable Routing/WA pending review notes.json',
        'tmp/ald-text/recovery-v2/rt/Published RT recovery receipt.json':
            'RT T Register/Published workbook recovery receipt.json',
        'tmp/ald-text/ald/manual-verification/source-derived-v3/Handoff preparation audit.json':
            'Manual verification/Workbook v3 handoff preparation audit.json',
        'tmp/ald-text/ald/manual-verification/pending-inventory-after-v3/Pending newly accepted AP and XM questions.json':
            'Manual verification/Pending newly accepted AP and XM questions.json',
        'tmp/ald-text/ku/source-derived-review/Root reacceptance receipt.json':
            'KU MCW, Scan, Logout/Source-derived root reacceptance receipt.json',
        'tmp/ald-text/ald/repository-export/KU owner mirror reconciliation/Reconciliation receipt.json':
            'Manual verification/KU owner mirror reconciliation receipt.json',
        'tmp/ald-text/ald/repository-export/KU owner mirror reconciliation/KU review record reconciliation receipt.json':
            'KU MCW, Scan, Logout/KU review record reconciliation receipt.json',
        'tmp/ald-text/kt/recoveries-v2/Frozen recovery acceptance receipts.json':
            'KT Indicator Rollers and Scan Bus/Frozen workbook recovery acceptance receipts.json',
        'tmp/ald-text/kt/recoveries-v3/Frozen V3 recovery acceptance receipts.json':
            'KT Indicator Rollers and Scan Bus/Frozen workbook V3 recovery acceptance receipts.json',
        'tmp/ald-text/kt/recoveries-v2/KT201 independent native U correction proof.json':
            'KT Indicator Rollers and Scan Bus/KT201 independent native U correction proof.json',
        'tmp/ald-text/kt/root/KT verified printed references.json':
            'KT Indicator Rollers and Scan Bus/KT verified printed references.json',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT source-derived recoveries.txt':
            'KT Indicator Rollers and Scan Bus/KT source-derived recoveries.txt',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT source-derived recoveries.json':
            'KT Indicator Rollers and Scan Bus/KT source-derived recoveries.json',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT source-derived V3 recoveries.txt':
            'KT Indicator Rollers and Scan Bus/KT source-derived V3 recoveries.txt',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT source-derived V3 recoveries.json':
            'KT Indicator Rollers and Scan Bus/KT source-derived V3 recoveries.json',
        'tmp/ald-text/ald/manual-verification/source-derived-v2/Owner notification receipts.json':
            'Manual verification/Source-derived workbook v2 owner notification receipts.json',
        'tmp/ald-text/ald/manual-verification/source-derived-v2/Summary ledger.json':
            'Manual verification/Source-derived workbook v2 summary ledger.json',
        'tmp/ald-text/ald/manual-verification/source-derived-v2/Already applied source-derived records.json':
            'Manual verification/Previously illegible source-derived LS records.json',
        'tmp/ald-text/ald/manual-verification/cross-reference-review-2026-10-13/ap source filename correction executed audit.json':
            'AP Parallel Adder/AP745 title filename correction audit.json',
        'tmp/ald-text/rx/identity/RX912 to RX921 filename correction audit.json':
            'RX ROS Address Register/RX912 to RX921 filename correction audit.json',
        'tmp/ald-text/ald/ap3/AP2 to AP3 takeover handoff.json':
            'AP Parallel Adder/AP2 to AP3 takeover handoff.json',
        'tmp/ald-text/ald/ap3/AP2 stopped and AP3 sole ownership receipt.json':
            'AP Parallel Adder/AP2 stopped and AP3 sole ownership receipt.json',
        'tmp/ald-text/ald/manual-verification/ap3-source-filename-corrections/AP3 executed source filename corrections receipt.json':
            'AP Parallel Adder/AP751 AP752 source filename corrections receipt.json',
        'tmp/ald-text/ald/manual-verification/ap3-ap762-source-filename-correction/AP762 executed source filename correction receipt.json':
            'AP Parallel Adder/AP762 source filename correction receipt.json',
        'tmp/ald-text/ald/manual-verification/ap3-ap771-source-filename-correction/AP771 executed source filename correction receipt.json':
            'AP Parallel Adder/AP771 source filename correction receipt.json',
        'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/WA160 focused native footer audit.json':
            'WA Cable Routing/WA160 focused native footer audit.json',
        'ALD_Visual_Transcriptions/ALD Diagrams/ZA column layout decisions.json':
            'ZA Programmed Grounds/ZA approved column layout decisions.json',
        'tmp/ald-text/ald/grid-verification/Printer grid specification.json':
            'Printer grid specification.json',
        'tmp/ald-text/ald/grid-verification/RT381 direct human approvals verified.json':
            'RT T Register/RT381 direct human approvals verified.json',
        'tmp/ald-text/ald/grid-verification/AP511 direct human approval verified.json':
            'AP Parallel Adder/AP511 direct human approval verified.json',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT unreadable print.txt':
            'KT Indicator Rollers and Scan Bus/KT unreadable print.txt',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT cross-page findings.txt':
            'KT Indicator Rollers and Scan Bus/KT cross-page findings.txt',
        'ALD_Visual_Transcriptions/KT Indicator Rollers and Scan Bus/KT package verification.json':
            'KT Indicator Rollers and Scan Bus/KT package verification.json',
        'ALD_Visual_Transcriptions/Allowed characters.json':
            'CAS allowed characters.json',
        'ALD_Visual_Transcriptions/ALD Diagrams/Allowed characters.json':
            'ALD allowed characters.json',
        'ALD_Visual_Transcriptions/CAS symbol reference.json':
            'CAS symbol reference.json',
        'ALD_Visual_Transcriptions/Character approval status.json':
            'Character approval status.json',
        'ALD_Visual_Transcriptions/ALD Diagrams/Confirmed filename corrections.json':
            'Confirmed filename corrections.json',
        'tmp/ald-text/ald/filename-corrections/A6611 catalogue correction audit.json':
            'A6 INDICES/A6611 catalogue correction audit.json',
        'tmp/ald-text/ald/filename-corrections/RB671 RB805 filename correction audit.json':
            'RB B Register/RB671 RB805 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/RR181 filename correction audit.json':
            'RR R Register/RR181 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/AP651 AP661 RT755 RT813 RT815 filename correction audit.json':
            'AP651 AP661 RT755 RT813 RT815 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/KT594 to KT591 filename correction audit.json':
            'KT Indicator Rollers and Scan Bus/KT594 to KT591 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/RT751 filename correction audit.json':
            'RT T Register/RT751 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/RB807 filename correction audit.json':
            'RB B Register/RB807 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/LS856 to LS861 filename correction audit.json':
            'LS LS Bus/LS856 to LS861 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/XM903 to XM905 filename correction audit.json':
            'XM Mixer/XM903 to XM905 filename correction audit.json',
        'tmp/ald-text/ald/filename-corrections/XL031 printed title filename correction audit.json':
            'XL LM Register/XL031 printed title filename correction audit.json',
        'tmp/ald-text/ald/repository-export/LS023 prior export ownership recovery.json':
            'LS LS Bus/LS023 previous export ownership recovery.json',
        'tmp/ald-text/ald/repository-export/LS023 prior reviewed snapshot.json':
            'LS LS Bus/LS023 previous reviewed snapshot.json',
        'tmp/ald-text/ald/repository-export/Interrupted verified note ownership recovery receipt.json':
            'Manual verification/Interrupted note reconciliation receipt.json',
        'tmp/ald-text/ald/repository-export/Supplemental note descriptor recovery receipt.json':
            'Manual verification/Interrupted supplemental note tracking recovery receipt.json',
        'tmp/ald-text/ald/repository-export/Interrupted supplemental note history/AP physical copy check.txt':
            'AP Parallel Adder/summary history/AP physical copy check before interrupted export.txt',
        'tmp/ald-text/ald/repository-export/Interrupted supplemental note history/FX transcription notes.txt':
            'FX External Bus/summary history/FX transcription notes before interrupted export.txt',
        'tmp/ald-text/ald/repository-export/Interrupted supplemental note history/RT transcription notes.txt':
            'RT T Register/summary history/RT transcription notes before interrupted export.txt',
    }
    for relative, name in shared.items():
        path = workspace/relative
        if path.is_file():
            copy(path, repo/'notes'/name, 'Provenance or approved convention')
    for path in retired_kt_fact_keepers(workspace):
        copy(path, repo/'notes/Card types/Function review answers/Batch7/Retired KT source facts'/path.name,
             'Historical KT companion retired after its bound TXT changed; primary page model retained')
    for source,destination in automatic_function_recovery_keepers(workspace):
        copy(source,repo/destination,'Independently accepted source-derived masked-function recovery; retained as inference provenance, not a native witness')
    for source,destination in H_rule_function_keepers(workspace):
        copy(source,repo/destination,'Exact human H/count rules and three A exceptions, independently accepted source-specific64-function correction and compact provenance; not new native witness evidence')
    for source,destination in native_three_correction_keepers(workspace):
        copy(source,repo/destination,'Native TIFF-supported PX311, KU641, and AP743 corrections, independent acceptance, published quartets, and release provenance')
    for source,destination in eleven_function_correction_keepers(workspace):
        copy(source,repo/destination,'Eleven independently accepted native and direct-human function corrections, source crops, published quartets, and provenance')
    for source,destination in sparse_shape_review_keepers(workspace):
        copy(source,repo/destination,'Seventeen native sparse-shape comparisons, direct human review, and independently accepted AP041 three-way portion correction')
    manual_reports = [
        ('SY22-2798-2 ALD notation review.md',
         'SY22-2798-2_LogicBlocks_AutomatedLogicDiagrams_SLT,SLD,ASLT,MST_TO_Oct71.pdf',
         '1d030693fea73b1161ef597473558ca8c8c75d4e5c19c4049a99f917c98a439e',
         'e3214d20d24a698beb464766df8acabcee20c5f4ea298c3e4b95407a455f84f7'),
        ('SLT-specific manual source review.md',
         'Z22-2798-1_Solid_Logic_Technology_Component_Circuits.pdf',
         '7cb58126da276c7b372be1f45abddf9ffa8f3e256ce3a63ee4daebc9807ab75c',
         '74ac2dc8b465c27deba94e4674674a927c44a9220b647f86c2bbabc8eb915623'),
        ('Older SLT card catalog source review.md',
         'SLT_Card_Schematics_Jan67.pdf',
         '71e191106a383b8a32e8885b8d59bb1798b1e920c4f34831223db3a55db11850',
         '32551f42c44f1a9f28cf6fd1d880412d84952712cbfb72b837586e84c54a8f5d'),
    ]
    for report_name,pdf_name,report_sha,pdf_sha in manual_reports:
        report=workspace/'tmp/ald-text/ald/manual-guide-review'/report_name
        pdf=Path('D:/Reference Materials/IBM 360')/pdf_name
        assert report.is_file() and pdf.is_file()
        assert digest(report.read_bytes())==report_sha and digest(pdf.read_bytes())==pdf_sha
        copy(report,repo/'notes/Card types/Reference manuals'/report_name,
             'Source-bound ALD and SLT manual interpretation; original PDF retained in reference materials')
    caption_records = workspace/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP accepted parity caption immutable records'
    human_prefix_records = workspace/'tmp/ald-text/ald/manual-verification/human-c2a-prefix-correction'
    if human_prefix_records.is_dir():
        for path in sorted(human_prefix_records.rglob('*')):
            if path.is_file() and path.suffix.lower() in {'.json', '.txt', '.png'}:
                copy(path, repo/'notes/Manual verification/C2A human prefix correction'/path.relative_to(human_prefix_records),
                     'Human-confirmed endpoint correction, independent review, or preserved predecessor')
    wa_reference_proofs = workspace/'tmp/ald-text/ald/manual-verification/pending-inventory-after-v4'
    if wa_reference_proofs.is_dir():
        for path in sorted(wa_reference_proofs.glob('*.png')):
            copy(path, repo/'notes/A1 Socket Listing/WA140 WA150 reciprocal native proofs'/path.name,
                 'Native WA reciprocal endpoint and A1 physical socket evidence')
    literal_records = workspace/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP001 AP291 corrected current immutable records'
    if literal_records.is_dir():
        for path in sorted(literal_records.iterdir()):
            if path.is_file() and path.suffix.lower() in {'.json', '.txt', '.png'}:
                copy(path, repo/'notes/AP Parallel Adder/native literal correction history'/path.name,
                     'Frozen predecessor, exact correction, independent acceptance, or native source evidence')
    if caption_records.is_dir():
        for path in sorted(caption_records.glob('*.json')):
            copy(path, repo/'notes/AP Parallel Adder/accepted parity caption immutable records'/path.name,
                 'Frozen native caption acceptance and preserved predecessor receipt')
    rx091_history = workspace/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/RX091 superseded caption history'
    if rx091_history.is_dir():
        for path in sorted(rx091_history.iterdir()):
            if path.is_file():
                copy(path, repo/'notes/RX ROS Address Register/superseded caption history'/path.name,
                     'Superseded RX091 caption before exact native diamond correction')
    # Keep the immutable JSON receipt chains needed to interpret named audits
    # after the private working directories are no longer available.
    audit_root = workspace/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3'
    chain_map = {}
    selected_audit_pages = {(x['review_record'].replace('\\', '/'), x['page'])
                            for x in exported['exported']}
    selected_audit_pages.update((x['review_record'].replace('\\','/'),
                                Path(x['transcription_source']).name.split(' ',1)[0])
                               for x in exported['exported'])
    for relative in shared:
        audit_path = workspace/relative
        if audit_path.parent != audit_root or not audit_path.is_file():
            continue
        record = read_json(audit_path)
        if record.get('passed') is not True:
            continue
        for page in record.get('pages', []):
            # Single-page readiness reports may have a differently shaped
            # pages field; they are preserved records, not acceptance chains.
            if not isinstance(page, dict):
                continue
            if page.get('eligible') is not True:
                continue
            if (audit_path.relative_to(workspace).as_posix(), page.get('page')) not in selected_audit_pages:
                continue
            for key in ['root_acceptance', 'owner_receipt', 'legacy_ledger',
                        'independent_audit', 'independent_acceptance']:
                link = page.get(key)
                if not isinstance(link, dict) or not link.get('file'):
                    continue
                source,raw = immutable_chain_binding(link,workspace)
                destination = repo/'notes/Manual verification/immutable receipts'/(link['sha256'][:16]+' '+source.name)
                add(destination, raw, source, 'Immutable named independent acceptance chain')
                chain_map[str(source)] = {'repository_path': destination.relative_to(repo).as_posix(),
                                          'sha256': link['sha256']}
    add(repo/'notes/Manual verification/Immutable receipt locations.json',
        (json.dumps(chain_map, ensure_ascii=False, indent=2)+'\n').encode('utf-8'),
        audit_root, 'Portable mapping of original acceptance receipt paths')
    ku_reconciliation = workspace/'tmp/ald-text/ald/repository-export/KU owner mirror reconciliation/KU review record reconciliation receipt.json'
    if ku_reconciliation.is_file():
        for record in read_json(ku_reconciliation)['updates']:
            prior = Path(record['preserved_path'])
            assert prior.resolve().is_relative_to(workspace)
            assert digest(prior.read_bytes()) == record['current_owner_record_sha256']
            copy(prior, repo/'notes/KU MCW, Scan, Logout/metadata history'/prior.name,
                 'Preserved independently accepted owner review metadata before coordinator regeneration')
    # Question recoveries are proposals with independently readable evidence;
    # preserving them never edits or confers acceptance on a diagram quartet.
    for version in ['v2', 'v3']:
        recovery_root = workspace/'tmp/ald-text/ald/manual-verification'/('source-derived-'+version)
        for path in sorted(recovery_root.glob('*/Reviewed recoveries.json')):
            assert path.parent.name in folders, path
            copy(path, repo/'notes'/path.parent.name/('Source-derived workbook '+version+' recoveries.json'),
                 'Reviewed source-derived question recovery evidence; owner publication separate')
    add(repo/'notes/Reviewed export provenance.json', manifest_raw,
        audit/'last export manifest.json', 'Original reviewed export snapshot')

    # One lightweight review record per exported text, separate from its model.
    diagram_fields = {'nodes', 'nets', 'paths', 'wire_paths', 'wires',
                      'junctions', 'labels', 'text', 'cells', 'annotations',
                      'wire_shapes', 'connections', 'footer', 'records',
                      'sections', 'cards', 'connectors', 'geometry'}
    receipts = defaultdict(list)
    for entry in exported['exported']:
        text = Path(entry['transcription_source'])
        raw = (repo/Path(entry['destination']).relative_to(repo)).read_bytes()
        assert digest(raw) == entry['text_sha256'], str(text)
        folder = Path(entry['source_relative']).parent
        metadata = companion(text)
        document = read_json(metadata) if metadata else {}
        review = {key: value for key, value in document.items()
                  if key not in diagram_fields} if isinstance(document, dict) else {}
        record = {
            'text_file': Path(entry['destination']).relative_to(repo).as_posix(),
            'text_sha256': entry['text_sha256'],
            'reference_scan': entry['source_relative'],
            'original_scan_name': entry['original_scan_name'],
            'original_scan_timestamp': entry['scan_timestamp'],
            'source_scan_id': entry['source_scan_id'],
            'acceptance_record': entry['review_record'],
            'working_metadata_source': str(metadata) if metadata else None,
            'working_metadata_sha256': digest(metadata.read_bytes()) if metadata else None,
            'review_metadata_snapshot': review,
            'diagram_content_fields_kept_in_working_model':
                sorted(set(document) & diagram_fields) if isinstance(document, dict) else [],
            'scope': 'Review/provenance snapshot for the exported text; '
                     'diagram content models are imported separately.',
        }
        add(repo/'notes'/folder/(text.stem+' review record.json'),
            (json.dumps(record, ensure_ascii=False, indent=2)+'\n').encode('utf-8'),
            metadata or text, 'Page review and provenance')
        proof = workspace/entry['review_record']
        if proof.is_file():
            receipts[(str(proof), str(folder))].append(text.name.split(' ', 1)[0])

        # Keep exact human replies and before evidence for current accepted
        # physical-copy corrections. These page records are distinct from
        # diagram models and would otherwise be skipped by collection rules.
        page = text.name.split(' ', 1)[0]
        physical_candidates = [exports/'ALD Diagrams'/(page+' physical copy review.json'),
                               text.with_name(text.stem+' physical copy review.json')]
        for physical in dict.fromkeys(physical_candidates):
          if physical.is_file():
            confirmation = read_json(physical)
            confirmed_hash = confirmation.get('text_sha256') or confirmation.get('final_artifacts', {}).get('.txt', {}).get('sha256')
            if confirmed_hash == entry['text_sha256']:
                copy(physical, repo/'notes'/folder/physical.name,
                     'Current source-bound human physical-copy correction proof')
                before_artifacts = confirmation.get('before_source_and_quartet', {}).get('artifacts', []) + confirmation.get('before_artifacts', [])
                for item in before_artifacts:
                    prior = Path(item.get('snapshot_path', item.get('snapshot', '')))
                    assert prior.resolve().is_relative_to(workspace)
                    assert digest(prior.read_bytes()) == item['sha256'], str(prior)
                    copy(prior, repo/'notes'/folder/'physical-copy-history'/page/prior.name,
                         'Preserved before physical-copy artifact')
                readings = confirmation.get('original_readings_file', {})
                if readings.get('snapshot_path'):
                    prior = Path(readings['snapshot_path'])
                    assert prior.resolve().is_relative_to(workspace)
                    assert digest(prior.read_bytes()) == readings['sha256'], str(prior)
                    copy(prior, repo/'notes'/folder/'physical-copy-history'/'Original human readings.json',
                         'Preserved exact original human readings')

    for (source, folder), pages in receipts.items():
        path = Path(source)
        if len(pages) == 1:
            name = pages[0]+' acceptance receipt.json'
        else:
            name = path.name
            if not name.startswith(pages[0][:2]):
                name = pages[0][:2]+' '+name
        # Named coordinator audits are already preserved once in shared
        # provenance. Keep distinct same-named owner ledgers as separate
        # records rather than allowing either one to overwrite the other.
        shared_name = shared.get(path.relative_to(workspace).as_posix())
        if shared_name:
            destination = repo/'notes'/shared_name
        else:
            destination = repo/'notes'/folder/name
            relative = destination.relative_to(repo).as_posix()
            if relative in planned and planned[relative]['sha256'] != digest(path.read_bytes()):
                destination = repo/'notes'/folder/'acceptance receipts'/path.relative_to(workspace/'tmp/ald-text')
        copy(path, destination, 'Original acceptance receipt or ledger')

    # Preserve the exact human answer and predecessor evidence for AP001's
    # independently accepted one-cell board/socket correction.
    human_ap = workspace/'tmp/ald-text/ald/ap3/root/human-confirmed/AP001-22f1584ecc'
    human_ap_receipt = human_ap/'Human correction publication receipt.json'
    if human_ap_receipt.is_file():
        accepted = read_json(human_ap_receipt)
        ap_entry = next(e for e in exported['exported'] if e['page']=='AP001')
        assert accepted['passed'] and accepted['human_answer']=='B-E1K6'
        # Subsequent independently reviewed human fields may supersede the
        # current AP001 quartet. Preserve this exact first correction as
        # history, bound to its immutable private candidate bytes.
        human_manifest = read_json(human_ap/'Private correction manifest.json')
        next_human_receipt = read_json(workspace/'tmp/ald-text/ald/ap3/root/human-batch-v4-5796f6dd2e40/Bounded human batch publication receipt.json')
        assert next_human_receipt['passed'] is True
        for kind, artifact in accepted['current_quartet'].items():
            # Publication adds review annotations to the JSON and notes;
            # the next batch preserves those exact published predecessor
            # bytes rather than the earlier unannotated private candidates.
            preserved = next_human_receipt['pages']['AP001']['before_quartet'][kind]
            assert preserved['sha256']==artifact['sha256']
            assert digest(Path(preserved['path']).read_bytes())==artifact['sha256']
            source = Path(preserved['path'])
            copy(source,repo/'notes/AP Parallel Adder/Human confirmed AP001 socket/Published prior socket quartet'/source.name,
                 'Exact first human-confirmed socket publication before later human corrections')
        assert digest(Path(accepted['source']['path']).read_bytes())==accepted['source']['sha256']
        for source in sorted(human_ap.rglob('*')):
            if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
                copy(source, repo/'notes/AP Parallel Adder/Human confirmed AP001 socket'/source.relative_to(human_ap),
                     'Exact human socket answer, independent acceptance and preserved before/candidate artifacts')

    # Keep current field applications with their preserved full-source
    # predecessors and independently checked deltas. Never copy private
    # candidates until the matching guarded publication receipt exists.
    application_root = workspace/'tmp/ald-text/ald/manual-verification/resolved-text-application-v1/non-ap'
    for subdir, receipt_name in [('', 'First ten non-AP publication receipt.json'),
                                ('older-firm','Remaining firm canonical publication receipt.json')]:
        batch_root = application_root/subdir
        receipt_path = batch_root/receipt_name
        if not receipt_path.is_file():
            continue
        batch = read_json(receipt_path)
        assert batch['passed'] is True
        for item in batch['pages']:
            folder = Path(item['source']['path']).parent.name
            page_root = batch_root/item['page']
            for source in sorted(page_root.rglob('*')):
                if source.is_file() and source.suffix.lower() in {'.json','.txt','.png','.csv'}:
                    copy(source,repo/'notes'/folder/'Confirmed field correction history'/item['page']/source.relative_to(page_root),
                         'Preserved source acceptance, exact field proof and independently reviewed candidate history')
        for source in sorted(batch_root.glob('*')):
            if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
                copy(source,repo/'notes/Manual verification/Applied confirmed fields'/subdir/source.name,
                     'Guarded field application batch receipt or independent delta review')
    # Function-only human corrections reuse prior full-page native acceptance
    # and keep their exact independently inspected deltas as separate history.
    for subdir,receipt_name,label in [
        ('non-ap-OR-correction','Non-AP OR function canonical publication receipt.json','OR'),
        ('non-ap-supplemental-function-correction','Non-AP supplemental function canonical publication receipt.json','Supplemental'),
        ('CA211-human-function-correction','CA211 human function canonical publication receipt.json','CA211 exact primary function'),
        ('R-TU-human-function-correction','R TU human function canonical publication receipt.json','R TU exact function spelling'),
        ('function-review-answers-v1/application','Returned function answers canonical publication receipt.json','Returned function review answers'),
        ('function-review-batch-2/application-ten','Batch2 ten function answers canonical publication receipt.json','Function review batch 2 answers'),
        ('function-review-batch-3/application','Batch3 function answers canonical publication receipt.json','Function review batch 3 answers'),
        ('function-review-batch-4/application','Batch4 function answers canonical publication receipt.json','Function review batch 4 answers'),
        ('function-review-batch-5/application','Batch5 function answers canonical publication receipt.json','Function review batch 5 answers'),
        ('function-review-batch-6/application-current-snapshot','Batch6 function answers canonical publication receipt.json','Function review batch 6 answers'),
        ('function-review-batch-7/application','Batch7 function answers canonical publication receipt.json','Function review batch 7 answers'),
        ('function-review-batch-8/application','Batch8 function answers canonical publication receipt.json','Function review batch 8 answers')]:
        function_batch = workspace/'tmp/ald-text/ald/card-type-database'/subdir
        function_receipt = function_batch/receipt_name
        if not function_receipt.is_file():
            continue
        batch = read_json(function_receipt)
        assert batch['passed'] is True
        for page in batch['pages']:
            folder = Path(page['source']['path']).parent.name
            page_root = Path(page['independently_reviewed_candidate_quartet']['txt']['path']).parent.parent
            file_page = Path(page['current_quartet']['txt']['path']).name.split(' ',1)[0]
            assert page_root.resolve().is_relative_to(function_batch.resolve())
            assert page_root.is_dir()
            for source in sorted(page_root.rglob('*')):
                if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
                    copy(source,repo/'notes'/folder/'Human function correction history'/label/file_page/source.relative_to(page_root),
                         'Exact human function correction, independently reviewed delta and preserved source acceptance')
        for source in sorted(function_batch.glob('*')):
            if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
                keeper=(repo/'notes/Card types/Function review answers/Application' if subdir=='function-review-answers-v1/application'
                        else repo/'notes/Card types/Function review answers/Batch 2/Application' if subdir=='function-review-batch-2/application-ten'
                        else repo/'notes/Card types/Function review answers/Batch3/Application' if subdir=='function-review-batch-3/application'
                        else repo/'notes/Card types/Function review answers/Batch4/Application' if subdir=='function-review-batch-4/application'
                        else repo/'notes/Card types/Function review answers/Batch5/Application' if subdir=='function-review-batch-5/application'
                        else repo/'notes/Card types/Function review answers/Batch6/Application' if subdir=='function-review-batch-6/application-current-snapshot'
                        else repo/'notes/Card types/Function review answers/Batch7/Application' if subdir=='function-review-batch-7/application'
                        else repo/'notes/Card types/Function review answers/Batch8/Application' if subdir=='function-review-batch-8/application'
                        else repo/'notes/Card types/Function correction history'/label)
                copy(source,keeper/source.name,
                     'Human function correction batch publication or independent acceptance')
    batch8_review = workspace/'tmp/ald-text/ald/card-type-database/function-review-batch-8/independent-review'
    if batch8_review.is_dir():
        for source in sorted(batch8_review.iterdir()):
            if source.is_file() and source.suffix.lower() in {'.json','.png'}:
                copy(source,repo/'notes/Card types/Function review answers/Batch8/Independent review'/source.name,
                     'Root independent batch8 acceptance, bound before/after panels, or preserved first diagnostic')
    for suffix in ['human-batch-v4-5796f6dd2e40','socket-high-followup-v1','definite-header-followup-v2','card-type-human-followup-v1','or-function-human-followup-v1','additional-function-human-followup-v1']:
        batch_root = workspace/'tmp/ald-text/ald/ap3/root'/suffix
        receipt_name = ('Bounded human batch publication receipt.json' if suffix.startswith('human')
                        else 'Definite header publication receipt.json' if suffix.startswith('definite')
                        else 'Card type human AP211 publication receipt.json' if suffix.startswith('card-type')
                        else 'OR function human publication receipt.json' if suffix.startswith('or-function')
                        else 'Additional function human publication receipt.json' if suffix.startswith('additional-function')
                        else 'Socket High followup publication receipt.json')
        receipt_path = batch_root/receipt_name
        if not receipt_path.exists() and suffix.startswith(('card-type','or-function','additional-function')):
            continue
        receipt = read_json(receipt_path)
        assert receipt['passed'] is True
        for page, item in receipt['pages'].items():
            for kind, artifact in item['before_quartet'].items():
                source = Path(artifact['path'])
                assert digest(source.read_bytes())==artifact['sha256']
                copy(source,repo/'notes/AP Parallel Adder/Confirmed field correction history'/suffix/page/'before accepted'/source.name,
                     'Exact published predecessor quartet before independently reviewed field corrections')
            frozen = item['frozen_independent_review']
            source = Path(frozen['path'])
            assert digest(source.read_bytes())==frozen['sha256']
            copy(source,repo/'notes/AP Parallel Adder/Confirmed field correction history'/suffix/page/'Frozen independent acceptance.json',
                 'Independent exact field-delta acceptance preserved before owner publication annotations')
        for source in sorted(batch_root.rglob('*')):
            if source.is_file() and source.suffix.lower() in {'.json','.txt','.png'}:
                copy(source,repo/'notes/AP Parallel Adder/Confirmed field correction history'/suffix/source.relative_to(batch_root),
                     'Exact human replies or independently reviewed source recoveries and superseded artifact history')
    v5_audit = read_json(workspace/'tmp/ald-text/ald/manual-verification/spreadsheet-v5/Workbook independent audit v5.json')
    assert v5_audit['passed'] is True and not v5_audit['failures']
    for key in ['workbook','manifest']:
        artifact = v5_audit[key]
        assert digest(Path(artifact['path']).read_bytes())==artifact['sha256']

    # Reviewed question deductions remain distinct from diagram publications.
    # Import them only after exact candidate/tool bindings and independent
    # native judgments have passed; the issued workbook remains unchanged.
    socket_work = workspace/'tmp/ald-text/ald/manual-verification/socket-function-recovery-v1'
    socket_audit = socket_work/'Independent final socket function audit.json'
    if socket_audit.is_file():
        review = read_json(socket_audit)
        assert review['passed'] is True and not review['failures']
        for key in ['candidate_file', 'builder_file', 'native_verdict_file']:
            item = review.get(key)
            if item:
                assert digest(Path(item['path']).read_bytes())==item['sha256'], key
        dataset = read_json(Path(review['candidate_file']['path']))
        assert {q['id'] for q in dataset['results'] if q['confidence']=='High'}==set(review['High_ids'])
        assert {q['id'] for q in dataset['results'] if q['confidence']=='Human confirmed'}==set(review['human_confirmed_ids'])
        for source in sorted(socket_work.rglob('*')):
            if not source.is_file() or '__pycache__' in source.parts:
                continue
            if source.name=='build_socket_function_recoveries.py':
                copy(source, repo/'tools/references'/source.name, 'Reusable physical socket, card-function and same-page candidate matching tool')
            elif source.suffix.lower() in {'.json','.txt','.png','.csv'}:
                copy(source, repo/'notes/Manual verification/Socket function reference checks'/source.relative_to(socket_work),
                     'Socket/function question deductions, independent native evidence and frozen inputs')

    # Collection-level reviews and inventories, rather than diagram data tables.
    selectors = ['review', 'validation', 'inventory', 'manifest', 'rename ledger',
                 'filename correction', 'acceptance ledger', 'printer grid',
                 'branch confirmation', 'unreadable', 'reconciliation',
                 'recovered fields', 'source corrections', 'comparison', 'checks']
    for path in sorted(exports.rglob('*')):
        if path.suffix.lower() not in {'.json', '.csv'} or not path.is_file():
            continue
        name = path.name.lower()
        if not any(word in name for word in selectors):
            continue
        # Page companions are represented by the filtered records above.
        token = path.name.split(' ', 1)[0]
        if path.suffix.lower()=='.json' and len(token) >= 5 and token[2:5].isdigit():
            continue
        parent = path.parent.name
        if parent in folders:
            folder = parent
        elif parent[:2] in by_family and parent not in {'ALD Diagrams', 'CAS Diagrams'}:
            folder = by_family[parent[:2]]
        elif path.name.startswith(('CAS ', 'A6 A7 A8 ')):
            folder = None
        elif path.name[:2] in by_family:
            folder = by_family[path.name[:2]]
        else:
            folder = None
        dest = repo/'notes'
        if folder:
            dest /= folder
        destination = dest/path.name
        if destination.relative_to(repo).as_posix() not in planned:
            copy(path, destination, 'Published collection review or inventory snapshot')

    # Preserve shared engines/checkers and their local Python dependencies;
    # exclude page-specific repair scripts and early OCR experiments.
    seed_names = [
        'a1_build_reference.py', 'a1_verify_complete.py', 'a678_canvas.py',
        'cas_reviewed_renderer.py', 'cas_characters.py', 'cas_local_grid.py',
        'cas_content_audit.py', 'cas_wire_qz_check.py', 'cas_export_package.py',
        'qq_renderer.py', 'qy_renderer.py', 'qz_package.py',
        'qz_reconcile.py', 'qz_reconciliation_report.py', 'compare_qz_emulator.py',
        'ce_grid_check.py', 'kc_grid_check.py', 'kx_grid_check.py', 'ra_grid_check.py',
        'ald/ap_batch_main/ald_page.py', 'ald/ap_batch_main/exact_grid_check.py',
        'ald/ap_batch_mid/core.py', 'ald/ap_batch_high/render_page.py',
        'ald/repository-export/export_reviewed.py',
    ]
    work = workspace/'tmp/ald-text'
    queue = [work/name for name in seed_names]
    tools = set()
    while queue:
        path = queue.pop()
        if path in tools or not path.is_file():
            continue
        tools.add(path)
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split('.')[0])
        for module in modules:
            for candidate in [path.parent/(module+'.py'), work/(module+'.py')]:
                if candidate.is_file():
                    queue.append(candidate)
                    break
    for path in sorted(tools):
        copy(path, repo/'tools/legacy'/path.relative_to(work),
             'Historical shared conversion/validation source; original workspace dependencies')
    copy(work/'cas_characters.py', repo/'tools/cas/cas_characters.py',
         'Reusable CAS glyph normalization helper')

    # Never silently replace a user's independently edited repository record.
    index_path = repo/'notes/Repository records manifest.json'
    old = read_json(index_path) if index_path.exists() else {}
    owned = {item['path']: item['sha256'] for item in old.get('files', [])}
    conflicts = []
    for relative, item in planned.items():
        path = repo/relative
        if path.exists() and digest(path.read_bytes()) not in {item['sha256'], owned.get(relative)}:
            conflicts.append(relative)
    assert not conflicts, 'Independent repository changes: '+str(conflicts)
    report = {'updated_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Reviewed text export plus preserved provenance and tool snapshots',
              'reviewed_texts': len(exported['exported']),
              'historical_shared_tools': len(tools),
              'files': [{key: value for key, value in item.items() if key != '_raw'}
                        for item in planned.values()]}
    if args.write:
        for relative, item in planned.items():
            path = repo/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or digest(path.read_bytes()) != item['sha256']:
                path.write_bytes(item['_raw'])
        # Include the published text/notes in the portable integrity inventory.
        managed = {item['path'] for item in report['files']}
        for branch in ['ALD', 'notes', 'json', 'csv', 'tools']:
            for path in (repo/branch).rglob('*'):
                if not path.is_file() or path==index_path or path.suffix.lower() not in {'.txt','.json','.csv','.py','.png'}:
                    continue
                relative = path.relative_to(repo).as_posix()
                if relative not in managed:
                    report['files'].append({'path': relative,
                        'sha256': digest(path.read_bytes()), 'role': 'Repository file'})
        index_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'planned_records_and_tools': len(planned),
                      'historical_shared_tools': len(tools),
                      'counts': dict(Counter(item['role'] for item in planned.values())),
                      'write': args.write}, ensure_ascii=False))


if __name__ == '__main__':
    main()

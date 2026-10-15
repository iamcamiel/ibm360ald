"""Preflight or publish only the independently accepted compact unified64 application.

Default is a private preflight report. --publish requires separate coordinator
release. No repository files or original TIFFs are written.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,hashlib,importlib.util,json,shutil,sys
sys.dont_write_bytecode=True
ROOT=Path('D:/Github/IBM360');HERE=Path(__file__).resolve().parent
CANONICAL=ROOT/'ALD_Visual_Transcriptions';SOURCE=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')
MANIFEST=HERE/'application-unified64-v3/Private unified H rule application manifest.json'
MANIFEST_SHA='a66c6e3145609d4ae0c5ff3996e40fdb8a593dbb100b1e369943ff86fcd14e1f'
AUDIT=HERE/'independent-inventory/unified64-review/Independent compact unified64 H application final acceptance.json'
AUDIT_SHA='3ec19ece8c388cf9d0f949f00b45f9c48e42c22dae161157ba5596c17f160fbd'
RULES=HERE/'Direct human H function and port-count rules.json';RULES_SHA='32b2e29139fbf497a84fe7bbfb9367134400f313020a2d52b81db7c674cc0469'
EXCEPTIONS=HERE/'Direct human three A exception confirmation.json';EXCEPTIONS_SHA='e5898ee7c105d5f9c6fa5ace92f16bf349fbbc0aaf9754f2d7e3f6400d6cdd36'
HISTORY='source_derived_H_rule_function_recovery_v1'
RECEIPT=MANIFEST.parent/'Unified H rule canonical publication receipt.json'
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
READ=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
BIND=lambda p:{'path':str(Path(p).resolve()),'sha256':SHA(p)}
def require(ok,message):
    if not ok:raise ValueError(message)
def checked(b):
    p=Path(b.get('path',b.get('file',''))).resolve();require(p.is_file()and SHA(p)==b['sha256'],'Changed or missing binding: '+str(p));return p
def pin(p,h):require(SHA(p)==h,'Changed authority/acceptance: '+str(p));return READ(p)
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def preflight():
    require(not RECEIPT.exists(),'Publication receipt already exists; do not republish')
    app=pin(MANIFEST,MANIFEST_SHA);peer=pin(AUDIT,AUDIT_SHA);pin(RULES,RULES_SHA);exception=pin(EXCEPTIONS,EXCEPTIONS_SHA)
    require(peer['passed']is True and not peer['failures']and peer['visual_review_pending']is False,'Independent acceptance not complete')
    require(checked(peer['manifest'])==checked(peer['application_manifest'])==MANIFEST.resolve(),'Independent manifest aliases differ')
    require(checked(app['authority'])==RULES.resolve()and app['raw_authority_records']==[BIND(EXCEPTIONS)]and app['history_key']==HISTORY,'Authority/history mismatch')
    for b in app['protected_inputs']+app['snapshot_inputs']:checked(b)
    helper=checked(app['preparation_helper']);spec=importlib.util.spec_from_file_location('accepted_stage_helper',helper);stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
    inventory=READ(checked(app['approved_inventory']));require(inventory['passed']is True and not inventory['failures'],'Unified inventory not accepted')
    cases={c['candidate_id']:c for c in inventory['cases']};ids=[];changes=[];pages=[];active_aliases=0
    peer_pages={(str(p['scan_id']),p['page']):p for p in peer['page_records']};require(len(peer_pages)==len(app['pages'])==33,'Wrong page count')
    for b in peer['bindings']:checked(b)
    for page in app['pages']:
        key=(str(page['source_scan_id']),page['page']);require(key in peer_pages,'Wrong approved scan');approval=peer_pages[key]
        require(approval['candidate_ids']==[f['candidate_id']for f in page['function_fields']],'Approved field IDs differ')
        ordered=lambda edits:sorted(edits,key=lambda e:(e['row'],e['column']))
        require(ordered(approval['exact_cell_edits'])==ordered(page['exact_meaningful_cell_changes']),'Independent accepted cells differ')
        source=checked(page['source']);require(source.is_relative_to(SOURCE.resolve()),'Original source escaped archive')
        guard=READ(checked(page['immutable_original_source_guard']));require(guard['source']==page['source']and guard['original_unchanged']is True,'Original hash guard mismatch')
        checked(page['prior_review_record'])
        for kind in ('txt','json','notes','preview'):
            current=checked(page['canonical_quartet'][kind]);before=checked(page['before_quartet'][kind]);candidate=checked(page['candidate_quartet'][kind])
            require(current.is_relative_to(CANONICAL.resolve())and before.is_relative_to(HERE.resolve())and candidate.is_relative_to(HERE.resolve()),'Quartet path escaped allowed root')
            require(current.name==before.name==candidate.name and SHA(current)==SHA(before),'Working quartet is not exact accepted before epoch')
        raw=checked(page['before_quartet']['txt']).read_bytes();newraw=checked(page['candidate_quartet']['txt']).read_bytes();old=raw.decode('utf-8').splitlines();new=newraw.decode('utf-8').splitlines();restored=newraw.decode('utf-8').splitlines(keepends=True)
        require(len(old)==len(new)==103 and all(len(a)==len(z)<=245 for a,z in zip(old,new)),'Changed geometry/line lengths')
        model=READ(checked(page['before_quartet']['json']));newmodel=READ(checked(page['candidate_quartet']['json']));expected=[]
        for field in page['function_fields']:
            cid=field['candidate_id'];require(cid in cases and cid not in ids,'Unknown/duplicate field ID');ids.append(cid);case=cases[cid];target=case['target'];r,c=field['row'],field['column'];before,after=field['function_before'],field['function_after'];node=model['nodes'][int(field['node_pointer'].split('/')[-1])]
            require(field['source_evidence']==case and str(target['scan_id'])==str(page['source_scan_id'])and target['page']==page['page'],'Wrong source-specific field proof')
            require((field['node_pointer'],field['node'],r,c,before,after)==(target['node_pointer'],target['node_identifier'],case['row'],case['column'],case['function_before'],case['function_after']),'Wrong function/node/coordinate/answer')
            require(before in {'H','�'}and after in {'A','R'}and node['id']==field['node']and node['function']==before,'Unsupported exact function identity')
            require(old[r][c]==before and new[r][c]==after,'Exact printed cell mismatch')
            if case['case_class']=='previously_ambiguous_unreadable_function':
                witness=case['selected_distinct_scan_native_witness'];require(witness['scan_id']!=target['scan_id']and witness['function_literal']==after and not witness['field_history_and_aliases']['matching_history']and not any(witness['field_recovery_dependencies'].values()),'Incomplete, derived or same-scan witness')
                for k in ('model_binding','text_binding','canonical_model_binding','canonical_text_binding','original_source_binding'):checked(witness[k])
            ins,outs=field['connected_inputs'],field['connected_outputs'];require((ins,outs)==(case['connected_inputs'],case['connected_outputs']),'Changed port evidence')
            if case.get('direct_A_exception'):
                require(ins==outs==1 and after=='A'and len([a for a in exception['answers']if a['page']==target['page']and a['block']in {target['block'],target['node_identifier']}and a['card_portion']==target['printed_card_portion']and a['function']==after])==1,'Exception is not exact direct human answer')
            else:require((after=='R'and ins==1 and outs==0)or(after=='A'and ins>=2 and outs==1),'Direct human count rule violated')
            edit={'row':r,'column':c,'before':before,'after':after};require(field['exact_meaningful_cell_changes']==[edit],'Wrong one-cell correction');expected.append(edit);restored[r]=restored[r][:c]+before+restored[r][c+1:]
        actual=[{'row':r,'column':c,'before':a,'after':z}for r,(x,y)in enumerate(zip(old,new))for c,(a,z)in enumerate(zip(x,y))if a!=z]
        require(ordered(actual)==ordered(expected)==ordered(page['exact_meaningful_cell_changes']),'Extra/missing meaningful text change')
        require(''.join(restored).encode('utf-8')==raw,'Unrelated byte, line ending or spacing change')
        expected_model,allowed=stage.replace_aliases(model,old,page['function_fields']);require(sorted(allowed,key=lambda c:c['json_pointer'])==sorted(page['allowed_active_semantic_changes'],key=lambda c:c['json_pointer']),'Unapproved active alias')
        history=newmodel.get(HISTORY);require(HISTORY not in model and isinstance(history,dict),'Wrong additive provenance history')
        require(history['authority']==app['authority']and history['raw_authority_records']==app['raw_authority_records']and history['approved_inventory']==app['approved_inventory']and history['source_sha256']==page['source']['sha256']and history['fields']==page['function_fields'],'Recovery provenance differs')
        expected_model[HISTORY]=history;require(expected_model==newmodel,'Node/pin/wire/route/decoration/other metadata changed')
        active_aliases+=len(allowed);changes+=actual;pages.append(page)
    require(len(ids)==64 and set(ids)==set(peer['approved_candidate_ids'])and not peer['held_candidate_ids']and len(changes)==64,'Incomplete accepted inventory')
    require(sum(cases[i]['function_before']=='H'for i in ids)==52 and sum(cases[i]['function_before']=='�'for i in ids)==12,'Wrong H/masked scope')
    for sheet in app['contact_sheets']:checked(sheet['image'])
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'mode':'guarded preflight; no canonical writes','manifest':BIND(MANIFEST),'independent_audit':BIND(AUDIT),'authority':BIND(RULES),'exception_authority':BIND(EXCEPTIONS),'publisher':BIND(Path(__file__)),'counts':{'pages':33,'functions':64,'exact_changed_cells':64,'quartet_files':132,'standalone_H':52,'masked':12,'direct_A_exceptions':3,'allowlisted_active_function_displays':active_aliases},'checks':{'all_current_quartets_equal_accepted_before':True,'all_candidates_equal_independently_approved_bytes':True,'all_original_TIFF_hashes_checked':True,'all_rules_exceptions_and_proofs_hash_checked':True,'all_readable_unrelated_text_spacing_endings_restored_exactly':True,'all_nodes_pins_routes_decorations_and_prior_history_invariant':True,'all64_ids_match_independent_approval':True},'canonical_writes':0,'repository_writes':0,'original_TIFFs_written':0}
    return app,pages,report
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--publish',action='store_true',help='Only after separate coordinator release');args=ap.parse_args();app,pages,report=preflight();pre=MANIFEST.parent/'Guarded unified64 publisher preflight.json';save(pre,report)
    if not args.publish:print(json.dumps({'passed':True,'published':False,'preflight':BIND(pre),'counts':report['counts']}));return
    staged=[]
    try:
        for page in pages:
            for kind in ('txt','json','notes','preview'):
                destination=checked(page['canonical_quartet'][kind]);candidate=checked(page['candidate_quartet'][kind]);temp=destination.with_name(destination.name+'.H-rule-publish.tmp');require(not temp.exists(),'Temporary publication collision');shutil.copyfile(candidate,temp);require(SHA(temp)==page['candidate_quartet'][kind]['sha256'],'Temporary copy changed');staged.append((destination,temp,page['canonical_quartet'][kind]['sha256'],page['candidate_quartet'][kind]['sha256']))
        for destination,temp,oldhash,newhash in staged:require(SHA(destination)==oldhash and SHA(temp)==newhash,'Source/candidate changed after whole-application preflight')
        for page in pages:checked(page['source'])
        for destination,temp,oldhash,newhash in staged:temp.replace(destination)
    finally:
        for destination,temp,oldhash,newhash in staged:
            if temp.exists():temp.unlink()
    published=[]
    for page in pages:
        current={kind:BIND(Path(b['path']))for kind,b in page['canonical_quartet'].items()}
        require(all(current[k]['sha256']==page['candidate_quartet'][k]['sha256']for k in current),'Published bytes differ from independent candidate');checked(page['source'])
        published.append({'page':page['page'],'source_scan_id':page['source_scan_id'],'source':page['source'],'before_quartet':page['before_quartet'],'current_quartet':current,'independently_reviewed_candidate_quartet':page['candidate_quartet'],'independent_candidate_audit':BIND(AUDIT),'prior_review_record':page['prior_review_record'],'function_fields':page['function_fields'],'exact_meaningful_cell_changes':page['exact_meaningful_cell_changes'],'allowed_active_semantic_changes':page['allowed_active_semantic_changes'],'metadata_changes':page['metadata_changes'],'current_bytes_equal_independently_reviewed_candidates':True})
    receipt={'created_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'failures':[],'manifest':BIND(MANIFEST),'independent_audit':BIND(AUDIT),'authority':BIND(RULES),'raw_authority_records':[BIND(EXCEPTIONS)],'approved_inventory':app['approved_inventory'],'publication_helper':BIND(Path(__file__)),'preflight':BIND(pre),'pages':published,'counts':report['counts'],'history_key':HISTORY,'repository_mirror_performed':False,'original_TIFFs_unchanged':True,'geometry_and_wiring_changes':0,'new_independent_native_witnesses_created':False};save(RECEIPT,receipt);print(json.dumps({'passed':True,'published':True,'receipt':BIND(RECEIPT),'counts':report['counts']}))
if __name__=='__main__':main()

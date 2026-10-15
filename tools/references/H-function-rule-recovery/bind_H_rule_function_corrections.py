"""Bind the published64 H/count-rule functions to exact independently accepted scans.

Dry-run by default; --emit writes only the current acceptance JSON. No source,
repository, exporter, importer or database operations are performed here.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
ROOT=Path('D:/Github/IBM360');HERE=ROOT/'tmp/ald-text/ald/card-type-database/function-H-review-v1'
CANONICAL=ROOT/'ALD_Visual_Transcriptions';SOURCE=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')
MANIFEST=HERE/'application-unified64-v3/Private unified H rule application manifest.json';MANIFEST_SHA='a66c6e3145609d4ae0c5ff3996e40fdb8a593dbb100b1e369943ff86fcd14e1f'
AUDIT=HERE/'independent-inventory/unified64-review/Independent compact unified64 H application final acceptance.json';AUDIT_SHA='3ec19ece8c388cf9d0f949f00b45f9c48e42c22dae161157ba5596c17f160fbd'
PUBLICATION=MANIFEST.parent/'Unified H rule canonical publication receipt.json';PUBLICATION_SHA='d4ac76fd0b3abb6018c89bfa3841660a30f97cc553247e5a8448fc6036b3497f'
AUTHORITY=HERE/'Direct human H function and port-count rules.json';AUTHORITY_SHA='32b2e29139fbf497a84fe7bbfb9367134400f313020a2d52b81db7c674cc0469'
EXCEPTIONS=HERE/'Direct human three A exception confirmation.json';EXCEPTIONS_SHA='e5898ee7c105d5f9c6fa5ace92f16bf349fbbc0aaf9754f2d7e3f6400d6cdd36'
INVENTORY=HERE/'Unified 64 H-rule approved private inventory.json';INVENTORY_SHA='f36bd3339b9492a97e38724497374913e79cc9002414c8fdf4cad28d26414e76'
NATIVE=HERE/'independent-inventory/Independent H function and count-rule review.json';NATIVE_SHA='efe17b639db8eb38d2dd106ba5d6a9808865acd26fb62203cd1e4fd0c5b99f08'
UNREADABLE=HERE/'Independent unreadable H exclusion review.json';UNREADABLE_SHA='6106b1a933eb9b8432f1329a97933dc4d4159eb9b34a97af3dd17009ce8a2449'
HISTORY='source_derived_H_rule_function_recovery_v1'
OUT=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/H function port rule current audit.json'
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
READ=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
BIND=lambda p:{'file':str(Path(p).resolve()),'sha256':SHA(p)}
def require(ok,message):
    if not ok:raise ValueError(message)
def checked(b):
    p=Path(b.get('path',b.get('file',''))).resolve();require(p.is_file()and SHA(p)==b['sha256'],'Missing/changed binding: '+str(p));return p
def pin(p,h):require(SHA(p)==h,'Wrong pinned proof: '+str(p));return READ(p)
def ordered(edits):return sorted(edits,key=lambda e:(e['row'],e['column']))
def validate_field(field,case,old,new,model,exceptions):
    t=case['target'];r,c=field['row'],field['column'];a,z=field['function_before'],field['function_after']
    require(field['source_evidence']==case,'Field evidence differs from approved inventory')
    require((field['node_pointer'],field['node'],r,c,a,z)==(t['node_pointer'],t['node_identifier'],case['row'],case['column'],case['function_before'],case['function_after']),'Wrong node/function placement or answer')
    require(a in {'H','�'}and z in {'A','R'}and old[r][c]==a and new[r][c]==z,'Wrong exact H/masked cell')
    node=model['nodes'][int(field['node_pointer'].split('/')[-1])];require(node['id']==field['node']and node['function']==a,'Wrong before node/function')
    ins,outs=field['connected_inputs'],field['connected_outputs'];require((ins,outs)==(case['connected_inputs'],case['connected_outputs']),'Altered connected-port evidence')
    if case.get('direct_A_exception'):
        require(a=='H'and z=='A'and ins==outs==1 and len([e for e in exceptions['answers']if e['page']==t['page']and e['block']in {t['block'],t['node_identifier']}and e['card_portion']==t['printed_card_portion']and e['function']==z])==1,'Unsupported direct exception')
    else:require((z=='R'and ins==1 and outs==0)or(z=='A'and ins>=2 and outs==1),'Direct human count rule violated')
    if case['case_class']=='previously_ambiguous_unreadable_function':
        witness=case['selected_distinct_scan_native_witness'];require(witness['scan_id']!=t['scan_id']and witness['function_literal']==z and not witness['field_history_and_aliases']['matching_history']and not any(witness['field_recovery_dependencies'].values()),'Witness is derived/incomplete/same scan')
        for key in ('model_binding','text_binding','canonical_model_binding','canonical_text_binding','original_source_binding'):checked(witness[key])
    require(field['exact_meaningful_cell_changes']==[{'row':r,'column':c,'before':a,'after':z}],'Changed field scope')
    return {'row':r,'column':c,'before':a,'after':z}
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--emit',action='store_true');args=parser.parse_args()
    app=pin(MANIFEST,MANIFEST_SHA);peer=pin(AUDIT,AUDIT_SHA);publication=pin(PUBLICATION,PUBLICATION_SHA);pin(AUTHORITY,AUTHORITY_SHA);exceptions=pin(EXCEPTIONS,EXCEPTIONS_SHA);inventory=pin(INVENTORY,INVENTORY_SHA);pin(NATIVE,NATIVE_SHA);pin(UNREADABLE,UNREADABLE_SHA)
    require(publication['passed']is True and not publication['failures']and peer['passed']is True and not peer['failures']and peer['visual_review_pending']is False,'Independent publication acceptance incomplete')
    require(checked(publication['manifest'])==checked(peer['manifest'])==checked(peer['application_manifest'])==MANIFEST.resolve()and checked(publication['independent_audit'])==AUDIT.resolve(),'Manifest/audit alias mismatch')
    require(checked(publication['authority'])==checked(app['authority'])==AUTHORITY.resolve()and publication['raw_authority_records']==app['raw_authority_records']==[{'path':str(EXCEPTIONS),'sha256':EXCEPTIONS_SHA}],'Wrong direct authority/exception chain')
    require(checked(publication['approved_inventory'])==checked(app['approved_inventory'])==INVENTORY.resolve()and publication['history_key']==app['history_key']==HISTORY,'Wrong approved inventory/history')
    require(publication['repository_mirror_performed']is False and publication['original_TIFFs_unchanged']is True and publication['geometry_and_wiring_changes']==0 and publication['new_independent_native_witnesses_created']is False,'Wrong publication scope')
    helper=checked(app['preparation_helper']);spec=importlib.util.spec_from_file_location('approved_H_stage_helper',helper);stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
    for b in app['snapshot_inputs']:checked(b)
    # Snapshot copies preserve accepted pre-publication epoch; do not require
    # historical live canonical/repository hashes once the mirror is updated.
    cases={c['candidate_id']:c for c in inventory['cases']};planned={(str(p['source_scan_id']),p['page']):p for p in app['pages']};approved={(str(p['scan_id']),p['page']):p for p in peer['page_records']};items=publication['pages'];require(len(items)==len(planned)==len(approved)==33,'Incomplete/duplicate page scope')
    records=[];allids=[];allcells=[]
    for item in items:
        key=(str(item['source_scan_id']),item['page']);require(key in planned and key in approved,'Wrong accepted scan');p=planned[key];approval=approved[key]
        require(item['source']==p['source']and checked(item['source']).is_relative_to(SOURCE.resolve()),'Source original mismatch')
        guard=READ(checked(p['immutable_original_source_guard']));require(guard['source']==item['source']and guard['original_unchanged']is True,'Original guard mismatch')
        for name in ('function_fields','exact_meaningful_cell_changes','allowed_active_semantic_changes','metadata_changes','prior_review_record'):require(item[name]==p[name],'Published field/details differ from accepted manifest: '+name)
        checked(item['prior_review_record']);require(checked(item['independent_candidate_audit'])==AUDIT.resolve(),'Per-page independent audit mismatch')
        for kind in ('txt','json','notes','preview'):
            before=checked(item['before_quartet'][kind]);candidate=checked(item['independently_reviewed_candidate_quartet'][kind]);current=checked(item['current_quartet'][kind])
            require(item['before_quartet'][kind]==p['before_quartet'][kind]and item['independently_reviewed_candidate_quartet'][kind]==p['candidate_quartet'][kind],'Before/candidate approval differs')
            require(current==Path(p['canonical_quartet'][kind]['path']).resolve()and current.is_relative_to(CANONICAL.resolve())and before.is_relative_to(HERE.resolve())and candidate.is_relative_to(HERE.resolve()),'Quartet identity/path escaped approved roots')
            require(current.name==candidate.name==before.name and SHA(current)==SHA(candidate),'Current bytes differ from independently accepted candidate')
        raw=checked(item['before_quartet']['txt']).read_bytes();newraw=checked(item['current_quartet']['txt']).read_bytes();old=raw.decode('utf-8').splitlines();new=newraw.decode('utf-8').splitlines();restored=newraw.decode('utf-8').splitlines(keepends=True);require(len(old)==len(new)==103 and all(len(a)==len(z)<=245 for a,z in zip(old,new)),'Changed grid/line lengths')
        model=READ(checked(item['before_quartet']['json']));currentmodel=READ(checked(item['current_quartet']['json']));expected=[]
        for field in item['function_fields']:
            cid=field['candidate_id'];require(cid in cases and cid not in allids,'Wrong/duplicate approved field');allids.append(cid);case=cases[cid];require(case['target']['page']==item['page']and str(case['target']['scan_id'])==str(item['source_scan_id']),'Field belongs to different scan');edit=validate_field(field,case,old,new,model,exceptions);expected.append(edit);r,c=edit['row'],edit['column'];restored[r]=restored[r][:c]+edit['before']+restored[r][c+1:]
        actual=[{'row':r,'column':c,'before':a,'after':z}for r,(x,y)in enumerate(zip(old,new))for c,(a,z)in enumerate(zip(x,y))if a!=z]
        require(ordered(actual)==ordered(expected)==ordered(item['exact_meaningful_cell_changes'])==ordered(approval['exact_cell_edits']),'Extra/missing function cells')
        require(''.join(restored).encode('utf-8')==raw,'Changed unrelated bytes, spacing or line endings')
        expectedmodel,allowed=stage.replace_aliases(model,old,item['function_fields']);require(sorted(allowed,key=lambda c:c['json_pointer'])==sorted(item['allowed_active_semantic_changes'],key=lambda c:c['json_pointer']),'Unexpected active function alias')
        history=currentmodel.get(HISTORY);require(HISTORY not in model and isinstance(history,dict),'Wrong additive history');require(history['fields']==item['function_fields']and history['authority']==app['authority']and history['raw_authority_records']==app['raw_authority_records']and history['approved_inventory']==app['approved_inventory']and history['source_sha256']==item['source']['sha256'],'Wrong reconstruction lineage')
        expectedmodel[HISTORY]=history;require(expectedmodel==currentmodel,'Unapproved pins/geometry/routes/decorations/metadata change')
        require(approval['candidate_ids']==[f['candidate_id']for f in item['function_fields']],'Independent per-page approval mismatch');allcells+=actual
        records.append({'page':item['page'],'printed_page':item['page'],'source_scan_id':str(item['source_scan_id']),'eligible':True,'artifact_schema':'reviewed-current-quartet-v1','source':item['source'],'current_quartet':item['current_quartet'],'owner_receipt':BIND(PUBLICATION),'independent_audit':BIND(AUDIT),'human_authority':BIND(AUTHORITY),'human_amendment':BIND(EXCEPTIONS),'frozen_occurrence_inventory':BIND(INVENTORY),'root_acceptance':BIND(NATIVE),'function_rule_unreadable_review':BIND(UNREADABLE),'function_rule_application_manifest':BIND(MANIFEST),'predecessor_acceptance':BIND(checked(item['prior_review_record'])),'candidate_ids':[f['candidate_id']for f in item['function_fields']],'changed_cells':actual,'checks':{'exact_independently_accepted_source_scan_and_current_quartet':True,'exact64_human_rule_or_direct_exception_fields_only':True,'old_bytes_lengths_endings_restored_exactly':True,'all_other_nodes_pins_routes_decorations_and_history_unchanged':True,'source_bound_native_complete_witnesses_for_masked_cases':True,'direct_exceptions_preserve_their_one_input_one_output':True,'reconstructed_values_marked_not_independent_native_witnesses':True}})
    require(len(allids)==len(set(allids))==64 and set(allids)==set(peer['approved_candidate_ids'])==set(cases)and not peer['held_candidate_ids']and len(allcells)==64,'Wrong complete accepted scope')
    result={'created_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'failures':[],'scope':'Exact source/scan/path-specific64 H and unreadable A/R function corrections on33 pages. The prior112 recovery provenance remains intact; all new results remain reconstructed. No change to other glyphs, wiring, port counts or function taxonomy.','pages':records,'counts':publication['counts'],'manifest':BIND(MANIFEST),'independent_application_audit':BIND(AUDIT),'publication':BIND(PUBLICATION),'authority':BIND(AUTHORITY),'exception_authority':BIND(EXCEPTIONS),'unreadable_approval':BIND(UNREADABLE),'native_H_approval':BIND(NATIVE),'binder':BIND(Path(__file__)),'out_of_scope_held_candidate_ids':peer['out_of_scope_held_candidate_ids'],'repository_writes':0,'canonical_writes':0}
    if args.emit:
        OUT.parent.mkdir(parents=True,exist_ok=True)
        if OUT.exists():
            historydir=OUT.parent/'H function port rule audit history';historydir.mkdir(exist_ok=True);history=historydir/(SHA(OUT)+'.json')
            if not history.exists():history.write_bytes(OUT.read_bytes())
        OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'mode':'emit'if args.emit else'dry-run','pages':33,'functions':64,'cells':64,'current_audit':BIND(OUT)if args.emit else None,'canonical_writes':0,'repository_writes':0}))
if __name__=='__main__':main()

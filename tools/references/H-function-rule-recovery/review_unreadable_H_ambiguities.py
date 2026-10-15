"""Freeze a read-only source-bound decision on the fourteen old ambiguities.

Writes only a private review JSON; no diagram, database or repository edits.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';BASE=ROOT/'tmp/ald-text/ald/card-type-database';HERE=Path(__file__).resolve().parent
DB=BASE/'build-accepted-v11-derived112';AUTHORITY=HERE/'Direct human H function and port-count rules.json'
V10=BASE/'function-unreadable-resolution-v1/expanded-shape-takeover-v1/v10-accepted-readonly/Expanded shape unreadable function candidates.json'
DERIVE=V10.parent.parent/'derive_expanded_candidates.py'
READ=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
BIND=lambda p:{'path':str(Path(p).resolve()),'sha256':SHA(p)}
def require(ok,message):
    if not ok:raise ValueError(message)
def main():
    require(SHA(AUTHORITY)=='32b2e29139fbf497a84fe7bbfb9367134400f313020a2d52b81db7c674cc0469','Wrong direct human rules')
    require(SHA(V10)=='2c3919e8676d585868f5fa4bb48f69bfd846570999e1262e250bfacc11efd981','Wrong prior ambiguity inventory')
    require(SHA(DERIVE)=='934254de4dba0591d5ea2d98b4233da26ac1cb177c8176898436759d9311000e','Changed independent field classifier')
    mp=DB/'notes/Card types/Build manifest.json';ap=REPO/'notes/Card types/Independent database audit.json';ip=DB/'json/Card types/Card type index.json'
    require(SHA(mp)=='9adb260eebad41271a90cdbe41c5ea54f432fbf3d9aeb7be0ab36e7d63e6167a' and SHA(ap)=='24b3bbaa7fd4973073bdf6c16320bc5a9c09a0d2244178f61692634a883b2c8c','Wrong accepted V11 snapshot')
    require(READ(ap)['passed'] is True and not READ(ap)['failures'],'V11 acceptance failed')
    outputs={r['path']:r['sha256']for r in READ(mp)['outputs']};require(SHA(ip)==outputs['json/Card types/Card type index.json'],'V11 index changed');index=READ(ip)
    spec=importlib.util.spec_from_file_location('frozen_function_proof',DERIVE);proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(proof);context=proof.make_field_context(index,REPO)
    exportfile=REPO/'notes/Reviewed export provenance.json';contentfile=REPO/'notes/Content data manifest.json';export={str(e['source_scan_id']):e for e in READ(exportfile)['exported']};content={e['path']:e for e in READ(contentfile)['files']}
    cards={};nativecache={}
    def original(o):
        rec=index['sources'][index['pages'][str(o['scan_id'])]['original_source_id']];path=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')/rec['path']
        if str(path)not in nativecache:nativecache[str(path)]=SHA(path)
        require(nativecache[str(path)]==rec['sha256'],'Original scan changed')
        return {'path':str(path),'sha256':rec['sha256']}
    def compact(o):
        ms=index['sources'][o['source_id']];ts=index['sources'][o['text_source_id']];entry=export[str(o['scan_id'])]
        require(SHA(entry['transcription_source'])==entry['text_sha256']==ts['sha256'],'Working/published accepted TXT mismatch')
        require(SHA(content[ms['path']]['source'])==ms['sha256'],'Working/published accepted model mismatch')
        require(not proof.eligibility(o) and not context(o)['reasons'],'Source/field/shape has unresolved dependencies')
        return {'observation_id':o['observation_id'],'page':o['page'],'scan_id':str(o['scan_id']),'block':o['printed_node_identifier']or o['node_identifier'],'node_identifier':o['node_identifier'],'node_pointer':o['JSON_pointer'],'station':o['station'],'card_type':o['card_type_literal'],'portion':o['portion_literal'],'printed_card_portion':o['printed_card_portion_literal'],'unit':o['unit_code_literal'],'location':o['location_literal'],'function_literal':o['function_literal'],'function_literal_bindings':o['literal_text_bindings']['function'],'model_binding':{'path':str(REPO/ms['path']),'sha256':ms['sha256']},'text_binding':{'path':str(REPO/ts['path']),'sha256':ts['sha256']},'canonical_model_binding':BIND(content[ms['path']]['source']),'canonical_text_binding':BIND(entry['transcription_source']),'original_source_binding':original(o),'field_recovery_dependencies':o['field_recovery_dependencies'],'field_history_and_aliases':context(o),'source_review_pending':o['source_review_pending']}
    ambiguous=[c for c in READ(V10)['cases']if len(c.get('matching_complete_literals',[]))>1];require(len(ambiguous)==14,'Unexpected ambiguity scope')
    safe=[];held=[]
    for case in ambiguous:
        t=case['target'];code=t['card_type'];record=next(r for r in index['card_types']if r['card_type']==code)
        if code not in cards:
            require(SHA(DB/record['file'])==outputs[record['file']],'Changed V11 card data');cards[code]=READ(DB/record['file'])['diagram_observations']
        observations=cards[code];o=next(x for x in observations if x['observation_id']==t['observation_id']);shape=proof.shape(o)
        require(shape==case['function_free_exact_shape'],'Target shape changed since V10')
        target=compact(o);pool=[];excluded=[]
        for w in observations:
            if w['portion_literal']!=o['portion_literal']or proof.shape(w)!=shape or not w['function_literal']or '�'in w['function_literal']or w['function_literal']=='H' or not proof.literal_matches(o['function_literal'],w['function_literal']):continue
            reasons=proof.eligibility(w)+context(w)['reasons']
            if context(w)['matching_history']:reasons+=['Witness has human or inferred field history; native-only review requires no history']
            if reasons:excluded.append({'observation_id':w['observation_id'],'reasons':sorted(set(reasons))});continue
            pool.append(w)
        names=sorted({w['function_literal']for w in pool});combo=shape['connected_count_and_decoration_shape'];inputs=combo['input']['exact_connected_count'];outputs_count=combo['output']['exact_connected_count']
        if 'H'not in case['matching_complete_literals']:
            held.append({'candidate_id':case['candidate_id'],'target':target,'current_complete_labels':names,'reason':'OR/UX ambiguity is unaffected by the H or A/R count rules'});continue
        require(len(names)==1 and names[0]in {'A','R'},'No unique permitted native literal remains');after=names[0]
        require((after=='R'and inputs==1 and outputs_count==0)or(after=='A'and isinstance(inputs,int)and inputs>=2 and outputs_count==1),'Native complete label conflicts with direct human port rule')
        selected=next(w for w in pool if str(w['scan_id'])!=str(o['scan_id']));witness=compact(selected)
        require(not witness['field_history_and_aliases']['matching_history'] and all(not v for v in witness['field_recovery_dependencies'].values()),'Witness is inferred or human-corrected')
        b=target['function_literal_bindings'];require(len(b)==1 and b[0]['literal']==target['function_literal']=='�','Wrong exact one-character target span')
        safe.append({'candidate_id':case['candidate_id'],'case_class':'previously_ambiguous_unreadable_function','target':target,'function_before':'�','function_after':after,'row':b[0]['row'],'column':b[0]['column'],'prior_matching_complete_literals':case['matching_complete_literals'],'complete_native_nonH_literal_inventory':names,'exact_function_free_shape':shape,'connected_inputs':inputs,'connected_outputs':outputs_count,'complete_native_witness_count':len(pool),'complete_native_witness_ids':[w['observation_id']for w in pool],'selected_distinct_scan_native_witness':witness,'excluded_witnesses':excluded,'checks':{'H_excluded_by_direct_human_rule':True,'native_literal_is_unique_after_exclusion':True,'direct_human_port_rule_satisfied':True,'shape_and_decorations_unchanged_since_V10':True,'target_canonical_published_text_model_and_original_hashes_current':True,'selected_complete_witness_has_no_human_or_derived_history':True,'selected_witness_is_different_source_scan':True}})
    require(len(safe)==12 and len(held)==2,'Unexpected decisions')
    result={'schema':'independent-unreadable-H-exclusion-review-v1','created_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'failures':[],'authority':BIND(AUTHORITY),'verbatim_human_statements':READ(AUTHORITY)['statements'],'V10_ambiguity_inventory':BIND(V10),'accepted_V11_manifest':BIND(mp),'accepted_V11_audit':BIND(ap),'V11_index':BIND(ip),'field_classifier':BIND(DERIVE),'accepted_export_manifest':BIND(exportfile),'accepted_content_manifest':BIND(contentfile),'review_script':BIND(Path(__file__)),'safe_unreadable_ids':[c['candidate_id']for c in safe],'cases':safe,'unchanged_ambiguities':held,'counts':{'reviewed_old_ambiguities':14,'safe_unreadable_functions':12,'safe_pages':len({c['target']['scan_id']for c in safe}),'R':sum(c['function_after']=='R'for c in safe),'A':sum(c['function_after']=='A'for c in safe),'unaffected_OR_UX':2},'source_writes':0,'repository_writes':0,'scope':'Private read-only evidence approval; no source correction or publication. Native witnesses are current accepted complete literals with no human or inferred field history.'}
    dest=HERE/'Independent unreadable H exclusion review.json';require(not dest.exists(),'Frozen review already exists');dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':True,'review':BIND(dest),'counts':result['counts']}))
if __name__=='__main__':main()

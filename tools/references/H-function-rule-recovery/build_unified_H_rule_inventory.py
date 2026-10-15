"""Combine independently checked cases and exact later human exceptions privately."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re
ROOT=Path('D:/Github/IBM360');HERE=Path(__file__).resolve().parent;REPO=ROOT/'ibm360ald'
READ=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
BIND=lambda p:{'path':str(Path(p).resolve()),'sha256':SHA(p)}
def checked(b):
    p=Path(b['path']);assert SHA(p)==b['sha256'],str(p);return p
def main():
    authority=HERE/'Direct human H function and port-count rules.json';exceptions=HERE/'Direct human three A exception confirmation.json';unreadable=HERE/'Independent unreadable H exclusion review.json';native=HERE/'independent-inventory/Independent H function and count-rule review.json'
    for p,h in [(authority,'32b2e29139fbf497a84fe7bbfb9367134400f313020a2d52b81db7c674cc0469'),(exceptions,'e5898ee7c105d5f9c6fa5ace92f16bf349fbbc0aaf9754f2d7e3f6400d6cdd36'),(unreadable,'6106b1a933eb9b8432f1329a97933dc4d4159eb9b34a97af3dd17009ce8a2449'),(native,'efe17b639db8eb38d2dd106ba5d6a9808865acd26fb62203cd1e4fd0c5b99f08')]:assert SHA(p)==h
    ur=READ(unreadable);nr=READ(native);assert ur['passed']is nr['passed']is True and not ur['failures']and not nr['failures'];assert len(nr['rule_fitting_cases'])==49 and len(nr['held_cases'])==3
    ep=REPO/'notes/Reviewed export provenance.json';cp=REPO/'notes/Content data manifest.json';entries={str(r['source_scan_id']):r for r in READ(ep)['exported']};content={r['path']:r for r in READ(cp)['files']};answers=READ(exceptions)['answers'];cases=list(ur['cases']);proofs=[BIND(unreadable),BIND(native),BIND(exceptions)]
    for case,is_exception in [(c,False)for c in nr['rule_fitting_cases']]+[(c,True)for c in nr['held_cases']]:
        t=case['target'];model=READ(checked(t['model']));node=model['nodes'][int(t['node_pointer'].split('/')[-1])];scan=str(t['scan_id']);entry=entries[scan];relative=Path(t['model']['path']).relative_to(REPO).as_posix();canonical_model=Path(content[relative]['source']);canonical_text=Path(entry['transcription_source']);assert SHA(canonical_model)==t['model']['sha256']and SHA(canonical_text)==t['text']['sha256'];assert node['function']=='H'
        inputs=case['connected_input_count'];outputs=case['connected_output_count'];after=case['function_after']
        if is_exception:
            matches=[a for a in answers if a['page']==t['page']and a['block']==t['block']and a['card_portion']==t['printed_card_portion']and a['function']=='A'];assert len(matches)==1 and inputs==outputs==1;after='A'
        else:assert (after=='R'and inputs==1 and outputs==0)or(after=='A'and inputs>=2 and outputs==1)
        native_evidence=case['native_evidence'];assert native_evidence['visual_identity_verified']is True;checked(native_evidence['crop']);checked(native_evidence['source']);assert native_evidence['source']==t['original']
        target={'observation_id':t['observation_id'],'page':t['page'],'scan_id':scan,'block':t.get('printed_block_identifier')or t['block'],'node_identifier':node['id'],'node_pointer':t['node_pointer'],'station':t['station'],'card_type':t['card_type'],'portion':t['portion'],'printed_card_portion':t['printed_card_portion'],'unit':t['unit'],'location':t['location'],'function_literal':'H','function_literal_bindings':t['function_bindings'],'model_binding':t['model'],'text_binding':t['text'],'canonical_model_binding':BIND(canonical_model),'canonical_text_binding':BIND(canonical_text),'original_source_binding':t['original']}
        normalized={'candidate_id':case['case_id'],'case_class':'standalone_H_function','target':target,'function_before':'H','function_after':after,'row':case['row'],'column':case['column'],'connected_inputs':inputs,'connected_outputs':outputs,'native_independent_review':BIND(native),'native_evidence':native_evidence,'independent_source_case':case,'direct_A_exception':is_exception}
        if is_exception:normalized['direct_exception_authority']=BIND(exceptions)
        cases.append(normalized)
    assert len(cases)==len({c['candidate_id']for c in cases})==64
    cases.sort(key=lambda c:(re.split(r'(\d+)',c['target']['page'])[0],int(re.search(r'\d+',c['target']['page'])[0]),int(c['target']['scan_id']),c['row'],c['column']))
    result={'schema':'unified-human-H-rule-approved-private-inventory-v1','created_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'failures':[],'authority':BIND(authority),'exception_authority':BIND(exceptions),'proof_inputs':proofs,'cases':cases,'held_cases':ur['unchanged_ambiguities'],'counts':{'fields':64,'standalone_H':52,'rule_fitting_H':49,'direct_H_A_exceptions':3,'masked':12,'R':sum(c['function_after']=='R'for c in cases),'A':sum(c['function_after']=='A'for c in cases),'pages':len({c['target']['scan_id']for c in cases})},'notes':['The3 one-input/one-output H cases are A by direct human confirmation; preserve their exact existing wires.','The2 OR/UX masked ambiguities remain out of scope.','KU101 BJ ✲PH is a separate finding and is never included.'],'source_writes':0,'repository_writes':0,'builder':BIND(Path(__file__))}
    dest=HERE/'Unified 64 H-rule approved private inventory.json';assert not dest.exists();dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'inventory':BIND(dest),'counts':result['counts']}))
if __name__=='__main__':main()

"""Read-only same-portion contact candidates from current accepted ALD nodes.

The historical card database supplies occurrence locations only; every contact
is reread from the current source model, never adopted as a correction here.
"""
from pathlib import Path
from collections import Counter,defaultdict
from hashlib import sha256
from functools import lru_cache
import json,re,sys

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';BASE=Path(__file__).resolve().parent
CONTACT=re.compile(r'\d*([BDGJ](?:0[2-9]|1[0-3]))[✲*]?T?\Z')
def read(p):return json.loads(p.read_text('utf-8-sig'))
def contact(p):
    value=p.get('pin',p.get('printed_pin'))
    match=CONTACT.fullmatch(str(value).strip())if value is not None else None
    return match[1]if match else None
def unit(n):return str(n.get('unit',n.get('circuit',n.get('technology','')))).strip()
@lru_cache(maxsize=256)
def model(path):
    p=REPO/path;raw=p.read_bytes();return json.loads(raw.decode('utf-8-sig')),sha256(raw).hexdigest()
requests={}
for g in (1,2,3):
    for page in read(BASE/f'Group {g} requests.json')['pages']:
        for case in page['cases']:requests[case['case_id']]=(page,case)
proposal_mode='--proposals' in sys.argv
findings=[]
for g in (1,2,3):
    p=BASE/f'Group {g} review/Findings.json'
    if not p.exists():continue
    doc=read(p)
    findings.extend(f for f in doc.get('cases',doc.get('findings',[]))if str(f.get('status','')).startswith('confident' if proposal_mode else 'uncertain'))
results=[]
for f in findings:
    page,case=requests[f['case_id']];node=case['node'];old=case['audit_flag']['physical_contact']
    target=f.get('proposed_contact')if proposal_mode else old
    assert target and re.fullmatch(r'[A-Z]\d{2}',target),f['case_id']
    card=str(node.get('card_type',''));portion=str(node.get('portion',''));side=case['audit_flag']['side']
    path=REPO/'json/Card types current'/(card+'.json');pool=defaultdict(list)
    if path.is_file():
        for occurrence in read(path)['diagram_occurrences']:
            if occurrence['portion']!=portion:continue
            relative=Path('json')/Path(occurrence['source_text']).relative_to('ALD').with_suffix('.json')
            try:doc,digest=model(relative.as_posix());ni=int(occurrence['node_pointer'].split('/')[-1]);other=doc['nodes'][ni]
            except (OSError,KeyError,IndexError,ValueError):continue
            if str(other.get('card_type'))!=card or str(other.get('portion'))!=portion or unit(other)!=unit(node):continue
            printed=other.get('printed_card_portion')
            if printed not in (None,'',card+portion):continue
            if relative.as_posix()==case['audit_flag']['model_path']and ni==int(case['audit_flag']['node_pointer'].split('/')[-1]):continue
            for pi,pin in enumerate(other.get('pins',[])):
                candidate=contact(pin)
                if pin.get('side')!=side or candidate is None or candidate[1:]!=target[1:]:continue
                proof={'page':occurrence['page'],'node':other.get('id'),'model_path':relative.as_posix(),
                    'model_sha256':digest,'node_pointer':f'/nodes/{ni}','pin_index':pi,'literal_pin':pin.get('pin',pin.get('printed_pin')),
                    'circuit':unit(other),'card_portion':card+portion}
                if proof not in pool[candidate]:pool[candidate].append(proof)
    occupied={contact(p)for pi,p in enumerate(node.get('pins',[]))if str(pi)!=case['audit_flag']['pin_index']and p.get('side')==side}
    eligible=[c for c,proof in pool.items()if c not in occupied and len(proof)>=2]
    results.append({'case_id':f['case_id'],'page':f['page'],'old_contact':old,'card_portion':card+portion,'circuit':unit(node),
        'candidate_counts':{k:len(v)for k,v in pool.items()},'same_side_contacts_already_used':sorted(x for x in occupied if x),
        'eligible_candidates':sorted(eligible),'unique_repeated_candidate':eligible[0]if len(eligible)==1 else None,
        'candidate_proofs':{k:v[:4]for k,v in pool.items()},'source_change_asserted':False})
    if proposal_mode:
        counts={k:len(v)for k,v in pool.items()}
        result=results[-1];result['proposed_contact']=target
        result['outlier_status']='not_observed'if counts and target not in counts else 'rare_among_other_readings'if counts.get(target,0)<=1 and max(counts.values(),default=0)>=8 else None
competing=defaultdict(list)
for result in results:
    page,case=requests[result['case_id']]
    if result['unique_repeated_candidate']:
        competing[(case['audit_flag']['model_path'],case['audit_flag']['node_pointer'],case['audit_flag']['side'],result['unique_repeated_candidate'])].append(result)
for entries in competing.values():
    if len(entries)>1:
        for result in entries:
            result['competing_unresolved_inputs']=[x['case_id']for x in entries if x is not result]
            result['withheld_competing_candidate']=result['unique_repeated_candidate']
            result['unique_repeated_candidate']=None
report={'schema':'uncertain-pin-current-source-corroboration-v2','source_changes_applied':False,
    'scope':'Current same-card/portion/circuit, same-side contacts with matching readable digits. Candidates still need native review. Reusing a contact already on this block needs separate electrical evidence.',
    'cases':results,'counts':{'cases':len(results),'unique_repeated_candidates':sum(bool(r['unique_repeated_candidate'])for r in results)}}
name='Proposed contact current-source cross-check.json'if proposal_mode else'Uncertain current-source corroboration v2.json'
(BASE/name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if proposal_mode:
    print(json.dumps({'counts':report['counts'],'outliers':[{k:r[k]for k in ['case_id','page','card_portion','old_contact','proposed_contact','candidate_counts','outlier_status']}for r in results if r['outlier_status']]},indent=2))
else:
    print(json.dumps({'counts':report['counts'],'unique_candidates':[{'case_id':r['case_id'],'page':r['page'],'old':r['old_contact'],'candidate':r['unique_repeated_candidate'],'counts':r['candidate_counts']}for r in results if r['unique_repeated_candidate']]},indent=2))

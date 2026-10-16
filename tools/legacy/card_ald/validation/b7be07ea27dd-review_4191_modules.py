"""Independent structural and visual-coherence proof for universal modules."""
import sys,json,hashlib,datetime,ast,re
from pathlib import Path
ROOT=Path('D:/Github/IBM360/ibm360ald');HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/card_ald'))
import generate_card as G
from review_boundary_card import trace
from review_graph_layout import metrics,preview
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return dict(path=str(p),sha256=sha(p))
def main():
    stage=ROOT.parent/'tmp/ald-text/ald/card-data/4191-grouped-collectors';frozen=stage/'4191 convergent module candidate freeze.json';freeze=read(frozen)
    spec=read(stage/'4191.json');evidence=read(stage/'4191 evidence.json');defpath=ROOT/'json/Card-ALD/definitions/4191.json';overlaypath=ROOT/'json/Card-ALD/build-overrides/4191.json';previous=read(defpath)
    bound=[freeze['definition'],freeze['evidence'],freeze['preview']]+freeze['files'];checks=[];failures=[]
    def check(name,ok,detail=None):
        checks.append(dict(name=name,passed=bool(ok),detail=detail))
        if not ok:failures.append(name)
    check('Every frozen candidate family hash current',all(sha(Path(b['path']))==b['sha256'] for b in bound))
    def semantics(s):return {b['portion']:(b['function'],b['circuit_identifier'],{p['id']:(p['side'],p['pin'],p['triangle']) for p in b['ports']}) for b in s['boxes']}
    check('All45portions133ports canonicalfunctions circuitIDs and semanticIDs unchanged',semantics(spec)==semantics(previous) and len(spec['boxes'])==45 and sum(len(b['ports']) for b in spec['boxes'])==133)
    check('All40physicalcontactroles and8powercontacts unchanged',sorted((p['pin'],p['side']) for p in spec['exterior_pins'])==sorted((p['pin'],p['side']) for p in previous['exterior_pins']) and spec['power_contacts']==previous['power_contacts'] and len(spec['exterior_pins'])==40)
    check('Exact62terminal partitions unchanged',spec['nets']==previous['nets'] and len(spec['nets'])==62)
    check('All17variant symbols/polarity combinations unchanged',{v['number']:v['box_overrides'] for v in spec['variants']}=={v['number']:v['box_overrides'] for v in previous['variants']})
    outputs,validation=G.build(spec)
    check('All18candidate files match exact newly rendered UTF8 bytes',len(outputs)==18 and all((stage/n).read_bytes()==raw for n,raw in outputs.items()))
    traced=trace(spec)
    check('Independentvisibletrace retains62separate net identities',set(traced)=={tuple(n) for n in previous['nets']})
    check('All electrical networks connected and acyclic',all(len(c['edges'])==len(c['nodes'])-1 for c in traced.values()))
    boxes={b['portion']:b for b in spec['boxes']};meta=evidence['relayout']['layout_hints']['metrics'];modules=meta['convergent_modules'];anchors=meta['termination_anchors'];profiles=[]
    for m in modules:
        c=boxes[m['collector']];sources=[boxes[s] for s in m['parallel_sources']];low=min(s['top'] for s in sources);high=max(s['top']+s['height']-1 for s in sources);center=c['top']+(c['height']-1)/2
        allowed=set(m['parallel_sources'])|{r for r,a in anchors.items() if a in m['parallel_sources']}
        occupants={b['portion'] for b in boxes.values() if b['x']==sources[0]['x'] and low<=b['top']<=high}
        profiles.append(dict(collector=m['collector'],sources=m['parallel_sources'],source_span=[low,high],source_span_center=(low+high)/2,collector_center=center,unrelated_intervening_blocks=sorted(occupants-allowed)))
    check('Four fanin modules identified directly from topology',len(profiles)==4 and {p['collector'] for p in profiles}=={'12','18','24','30'})
    check('Everycollector centered exactly within its own fanin family',all(p['collector_center']==p['source_span_center'] for p in profiles),profiles)
    check('Primitive sibling gates stay contiguous with related Rterminations',all(not p['unrelated_intervening_blocks'] for p in profiles))
    check('Collectors remain separate instead of flattened sibling unit',not any({'12','18','24'}<=set(g) for g in meta['sibling_groups']))
    followers={'12':['31','32'],'18':['33','34'],'24':['36','37'],'30':['38','39']};followerprofiles=[]
    for c,fs in followers.items():
        middle=(min(boxes[p]['top'] for p in fs)+max(boxes[p]['top']+boxes[p]['height']-1 for p in fs))/2
        followerprofiles.append(dict(collector=c,follower_center=middle,collector_center=boxes[c]['top']+3))
    check('Related outputbuffer pairs stay beside their own collector',all(abs(p['follower_center']-p['collector_center'])<=1 for p in followerprofiles),followerprofiles)
    groups={a:sorted([r for r,aa in anchors.items() if aa==a],key=lambda r:boxes[r]['top']) for a in set(anchors.values())};gap=evidence['relayout']['layout_hints']['row_gap']
    check('Terminatingresistors stay directly underneath related gates',all(boxes[r]['x']==boxes[a]['x'] and boxes[r]['top']==boxes[a]['top']+boxes[a]['height']+gap+i*(7+gap) for a,rs in groups.items() for i,r in enumerate(rs)))
    vertical={(m['x'],m['y']) for m in spec['wiring']['marks'] if m['symbol'] in '│┌┐└┘┼' or m['symbol']=='◇' and set(m['arms'])&set('NS')};obs=[]
    for b in boxes.values():
        obs.extend((y,b['x'],b['x']+7) for y in range(b['top'],b['top']+b['height']))
        for p in b['ports']:
            if p['pin']:obs.append((p['row'],b['x']-3,b['x']-1) if p['side']=='input' else (p['row'],b['x']+8,b['x']+10))
    check('Independent two-cell box/pin clearance',all(not(y==yy and l-2<=x<=r+2) for x,y in vertical for yy,l,r in obs))
    check('Independent one-column parallel-track clearance',not any((x+1,y) in vertical for x,y in vertical))
    synthetic=read(HERE/'Convergent module synthetic review.json');check('Generic three-modules-plus-parent counterexample passes5checks',synthetic['passed'] and len(synthetic['checks'])==5 and all(sha(Path(b['path']))==b['sha256'] for b in synthetic['candidate_bindings']))
    tree=ast.parse((ROOT/'tools/card_ald/graph_card_layout.py').read_text(encoding='utf-8-sig'));fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='plan');literals=[n.value for n in ast.walk(fn) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
    check('Planner has no literal cardnumber pin or portion-specific branch',not any(re.fullmatch(r'\d{4}|[BDGJ](?:0[2-9]|1[0-3])|[A-Z]\d',s) for s in literals))
    graph=read(HERE/'Graph layout independent review.json');data=read(HERE/'Card data independent preflight.json')
    check('Final full graph and default124file regressions pass on stable sources',graph['passed'] and len(graph['checks'])==42 and set(graph['details'])=={'0141','4191','4633','4634'} and data['passed'] and all(sha(Path(b['path']))==b['sha256'] for d in [graph,data] for b in d['candidate_bindings']))
    check('Fresh full4191build exactly reproduces frozen module candidate',read(HERE/'4191 graph candidate.json')==spec)
    metrics_before,metrics_after=metrics(previous),metrics(spec);preview('4191 modules final',outputs['4191.txt'].decode('utf-8').splitlines())
    sourcearchive=ROOT/'tools/legacy/card_ald/before-convergent-module-placement';archives=[sourcearchive/'Archive bindings.json']+list(sourcearchive.glob('*.py'))
    receipt=dict(schema='independent-convergent-module-card-review-v1',card_type='4191',passed=not failures,failures=failures,checks=checks,reviewed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),validation=validation,module_profiles=profiles,independent_metrics={'before':metrics_before,'after':metrics_after},layout_recommendation='Retain current published4191; coherent candidate kept as private preview. Universal planner fix is validated.',visual_review='JuliaMono inspected: four distinct gate/collector modules and nearby outputbuffer pairs are coherent; shared clock/feedback tracks and terminating resistors remain readable. Candidate is wider and has more crossings/bends than the existing manual layout, although substantially shorter.',candidate_bindings=[bind(frozen),bind(defpath),bind(overlaypath)]+[bind(Path(b['path'])) for b in bound]+graph['candidate_bindings'],supporting_files=[bind(HERE/n) for n in ['review_4191_modules.py','review_boundary_card.py','review_graph_layout.py','Graph layout independent review.json','check_convergent_modules.py','Convergent module synthetic review.json','4191 modules final graph visual.png']]+[bind(p) for p in archives])
    out=HERE/'other-cards-20261016/4191 modules independent review.json';assert not out.exists(),'Preserve earlier module review before replacing';out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(passed=not failures,failures=failures,checks=len(checks))))
if __name__=='__main__':main()

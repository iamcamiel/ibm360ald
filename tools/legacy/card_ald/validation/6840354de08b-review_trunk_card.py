import sys,json,hashlib,datetime,copy,ast,re
from pathlib import Path
ROOT=Path('D:/Github/IBM360/ibm360ald');HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/card_ald'))
sys.path.insert(0,str(ROOT.parent/'tmp/ald-text/card-layout-deps'))
import generate_card as G,build_card_data as B,render_composite_card as R
from review_boundary_card import trace
from review_graph_layout import metrics,preview
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return dict(path=str(p),sha256=sha(p))
def xyedges(component):return {tuple(sorted((a[:2],b[:2]))) for a,b in component['edges']}
def horizontal(x1,x2,y):return {tuple(sorted(((x,y),(x+1,y)))) for x in range(min(x1,x2),max(x1,x2))}
def vertical(x,y1,y2):return {tuple(sorted(((x,y),(x,y+1)))) for y in range(min(y1,y2),max(y1,y2))}
def main():
    stage=ROOT.parent/'tmp/ald-text/ald/card-data/4633-trunk-optimized';frozen=stage/'4633 fanout trunk candidate freeze.json';freeze=read(frozen)
    priorpath=ROOT.parent/'tmp/ald-text/ald/card-data/4633-boundary-j11/4633.json';old=read(priorpath);spec=read(stage/'4633.json')
    checks=[];failures=[]
    def check(name,ok,detail=None):
        checks.append(dict(name=name,passed=bool(ok),detail=detail))
        if not ok:failures.append(name)
    bound=[freeze['definition'],freeze['evidence']]+freeze['files']
    check('Every frozen candidate hash current',all(sha(Path(b['path']))==b['sha256'] for b in bound))
    check('All boxes semanticports canonicalforms and19variants unchanged',all(old[k]==spec[k] for k in ['canvas','boxes','variants','power_contacts']))
    check('Exact59 physical/semantic terminal partitions unchanged',old['nets']==spec['nets'] and len(spec['nets'])==59)
    outputs,validation=G.build(spec);before_outputs,_=G.build(old)
    check('All20 rendered files exactly match frozen candidate bytes',len(outputs)==20 and all((stage/n).read_bytes()==raw for n,raw in outputs.items()))
    check('All20headers unchanged',all(raw.splitlines()[:7]==before_outputs[n].splitlines()[:7] for n,raw in outputs.items()))
    pins={p['pin']:p for p in spec['exterior_pins']};boxes={b['portion']:b for b in spec['boxes']};lines=outputs['4633.txt'].decode('utf-8').splitlines()
    check('J11 remains belowK8 with straight tail to exterior',pins['J11']['row']>boxes['K8']['top']+boxes['K8']['height']-1 and set(lines[pins['J11']['row']][boxes['K8']['x']:pins['J11']['x']])=={'─'})
    check('B10 straight output and B13/G04 order retained',set(lines[pins['B10']['row']][boxes['A8']['x']+11:pins['B10']['x']])=={'─'} and pins['B13']['row']>pins['B10']['row'] and pins['G04']['row']>pins['J06']['row'])
    check('Exteriorpins retain physical identities and directions',sorted((p['pin'],p['side'],p['x']) for p in old['exterior_pins'])==sorted((p['pin'],p['side'],p['x']) for p in spec['exterior_pins']))
    prior=trace(old);current=trace(spec)
    check('Independent visible graph retains exact separate net partitions',set(prior)==set(current)=={tuple(n) for n in spec['nets']})
    check('All59 electrical networks are acyclic connected trees',all(len(v['edges'])==len(v['nodes'])-1 for v in current.values()))
    reports=spec['provenance']['fanout_trunk_optimization']['changes'];changedpins={r['pin'] for r in reports}
    changedkeys={labels for labels in prior if xyedges(prior[labels])!=xyedges(current[labels])}
    check('Only declared shared fanout nets change their routes',changedkeys=={labels for labels in prior if any('PIN:'+p in labels for p in changedpins)},{'changed_pins':sorted(changedpins),'unchanged_networks':len(prior)-len(changedkeys)})
    j10=next(v for labels,v in current.items() if 'PIN:J10' in labels);edges=xyedges(j10);row=pins['J10']['row'];rise=next(r['source_riser_x'] for r in reports if r['pin']=='J10')
    source=boxes['K4'];out=next(p for p in source['ports'] if p['side']=='output' and p['pin']=='J10')
    expected=horizontal(source['x']+8,rise,out['row'])|vertical(rise,out['row'],row)|horizontal(rise,pins['J10']['x']+2,row)
    sinks=[boxes['K6'],boxes['K7']]
    for b in sinks:
        p=next(p for p in b['ports'] if p['side']=='input' and p['pin']=='J10');drop=(b['x']-6)//2*2
        expected|=vertical(drop,row,p['row'])|horizontal(drop,b['x']-1,p['row'])
    check('J10 is exactly one source riser full horizontal trunk and short sinkdrops',edges==expected,{'rise':rise,'trunk_row':row})
    check('J10selectedbus lies above or below all receiver boxes',row<min(b['top'] for b in sinks) or row>=max(b['top']+b['height'] for b in sinks))
    before,after=metrics(old),metrics(spec)
    check('Routing objective improves13cross93bend→13cross85bend',before['crossings']==after['crossings']==13 and before['bends']==93 and after['bends']==85 and after['wire_cells']==4700)
    # Independently enumerate actual geometric clearance from the visible marks.
    vert={(m['x'],m['y']) for m in spec['wiring']['marks'] if m['symbol'] in '│┌┐└┘┼' or m['symbol']=='◇' and set(m['arms'])&set('NS')};obstacles=[]
    for b in spec['boxes']:
        obstacles.extend((y,b['x'],b['x']+7) for y in range(b['top'],b['top']+b['height']))
        for p in b['ports']:
            if p['pin']:obstacles.append((p['row'],b['x']-3,b['x']-1) if p['side']=='input' else (p['row'],b['x']+8,b['x']+10))
    check('Two-clear-cell wire/box/pinlabel spacing preserved',all(not(y==yy and l-2<=x<=r+2) for x,y in vert for yy,l,r in obstacles))
    check('One-clear-column parallel wire spacing preserved',not any((x+1,y) in vert for x,y in vert))
    parsed=ast.parse((ROOT/'tools/card_ald/render_composite_card.py').read_text(encoding='utf-8-sig'))
    funcs=[f for f in parsed.body if isinstance(f,ast.FunctionDef) and f.name in ['_optimize_boundary_pins','optimize_boundary_pins','optimize_fanout_trunks']]
    literals=[n.value for f in funcs for n in ast.walk(f) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
    check('Universal routing functions contain no literal card portion or physicalpin identities',not any(re.fullmatch(r'\d{4}|[BDGJ](?:0[2-9]|1[0-3])|[A-Z]\d',s) for s in literals))
    # A mirrored, renamed card fixture must exercise the LOWER alternative,
    # independently of any named real card, portion, or pin exception.
    evidence=read(stage/'4633 evidence.json');overlay=read(ROOT/'json/Card-ALD/build-overrides/4633.json')
    model=B.reviewed_routing_model(overlay,evidence['derived_model']);model['layout_hints']=evidence['relayout']['layout_hints'];model['card_type']='9998'
    for n in model['portions'].values():n['card_type']='9998'
    geometry=R.prepare(model);geometry,_=R.optimize_boundary_pins(model,geometry);positions,ports,exterior,router=copy.deepcopy(geometry);h=router.height
    for p in positions.values():p['top']=h-p['top']-p['height']
    for p in ports.values():p['point']=(p['point'][0],h-1-p['point'][1])
    for p in exterior.values():p['row']=h-1-p['row']
    flip=lambda xy:(xy[0],h-1-xy[1]);direction=lambda d:{1:3,3:1}.get(d,d)
    router.wires=defaultdict(dict,{flip(p):{net:{direction(d) for d in ds} for net,ds in ns.items()} for p,ns in router.wires.items()})
    router.by_net=defaultdict(set,{n:{flip(p) for p in ps} for n,ps in router.by_net.items()})
    router.blocked={flip(p) for p in router.blocked};router.reserved={flip(p):n for p,n in router.reserved.items()};router.vertical_forbidden={flip(p) for p in router.vertical_forbidden};router.clearance_obstacles={flip(p) for p in router.clearance_obstacles}
    router.virtual_endpoint_directions=defaultdict(lambda:defaultdict(set),{flip(p):defaultdict(set,{n:{direction(d) for d in ds} for n,ds in ns.items()}) for p,ns in router.virtual_endpoint_directions.items()})
    mirrored=(positions,ports,exterior,router);R.verify(model,mirrored);result,report=R.optimize_fanout_trunks(model,mirrored)
    check('Renamed9998 mirrored fixture genuinely selects lower trunks',report['accepted'] and any(r['trunk_side']=='below' for r in report['changes']),{'accepted_sides':[r['trunk_side'] for r in report['changes']]})
    graph=read(HERE/'Graph layout independent review.json');data=read(HERE/'Card data independent preflight.json')
    check('Final full graph42 and data26 regressions pass on unchanged tool sources',graph['passed'] and data['passed'] and all(sha(Path(b['path']))==b['sha256'] for d in [graph,data] for b in d['candidate_bindings']))
    check('Fresh end-to-end builder output exactly equals frozen trunk specification',read(HERE/'4633 graph candidate.json')==spec)
    preview('4633 trunk',lines)
    receipt=dict(schema='independent-universal-trunk-card-review-v1',card_type='4633',passed=not failures,failures=failures,checks=checks,reviewed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),validation=validation,independent_metrics={'before':before,'after':after},candidate_bindings=[bind(frozen),bind(priorpath)]+[bind(Path(b['path'])) for b in bound]+graph['candidate_bindings']+[bind(ROOT/'tools/card_ald/adopt_card_layout.py')],supporting_files=[bind(HERE/n) for n in ['review_trunk_card.py','review_boundary_card.py','review_graph_layout.py','Graph layout independent review.json','4633 trunk graph visual.png']],source_inspection='All exterior pins share the same boundary trials; every eligible shared forward net tries both upper and lower buses. The objective is crossings, bends, then wire length. No named card/pin/portion branch or special layout override exists.')
    (HERE/'4633 trunk independent review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(passed=not failures,failures=failures,checks=len(checks))))
if __name__=='__main__':
    from collections import defaultdict
    main()

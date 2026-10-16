"""Independent, per-family acceptance of unchanged shared-script relayouts."""
import sys,json,hashlib,datetime
from pathlib import Path
ROOT=Path('D:/Github/IBM360/ibm360ald');HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/card_ald'))
import generate_card as G
from review_boundary_card import trace
from review_graph_layout import metrics,preview
CODE=['build_card_data.py','graph_card_layout.py','render_composite_card.py','card_canvas.py','generate_card.py','adopt_card_layout.py','requirements.txt']
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return dict(path=str(p),sha256=sha(p))
def review(card):
    stage=ROOT.parent/'tmp/ald-text/ald/card-data/other-cards-20261016'/card
    target=HERE/'other-cards-20261016';target.mkdir(exist_ok=True)
    defpath=ROOT/'json/Card-ALD/definitions'/f'{card}.json';overlay=ROOT/'json/Card-ALD/build-overrides'/f'{card}.json'
    inputs=[stage/f'{card}.json',stage/f'{card} evidence.json',defpath,overlay]+[ROOT/'tools/card_ald'/n for n in CODE]
    candidate=read(inputs[0]);previous=read(defpath);evidence=read(inputs[1]);outs,validation=G.build(candidate)
    inputs += [stage/n for n in outs]
    snapshots=[bind(p) for p in inputs]
    checks=[];failures=[]
    def check(name,ok,detail=None):
        checks.append(dict(name=name,passed=bool(ok),detail=detail))
        if not ok:failures.append(name)
    check('Candidate/card identity and complete expected family',candidate['card_type']==card and set(outs)=={p.name for p in stage.glob(card+'*.txt')})
    def semantics(spec):return {b['portion']:(b['function'],b['circuit_identifier'],{p['id']:(p['side'],p['pin'],p['triangle']) for p in b['ports']}) for b in spec['boxes']}
    check('Every portion canonical function/circuit and semantic port identity invariant',semantics(candidate)==semantics(previous),{'portions_before':len(previous['boxes']),'portions_after':len(candidate['boxes'])})
    check('Powerpins unchanged',candidate['power_contacts']==previous['power_contacts'])
    check('All exact reviewed terminal partitions unchanged',candidate['nets']==previous['nets'])
    check('All physical contacts retain identities and directions',sorted((p['pin'],p['side']) for p in candidate['exterior_pins'])==sorted((p['pin'],p['side']) for p in previous['exterior_pins']))
    def forms(spec):return {v['number']:v.get('box_overrides',{}) for v in spec['variants']}
    check('Every numbered variant retains exact function/polarity form',forms(candidate)==forms(previous),{'variants':len(candidate['variants'])})
    check('Every expected UTF8 file matches freshly rendered bytes',all((stage/n).read_bytes()==raw for n,raw in outs.items()),{'files':len(outs)})
    oldtrace=trace(previous);newtrace=trace(candidate)
    check('Independent visible-wire trace retains exact separated nets',set(oldtrace)==set(newtrace)=={tuple(n) for n in candidate['nets']})
    check('All visible electrical networks are connected acyclic trees',all(len(c['edges'])==len(c['nodes'])-1 for c in newtrace.values()),{'networks':len(newtrace)})
    vertical={(m['x'],m['y']) for m in candidate['wiring']['marks'] if m['symbol'] in '│┌┐└┘┼' or m['symbol']=='◇' and set(m['arms'])&set('NS')}
    obstacles=[]
    for b in candidate['boxes']:
        obstacles.extend((y,b['x'],b['x']+7) for y in range(b['top'],b['top']+b['height']))
        for p in b['ports']:
            if p['pin']:obstacles.append((p['row'],b['x']-3,b['x']-1) if p['side']=='input' else (p['row'],b['x']+8,b['x']+10))
    check('Two clear cells from vertical wires to boxes or attached pinlabels',all(not(y==yy and left-2<=x<=right+2) for x,y in vertical for yy,left,right in obstacles))
    check('One clear column between parallel vertical wires',not any((x+1,y) in vertical for x,y in vertical))
    # Explicitly verify each variant only changes the permitted function/border
    # cells and header rows, leaving every route and physical label fixed.
    base=outs[card+'.txt'].decode('utf-8').splitlines();variant_errors=[]
    for v in candidate['variants']:
        allowed={(x,y) for y in range(candidate['canvas']['header_rows']) for x in range(candidate['canvas']['width'])}
        for b in candidate['boxes']:
            if b['portion'] not in v.get('box_overrides',{}):continue
            allowed.update((x,b['top']+1) for x in range(b['x']+1,b['x']+7))
            allowed.update((b['x'] if p['side']=='input' else b['x']+7,p['row']) for p in b['ports'])
        lines=outs[f"{card}-{v['number']:02}.txt"].decode('utf-8').splitlines()
        for y,(a,b) in enumerate(zip(base,lines)):
            for x,(ca,cb) in enumerate(zip(a.ljust(candidate['canvas']['width']),b.ljust(candidate['canvas']['width']))):
                if ca!=cb and (x,y) not in allowed:variant_errors.append((v['number'],x,y))
        if len(lines)!=len(base):variant_errors.append((v['number'],'height'))
    check('All variant wire/box/pin geometry exactly common to canonical',not variant_errors,variant_errors[:10])
    check('Candidate is private reviewed-topology graph relayout',bool(evidence.get('relayout',{}).get('terminal_partition_identity_verified')))
    before=metrics(previous);after=metrics(candidate)
    objective=lambda m:(m['crossings'],m['bends'],m['wire_cells'])
    recommendation='adopt candidate' if objective(after)<objective(before) else 'retain existing layout'
    tradeoffs={k:after[k]-before[k] for k in before}
    # Separate structural acceptance from the layout recommendation.
    check('Bound per-card inputs and shared code stable throughout review',all(sha(Path(b['path']))==b['sha256'] for b in snapshots))
    preview(card+' other',base)
    png=HERE/f'{card} other graph visual.png'
    receipt=dict(schema='independent-other-card-relayout-review-v1',card_type=card,reviewed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=not failures,failures=failures,checks=checks,validation=validation,independent_metrics={'before':before,'after':after,'delta':tradeoffs},layout_recommendation=recommendation,candidate_bindings=snapshots,supporting_files=[bind(HERE/n) for n in ['review_other_cards.py','review_boundary_card.py','review_graph_layout.py']]+[bind(png)],visual_review='Pending human inspection by independent reviewer; structural acceptance alone is not publication.')
    path=target/f'{card} independent review.json'
    if path.exists():raise ValueError('Preserve prior acceptance before replacing: '+str(path))
    path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(card=card,passed=not failures,failures=failures,checks=len(checks),recommendation=recommendation,metrics=receipt['independent_metrics']),ensure_ascii=False),flush=True)
if __name__=='__main__':
    for card in sys.argv[1:]:review(card)

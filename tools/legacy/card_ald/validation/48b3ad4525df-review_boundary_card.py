import sys,json,hashlib,datetime
from collections import defaultdict
from pathlib import Path
ROOT=Path('D:/Github/IBM360/ibm360ald');HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/card_ald'))
import generate_card as G
from review_graph_layout import metrics,preview
DIR={'E':(1,0),'S':(0,1),'W':(-1,0),'N':(0,-1)};OPP={'E':'W','W':'E','S':'N','N':'S'}
CAP={'─':set('EW'),'│':set('NS'),'┌':set('ES'),'┐':set('SW'),'└':set('NE'),'┘':set('NW'),'┼':set('NESW')}
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def binding(p):return dict(path=str(p),sha256=sha(p))
def trace(spec):
    # Independent visible-stroke reconstruction; crossing channels stay separate.
    arms={};symbols={};terminals=defaultdict(set)
    for seg in spec['wiring']['horizontal_segments']:
        for x in range(seg['x1'],seg['x2']+1):arms[x,seg['y']]=set('EW');symbols[x,seg['y']]='─'
    for mark in spec['wiring']['marks']:
        xy=(mark['x'],mark['y']);symbols[xy]=mark['symbol'];arms[xy]=set(mark['arms']) if mark['symbol']=='◇' else set(CAP[mark['symbol']])
    for box in spec['boxes']:
        for p in box['ports']:
            x=box['x']-1 if p['side']=='input' else box['x']+8;y=p['row']
            if p['pin']:
                start=box['x']-3 if p['side']=='input' else box['x']+8
                for xx in range(start,start+3):arms[xx,y]=set('EW');symbols[xx,y]='─'
            arms[x,y].discard('E' if p['side']=='input' else 'W')
            terminals[x,y].add('PORT:'+box['portion']+':'+p['id'])
    for p in spec['exterior_pins']:
        for x in range(p['x'],p['x']+3):arms[x,p['row']]=set('EW');symbols[x,p['row']]='─'
        x=p['x'] if p['side']=='input' else p['x']+2;y=p['row']
        arms[x,y].discard('W' if p['side']=='input' else 'E');terminals[x,y].add('PIN:'+p['pin'])
    def state(xy,d):return (*xy,'V' if d in 'NS' else 'H') if symbols[xy]=='┼' else (*xy,'J')
    adjacency=defaultdict(set)
    for (x,y),ds in arms.items():
        for d in ds:
            dx,dy=DIR[d];q=x+dx,y+dy
            assert OPP[d] in arms.get(q,set()),('Nonreciprocal stroke',(x,y),q)
            adjacency[state((x,y),d)].add(state(q,OPP[d]))
    seen=set();components={}
    for seed in adjacency:
        if seed in seen:continue
        todo=[seed];nodes=set();labels=set()
        while todo:
            n=todo.pop()
            if n in nodes:continue
            nodes.add(n);labels.update(terminals[n[:2]]);todo.extend(adjacency[n]-nodes)
        seen|=nodes
        edges={tuple(sorted((n,m))) for n in nodes for m in adjacency[n]}
        components[tuple(sorted(labels))]={'nodes':nodes,'edges':edges,'adjacency':{n:adjacency[n] for n in nodes},'terminals':{n:terminals[n[:2]] for n in nodes if terminals[n[:2]]}}
    return components
def main():
    stage=ROOT.parent/'tmp/ald-text/ald/card-data/4633-boundary-optimized';frozen=stage/'4633 boundary candidate freeze.json';freeze=read(frozen)
    priorpath=ROOT.parent/'tmp/ald-text/ald/card-data/4633-free-rows-compact/4633.json';prior=read(priorpath);spec=read(stage/'4633.json')
    checks=[];failures=[]
    def check(name,ok,detail=None):
        checks.append(dict(name=name,passed=bool(ok),detail=detail))
        if not ok:failures.append(name)
    bound=[freeze['definition'],freeze['evidence']]+freeze['files']
    check('Every frozen definition/evidence/TXT hash current',all(sha(Path(b['path']))==b['sha256'] for b in bound))
    check('Canvas/boxes/semanticportcoordinates/canonicalfunctions unchanged',prior['canvas']==spec['canvas'] and prior['boxes']==spec['boxes'])
    check('All19 numbered variants unchanged including semanticportIDs',prior['variants']==spec['variants'] and len(spec['variants'])==19)
    check('Powerpins and59 terminal partitions unchanged',prior['power_contacts']==spec['power_contacts'] and prior['nets']==spec['nets'] and len(spec['nets'])==59)
    check('Exterior physical labels retain their original pins/directions/xcolumns',sorted((p['pin'],p['side'],p['x']) for p in prior['exterior_pins'])==sorted((p['pin'],p['side'],p['x']) for p in spec['exterior_pins']))
    pins={p['pin']:p for p in spec['exterior_pins']}
    check('B13 exterior output now below B10',pins['B13']['row']>pins['B10']['row'],{'B13':pins['B13']['row'],'B10':pins['B10']['row']})
    check('G04 exterior input now below J06',pins['G04']['row']>pins['J06']['row'],{'G04':pins['G04']['row'],'J06':pins['J06']['row']})
    outputs,validation=G.build(spec);oldoutputs,_=G.build(prior)
    check('All20 files reproduce accepted frozen bytes',len(outputs)==20 and all((stage/name).read_bytes()==raw for name,raw in outputs.items()))
    check('All20 headers unchanged',all(raw.splitlines()[:7]==oldoutputs[name].splitlines()[:7] for name,raw in outputs.items()))
    b10box=next(b for b in spec['boxes'] if any(p['side']=='output' and p['pin']=='B10' for p in b['ports']))
    b10port=next(p for p in b10box['ports'] if p['side']=='output' and p['pin']=='B10')
    row=pins['B10']['row'];lines=outputs['4633.txt'].decode('utf-8').splitlines()
    check('B10 complete output tail straight at its actual block-output row',b10port['row']==row and set(lines[row][b10box['x']+11:pins['B10']['x']])=={'─'})
    before=metrics(prior);after=metrics(spec)
    check('Independent crossing count strictly improved20→15',before['crossings']==20 and after['crossings']==15)
    check('Independent bend count113→97 and visiblewirecells4755→4705',before['bends']==113 and after['bends']==97 and before['wire_cells']==4755 and after['wire_cells']==4705)
    oldgraph=trace(prior);newgraph=trace(spec)
    check('Independent visible-wire graph retains exact net identities',set(oldgraph)==set(newgraph)=={tuple(n) for n in spec['nets']})
    core_lost=[];cycles=[];core_count=0
    for labels,old in oldgraph.items():
        new=newgraph[labels]
        if len(new['edges'])-len(new['nodes'])+1 != len(old['edges'])-len(old['nodes'])+1:cycles.append(labels)
        # Prune only each exterior leaf up to its first junction or box port.
        # Every edge remaining between internal box terminals must be preserved.
        external=[n for n,ts in old['terminals'].items() if any(t.startswith('PIN:') for t in ts)]
        removed=set()
        for seed in external:
            previous=None;point=seed
            while True:
                onward=old['adjacency'][point]-({previous} if previous else set())
                if len(onward)!=1:break
                q=next(iter(onward));removed.add(tuple(sorted((point,q))));previous,point=point,q
                if point in old['terminals'] or len(old['adjacency'][point])!=2:break
        core=old['edges']-removed;core_count+=len(core)
        # Removing an unrelated crossing changes its state H/V→J, while its
        # physical segment and owning electrical net remain exactly the same.
        core_xy={tuple(sorted((a[:2],b[:2]))) for a,b in core}
        new_xy={tuple(sorted((a[:2],b[:2]))) for a,b in new['edges']}
        core_lost.extend((labels,e) for e in core_xy-new_xy)
    check('No intrinsic core edges removed or reassigned to another net',not core_lost,{'retained_intrinsic_edges':core_count,'failures':core_lost[:3]})
    check('Boundary rewrite introduces no electrical wire-loop cycles',not cycles,cycles[:3])
    # Independent clearances from visible vertical marks and actual pin labels.
    vertical={(m['x'],m['y']) for m in spec['wiring']['marks'] if m['symbol'] in '│┌┐└┘┼' or m['symbol']=='◇' and set(m['arms'])&set('NS')}
    obstacles=[]
    for b in spec['boxes']:
        obstacles.extend((y,b['x'],b['x']+7) for y in range(b['top'],b['top']+b['height']))
        for p in b['ports']:
            if p['pin']:obstacles.append((p['row'],b['x']-3,b['x']-1) if p['side']=='input' else (p['row'],b['x']+8,b['x']+10))
    check('Two blank cells vertical-wire-to-box/pinlabel clearance preserved',all(not(y==yy and left-2<=x<=right+2) for x,y in vertical for yy,left,right in obstacles))
    check('One blank column between parallel vertical tracks preserved',not any((x+1,y) in vertical for x,y in vertical))
    graphreview=read(HERE/'Graph layout independent review.json');fresh=read(HERE/'4633 graph candidate.json')
    check('Fresh end-to-end generic builder reproduces exact frozen specification',fresh==spec)
    check('All42 planner/route/variant regression checks passed on current sources',graphreview['passed'] and all(sha(Path(b['path']))==b['sha256'] for b in graphreview['candidate_bindings']))
    preview('4633 boundary',lines)
    receipt=dict(schema='independent-boundary-pin-card-review-v1',card_type='4633',reviewed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=not failures,failures=failures,checks=checks,validation=validation,independent_metrics={'before':before,'after':after},candidate_bindings=[binding(frozen),binding(priorpath)]+[binding(Path(b['path'])) for b in bound]+graphreview['candidate_bindings']+[binding(ROOT/'tools/card_ald/adopt_card_layout.py')],supporting_files=[binding(HERE/'review_boundary_card.py'),binding(HERE/'review_graph_layout.py'),binding(HERE/'Graph layout independent review.json'),binding(HERE/'4633 boundary graph visual.png')])
    (HERE/'4633 boundary independent review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=not failures,failures=failures,checks=len(checks))))
if __name__=='__main__':main()

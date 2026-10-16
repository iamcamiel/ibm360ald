"""Preview compact shared-net resistor terminations without moving other blocks.

Usage: python tools/card_ald/compact_terminations.py 4191 --output-dir PRIVATE
Default AUTO: retain reviewed free-row geometry (grid_step=1), otherwise run
the current universal free-row planner, then compact R notation. --relayout
forces fresh placement; --keep-layout deliberately retains any published grid.
Published files remain unchanged; the output is a private preview. The pure
transform(spec) API preserves box placement and rewrites only eligible R and
exterior leaf wiring, preserving all intrinsic connections.
"""
import argparse
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import generate_card as renderer
from build_card_data import compact_segments

ROOT=Path(__file__).resolve().parents[2]
D={'E':(1,0),'S':(0,1),'W':(-1,0),'N':(0,-1)}
OP={'E':'W','W':'E','N':'S','S':'N'}
GLYPHS={frozenset(v):k for k,v in {'─':'EW','│':'NS','┌':'ES','┐':'WS','└':'EN','┘':'WN'}.items()}

def primary(function):
    parts=function.strip().split()
    return parts[0] if parts else ''

def classification(spec):
    netof={terminal:i for i,net in enumerate(spec['nets']) for terminal in net}
    result=[]
    for box in spec['boxes']:
        if primary(box['function'])!='R':continue
        ports=box['ports'];inputs=[p for p in ports if p['side']=='input'];outputs=[p for p in ports if p['side']=='output']
        reason=None
        if len(inputs)!=1 or outputs:reason='Requires exactly one input and no output'
        if reason is None:
            terminal='PORT:'+box['portion']+':'+inputs[0]['id'];index=netof[terminal]
            if not any(t.startswith('PORT:') and not t.startswith('PORT:'+box['portion']+':') for t in spec['nets'][index]):reason='Standalone termination: no other block on its net'
            elif any(primary(v.get('box_overrides',{}).get(box['portion'],{}).get('function',box['function']))!='R' for v in spec['variants']):reason='A notation variant has a non-R primary function'
        result.append({'portion':box['portion'],'eligible':reason is None,'reason':reason})
    return result

def graph(spec):
    """Visible wire layers plus implicit printed label contacts, split at crosses."""
    cells={};visible=set();terminals=defaultdict(set);removed=defaultdict(set)
    for seg in spec['wiring']['horizontal_segments']:
        for x in range(seg['x1'],seg['x2']+1):cells[x,seg['y']]={'symbol':'─','arms':set('EW')};visible.add((x,seg['y']))
    for mark in spec['wiring']['marks']:
        xy=mark['x'],mark['y'];cells[xy]={'symbol':mark['symbol'],'arms':set(mark.get('arms',renderer.ARMS[mark['symbol']]))};visible.add(xy)
    for box in spec['boxes']:
        compact=box.get('compact_termination')
        for port in box['ports']:
            if compact:
                xy=tuple(compact['point']);removed[xy].add('E')
            else:
                xy=(box['x']-1 if port['side']=='input' else box['x']+8,port['row']);removed[xy].add('E' if port['side']=='input' else 'W')
                if port['pin']:
                    start=box['x']-3 if port['side']=='input' else box['x']+8
                    for x in range(start,start+3):
                        assert (x,port['row']) not in cells
                        cells[x,port['row']]={'symbol':'─','arms':set('EW')}
            terminals[xy].add('PORT:'+box['portion']+':'+port['id'])
    for pin in spec['exterior_pins']:
        for x in range(pin['x'],pin['x']+3):
            xy=x,pin['row'];assert xy not in cells;cells[xy]={'symbol':'─','arms':set('EW')}
        xy=(pin['x'] if pin['side']=='input' else pin['x']+2,pin['row']);removed[xy].add('W' if pin['side']=='input' else 'E');terminals[xy].add('PIN:'+pin['pin'])
    adjacency=defaultdict(set)
    def state(xy,d):return xy+(('V' if d in 'NS' else 'H') if cells[xy]['symbol']=='┼' else 'J',)
    for xy,cell in cells.items():
        for d in cell['arms']-removed[xy]:
            dx,dy=D[d];q=xy[0]+dx,xy[1]+dy
            assert q in cells and OP[d] in cells[q]['arms']-removed[q],('Dangling geometry',xy,d)
            adjacency[state(xy,d)].add(state(q,OP[d]))
    expected={frozenset(n):i for i,n in enumerate(spec['nets'])};visited=set();layers=defaultdict(dict);node_net={}
    for start in adjacency:
        if start in visited:continue
        todo=[start];component=set();found=set()
        while todo:
            node=todo.pop()
            if node in component:continue
            component.add(node);found|=terminals[node[:2]];todo.extend(adjacency[node]-component)
        visited|=component
        assert frozenset(found) in expected,('Unexpected terminal component',sorted(found))
        net=expected[frozenset(found)]
        for node in component:
            node_net[node]=net;xy=node[:2]
            if xy in visible:
                # Keep virtual label arms in displayed endpoint glyphs.
                dirs=set(cells[xy]['arms'])
                if cells[xy]['symbol']=='┼':dirs&=set('NS' if node[2]=='V' else 'EW')
                layers[xy][net]=dirs
    return adjacency,terminals,layers,node_net

def rewrite(spec,layers):
    cells={}
    for xy,nets in layers.items():
        if not nets:continue
        if len(nets)>1:char,arms='┼',set('NESW')
        else:
            arms=next(iter(nets.values()));char='◇' if len(arms)>=3 else GLYPHS[frozenset(arms)]
        cells[xy]=char,arms
    spec['wiring']=compact_segments(cells)

def label_width(spec,box):
    suffix=' '+box['circuit_identifier']+' '+box['portion']
    labels=[box['function']+suffix]+[v.get('box_overrides',{}).get(box['portion'],{}).get('function',box['function'])+suffix for v in spec['variants']]
    return max(len(labels[0])+3,max(map(len,labels)))

def text_obstacles(spec):
    occupied=set();labels=set()
    for box in spec['boxes']:
        compact=box.get('compact_termination')
        if compact:
            x,y=compact['point'];labels.update((xx,y) for xx in range(x+1,x+1+compact['label_width']))
            continue
        x,y,h=box['x'],box['top'],box['height'];occupied.update((xx,yy) for xx in range(x,x+8) for yy in range(y,y+h))
        for port in box['ports']:
            if port['pin']:
                start=x-3 if port['side']=='input' else x+8;labels.update((xx,port['row']) for xx in range(start,start+3))
    for pin in spec['exterior_pins']:labels.update((xx,pin['row']) for xx in range(pin['x'],pin['x']+3))
    for a in spec['annotations']:labels.update((xx,a['row']) for xx in range(a['x'],a['x']+len(a['text'])))
    return occupied|labels

def cleanup_termination_inputs(spec):
    """Straighten a single gate's external input and rehang its passive stubs."""
    best=spec;changes=[]
    def score(layers):
        return (sum(len(n)>1 for n in layers.values()),
                sum(len(a)==2 and a not in (set('EW'),set('NS')) for n in layers.values() for a in n.values()),
                sum(bool(n) for n in layers.values()))
    for index,net in enumerate(spec['nets']):
        portions={t.split(':',2)[1] for t in net if t.startswith('PORT:')}
        boxes=[b for b in best['boxes'] if b['portion'] in portions]
        stubs=[b for b in boxes if b.get('compact_termination')]
        real=[b for b in boxes if not b.get('compact_termination')]
        outside=[p for p in best['exterior_pins'] if 'PIN:'+p['pin'] in net]
        if not stubs or len(real)!=1 or len(outside)!=1 or outside[0]['side']!='input':continue
        ports=[p for p in real[0]['ports'] if 'PORT:'+real[0]['portion']+':'+p['id'] in net]
        if len(ports)!=1 or ports[0]['side']!='input':continue
        target=real[0];port=ports[0];row=port['row'];end=target['x']-(4 if port['pin'] else 1)
        if any(p['side']=='input' and p['row']==row and p['pin']!=outside[0]['pin'] for p in best['exterior_pins']):continue
        trial=deepcopy(best);_,_,layers,_=graph(trial);before_score=score(layers)
        for nets in layers.values():nets.pop(index,None)
        for b in trial['boxes']:
            if b['portion'] in {x['portion'] for x in stubs}:b['compact_termination']['point']=[-100,-100]
        next(p for p in trial['exterior_pins'] if p['pin']==outside[0]['pin'])['row']=row
        obstacles=text_obstacles(trial);valid=True
        for x in range(3,end+1):
            if (x,row) in obstacles or any(arms!=set('NS') for arms in layers[x,row].values()):valid=False;break
            layers[x,row][index]=set('EW')
        if not valid:continue
        replacements=[]
        for stub in stubs:
            box=next(b for b in trial['boxes'] if b['portion']==stub['portion']);width=box['compact_termination']['label_width']
            wires={xy for xy,nets in layers.items() if nets}
            vertical={xy for xy,nets in layers.items() if any(set('NS')&a for a in nets.values())}
            options=[]
            for x in range(3,end+1):
                if len(layers[x,row])!=1:continue
                reserved={(xx,row+1) for xx in range(x,x+width+1)}
                if x+width>=trial['canvas']['width']-3 or row+1>=trial['canvas']['height']:continue
                if reserved&(obstacles|wires):continue
                if any(abs(x-xx)<3 and yy in (row,row+1) for xx,yy in obstacles):continue
                if any(abs(x-xx)<2 and yy in (row,row+1) for xx,yy in vertical):continue
                if any(abs(xx-vx)<3 and vy==row+1 for xx,yy in reserved if xx!=x for vx,vy in vertical):continue
                options.append((abs(end-x),x))
            if not options:valid=False;break
            _,x=min(options);box['compact_termination']['point']=[x,row+1];layers[x,row][index].add('S');layers[x,row+1][index]=set('NE')
            replacements.append({'portion':box['portion'],'old_point':stub['compact_termination']['point'],'point':[x,row+1]})
            obstacles=text_obstacles(trial)
        if not valid:continue
        rewrite(trial,layers)
        try:renderer.validate(trial)
        except (AssertionError,KeyError):continue
        after_score=score(layers)
        if after_score>=before_score:continue
        assert trial['nets']==best['nets']
        changes.append({'net':index,'pin':outside[0]['pin'],'old_exterior_row':outside[0]['row'],'row':row,
                        'stubs':replacements,'before_crossings_bends_cells':before_score,'after_crossings_bends_cells':after_score})
        best=trial
    return best,{'method':'Single functional input plus exterior and compact passive leaves: compare straight input with directly rehung stubs; strict visible crossing/bend/length improvement','changes':changes}


def transform(spec):
    candidate=deepcopy(spec);report={'schema':'compact-termination-preview-v1','classification':classification(spec),'changes':[],'unresolved':[]}
    for item in report['classification']:
        if not item['eligible']:continue
        box=next(b for b in candidate['boxes'] if b['portion']==item['portion']);port=box['ports'][0]
        adjacency,terminals,layers,node_net=graph(candidate)
        start=(box['x']-1,port['row'],'J');assert start in adjacency
        net=node_net[start];path=[start];previous=None
        while True:
            node=path[-1]
            if len(path)>1 and (len(adjacency[node])!=2 or terminals[node[:2]]):break
            choices=adjacency[node]-({previous} if previous else set())
            assert len(choices)==1,('R input is not an unambiguous leaf',item)
            previous=node;path.append(next(iter(choices)))
        attachment=path[-1]
        for node in path[:-1]:
            xy=node[:2]
            if xy in layers:layers[xy].pop(net,None)
        if attachment[:2] in layers:
            a=attachment[:2];b=path[-2][:2];direction=next(d for d,delta in D.items() if (a[0]+delta[0],a[1]+delta[1])==b);layers[a][net].discard(direction)
        before=deepcopy(box);width=label_width(candidate,box)
        # Temporarily suppress the old box and its pin labels for placement.
        box['compact_termination']={'point':[0,0],'label_width':width}
        obstacles=text_obstacles(candidate)-{(xx,0) for xx in range(1,width+1)}
        wires={xy for xy,nets in layers.items() if nets}
        vertical={xy for xy,nets in layers.items() if any(set('NS')&arms for arms in nets.values())}
        other_ports=[]
        for b in candidate['boxes']:
            if b['portion']==box['portion'] or b.get('compact_termination'):continue
            for p in b['ports']:
                t='PORT:'+b['portion']+':'+p['id']
                if t in candidate['nets'][net]:other_ports.append((b['x']-1 if p['side']=='input' else b['x']+8,p['row']))
        choices=[]
        for (x,y),nets in layers.items():
            if len(nets)!=1 or nets.get(net)!=set('EW'):continue
            point=x,y+1;reserved={(xx,y+1) for xx in range(x,x+width+1)}
            if x<3 or x+width>=candidate['canvas']['width']-3 or y+1>=candidate['canvas']['height']:continue
            if reserved&(obstacles|wires):continue
            if any(abs(x-xx)<3 and yy in (y,y+1) for xx,yy in obstacles):continue
            if any(abs(x-xx)<2 and yy in (y,y+1) for xx,yy in vertical):continue
            if any(abs(xx-vx)<3 and vy==y+1 for xx,yy in reserved if xx!=x for vx,vy in vertical):continue
            distance=min((abs(x-px)+abs(y-py) for px,py in other_ports),default=0)
            choices.append((distance,abs(x-attachment[0])+abs(y-attachment[1]),y,x))
        if not choices:
            box.clear();box.update(before);report['unresolved'].append({'portion':item['portion'],'reason':'No collision-free horizontal main-net segment has room below for reserved variant label'});continue
        _,_,y,x=min(choices);box['compact_termination']={'point':[x,y+1],'label_width':width};layers[x,y][net].add('S');layers[x,y+1][net]=set('NE')
        rewrite(candidate,layers)
        report['changes'].append({'portion':item['portion'],'net':net,'old_leaf_path_steps':len(path)-1,'attachment':list(attachment[:2]),'point':[x,y+1],'label_width':width})
    candidate,cleanup=cleanup_termination_inputs(candidate)
    report['exterior_termination_cleanup']=cleanup
    assert renderer.wiring_graph(candidate)==spec['nets']
    candidate['provenance']=deepcopy(candidate.get('provenance',{}));candidate['provenance']['compact_termination_preview']=report
    candidate.pop('layout_validation',None)
    return candidate,report

def layout_policy(spec, mode='auto'):
    """Universal metadata-based placement decision; never rank old grids by score."""
    if mode not in ('auto','force','keep'):raise ValueError('Unknown placement mode: '+mode)
    free=spec['canvas'].get('grid_step',7)==1
    action='relayout' if mode=='force' or (mode=='auto' and not free) else 'reuse-free' if free else 'keep-explicit'
    return {'mode':mode,'action':action,'input_grid_step':spec['canvas'].get('grid_step',7),
            'reason':'Preserve reviewed free placement and routing' if action=='reuse-free' else
                     'Current universal free-row planner required' if action=='relayout' else 'Published geometry retained by explicit request'}


def prepare_layout(card_type, spec, mode='auto'):
    origin=layout_policy(spec,mode)
    if origin['action']=='relayout':
        from build_card_data import build
        result,evidence=build(card_type,root=ROOT,relayout=True)
        if result is None:raise ValueError('Universal relayout did not produce a validated definition')
    else:result,evidence=deepcopy(spec),{'retained_reviewed_definition':True}
    wording_changes=0
    if result['canvas'].get('grid_step',7)==1:
        annotations=result['annotations']+[a for v in result['variants'] for a in v.get('annotation_overrides',[])]
        for annotation in annotations:
            old=annotation['text']
            if 'SEVEN-LINE BOX GRID' not in old:continue
            new=old.replace('SEVEN-LINE BOX GRID','SEVEN-LINE BOXES; FREE VERTICAL PLACEMENT')
            if annotation.get('x',0)+len(new)>result['canvas']['width']:
                new=old.replace('SEVEN-LINE BOX GRID','7-HIGH; FREE ROWS')
            annotation['text']=new;wording_changes+=1
    origin['free_placement_header_updates']=wording_changes
    evidence['layout_origin']=origin
    return result,evidence,origin


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('card_type');parser.add_argument('--output-dir',type=Path,required=True)
    placement=parser.add_mutually_exclusive_group()
    placement.add_argument('--relayout',dest='placement_mode',action='store_const',const='force',help='Force fresh universal free-row placement/routing, including definitions already on a free grid')
    placement.add_argument('--keep-layout',dest='placement_mode',action='store_const',const='keep',help='Deliberately retain any published placement before compact R')
    parser.set_defaults(placement_mode='auto')
    args=parser.parse_args()
    source=ROOT/'json/Card-ALD/definitions'/(args.card_type+'.json')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    published={'path':str(source.resolve()),'sha256':sha256(source.read_bytes()).hexdigest()}
    try:spec,evidence,origin=prepare_layout(args.card_type,renderer.read(source),args.placement_mode)
    except ValueError as exc:parser.error(str(exc))
    origin['published_definition']=published
    evidence_path=args.output_dir/(args.card_type+' relayout evidence.json')
    evidence_path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    source=args.output_dir/(args.card_type+' relayout input.json')
    source.write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    candidate,report=transform(spec)
    report['pipeline']='ensure reviewed free-row placement, then compact terminations'
    report['layout_origin']=origin
    report['source_definition']={'path':str(source.resolve()),'sha256':sha256(source.read_bytes()).hexdigest()}
    report['transformer']={'path':str(Path(__file__).resolve()),'sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    (args.output_dir/(args.card_type+'.json')).write_text(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n',encoding='utf8');(args.output_dir/'Compact termination report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    files,validation=renderer.build(candidate)
    for name,raw in files.items():(args.output_dir/name).write_bytes(raw)
    print(json.dumps({'card_type':args.card_type,'compact':len(report['changes']),'unresolved':len(report['unresolved']),'validation':validation}))
if __name__=='__main__':main()

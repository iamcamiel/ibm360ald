"""Independent channel-aware trace including compact terminating nodes."""
from collections import defaultdict

DIRS={'E':(1,0),'W':(-1,0),'N':(0,-1),'S':(0,1)}
OPP={'E':'W','W':'E','N':'S','S':'N'}
ARMS={'─':'EW','│':'NS','┌':'ES','┐':'WS','└':'EN','┘':'WN','┼':'NSEW'}

def trace(spec):
    strokes={};symbols={};labels=defaultdict(set)
    for seg in spec['wiring']['horizontal_segments']:
        for x in range(seg['x1'],seg['x2']+1):
            assert (x,seg['y']) not in strokes
            strokes[x,seg['y']]=set('EW');symbols[x,seg['y']]='─'
    for mark in spec['wiring']['marks']:
        xy=mark['x'],mark['y'];assert xy not in strokes
        strokes[xy]=set(mark['arms'] if mark['symbol']=='◇' else ARMS[mark['symbol']]);symbols[xy]=mark['symbol']
    for box in spec['boxes']:
        for port in box['ports']:
            if 'compact_termination' in box:
                xy=tuple(box['compact_termination']['point'])
                assert symbols[xy]=='└' and strokes[xy]==set('NE')
                strokes[xy].remove('E')
            else:
                x=box['x']-1 if port['side']=='input' else box['x']+8;y=port['row'];xy=x,y
                if port['pin']:
                    start=box['x']-3 if port['side']=='input' else box['x']+8
                    for xx in range(start,start+3):
                        assert (xx,y) not in strokes
                        strokes[xx,y]=set('EW');symbols[xx,y]='─'
                strokes[xy].remove('E' if port['side']=='input' else 'W')
            labels[xy].add('PORT:'+box['portion']+':'+port['id'])
    for pin in spec['exterior_pins']:
        x,y=pin['x'],pin['row']
        for xx in range(x,x+3):
            assert (xx,y) not in strokes
            strokes[xx,y]=set('EW');symbols[xx,y]='─'
        xy=(x,y) if pin['side']=='input' else (x+2,y)
        strokes[xy].remove('W' if pin['side']=='input' else 'E');labels[xy].add('PIN:'+pin['pin'])
    def node(xy,arm):
        return (*xy,'V' if arm in 'NS' else 'H') if symbols[xy]=='┼' else (*xy,'J')
    adj=defaultdict(set)
    for (x,y),arms in strokes.items():
        assert arms,('Isolated stroke',x,y)
        for arm in arms:
            dx,dy=DIRS[arm];other=x+dx,y+dy
            assert OPP[arm] in strokes.get(other,set()),('Nonreciprocal stroke',x,y,arm)
            adj[node((x,y),arm)].add(node(other,OPP[arm]))
    seen=set();out={}
    for seed in adj:
        if seed in seen:continue
        pending=[seed];nodes=set();terms=set()
        while pending:
            v=pending.pop()
            if v in nodes:continue
            nodes.add(v);terms|=labels[v[:2]];pending.extend(adj[v]-nodes)
        seen|=nodes
        edges={tuple(sorted((v,w))) for v in nodes for w in adj[v]}
        assert len(terms)>=2
        assert tuple(sorted(terms)) not in out
        out[tuple(sorted(terms))]={'vertices':len(nodes),'edges':len(edges),'cycle_rank':len(edges)-len(nodes)+1,
                                 'edge_set':edges,'adjacency':{n:adj[n] for n in nodes},
                                 'terminal_nodes':{n:labels[n[:2]] for n in nodes if labels[n[:2]]}}
    return out

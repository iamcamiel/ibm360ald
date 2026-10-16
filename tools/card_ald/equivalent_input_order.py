"""Reroute interchangeable A/OR input slots without changing their semantics.

The public optimize(model, geometry) API accepts the composite router's
(positions, ports, exterior, router) tuple. Semantic port keys, physical pins,
net identities and decorations travel together; only input endpoint rows move.
Each trial removes selected leaf tails, keeps every core wire edge, and joins
the moved leaves to the retained connected net. Only strict actual improvements
in (crossings, bends, wire length) are retained. No card-specific rules exist.
"""
from collections import defaultdict
from copy import deepcopy
from statistics import median

from render_composite_card import DIRS, OPPOSITE, verify


def primary(node):
    parts=str(node.get('function','')).strip().lstrip('✲*').split()
    return parts[0] if parts else ''


def _obstacles(positions,ports,exterior,width):
    boxes={(x,y) for pos in positions.values() for x in range(pos['x'],pos['x']+8)
           for y in range(pos['top'],pos['top']+pos['height'])}
    labels=set();reserved=defaultdict(set);endpoints=set()
    for (_,side,_),port in ports.items():
        x,y=port['point'];endpoints.add((x,y));net=port['net']
        if port['pin']:
            labels.update((xx,y) for xx in (range(x+1,x+4) if side=='input' else range(x-3,x)))
        for xx in (range(x-3,x+1) if side=='input' else range(x,x+4)):reserved[xx,y].add(net)
    for pin,data in exterior.items():
        side,row,net=data['side'],data['row'],data['net']
        endpoints.add((3 if side=='input' else width-4,row))
        labels.update((x,row) for x in (range(0,3) if side=='input' else range(width-3,width)))
        for x in (range(3,7) if side=='input' else range(width-7,width-3)):reserved[x,row].add(net)
    clearance=boxes|labels
    return boxes|labels|endpoints,clearance,reserved,labels


def _leaf(router,net,start,other_terminals):
    path=[start];previous=None
    while True:
        point=path[-1];directions=router.wires.get(point,{}).get(net,set())
        if len(path)>1 and (point in other_terminals or len(directions)!=2):break
        onward=[(point[0]+DIRS[d][0],point[1]+DIRS[d][1]) for d in directions
                if (point[0]+DIRS[d][0],point[1]+DIRS[d][1])!=previous]
        if len(onward)!=1:return None
        previous=point;path.append(onward[0])
        if len(path)>router.width*router.height:return None
    return path if len(path)>=2 else None


def _score(metrics):
    return metrics['crossings'],metrics['bends'],metrics['routed_grid_steps']


def _trial(model,geometry,keys):
    positions,oldports,exterior,original=geometry
    ports=deepcopy(oldports);router=deepcopy(original)
    terminals=defaultdict(set)
    for port in oldports.values():terminals[port['net']].add(port['point'])
    for data in exterior.values():terminals[data['net']].add((3 if data['side']=='input' else router.width-4,data['row']))
    leaves=[]
    for key in keys:
        port=oldports[key];path=_leaf(router,port['net'],port['point'],terminals[port['net']]-{port['point']})
        if path is None:return geometry,{'accepted':False,'reason':'An input is not an unambiguous removable leaf.'}
        leaves.append((key,port['net'],path))
    # Remove only the chosen leaf edges; unrelated wires at crossings stay.
    for key,net,path in leaves:
        for a,b in zip(path,path[1:]):
            direction=DIRS.index((b[0]-a[0],b[1]-a[1]))
            router.wires[a][net].discard(direction);router.wires[b][net].discard(OPPOSITE[direction])
        for point in path[:-1]:
            if not router.wires[point].get(net):
                router.wires[point].pop(net,None);router.by_net[net].discard(point)
        router.virtual_endpoint_directions[path[0]].pop(net,None)
    first,second=keys
    ports[first]['point']=(ports[first]['point'][0],oldports[second]['point'][1])
    ports[second]['point']=(ports[second]['point'][0],oldports[first]['point'][1])
    oldblocked,oldclearance,oldreserved,_=_obstacles(positions,oldports,exterior,router.width)
    newblocked,newclearance,newreserved,newlabels=_obstacles(positions,ports,exterior,router.width)
    router.blocked=(original.blocked-oldblocked)|newblocked
    router.clearance_obstacles=(original.clearance_obstacles-oldclearance)|newclearance
    oldforbidden={(x+dx,y) for x,y in original.clearance_obstacles for dx in range(-2,3)}
    router.vertical_forbidden=(original.vertical_forbidden-oldforbidden)|{(x+dx,y) for x,y in router.clearance_obstacles for dx in range(-2,3)}
    router.reserved=defaultdict(set)
    for point,nets in original.reserved.items():
        router.reserved[point].update(set(nets)-oldreserved.get(point,set()))
    for point,nets in newreserved.items():router.reserved[point].update(nets)
    if any(router.wires.get(point) for point in newlabels):return geometry,{'accepted':False,'reason':'Moved pin label would overlap a retained wire.'}
    retained={(point,net,d) for point,nets in router.wires.items() for net,dirs in nets.items() for d in dirs}
    try:
        for key,net,path in leaves:
            start=ports[key]['point'];router.virtual_endpoint_directions[start][net].add(0)
            # The retained net is connected; stopping at its first reached
            # point adds one leaf and cannot create a same-net routing loop.
            goals=set(router.by_net[net])|{path[-1]}
            router.route(net,start,goals)
        candidate=(positions,ports,exterior,router)
        assert all(d in router.wires[p].get(net,set()) for p,net,d in retained),'A retained core edge changed.'
        assert all({k:v for k,v in p.items() if k!='point'}=={k:v for k,v in oldports[key].items() if k!='point'} for key,p in ports.items())
        assert all(p==oldports[key] for key,p in ports.items() if key[1]!='input')
        before=verify(model,geometry);after=verify(model,candidate)
        if _score(after)>=_score(before):return geometry,{'accepted':False,'reason':'No strict crossing/bend/length improvement.','before':before,'after':after}
        return candidate,{'accepted':True,'portion':first[0],
            'changes':[{'port_key':list(key),'id':ports[key].get('id'),'pin':ports[key]['pin'],'net':ports[key]['net'],
                        'triangle':ports[key]['triangle'],'old_row':oldports[key]['point'][1],'row':ports[key]['point'][1]} for key in keys],
            'before':before,'after':after,'retained_core_directed_edges':len(retained),
            'retained_core_routes_unchanged':True,'semantic_port_metadata_unchanged':True,'output_ports_unchanged':True}
    except (AssertionError,ValueError,KeyError) as exc:return geometry,{'accepted':False,'reason':str(exc)}


def optimize(model,geometry,max_trials=None):
    """Greedily trial adjacent input swaps in incoming-wire vertical order."""
    original=geometry;best=geometry;reports=[]
    limit=max_trials if max_trials is not None else model.get('layout_hints',{}).get('equivalent_input_max_trials',24)
    initial=verify(model,geometry)
    attempted=set()
    while len(reports)<limit:
        positions,ports,exterior,router=best
        candidates=[]
        for portion,node in model['portions'].items():
            if primary(node) not in ('A','OR'):continue
            keys=sorted((key for key in ports if key[0]==portion and key[1]=='input'),key=lambda key:ports[key]['point'][1])
            def arrival(key):
                net=ports[key]['net'];drivers=[p['point'][1] for k,p in ports.items() if p['net']==net and k[1]=='output']
                if drivers:return median(drivers)
                boundary=[p['row'] for p in exterior.values() if p['net']==net]
                if boundary:return median(boundary)
                return median([p['point'][1] for k,p in ports.items() if p['net']==net and k!=key] or [ports[key]['point'][1]])
            for a,b in zip(keys,keys[1:]):
                if ports[a]['net']==ports[b]['net']:continue
                state=(a,b,ports[a]['point'][1],ports[b]['point'][1])
                if state in attempted:continue
                ay,by=arrival(a),arrival(b);ar,br=ports[a]['point'][1],ports[b]['point'][1]
                gain=abs(ar-ay)+abs(br-by)-abs(br-ay)-abs(ar-by)
                if gain<=0 and ay<=by:continue
                candidates.append((-gain,str(a),str(b),state,(a,b)))
        if not candidates:break
        accepted=False
        for _,_,_,state,keys in sorted(candidates):
            if len(reports)>=limit:break
            attempted.add(state);candidate,report=_trial(model,best,keys);reports.append(report)
            if report.get('accepted'):best=candidate;accepted=True;break
        if not accepted:break
    return best,{'schema':'equivalent-input-order-preview-v1','accepted':any(r.get('accepted') for r in reports),
        'method':'Adjacent interchangeable A/OR input slots ordered by actual incoming driver or exterior rows; only selected leaves rerouted to retained net cores.',
        'trials':reports,'before':initial,'after':verify(model,best),
        'semantic_port_ids_pins_nets_decorations_preserved':True,'output_ports_unchanged':True,
        'box_placement_unchanged':True,'canonical_models_modified':False}

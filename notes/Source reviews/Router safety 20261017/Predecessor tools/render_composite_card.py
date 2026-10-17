"""Render composite card networks with identical geometry for symbol variants.

All box/port locations and wire paths are fixed before function variants are
drawn. Unrelated crossings are crosses; branches of one electrical net are
diamonds. A* routing permits feedback while avoiding box and pin-label cells.
"""
from collections import defaultdict, Counter
from copy import deepcopy
from heapq import heappop, heappush
from itertools import count
import json
from pathlib import Path

from card_canvas import Canvas

DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))
OPPOSITE = (2, 3, 0, 1)

def rank_nodes(nodes, edges):
    """Keep a maximal supported acyclic subset; route other edges as feedback."""
    adj = defaultdict(set)
    def reaches(start, target):
        todo, seen = [start], set()
        while todo:
            p = todo.pop()
            if p == target:
                return True
            if p in seen:
                continue
            seen.add(p)
            todo.extend(adj[p])
        return False
    for e in sorted(edges, key=lambda e: (-len(e.get("evidence", [])), e["source"], e["target"])):
        s, t = e["source"], e["target"]
        if s != t and not reaches(t, s):
            adj[s].add(t)
    ranks = dict.fromkeys(nodes, 0)
    for _ in nodes:
        changed = False
        for source, sinks in adj.items():
            for target in sinks:
                if ranks[target] <= ranks[source]:
                    ranks[target] = ranks[source] + 1
                    changed = True
        if not changed:
            break
    return ranks

class Router:
    def __init__(self, width, height, blocked, reserved=None, vertical_forbidden=None, clearance_obstacles=None, crossing_penalty=4, bend_penalty=5):
        self.width, self.height, self.blocked = width, height, blocked
        self.reserved = reserved or {}
        self.vertical_forbidden = vertical_forbidden or set()
        self.clearance_obstacles = clearance_obstacles or set()
        self.crossing_penalty=crossing_penalty
        self.bend_penalty=bend_penalty
        self.wires = defaultdict(dict)
        self.by_net = defaultdict(set)
        self.virtual_endpoint_directions = defaultdict(lambda: defaultdict(set))

    def route(self, net, start, goals):
        """Find one orthogonal route; cross only a straight unrelated wire."""
        # Goals are often a long existing tree. Use the entire tree as the
        # target, with a bounding-box lower bound for an admissible heuristic.
        minx, maxx = min(x for x, _ in goals), max(x for x, _ in goals)
        miny, maxy = min(y for _, y in goals), max(y for _, y in goals)
        def heuristic(x, y):
            return max(minx-x, x-maxx, 0) + max(miny-y, y-maxy, 0)
        serial = count()
        heap = [(heuristic(*start), 0, next(serial), (*start, -1))]
        costs, parent = {(*start, -1): 0}, {}
        final = None
        while heap:
            _, cost, _, state = heappop(heap)
            if cost != costs.get(state):
                continue
            x, y, direction = state
            if (x, y) in goals:
                # No branch can originate at a crossing of unrelated nets.
                if len(self.wires[(x, y)]) <= 1:
                    final = state
                    break
            current_others = {n: ds for n, ds in self.wires[(x, y)].items() if n != net}
            for nd, (dx, dy) in enumerate(DIRS):
                if current_others and direction >= 0 and nd != direction:
                    continue
                nx, ny = x + dx, y + dy
                if not (3 <= nx < self.width - 3 and 7 <= ny < self.height - 1):
                    continue
                if (nx, ny) in self.blocked and (nx, ny) not in goals:
                    continue
                if (nx, ny) in self.reserved and net not in self.reserved[(nx, ny)]:
                    continue
                # Vertical tracks have a full character gap between them.
                if dy and nx % 2:
                    continue
                if dy and ((x,y) in self.vertical_forbidden or (nx,ny) in self.vertical_forbidden):
                    continue
                others = {n: ds for n, ds in self.wires[(nx, ny)].items() if n != net}
                if others:
                    if len(others) != 1:
                        continue
                    dirs = next(iter(others.values()))
                    if dirs not in ({0, 2}, {1, 3}):
                        continue
                    if nd in dirs:
                        continue
                if dy and any(n != net and ({1, 3} & ds) for xx in (nx-1, nx+1)
                              for n, ds in self.wires[(xx, ny)].items()):
                    continue
                step = 1 + (self.bend_penalty if direction >= 0 and direction != nd else 0) + (self.crossing_penalty if others else 0)
                new_cost = cost + step
                ns = (nx, ny, nd)
                if new_cost < costs.get(ns, 10**12):
                    costs[ns] = new_cost
                    parent[ns] = state
                    heappush(heap, (new_cost + heuristic(nx, ny), new_cost, next(serial), ns))
        if final is None:
            raise ValueError(("No orthogonal route", net, start, len(goals)))
        path = []
        while final in parent:
            path.append(final[:2])
            final = parent[final]
        path.append(start)
        path.reverse()
        for a, b in zip(path, path[1:]):
            delta = (b[0]-a[0], b[1]-a[1])
            nd = DIRS.index(delta)
            self.wires[a].setdefault(net, set()).add(nd)
            self.wires[b].setdefault(net, set()).add(OPPOSITE[nd])
        self.by_net[net].update(path)
        return path

    def draw(self, canvas):
        glyphs = {frozenset({0, 2}): "─", frozenset({1, 3}): "│",
                  frozenset({0, 1}): "┌", frozenset({1, 2}): "┐",
                  frozenset({0, 3}): "└", frozenset({2, 3}): "┘"}
        for (x, y), nets in self.wires.items():
            if not nets:
                continue
            if len(nets) > 1:
                ch = "┼"
            else:
                net, real_dirs = next(iter(nets.items()))
                ds = real_dirs | self.virtual_endpoint_directions[(x,y)].get(net,set())
                ch = "◇" if len(ds) >= 3 else glyphs.get(frozenset(ds), "─" if ds & {0,2} else "│")
            canvas.put(x, y, ch)

def prepare(model):
    nodes = model["portions"]
    hints = model.get("layout_hints", {})
    ranks = hints.get("ranks") or rank_nodes(nodes, model["edges"])
    assert set(ranks) == set(nodes), "Planner rank coverage differs from portions"
    nets = defaultdict(lambda: {"inputs": [], "outputs": []})
    # Every physical contact is exactly one net. Pinless outputs are one net
    # per driving portion; all observed consumers merge into that net.
    if model.get("networks") is not None:
        for network in model["networks"]:
            key=network["id"]
            nets[key]["_external_pin"]=network.get("exterior_pin")
            for side,field in (("input","_inputs"),("output","_outputs")):
                for portion,port_id in network[side+"s"]:
                    p=dict(next(p for p in nodes[portion][field] if p["id"]==port_id))
                    p["_port_key"]=port_id
                    nets[key][side+"s"].append((portion,p))
    else:
        for portion, node in nodes.items():
            for side, key in (("input", "_inputs"), ("output", "_outputs")):
                for p in node[key]:
                    if p["pin"]:
                        nets[p["pin"]][side + "s"].append((portion, p))
        for edge in model["edges"]:
            s, t, o, i = (edge[k] for k in ("source", "target", "output_ref", "input_ref"))
            key = o if o != "PINLESS" else "INTERNAL:" + s
            if not nets[key]["outputs"]:
                port=next((p for p in nodes[s]["_outputs"] if p["pin"] is None),{"pin":None,"triangle":False})
                nets[key]["outputs"].append((s,dict(port)))
            if i == "PINLESS" and not any(p == t for p, _ in nets[key]["inputs"]):
                options=[p for p in nodes[t]["_inputs"] if p["pin"] is None]
                port=next((p for p in options if p.get("ref")==s),options[0] if options else {"pin":None,"triangle":False})
                nets[key]["inputs"].append((t,dict(port)))
    inputs, outputs = defaultdict(list), defaultdict(list)
    for key, net in nets.items():
        for portion, p in net["inputs"]:
            inputs[portion].append((key, p))
        for portion, p in net["outputs"]:
            outputs[portion].append((key, p))
    positions = {}
    by_rank = defaultdict(list)
    bank_interval = hints.get("bank_interval", 48)
    row_step = hints.get("row_step", 7)
    row_gap = hints.get("row_gap", 0)
    assert row_step in (1, 7) and row_gap in (0, 1)
    for p in nodes:
        by_rank[ranks[p]].append(p)
    for rank, portions in by_rank.items():
        y = 14
        planned=hints.get("order",{}).get(str(rank),hints.get("order",{}).get(rank,[]))
        portions.sort(key=lambda p:(planned.index(p) if p in planned else len(planned),p))
        # R termination blocks stay immediately under a same-contact gate
        # where their logical depth agrees.
        for p in list(portions):
            if not nodes[p]["function"].startswith("R"):
                continue
            pins = {key for key, _ in inputs[p]}
            anchors = [q for q in portions if q != p and not nodes[q]["function"].startswith("R")
                       and any(key in pins for key, _ in inputs[q])]
            if anchors:
                anchor = anchors[0]
                portions.remove(p)
                portions.insert(portions.index(anchor)+1, p)
        for p in portions:
            height = max(7, len(inputs[p])+2, len(outputs[p])+2)
            top=hints.get("tops",{}).get(p,y)
            positions[p] = {"x": hints.get("first_bank_x",60) + rank*bank_interval, "top": top, "height": height}
            y=max(y,top+((height+row_gap+row_step-1)//row_step)*row_step)
    width = max(max(p["x"] for p in positions.values()) + hints.get("right_margin",60),hints.get("minimum_width",0))
    height = max(p["top"]+p["height"] for p in positions.values()) + 35
    ports = {}
    blocked = set()
    for p, pos in positions.items():
        x, y, h = pos["x"], pos["top"], pos["height"]
        blocked.update((xx, yy) for xx in range(x, x+8) for yy in range(y, y+h))
        for side, values in (("input", inputs[p]), ("output", outputs[p])):
            offsets = range(1, h-1) if side == "input" else [3,2,4,1,5] + list(range(6,h-1))
            for (key, port), off in zip(sorted(values,key=lambda v:(v[0],v[1].get("id",""))), offsets):
                yy = y + off
                pin = port["pin"]
                if side == "input":
                    endpoint = (x-4 if pin else x-1, yy)
                    if pin:
                        blocked.update((xx, yy) for xx in range(x-3, x))
                else:
                    endpoint = (x+11 if pin else x+8, yy)
                    if pin:
                        blocked.update((xx, yy) for xx in range(x+8, x+11))
                port_key=port.get("_port_key",key)
                ports[(p, side, port_key)] = {"point": endpoint, "pin": pin, "triangle": port["triangle"],"net":key,"id":port.get("id")}
    exterior = {}
    endpoints = {}
    reserved = defaultdict(set)
    for (p, side, port_key), port in ports.items():
        key=port["net"]
        x, y = port["point"]
        for xx in range(x-3 if side == "input" else x, x+1 if side == "input" else x+4):
            reserved[(xx,y)].add(key)
    used_rows = defaultdict(set)
    clearance_obstacles = set(blocked)
    for key, net in nets.items():
        ends = []
        for side in ("output", "input"):
            ends += [ports[(p, side,record.get("_port_key",key))]["point"] for p,record in net[side+"s"]]
        if not ends:
            continue
        physical_pin=net.get("_external_pin",key if not key.startswith("INTERNAL:") else None)
        if physical_pin:
            side = "output" if net["outputs"] else "input"
            row = ends[0][1]
            while row in used_rows[side]:
                row += 1
            used_rows[side].add(row)
            endpoint = (width-4 if side == "output" else 3, row)
            ends.append(endpoint)
            exterior[physical_pin] = {"side": side, "row": row,"net":key}
            clearance_obstacles.update((xx,row) for xx in
                (range(0,3) if side == "input" else range(width-3,width)))
            for xx in range(3 if side == "input" else width-7, 7 if side == "input" else width-3):
                reserved[(xx,row)].add(key)
        endpoints[key] = ends
        blocked.update(ends)
    vertical_forbidden = {(x+dx,y) for x,y in clearance_obstacles for dx in range(-2,3)}
    router = Router(width, height, blocked, reserved, vertical_forbidden, clearance_obstacles,
                    hints.get("crossing_penalty",4),hints.get("bend_penalty",5))
    for (p, side, port_key), port in ports.items():
        router.virtual_endpoint_directions[port["point"]][port["net"]].add(0 if side == "input" else 2)
    for pin, data in exterior.items():
        key=data["net"]
        point = (3 if data["side"] == "input" else width-4, data["row"])
        router.virtual_endpoint_directions[point][key].add(2 if data["side"] == "input" else 0)
    # Route the longest/highest-fanout nets first to reserve clean trunks.
    def routing_priority(item):
        key,net=item
        if hints.get("routing_strategy")=="centrality-first":
            priority=hints.get("node_priority",{})
            score=max((priority.get(p,0) for p,_ in net["inputs"]+net["outputs"]),default=0)
            return (-score,-len(net["inputs"]),key)
        return (not key.startswith("INTERNAL:"),-len(net["inputs"]),key)
    for key, net in sorted(nets.items(), key=routing_priority):
        ends = endpoints.get(key, [])
        if not ends:
            continue
        tree = {ends[0]}
        for endpoint in ends[1:]:
            router.route(key, endpoint, tree)
            tree = router.by_net[key] | tree
    return positions, ports, exterior, router

def _optimize_boundary_pins(model, geometry, strategy="first-detour", selected_pin=None):
    """Reroute only exterior leaf tails; keep the entire retained circuit fixed."""
    positions,ports,exterior,original=geometry
    router=deepcopy(original)
    exterior=deepcopy(exterior)
    terminals={port["point"] for port in ports.values()}
    tails=[]
    for pin,data in exterior.items():
        if selected_pin is not None and pin!=selected_pin:continue
        side,net=data["side"],data["net"]
        start=(3 if side=="input" else router.width-4,data["row"])
        path=[start]
        previous=None
        while True:
            point=path[-1]
            directions=router.wires[point].get(net,set())
            if len(path)>1 and (point in terminals or len(directions)!=2):
                break
            neighbors=[(point[0]+DIRS[d][0],point[1]+DIRS[d][1]) for d in directions]
            onward=[q for q in neighbors if q!=previous]
            if len(onward)!=1:break
            # Keep the approach after the first outer vertical detour; moving
            # its label to this row removes the detour and its crossings.
            if strategy=="first-detour" and previous is not None and previous[0]==point[0] and onward[0][1]==point[1]:
                break
            previous=point
            path.append(onward[0])
        if len(path)<2:return geometry,{"accepted":False,"reason":"Exterior endpoint is not a removable leaf"}
        tails.append({"pin":pin,"side":side,"net":net,"path":path,"attachment":path[-1]})
    for tail in tails:
        net=tail["net"]
        for a,b in zip(tail["path"],tail["path"][1:]):
            direction=DIRS.index((b[0]-a[0],b[1]-a[1]))
            router.wires[a][net].discard(direction)
            router.wires[b][net].discard(OPPOSITE[direction])
        for point in tail["path"][:-1]:
            if not router.wires[point].get(net):
                router.wires[point].pop(net,None)
                router.by_net[net].discard(point)
        router.virtual_endpoint_directions[tail["path"][0]].pop(net,None)
        router.blocked.discard(tail["path"][0])
    changes=[]
    for side in ("input","output"):
        previous_row=6
        fixed_rows={data["row"] for pin,data in exterior.items() if data["side"]==side and pin not in {t["pin"] for t in tails}}
        for tail in tails:
            if tail["side"]!=side:continue
            row=tail["attachment"][1]
            if strategy=="terminal-row":
                options=[p["point"][1] for key,p in ports.items() if p["net"]==tail["net"] and key[1]==side
                         and not model["portions"][key[0]]["function"].strip().startswith("R")]
                if options:row=min(options,key=lambda y:(abs(y-exterior[tail["pin"]]["row"]),y))
            if strategy in ("below-obstacles","above-obstacles"):
                for _ in positions:
                    hits=[p for p in positions.values() if p["top"]<=row<p["top"]+p["height"] and
                          (p["x"]>=tail["attachment"][0] if side=="output" else p["x"]+7<=tail["attachment"][0])]
                    if not hits:break
                    row=(max(p["top"]+p["height"] for p in hits) if strategy=="below-obstacles"
                         else min(p["top"] for p in hits)-1)
            tail["preferred_row"]=row
        side_tails=[t for t in tails if t["side"]==side]
        if selected_pin is not None and side_tails and all(t["preferred_row"]==exterior[t["pin"]]["row"] for t in side_tails):
            return geometry,{"accepted":False,"reason":"Boundary label already on unobstructed approach row"}
        for tail in sorted((t for t in tails if t["side"]==side),key=lambda t:(t["preferred_row"],t["pin"])):
            row=max(previous_row+1,tail["preferred_row"])
            while row in fixed_rows:row+=1
            previous_row=row
            old=exterior[tail["pin"]]["row"]
            exterior[tail["pin"]]["row"]=row
            changes.append({"pin":tail["pin"],"side":side,"old_row":old,"row":row,"attachment":list(tail["attachment"])})
    label_cells={(x,data["row"]) for data in exterior.values() for x in
        (range(0,3) if data["side"]=="input" else range(router.width-3,router.width))}
    old_label_cells={(x,data["row"]) for data in geometry[2].values() for x in
        (range(0,3) if data["side"]=="input" else range(router.width-3,router.width))}
    router.clearance_obstacles-=old_label_cells
    router.clearance_obstacles|=label_cells
    router.vertical_forbidden={(x+dx,y) for x,y in router.clearance_obstacles for dx in range(-2,3)}
    for tail in tails:
        data=exterior[tail["pin"]];net=tail["net"]
        start=(3 if tail["side"]=="input" else router.width-4,data["row"])
        router.blocked.add(start)
        router.virtual_endpoint_directions[start][net].add(2 if tail["side"]=="input" else 0)
    # Old boundary escape reservations no longer correspond to the moved pins.
    router.reserved={p:nets for p,nets in router.reserved.items() if 7<=p[0]<router.width-7}
    for pin,data in exterior.items():
        net=data["net"]
        row=data["row"]
        for x in (range(3,7) if data["side"]=="input" else range(router.width-7,router.width-3)):
            router.reserved.setdefault((x,row),set()).add(net)
    retained_edges={(point,net,direction) for point,nets in router.wires.items()
                    for net,directions in nets.items() for direction in directions}
    try:
        for tail in sorted(tails,key=lambda t:(t["attachment"][1],t["pin"])):
            net=tail["net"];side=tail["side"];attachment=tail["attachment"]
            start=(3 if side=="input" else router.width-4,exterior[tail["pin"]]["row"])
            saved_blocked=router.blocked
            goals=set(router.by_net[net])|{attachment}
            limit=(max(x for x,y in goals) if side=="input" else min(x for x,y in goals))
            interior={(x,y) for x in range(router.width) for y in range(7,router.height)
                      if (x>limit if side=="input" else x<limit)}
            router.blocked=saved_blocked|interior
            router.route(net,start,goals)
            router.blocked=saved_blocked
        candidate=(positions,ports,exterior,router)
        assert all(direction in router.wires[point].get(net,set()) for point,net,direction in retained_edges), "Retained core route changed"
        before=verify(model,geometry);after=verify(model,candidate)
        def alignment(labels):
            return sum(min((abs(data["row"]-p["point"][1]) for key,p in ports.items() if p["net"]==data["net"] and key[1]==data["side"]
                            and not model["portions"][key[0]]["function"].strip().startswith("R")),default=0) for data in labels.values())
        score=lambda m,labels:(m["crossings"],m["bends"],m["routed_grid_steps"],alignment(labels))
        if score(after,exterior)>=score(before,geometry[2]):return geometry,{"accepted":False,"reason":"No strict crossing/bend/length/alignment improvement","before":before,"after":after}
        return candidate,{"accepted":True,"method":"Exterior leaf tails join their first reached retained same-net core; terminal-row alignment breaks equal-metric ties",
                          "terminal_alignment_before":alignment(geometry[2]),"terminal_alignment_after":alignment(exterior),
                          "strategy":strategy,
                          "retained_core_directed_edges":len(retained_edges),"retained_core_routes_unchanged":True,
                          "boxes_and_semantic_ports_unchanged":True,"changes":changes,"before":before,"after":after}
    except (AssertionError,ValueError,KeyError) as exc:
        return geometry,{"accepted":False,"reason":str(exc)}


def optimize_boundary_pins(model, geometry):
    """Choose only strict improvements among approach and obstacle-aware tails."""
    best=geometry
    reports=[]
    trials=[("first-detour",None)]+[(strategy,pin) for pin in sorted(geometry[2])
                                   for strategy in ("terminal-row","attachment-row","above-obstacles","below-obstacles")]
    for strategy,pin in trials:
        candidate,report=_optimize_boundary_pins(model,best,strategy,pin)
        report["selected_pin"]=pin
        reports.append(report)
        if report.get("accepted"):best=candidate
    accepted=[r for r in reports if r.get("accepted")]
    return best,{"accepted":bool(accepted),"passes":reports,
                 "before":verify(model,geometry),"after":verify(model,best),
                 "retained_core_routes_unchanged":all(r.get("retained_core_routes_unchanged",True) for r in reports)}


def optimize_fanout_trunks(model, geometry):
    """Compare upper/lower horizontal buses with short forward fanout drops."""
    best=geometry
    reports=[]
    for pin,original_data in sorted(geometry[2].items()):
        positions,ports,exterior,oldrouter=best
        data=exterior[pin];net=data["net"]
        drivers=[(key,p) for key,p in ports.items() if p["net"]==net and key[1]=="output"]
        sinks=[(key,p) for key,p in ports.items() if p["net"]==net and key[1]=="input"]
        if data["side"]!="output" or len(drivers)!=1 or len(sinks)<2:continue
        source=drivers[0][1]["point"]
        if not all(p["point"][0]>source[0] for key,p in sinks):continue
        baseline=verify(model,best)
        proposal=None;proposal_score=None
        trunk_top=min(positions[key[0]]["top"] for key,p in sinks)-1
        trunk_bottom=max(positions[key[0]]["top"]+positions[key[0]]["height"] for key,p in sinks)
        alternatives=[("above",y) for y in range(trunk_top,max(6,trunk_top-8),-1)]
        alternatives += [("below",y) for y in range(trunk_bottom,min(oldrouter.height-1,trunk_bottom+8))]
        for trunk_side,trunk_row in alternatives:
            if any(p["side"]=="output" and p["row"]==trunk_row for other,p in exterior.items() if other!=pin):continue
            router=deepcopy(oldrouter);outside=deepcopy(exterior)
            for point in list(router.by_net[net]):router.wires[point].pop(net,None)
            router.by_net[net]=set()
            oldendpoint=(router.width-4,data["row"])
            newendpoint=(router.width-4,trunk_row)
            router.blocked.discard(oldendpoint);router.blocked.add(newendpoint)
            router.virtual_endpoint_directions[oldendpoint].pop(net,None)
            router.virtual_endpoint_directions[newendpoint][net].add(0)
            outside[pin]["row"]=trunk_row
            oldlabels={(x,data["row"]) for x in range(router.width-3,router.width)}
            newlabels={(x,trunk_row) for x in range(router.width-3,router.width)}
            router.clearance_obstacles-=oldlabels;router.clearance_obstacles|=newlabels
            router.vertical_forbidden={(x+dx,y) for x,y in router.clearance_obstacles for dx in range(-2,3)}
            def vertical_ok(x,y1,y2):
                return x%2==0 and all((x,y) not in router.vertical_forbidden and
                    not any(other!=net and directions&{1,3} for xx in (x-1,x+1) for other,directions in router.wires[(xx,y)].items())
                    for y in range(min(y1,y2),max(y1,y2)+1))
            rise=next((x for x in range(source[0]+1,min(p["point"][0] for key,p in sinks)) if vertical_ok(x,source[1],trunk_row)),None)
            if rise is None:continue
            drops=[]
            for key,p in sinks:
                point=p["point"]
                drop=next((x for x in range(point[0]-1,rise,-1) if vertical_ok(x,point[1],trunk_row)),None)
                if drop is None:break
                drops.append((point,drop))
            if len(drops)!=len(sinks):continue
            segments=[(source,(rise,source[1])),((rise,source[1]),(rise,trunk_row)),((rise,trunk_row),newendpoint)]
            segments += [(point,(drop,point[1])) for point,drop in drops]
            segments += [((drop,point[1]),(drop,trunk_row)) for point,drop in drops]
            layer=defaultdict(set)
            for a,b in segments:
                x,y=a;dx=0 if a[0]==b[0] else (1 if b[0]>a[0] else -1);dy=0 if a[1]==b[1] else (1 if b[1]>a[1] else -1)
                if a==b:continue
                direction=DIRS.index((dx,dy))
                while (x,y)!=b:
                    q=(x+dx,y+dy);layer[x,y].add(direction);layer[q].add(OPPOSITE[direction]);x,y=q
            allowed={source,newendpoint}|{p["point"] for key,p in sinks}
            valid=True
            for point,directions in layer.items():
                if point in router.blocked and point not in allowed:valid=False;break
                if point in router.reserved and net not in router.reserved[point]:valid=False;break
                other=[ds for other,ds in router.wires[point].items() if other!=net]
                if other and (len(other)!=1 or {frozenset(directions),frozenset(other[0])}!={frozenset({0,2}),frozenset({1,3})}):valid=False;break
                if directions&{1,3} and point in router.vertical_forbidden:valid=False;break
            if not valid:continue
            # One source bus with independent drops must remain an acyclic tree.
            if sum(len(ds) for ds in layer.values())//2 != len(layer)-1:continue
            for point,directions in layer.items():router.wires[point][net]=directions
            router.by_net[net]=set(layer)
            candidate=(positions,ports,outside,router)
            try:metrics=verify(model,candidate)
            except AssertionError:continue
            score=(metrics["crossings"],metrics["bends"],metrics["routed_grid_steps"])
            base_score=(baseline["crossings"],baseline["bends"],baseline["routed_grid_steps"])
            if score<base_score and (proposal_score is None or score<proposal_score):
                proposal=candidate;proposal_score=score
                result={"pin":pin,"net":net,"source":list(source),"trunk_row":trunk_row,"trunk_side":trunk_side,"source_riser_x":rise,
                        "sink_drops":[{"port":list(p),"x":x} for p,x in drops],"before":baseline,"after":metrics,
                        "target_net_is_tree":True,"other_net_routes_unchanged":True}
        if proposal is not None:best=proposal;reports.append(result)
    return best,{"accepted":bool(reports),"method":"Compare buses above and below forward shared-output receivers, nearest legal source turn and short receiver drops; only strict crossing/bend/length improvements retained","changes":reports}


def draw(model, geometry, forms=None, header=None):
    positions, ports, exterior, router = geometry
    c = Canvas(router.width, router.height, card_type=model["card_type"], grid_step=model.get("layout_hints",{}).get("row_step",7))
    lines = header or [f"CARD-ALD {model['card_type']} COMPOSITE PINOUT",
                       "POWER: " + "; ".join(pin+" "+level for pin,level in model.get("power_pins",{}).items()),
                       f"{model['observations']} REVIEWED OCCURRENCES; {model['pages']} PAGES; ALL {len(model['portions'])} OBSERVED PORTIONS"]
    for y, text in enumerate(lines):
        c.text(0, y, text)
    router.draw(c)
    for portion, pos in positions.items():
        n = model["portions"][portion]
        form = (forms or {}).get(portion, {})
        x, y, h = pos["x"], pos["top"], pos["height"]
        c.box(x, y, y+h-1, portion, form.get("function", n["function"]), n["unit"],
              input_count=max(0,h-2) if h > 7 else 0)
        c.text(x+1, y+4, model["card_type"]+portion)
        for (p, side, key), port in ports.items():
            if p != portion:
                continue
            xx, yy = port["point"]
            wedge = form.get(side + "_wedges", {}).get(key,
                        form.get(side + "_wedge", port["triangle"]))
            c.put(x if side == "input" else x+7, yy, "◺" if wedge else "│")
            if port["pin"]:
                c.text(x-3 if side == "input" else x+8, yy, port["pin"])
    for pin, data in exterior.items():
        c.text(0 if data["side"] == "input" else router.width-3, data["row"], pin)
    return c.render().rstrip()+"\n"

def verify(model, geometry):
    positions, ports, exterior, router = geometry
    box_cells = {(x,y) for p in positions.values()
                 for x in range(p["x"],p["x"]+8)
                 for y in range(p["top"],p["top"]+p["height"])}
    occupied = {point for point,nets in router.wires.items() if nets}
    assert not occupied & box_cells, "A routed wire entered a block"
    crossings = []
    joins = []
    for point, nets in router.wires.items():
        if len(nets) > 1:
            assert len(nets) == 2
            assert {frozenset(ds) for ds in nets.values()} == {frozenset({0,2}),frozenset({1,3})}, (point,nets)
            crossings.append(point)
        if len(nets) == 1 and len(next(iter(nets.values()))) >= 3:
            joins.append(point)
    for net, points in router.by_net.items():
        if not points:
            continue
        todo, seen = [next(iter(points))], set()
        while todo:
            point = todo.pop()
            if point in seen:
                continue
            seen.add(point)
            x,y = point
            for d in router.wires[point][net]:
                dx,dy = DIRS[d]
                q = x+dx,y+dy
                if q in points:
                    todo.append(q)
        assert seen == points, (net,"Disconnected wire cells")
    physical = {port["pin"] for port in ports.values() if port["pin"]}
    assert physical == set(model["signal_pins"]) == set(exterior)
    for (portion, side, port_key), port in ports.items():
        net=port["net"]
        assert port["point"] in router.by_net[net], (portion,side,net,"unrouted port")
    row_step=model.get("layout_hints",{}).get("row_step",7)
    assert all(pos["top"] % row_step == 0 for pos in positions.values())
    assert all(3 <= x < router.width-3 for x,y in occupied)
    vertical_points = {point for point,nets in router.wires.items()
                       if any(ds & {1,3} for ds in nets.values())}
    assert not vertical_points & router.vertical_forbidden
    obstacles_by_row = defaultdict(set)
    for x,y in router.clearance_obstacles:
        obstacles_by_row[y].add(x)
    minimum_clearance = min((abs(x-xx)-1 for x,y in vertical_points
                             for xx in obstacles_by_row[y]), default=None)
    assert minimum_clearance is None or minimum_clearance >= 2
    vertical_by_row = defaultdict(set)
    for x,y in vertical_points:
        vertical_by_row[y].add(x)
    minimum_parallel_gap = min((b-a-1 for values in vertical_by_row.values()
                                for a,b in zip(sorted(values),sorted(values)[1:])), default=None)
    assert minimum_parallel_gap is None or minimum_parallel_gap >= 1
    wire_length=sum(len(ds) for nets in router.wires.values() for ds in nets.values())//2
    bends=sum(len(directions)==2 and directions not in ({0,2},{1,3})
              for point,nets in router.wires.items() for net,ds in nets.items()
              for directions in [ds|router.virtual_endpoint_directions[point].get(net,set())])
    return {"no_wire_through_box": True, "all_net_layers_connected": True,
            "all_ports_routed": True, "all_physical_contacts_once_at_exterior": True,
            "all_pin_bearing_ports_have_box_labels": True,
            "all_box_tops_on_configured_grid": True, "grid_step": row_step,
            "no_vertical_wires_outside_exterior_contacts": True,
            "multi_net_crossings_are_perpendicular_straight_wires": True,
            "minimum_blank_cells_vertical_wire_to_box_or_pin_label": minimum_clearance,
            "minimum_blank_columns_between_parallel_vertical_wires": minimum_parallel_gap,
            "diagram_width": router.width,
            "routed_grid_steps":wire_length,"bends":bends,
            "crossings": len(crossings), "junctions": len(joins),
            "signals": len(exterior), "portions": len(positions), "ports": len(ports)}

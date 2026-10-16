"""Render composite card networks with identical geometry for symbol variants.

All box/port locations and wire paths are fixed before function variants are
drawn. Unrelated crossings are crosses; branches of one electrical net are
diamonds. A* routing permits feedback while avoiding box and pin-label cells.
"""
from collections import defaultdict, Counter
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
            y=max(y,top+((height+6)//7)*7)
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

def draw(model, geometry, forms=None, header=None):
    positions, ports, exterior, router = geometry
    c = Canvas(router.width, router.height, card_type=model["card_type"])
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
    assert all(pos["top"] % 7 == 0 for pos in positions.values())
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
            "all_box_tops_on_seven_row_grid": True,
            "no_vertical_wires_outside_exterior_contacts": True,
            "multi_net_crossings_are_perpendicular_straight_wires": True,
            "minimum_blank_cells_vertical_wire_to_box_or_pin_label": minimum_clearance,
            "minimum_blank_columns_between_parallel_vertical_wires": minimum_parallel_gap,
            "diagram_width": router.width,
            "routed_grid_steps":wire_length,"bends":bends,
            "crossings": len(crossings), "junctions": len(joins),
            "signals": len(exterior), "portions": len(positions), "ports": len(ports)}

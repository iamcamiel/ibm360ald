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

from source_4191 import Canvas

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
    def __init__(self, width, height, blocked, reserved=None):
        self.width, self.height, self.blocked = width, height, blocked
        self.reserved = reserved or {}
        self.wires = defaultdict(dict)
        self.by_net = defaultdict(set)

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
                step = 1 + (5 if direction >= 0 and direction != nd else 0) + (4 if others else 0)
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
                ds = next(iter(nets.values()))
                ch = "◇" if len(ds) >= 3 else glyphs.get(frozenset(ds), "─" if ds & {0,2} else "│")
            canvas.put(x, y, ch)

def prepare(model):
    nodes = model["portions"]
    ranks = rank_nodes(nodes, model["edges"])
    nets = defaultdict(lambda: {"inputs": [], "outputs": []})
    # Every physical contact is exactly one net. Pinless outputs are one net
    # per driving portion; all observed consumers merge into that net.
    for portion, node in nodes.items():
        for side, key in (("input", "_inputs"), ("output", "_outputs")):
            for p in node[key]:
                if p["pin"]:
                    nets[p["pin"]][side + "s"].append((portion, p))
    for edge in model["edges"]:
        s, t, o, i = (edge[k] for k in ("source", "target", "output_ref", "input_ref"))
        key = o if o != "PINLESS" else "INTERNAL:" + s
        if not nets[key]["outputs"]:
            nets[key]["outputs"].append((s, {"pin": None, "triangle": False}))
        # A physical input already belongs to its contact net. A source edge
        # carrying a different contact must have been excluded by extraction.
        if i == "PINLESS" and not any(p == t for p, _ in nets[key]["inputs"]):
            nets[key]["inputs"].append((t, {"pin": None, "triangle": False}))
    inputs, outputs = defaultdict(list), defaultdict(list)
    for key, net in nets.items():
        for portion, p in net["inputs"]:
            inputs[portion].append((key, p))
        for portion, p in net["outputs"]:
            outputs[portion].append((key, p))
    positions = {}
    by_rank = defaultdict(list)
    for p in nodes:
        by_rank[ranks[p]].append(p)
    for rank, portions in by_rank.items():
        y = 14
        portions.sort()
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
            positions[p] = {"x": 90 + rank*80, "top": y, "height": height}
            y += ((height+6)//7)*7
    width = max(p["x"] for p in positions.values()) + 100
    height = max(p["top"]+p["height"] for p in positions.values()) + 35
    ports = {}
    blocked = set()
    for p, pos in positions.items():
        x, y, h = pos["x"], pos["top"], pos["height"]
        blocked.update((xx, yy) for xx in range(x, x+8) for yy in range(y, y+h))
        for side, values in (("input", inputs[p]), ("output", outputs[p])):
            offsets = range(1, h-1) if side == "input" else [3,2,4,1,5] + list(range(6,h-1))
            for (key, port), off in zip(sorted(values), offsets):
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
                ports[(p, side, key)] = {"point": endpoint, "pin": pin, "triangle": port["triangle"]}
    exterior = {}
    endpoints = {}
    reserved = defaultdict(set)
    for (p, side, key), port in ports.items():
        x, y = port["point"]
        for xx in range(x-3 if side == "input" else x, x+1 if side == "input" else x+4):
            reserved[(xx,y)].add(key)
    used_rows = defaultdict(set)
    for key, net in nets.items():
        ends = []
        for side in ("output", "input"):
            ends += [ports[(p, side, key)]["point"] for p, _ in net[side+"s"]]
        if not ends:
            continue
        if not key.startswith("INTERNAL:"):
            side = "output" if net["outputs"] else "input"
            row = ends[0][1]
            while row in used_rows[side]:
                row += 1
            used_rows[side].add(row)
            endpoint = (width-4 if side == "output" else 3, row)
            ends.append(endpoint)
            exterior[key] = {"side": side, "row": row}
            for xx in range(3 if side == "input" else width-7, 7 if side == "input" else width-3):
                reserved[(xx,row)].add(key)
        endpoints[key] = ends
        blocked.update(ends)
    router = Router(width, height, blocked, reserved)
    # Route the longest/highest-fanout nets first to reserve clean trunks.
    for key, net in sorted(nets.items(), key=lambda kv: (-len(kv[1]["inputs"]), kv[0])):
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
    c = Canvas(router.width, router.height)
    lines = header or [f"CARD-ALD 580{model['card_type']} DOUBLE CARD  COMPOSITE PINOUT",
                       "POWER: GROUND D08 J08; +3V D03 J03; -3V B06 G06; +6V B11 G11",
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

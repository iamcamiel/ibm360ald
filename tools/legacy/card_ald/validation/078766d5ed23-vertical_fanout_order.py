"""Consolidate fanout trees into one vertical bus without moving terminals.

Only a net with one block output, or one exterior input and no block output,
is eligible. Every terminal retains its semantic identity and coordinates.
Templates are accepted only after full geometry validation and a strict
lexicographic improvement in crossings, bends, then total wire length.
"""
from collections import defaultdict
from copy import deepcopy
from statistics import median

from render_composite_card import DIRS, OPPOSITE, verify


def _score(metrics):
    return metrics['crossings'], metrics['bends'], metrics['routed_grid_steps']


def _layer(terminals, track):
    layer = defaultdict(set)
    rows = [point[1] for point, _ in terminals]
    segments = [((track, min(rows)), (track, max(rows)))]
    segments.extend((point, (track, point[1])) for point, _ in terminals)
    for a, b in segments:
        if a == b:
            continue
        dx = (b[0] > a[0]) - (b[0] < a[0])
        dy = (b[1] > a[1]) - (b[1] < a[1])
        direction = DIRS.index((dx, dy))
        while a != b:
            q = a[0] + dx, a[1] + dy
            layer[a].add(direction)
            layer[q].add(OPPOSITE[direction])
            a = q
    return layer


def _valid(router, net, layer, terminals):
    allowed = {point for point, _ in terminals}
    if not layer or sum(map(len, layer.values())) // 2 != len(layer) - 1:
        return False
    # Each endpoint must approach horizontally from its declared wire side.
    for point, direction in terminals:
        if layer.get(point) != {direction}:
            return False
    for (x, y), directions in layer.items():
        point = x, y
        if not (3 <= x < router.width - 3 and 7 <= y < router.height - 1):
            return False
        if point in router.blocked and point not in allowed:
            return False
        if point in router.reserved and net not in router.reserved[point]:
            return False
        others = [ds for name, ds in router.wires.get(point, {}).items() if name != net]
        if others and (len(others) != 1 or
                       {frozenset(directions), frozenset(others[0])} !=
                       {frozenset({0, 2}), frozenset({1, 3})}):
            return False
        if directions & {1, 3}:
            if x % 2 or point in router.vertical_forbidden:
                return False
            if any(name != net and ds & {1, 3}
                   for xx in (x - 1, x + 1)
                   for name, ds in router.wires.get((xx, y), {}).items()):
                return False
    return True


def optimize(model, geometry, max_tracks=None):
    """Try a bounded set of one-bus templates for all eligible fanout nets."""
    best = geometry
    initial = verify(model, geometry)
    changes = []
    trials = 0
    limit = max_tracks if max_tracks is not None else model.get('layout_hints', {}).get('vertical_fanout_max_tracks', 24)
    nets = sorted({p['net'] for p in geometry[1].values()})
    for net in nets:
        positions, ports, exterior, router = best
        drivers = [p for key, p in ports.items() if p['net'] == net and key[1] == 'output']
        outside_inputs = [p for p in exterior.values() if p['net'] == net and p['side'] == 'input']
        if len(drivers) + len(outside_inputs) != 1:
            continue
        terminals = [(p['point'], 2 if key[1] == 'input' else 0)
                     for key, p in ports.items() if p['net'] == net]
        terminals += [((3 if p['side'] == 'input' else router.width - 4, p['row']),
                       0 if p['side'] == 'input' else 2)
                      for p in exterior.values() if p['net'] == net]
        if len(terminals) < 3 or len({point for point, _ in terminals}) != len(terminals):
            continue
        # One vertical track must lie beyond every source and before every sink.
        lower = max(point[0] for point, direction in terminals if direction == 0) + 1
        upper = min(point[0] for point, direction in terminals if direction == 2) - 1
        candidates = list(range(lower + lower % 2, upper + 1, 2))
        if not candidates:
            continue
        existing = [x for (x, y) in router.by_net[net]
                    if router.wires.get((x, y), {}).get(net, set()) & {1, 3}]
        preferred = median(existing or candidates)
        # Nearby existing tracks usually retain the smallest source/sink spurs.
        candidates.sort(key=lambda x: (abs(x - preferred), x))
        before = verify(model, best)
        proposal = None
        proposal_score = _score(before)
        result = None
        for track in candidates[:max(0, limit)]:
            trials += 1
            layer = _layer(terminals, track)
            if not _valid(router, net, layer, terminals):
                continue
            candidate_router = deepcopy(router)
            for point in candidate_router.by_net[net]:
                candidate_router.wires[point].pop(net, None)
            candidate_router.by_net[net] = set(layer)
            for point, directions in layer.items():
                candidate_router.wires[point][net] = set(directions)
            candidate = positions, ports, exterior, candidate_router
            try:
                after = verify(model, candidate)
            except AssertionError:
                continue
            if _score(after) < proposal_score:
                proposal, proposal_score = candidate, _score(after)
                result = {'net': net, 'track_x': track,
                          'old_vertical_track_columns': sorted(set(existing)),
                          'new_vertical_track_columns': [track],
                          'semantic_terminals': [{'key': list(key), 'id': p.get('id'),
                                                  'pin': p.get('pin'), 'point': list(p['point'])}
                                                 for key, p in ports.items() if p['net'] == net],
                          'exterior_terminals': [{'pin': pin, **p} for pin, p in exterior.items() if p['net'] == net],
                          'terminal_points_and_directions': [[list(p), d] for p, d in terminals],
                          'before': before, 'after': after,
                          'target_net_is_tree': True, 'all_other_net_layers_preserved': True}
        if proposal is not None:
            # Explicitly guard the optimizer's publication contract.
            other_before = {(point, name): frozenset(ds) for point, layers in router.wires.items()
                            for name, ds in layers.items() if name != net}
            other_after = {(point, name): frozenset(ds) for point, layers in proposal[3].wires.items()
                           for name, ds in layers.items() if name != net}
            assert other_before == other_after
            best = proposal
            changes.append(result)
    return best, {'schema': 'vertical-fanout-order-preview-v1',
                  'accepted': bool(changes), 'changes': changes, 'tracks_tested': trials,
                  'method': 'Single vertical bus with horizontal terminal spurs; bounded track search and strict crossing/bend/length improvement.',
                  'before': initial, 'after': verify(model, best),
                  'all_semantic_ports_and_exterior_pins_unchanged': True,
                  'all_box_placements_unchanged': True, 'canonical_models_modified': False}

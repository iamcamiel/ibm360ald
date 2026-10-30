"""Normalize net contacts to the cell outside a fixed three-character pin slot.

The slot is the physical pin label or a three-character wire for null/omitted
identities. Annotations do not change its attachment coordinate. Only an
existing terminal endpoint is adjusted. An annotated vertical endpoint can
retain its position with a short horizontal leg to the normal contact. A
crossing at that contact and existing same-net branches are valid; crossings
elsewhere in the changed interval remain explicit layout holds.
"""
MARKERS = ('2', '3', '8', 'L')
LETTERS = 'ABCDEFGHJKLMN'


def covers(net, point):
    x, y = point
    for route in net['routing']:
        if list(point) in route:
            return True
        for a, b in zip(route, route[1:]):
            if a[1] == b[1] == y and min(a[0], b[0]) <= x <= max(a[0], b[0]):
                return True
            if a[0] == b[0] == x and min(a[1], b[1]) <= y <= max(a[1], b[1]):
                return True
    return False


def normalize_annotation_leads(data, details=None, only_terminals=None):
    offsets = {d['num']: d['deviation'] for d in data.get('column deviations', []) if d['type'] == 'block'}
    changes, holds = [], []
    masks = {u['field']:u.get('visible text','') for u in (details or {}).get('uncertainties',[])
             if u.get('status')=='unresolved' and isinstance(u.get('visible text'),str)}
    for block in data['blocks']:
        column = int(block['grid position'][:-1])
        left = 27 + 23 * column + offsets.get(column, 0)
        top = 2 + 7 * LETTERS.index(block['grid position'][-1])
        for pin in block['pins']:
            node = f"blocks/{block['serial']}/pins/{pin['side']}/{pin['line']}"
            if only_terminals is not None and node not in only_terminals:
                continue
            owners = [net for net in data['nets'] if node in net['nodes']]
            if len(owners) != 1 or owners[0]['nodes'].count(node) != 1:
                continue
            net = owners[0]
            marks = [a for a in net.get('annotations', []) if a.get('at') == node]
            if len(marks) > 1:
                continue
            direction = 1 if pin['side'] == 'L' else -1
            border = left if pin['side'] == 'L' else left + 7
            row = top + pin['line'] - 1
            number = pin.get('pin','')
            if isinstance(number,str) and number and len(number)!=3:continue
            if number is None:
                number = masks.get(node+'/pin','')
            if not isinstance(number,str):
                continue
            mark = marks[0]['text'] if marks else ''
            old = [border - (1+len(number)+len(mark))*direction, row]
            new = [border - 4*direction, row]
            if old == new or any(route and (route[0]==new or route[-1]==new) for route in net['routing']):
                continue
            candidates = []
            for i, route in enumerate(net['routing']):
                if len(route) < 2:
                    continue
                for j, neighbor in ((0, 1), (len(route) - 1, len(route) - 2)):
                    if (route[j] == old and route[neighbor][1] == row
                            and (old[0] - route[neighbor][0]) * direction > 0):
                        candidates.append((i, j))
            # A pin annotation used to widen the label slot. Preserve the
            # external vertical route, adding only the missing horizontal leg.
            vertical = False
            if not candidates and mark and (new[0] - old[0]) * direction > 0:
                for i, route in enumerate(net['routing']):
                    if len(route) < 2:
                        continue
                    for j, neighbor in ((0, 1), (len(route) - 1, len(route) - 2)):
                        if (route[j] == old and route[neighbor][0] == old[0]
                                and route[neighbor][1] != row):
                            candidates.append((i, j))
                vertical = bool(candidates)
            boundary = (len(candidates) == 1 and
                        not vertical and
                        net['routing'][candidates[0][0]][1 if candidates[0][1] == 0 else -2] == new)
            reason = None
            swept = [[x,row] for x in range(min(old[0],new[0]),max(old[0],new[0])+1)]
            if len(candidates) != 1:
                reason = 'No unique horizontal endpoint at the old terminal presentation boundary'
            elif not boundary and not vertical and (new[0]-net['routing'][candidates[0][0]][1 if candidates[0][1]==0 else -2][0])*direction < 0:
                reason = 'A bend lies inside the fixed three-character pin slot; moving it requires separate layout review'
            elif not boundary and any(other is not net and any(covers(other,p) for p in swept if p not in (old,new)) for other in data['nets']):
                reason = 'The changed lead interval is occupied by another net'
            if reason:
                holds.append({'terminal': node, 'net': net['net number'], 'reason': reason})
                continue
            i, j = candidates[0]
            route = net['routing'][i]
            # The renderer supplies the horizontal pin stub. A vertical route
            # may end at its outer contact cell; no separate bend is required.
            # A two-point route wholly inside that stub is already equivalent.
            if boundary and len(route) == 2:
                continue
            before_route = [p[:] for p in route]
            if boundary:
                del route[j]
            elif vertical:
                route.insert(0, new) if j == 0 else route.append(new)
            else:
                route[j] = new
            adjusted = []
            for a, annotation in enumerate(net.get('annotations', [])):
                at = annotation.get('at')
                if not isinstance(at, dict) or at.get('polyline') != i:
                    continue
                point = at['point']
                replacement_point = (max(0, point - 1) if j == 0 else min(point, len(route) - 1)) if boundary else point
                if vertical and j == 0:
                    replacement_point = point + 1
                old_anchor, new_anchor = before_route[point], route[replacement_point]
                prior = annotation.get('offset', [0, 0])
                replacement = [prior[0] + old_anchor[0] - new_anchor[0],
                               prior[1] + old_anchor[1] - new_anchor[1]]
                if replacement_point != point or replacement != prior:
                    adjusted.append({'annotation': a, 'before': annotation.get('offset'),
                                     'after': replacement, 'point before': point,
                                     'point after': replacement_point})
                    annotation['at'] = {**at, 'point': replacement_point}
                    if replacement != prior:
                        annotation['offset'] = replacement
            change = {'terminal': node, 'net': net['net number'], 'polyline': i,
                      'point': j, 'before': old, 'after': new, 'annotation offsets': adjusted}
            if boundary:
                change.update({'removed redundant endpoint': True,
                               'before routing': before_route, 'after routing': [p[:] for p in route]})
            if vertical:
                change.update({'added horizontal annotation contact': True,
                               'before routing': before_route, 'after routing': [p[:] for p in route]})
            changes.append(change)
    return changes, holds

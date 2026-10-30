"""Normalize net contacts to the cell outside a fixed three-character pin slot.

The slot is the physical pin label or a three-character wire for null/omitted
identities. Annotations do not change its attachment coordinate. Only an
existing unique horizontal terminal endpoint is adjusted; other geometry or
competing route claims remain explicit holds requiring layout review.
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


def normalize_annotation_leads(data, details=None):
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
            reason = None
            swept = [[x,row] for x in range(min(old[0],new[0]),max(old[0],new[0])+1)]
            if len(candidates) != 1:
                reason = 'No unique horizontal endpoint at the old terminal presentation boundary'
            elif (new[0]-net['routing'][candidates[0][0]][1 if candidates[0][1]==0 else -2][0])*direction <= 0:
                reason = 'A bend lies inside the fixed three-character pin slot; moving it requires separate layout review'
            elif any(other is not net and any(covers(other,p) for p in swept if p!=old) for other in data['nets']):
                reason = 'The changed lead interval is occupied by another net'
            elif any(covers({'routing':[route]},p) for k,route in enumerate(net['routing'])
                     if k!=candidates[0][0] for p in swept if p!=new):
                reason = 'Another same-net route intersects the changed lead interval'
            if reason:
                holds.append({'terminal': node, 'net': net['net number'], 'reason': reason})
                continue
            i, j = candidates[0]
            net['routing'][i][j] = new
            adjusted = []
            for a, annotation in enumerate(net.get('annotations', [])):
                if annotation.get('at') == {'polyline': i, 'point': j}:
                    prior = annotation.get('offset', [0, 0])
                    replacement = [prior[0] + old[0] - new[0], prior[1]]
                    adjusted.append({'annotation': a, 'before': annotation.get('offset'), 'after': replacement})
                    annotation['offset'] = replacement
            changes.append({'terminal': node, 'net': net['net number'], 'polyline': i,
                            'point': j, 'before': old, 'after': new, 'annotation offsets': adjusted})
    return changes, holds

"""One-time migration of reviewed layouts to portable renderer definitions.

This imports already reviewed drawing geometry; it does not infer a card's
circuit from arbitrary scans. Normal rebuilds use generate_card.py alone.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re

from generate_card import ARMS, DIRS, OPPOSITE, ROOT, PIN, build, digest, read, wiring_graph


def compile_definition(card, source_dir):
    base_path = source_dir/(card+'.txt')
    raw = base_path.read_bytes()
    lines = raw.decode('utf-8').splitlines()
    width, height = max(map(len, lines)), len(lines)
    rows = [list(s.ljust(width)) for s in lines]
    removed = []
    for y, line in enumerate(lines):
        for match in re.finditer(r'\bGROUP\s+\d+\b', line):
            rows[y][match.start():match.end()] = [' '] * len(match.group())
            removed.append({'row': y, 'x': match.start(), 'text': match.group()})
    expected_base = [''.join(r).rstrip() for r in rows]
    consumed = set()
    boxes = []
    for y, row in enumerate(expected_base):
        for match in re.finditer(card + r'([0-9A-Z]{2})(?![0-9A-Z])', row):
            x, top = match.start() - 1, y - 4
            if x < 0 or top < 0 or ''.join(rows[top][x:x+8]) != '┌──────┐':
                continue
            bottom = top + 6
            while ''.join(rows[bottom][x:x+8]) != '└──────┘':
                bottom += 1
                assert bottom < height
            box = {'portion': match.group(1), 'x': x, 'top': top, 'height': bottom-top+1,
                   'function': ''.join(rows[top+1][x+1:x+7]).strip(),
                   'circuit_identifier': ''.join(rows[top+3][x+1:x+6]), 'ports': []}
            for yy in range(top+1, bottom):
                for side in ['input', 'output']:
                    adjacent = x-1 if side == 'input' else x+8
                    if not 0 <= adjacent < width or rows[yy][adjacent] not in '─BDGJ0123456789':
                        continue
                    start = x-3 if side == 'input' else x+8
                    label = ''.join(rows[yy][start:start+3])
                    pin = label if PIN.fullmatch(label) else None
                    border = x if side == 'input' else x+7
                    assert rows[yy][border] in '│◺'
                    port = {'id': f'{side}:{yy-top}', 'row': yy, 'side': side,
                            'pin': pin, 'triangle': rows[yy][border] == '◺'}
                    box['ports'].append(port)
                    if pin:
                        consumed.update((xx, yy) for xx in range(start, start+3))
            consumed.update((xx, yy) for yy in range(top, bottom+1) for xx in range(x, x+8))
            boxes.append(box)
    assert boxes
    first_box = min(b['top'] for b in boxes)
    header_rows = next((y for y, row in enumerate(expected_base) if not row), first_box) + 1
    exterior = []
    for y, row in enumerate(rows):
        if y < header_rows:
            continue
        for x, side in [(0, 'input'), (width-3, 'output')]:
            label = ''.join(row[x:x+3])
            if PIN.fullmatch(label):
                exterior.append({'pin': label, 'side': side, 'x': x, 'row': y})
                consumed.update((xx, y) for xx in range(x, x+3))
    segments, marks, annotations = [], [], []
    for y, row in enumerate(rows):
        x = 0
        while x < width:
            if (x, y) in consumed or row[x] == ' ':
                x += 1
            elif row[x] == '─':
                end = x
                while end+1 < width and row[end+1] == '─' and (end+1, y) not in consumed:
                    end += 1
                segments.append({'x1': x, 'x2': end, 'y': y})
                x = end+1
            elif row[x] in ARMS:
                marks.append({'x': x, 'y': y, 'symbol': row[x]})
                x += 1
            else:
                end = x
                while end+1 < width and (end+1, y) not in consumed and row[end+1] not in ARMS:
                    end += 1
                text = ''.join(row[x:end+1]).rstrip()
                if text:
                    annotations.append({'x': x, 'row': y, 'text': text})
                x = end+1
    power = {'D08':'GROUND','D03':'+3V','B06':'-3V','B11':'+6V'}
    if 'DOUBLE CARD' in lines[0]:
        power.update({'J08':'GROUND','J03':'+3V','G06':'-3V','G11':'+6V'})
    spec = {'schema':'reviewed-card-render-definition-v1', 'card_type':card,
            'canvas':{'width':width,'height':height,'header_rows':header_rows,'grid_origin':boxes[0]['top']%7},
            'power_contacts':power, 'canonical_line_ending':'CRLF' if b'\r\n' in raw else 'LF',
            'boxes':boxes,'wiring':{'horizontal_segments':segments,'marks':marks},
            'exterior_pins':exterior,'annotations':annotations,'nets':[],'variants':[],
            'provenance':{'source':'Independently reviewed universal card drawings; explicit human removal of GROUP labels.',
                          'canonical_predecessor_sha256':digest(raw),'removed_annotations':removed,
                          'evidence_directory':f'notes/Card-ALD/Universal/{card}',
                          'independent_acceptance':f'notes/Card-ALD/Universal/Independent review/{card} independent review.json'}}
    geometry_path = ROOT/f'notes/Card-ALD/Universal/{card}/{card} render provenance.json'
    reviewed_geometry = read(geometry_path)['geometry'] if geometry_path.exists() else None
    occupied_wires = {(x, s['y']):'─' for s in segments for x in range(s['x1'],s['x2']+1)}
    occupied_wires.update({(p['x'],p['y']):p['symbol'] for p in marks})
    for pin in exterior:
        occupied_wires.update({(xx,pin['row']):'─' for xx in range(pin['x'],pin['x']+3)})
    for box in boxes:
        for port in box['ports']:
            if port['pin']:
                xx = box['x']-3 if port['side']=='input' else box['x']+8
                occupied_wires.update({(x,port['row']):'─' for x in range(xx,xx+3)})
    for mark in marks:
        if mark['symbol'] != '◇':
            continue
        point = mark['x'], mark['y']
        if reviewed_geometry:
            owners = [net for net,cells in reviewed_geometry['net_wire_cells'].items() if list(point) in cells]
            assert len(owners)==1
            points = {tuple(p) for p in reviewed_geometry['net_wire_cells'][owners[0]]}
            flags = {d for d,(dx,dy) in DIRS.items() if (point[0]+dx,point[1]+dy) in points}
            for endpoint in reviewed_geometry['virtual_endpoint_directions']:
                if tuple(endpoint['point']) == point:
                    flags |= {['E','S','W','N'][d] for d in endpoint['nets'].get(owners[0],[])}
            mark['arms'] = ''.join(sorted(flags))
        else:
            flags = set()
            for d,(dx,dy) in DIRS.items():
                neighbor = occupied_wires.get((point[0]+dx,point[1]+dy))
                assert neighbor != '◇', 'Adjacent junctions require reviewed net directions'
                if neighbor and OPPOSITE[d] in ARMS[neighbor]:
                    flags.add(d)
            mark['arms'] = ''.join(sorted(flags))
    if reviewed_geometry:
        from collections import defaultdict
        nets = defaultdict(list)
        box_index = {b['portion']:b for b in boxes}
        for port in reviewed_geometry['ports']:
            matches = [p for p in box_index[port['portion']]['ports'] if p['side']==port['side'] and p['row']==port['point'][1]]
            assert len(matches)==1
            nets[port['net']].append('PORT:'+port['portion']+':'+matches[0]['id'])
        for pin in reviewed_geometry['exterior_contacts']:
            nets[pin].append('PIN:'+pin)
        spec['nets'] = sorted(sorted(values) for values in nets.values())
        spec['provenance']['reviewed_net_geometry'] = {'path':geometry_path.relative_to(ROOT).as_posix(),'sha256':digest(geometry_path.read_bytes())}
        assert wiring_graph(spec) == spec['nets'], 'Rendered wires differ from independently reviewed net identities'
    else:
        spec['nets'] = wiring_graph(spec)
    for path in sorted(source_dir.glob(card+'-[0-9][0-9].txt')):
        vr = path.read_bytes()
        vl = vr.decode('utf-8').splitlines()
        assert len(vl) == height
        overrides = {}
        for box in boxes:
            x, y = box['x'], box['top']
            change = {}
            function = vl[y+1].ljust(width)[x+1:x+7].strip()
            if function != box['function']:
                change['function'] = function
            flags = {}
            for p in box['ports']:
                bx = x if p['side'] == 'input' else x+7
                symbol = vl[p['row']].ljust(width)[bx]
                assert symbol in '│◺'
                if (symbol == '◺') != p['triangle']:
                    flags[p['id']] = symbol == '◺'
            if flags:
                change['port_triangles'] = flags
            if change:
                overrides[box['portion']] = change
        annotation_overrides = [{'row':y,'text':line} for y,line in enumerate(vl[:header_rows]) if line != lines[y]]
        variant = {'number':int(path.stem.split('-')[1]), 'box_overrides':overrides,
                   'annotation_overrides':annotation_overrides,
                   'line_ending':'CRLF' if b'\r\n' in vr else 'LF',
                   'predecessor_sha256':digest(vr)}
        spec['variants'].append(variant)
    # Exact equivalence is a migration gate, not an assumed property.
    from generate_card import render
    for variant in [None] + spec['variants']:
        name = card + (f'-{variant["number"]:02}' if variant else '') + '.txt'
        before = (source_dir/name).read_bytes().decode('utf-8').splitlines()
        expected = [re.sub(r'\bGROUP\s+\d+\b', lambda m:' '*len(m.group()), line).rstrip() for line in before]
        assert render(spec, variant) == expected, ('Not equivalent to reviewed layout',name)
    build(spec)
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('card_type')
    parser.add_argument('--source-dir', type=Path, default=ROOT/'Card-ALD')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'json/Card-ALD/definitions')
    args = parser.parse_args()
    assert re.fullmatch(r'\d{4}', args.card_type)
    definition = compile_definition(args.card_type, args.source_dir)
    target = args.output_dir/(args.card_type+'.json')
    assert not target.exists(), 'Do not replace an edited rendering definition through migration'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(definition,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'card_type':args.card_type,'portions':len(definition['boxes']),'variants':len(definition['variants'])}))


if __name__ == '__main__':
    main()

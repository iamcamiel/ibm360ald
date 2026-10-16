"""Render a reviewed card definition: python tools/card_ald/generate_card.py 4191.

Definitions under json/Card-ALD/definitions contain the reviewed layout and
notation patterns. This renderer has no card-specific code or dependencies.
Use --output-dir for a private build; otherwise update Card-ALD and its receipt.
"""
import argparse
from collections import defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[2]
PIN = re.compile(r'[BDGJ](?:0[2-9]|1[0-3])\Z')
DIRS = {'E': (1, 0), 'S': (0, 1), 'W': (-1, 0), 'N': (0, -1)}
OPPOSITE = {'E': 'W', 'W': 'E', 'N': 'S', 'S': 'N'}
ARMS = {'─': 'EW', '│': 'NS', '┌': 'ES', '┐': 'WS',
        '└': 'EN', '┘': 'WN', '┼': 'NSEW', '◇': 'NSEW'}


def digest(raw):
    return sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def put(rows, x, y, text):
    assert 0 <= y < len(rows) and 0 <= x <= len(rows[y]) - len(text), (x, y, text)
    for offset, char in enumerate(text):
        assert rows[y][x + offset] == ' ', ('Drawing collision', x + offset, y, char)
        rows[y][x + offset] = char


def termination_label(box, variant=None):
    change = (variant or {}).get('box_overrides', {}).get(box['portion'], {})
    return ' '.join([change.get('function', box['function']),
                     box['circuit_identifier'], box['portion']])


def render(spec, variant=None):
    width, height = spec['canvas']['width'], spec['canvas']['height']
    rows = [[' '] * width for _ in range(height)]
    for segment in spec['wiring']['horizontal_segments']:
        put(rows, segment['x1'], segment['y'], '─' * (segment['x2'] - segment['x1'] + 1))
    for point in spec['wiring']['marks']:
        assert point['symbol'] in ARMS and point['symbol'] != '─'
        put(rows, point['x'], point['y'], point['symbol'])
    replacements = (variant or {}).get('box_overrides', {})
    assert set(replacements) <= {b['portion'] for b in spec['boxes']}
    for box in spec['boxes']:
        x, y, h = box['x'], box['top'], box['height']
        change = replacements.get(box['portion'], {})
        assert set(change) <= {'function', 'port_triangles'}, 'A variant may not move geometry'
        function = change.get('function', box['function'])
        assert isinstance(function, str) and 0 < len(function) <= 6
        if 'compact_termination' in box:
            compact = box['compact_termination']
            xx, yy = compact['point']
            label = termination_label(box, variant)
            assert len(label) <= compact['label_width'], 'Compact termination label exceeds its reserved space'
            triangles = change.get('port_triangles', {})
            assert set(triangles) <= {p['id'] for p in box['ports']}
            port = box['ports'][0]
            if triangles.get(port['id'], port['triangle']):
                assert rows[yy][xx] == '└', 'Compact input decoration requires its terminal corner'
                rows[yy][xx] = '◺'
            put(rows, xx + 1, yy, label.ljust(compact['label_width']))
            continue
        put(rows, x, y, '┌──────┐')
        put(rows, x, y + h - 1, '└──────┘')
        for yy in range(y + 1, y + h - 1):
            put(rows, x, yy, '│')
            put(rows, x + 7, yy, '│')
        put(rows, x + 1, y + 1, function)
        put(rows, x + 1, y + 3, box['circuit_identifier'])
        put(rows, x + 1, y + 4, spec['card_type'] + box['portion'])
        triangles = change.get('port_triangles', {})
        assert set(triangles) <= {p['id'] for p in box['ports']}
        for port in box['ports']:
            border = x if port['side'] == 'input' else x + 7
            rows[port['row']][border] = '◺' if triangles.get(port['id'], port['triangle']) else '│'
            if port['pin']:
                put(rows, x - 3 if port['side'] == 'input' else x + 8, port['row'], port['pin'])
    for pin in spec['exterior_pins']:
        put(rows, pin['x'], pin['row'], pin['pin'])
    for annotation in spec['annotations']:
        put(rows, annotation['x'], annotation['row'], annotation['text'])
    for change in (variant or {}).get('annotation_overrides', []):
        assert 0 <= change['row'] < spec['canvas']['header_rows']
        rows[change['row']] = list(change['text'].ljust(width))
        assert len(rows[change['row']]) == width
    lines = [''.join(row).rstrip() for row in rows]
    assert not any(re.search(r'\bGROUP\s+\d+\b', line) for line in lines)
    return lines


def wiring_graph(spec):
    """Trace visible wires; a cross has two separate tracks, a diamond joins."""
    cells = {}
    explicit_arms = {}
    for seg in spec['wiring']['horizontal_segments']:
        for x in range(seg['x1'], seg['x2'] + 1):
            assert (x, seg['y']) not in cells, 'Overlapping wire segments'
            cells[x, seg['y']] = '─'
    for point in spec['wiring']['marks']:
        xy = point['x'], point['y']
        assert xy not in cells, 'Overlapping wire marks'
        cells[xy] = point['symbol']
        if point['symbol'] == '◇':
            assert 'arms' in point, 'A junction requires reviewed incident directions'
            explicit_arms[xy] = set(point['arms'])
    endpoints = defaultdict(list)
    removed_arms = defaultdict(set)
    for box in spec['boxes']:
        for port in box['ports']:
            if 'compact_termination' in box:
                x, y = box['compact_termination']['point']
                endpoints[x, y].append('PORT:' + box['portion'] + ':' + port['id'])
                removed_arms[x, y].add('E')
                continue
            left = port['side'] == 'input'
            x, y = (box['x'] - 1 if left else box['x'] + 8), port['row']
            terminal = 'PORT:' + box['portion'] + ':' + port['id']
            endpoints[x, y].append(terminal)
            removed_arms[x, y].add('E' if left else 'W')
            if port['pin']:
                start = box['x'] - 3 if left else box['x'] + 8
                for xx in range(start, start + 3):
                    assert (xx, y) not in cells, 'Pin label overlaps a routed wire'
                    cells[xx, y] = '─'
    for pin in spec['exterior_pins']:
        x, y = pin['x'], pin['row']
        for xx in range(x, x + 3):
            assert (xx, y) not in cells, 'Exterior label overlaps wire'
            cells[xx, y] = '─'
        endpoint = (x, y) if pin['side'] == 'input' else (x + 2, y)
        endpoints[endpoint].append('PIN:' + pin['pin'])
        removed_arms[endpoint].add('W' if pin['side'] == 'input' else 'E')
    arms = {xy: explicit_arms.get(xy, set(ARMS[ch])) - removed_arms[xy] for xy, ch in cells.items()}
    for (x, y), ch in cells.items():
        if ch == '◇':
            assert len(arms[x, y]) >= 3, ('Diamond is not a junction', x, y)
    adjacency = defaultdict(set)
    states = {}
    for xy, directions in arms.items():
        x, y = xy
        assert directions, ('Isolated wire', xy)
        for d in directions:
            dx, dy = DIRS[d]
            neighbor = x + dx, y + dy
            assert OPPOSITE[d] in arms.get(neighbor, set()), ('Dangling wire', xy, d, cells[xy])
            state = (x, y, 'V' if cells[xy] == '┼' and d in 'NS' else 'H' if cells[xy] == '┼' else 'J')
            other = (*neighbor, 'V' if cells[neighbor] == '┼' and d in 'NS' else 'H' if cells[neighbor] == '┼' else 'J')
            adjacency[state].add(other)
            states[xy, d] = state
    components, seen = [], set()
    for state in adjacency:
        if state in seen:
            continue
        todo, component, terminals = [state], set(), set()
        while todo:
            node = todo.pop()
            if node in component:
                continue
            component.add(node)
            terminals.update(endpoints[node[:2]])
            todo.extend(adjacency[node] - component)
        seen |= component
        assert len(terminals) >= 2, ('Wire has fewer than two terminals', sorted(terminals), min(component))
        components.append(sorted(terminals))
    assert set(endpoints) <= set(cells), 'Unrouted terminal'
    return sorted(components)


def validate(spec):
    assert spec['schema'] == 'reviewed-card-render-definition-v1'
    assert re.fullmatch(r'\d{4}', spec['card_type'])
    boxes = spec['boxes']
    assert len({b['portion'] for b in boxes}) == len(boxes), 'Duplicate portion'
    assert len({p['pin'] for p in spec['exterior_pins']}) == len(spec['exterior_pins']), 'Duplicate exterior pin'
    power = set(spec['power_contacts'])
    for pin in spec['exterior_pins']:
        assert PIN.fullmatch(pin['pin']) and pin['pin'] not in power
    occupied = set()
    compact_labels = {}
    marks = {(m['x'], m['y']): m for m in spec['wiring']['marks']}
    grid_step = spec['canvas'].get('grid_step', 7)
    assert grid_step in [1, 7], 'Unsupported box row spacing'
    for b in boxes:
        assert b['height'] == max(7, len([p for p in b['ports'] if p['side'] == 'input']) + 2)
        assert (b['top'] - spec['canvas']['grid_origin']) % grid_step == 0
        assert len(b['circuit_identifier']) == 5
        assert len({p['id'] for p in b['ports']}) == len(b['ports'])
        assert all(p['side'] in ['input', 'output'] and b['top'] < p['row'] < b['top'] + b['height'] - 1 for p in b['ports'])
        for p in b['ports']:
            assert p['pin'] is None or PIN.fullmatch(p['pin']) and p['pin'] not in power
        if 'compact_termination' in b:
            compact = b['compact_termination']
            assert set(compact) == {'point', 'label_width'}, 'Unsupported compact termination geometry'
            assert b['function'].split()[0] == 'R', 'Only terminating R portions may use compact notation'
            assert len(b['ports']) == 1 and b['ports'][0]['side'] == 'input', 'Compact R must have one input and no outputs'
            p = b['ports'][0]
            terminal = 'PORT:' + b['portion'] + ':' + p['id']
            nets = [net for net in spec['nets'] if terminal in net]
            assert len(nets) == 1 and any(t.startswith('PORT:') and not t.startswith('PORT:' + b['portion'] + ':')
                                         for t in nets[0]), 'A standalone R must retain its standard box'
            labels = [termination_label(b)]
            for variant in spec['variants']:
                change = variant.get('box_overrides', {}).get(b['portion'], {})
                assert change.get('function', b['function']).split()[0] == 'R', 'Compact variants must retain their R function'
                assert set(change.get('port_triangles', {})) <= {p['id']}, 'Unknown compact port decoration'
                labels.append(termination_label(b, variant))
            assert isinstance(compact['label_width'], int) and compact['label_width'] >= max(len(labels[0]) + 3, *map(len, labels)), 'Compact R needs three reserved variant characters'
            x, y = compact['point']
            assert isinstance(x, int) and isinstance(y, int)
            assert marks.get((x, y), {}).get('symbol') == '└', 'Compact R endpoint must be a dangling corner'
            above = marks.get((x, y - 1), {})
            assert above.get('symbol') == '◇' and set('EWS') <= set(above.get('arms', '')), 'Compact R must hang directly below its net junction'
            assert 0 <= x < x + compact['label_width'] < spec['canvas']['width'] and 0 < y < spec['canvas']['height']
            compact_labels[(x, y)] = {(xx, y) for xx in range(x + 1, x + 1 + compact['label_width'])}
            continue
        area = {(x, y) for x in range(b['x'], b['x'] + 8) for y in range(b['top'], b['top'] + b['height'])}
        assert not occupied & area, 'Overlapping boxes'
        occupied |= area
    assert {p['pin'] for b in boxes for p in b['ports'] if p['pin']} == {p['pin'] for p in spec['exterior_pins']}, 'Exterior and block pin coverage differ'
    assert wiring_graph(spec) == spec['nets'], 'Wiring differs from reviewed terminal connections'
    base = render(spec)
    box_and_label = occupied | {(x, p['row']) for b in boxes if 'compact_termination' not in b for p in b['ports'] if p['pin']
                                for x in range(b['x'] - 3, b['x']) if p['side'] == 'input'}
    box_and_label |= {(x, p['row']) for b in boxes if 'compact_termination' not in b for p in b['ports'] if p['pin'] and p['side'] == 'output'
                      for x in range(b['x'] + 8, b['x'] + 11)}
    vertical_by_row = defaultdict(set)
    for p in spec['wiring']['marks']:
        if p['symbol'] in '│┌┐└┘┼◇':
            assert 3 <= p['x'] < spec['canvas']['width'] - 3, 'Vertical wire outside pin margins'
            vertical_by_row[p['y']].add(p['x'])
            assert all(abs(p['x'] - x) >= 3 for x, y in box_and_label if y == p['y']), 'Wire too close to box/pin label'
            assert all(abs(p['x'] - x) >= 3 for own_point, cells in compact_labels.items()
                       if own_point != (p['x'], p['y']) for x, y in cells if y == p['y']), 'Wire too close to a compact R label'
    assert all(b - a >= 2 for xs in vertical_by_row.values() for a, b in zip(sorted(xs), sorted(xs)[1:])), 'Parallel wires too close'
    variants = spec['variants']
    assert len({v['number'] for v in variants}) == len(variants)
    for variant in variants:
        assert set(variant) <= {'number', 'box_overrides', 'annotation_overrides', 'line_ending', 'predecessor_sha256'}, 'A variant cannot define geometry'
        render(spec, variant)
    return {'portions': len(boxes), 'exterior_signal_pins': len(spec['exterior_pins']),
            'nets': len(spec['nets']), 'variants': len(variants),
            'width': spec['canvas']['width'], 'compact_terminations': len(compact_labels),
            'spacing': {'box_or_pin_label': 2, 'parallel_wires': 1}}


def build(spec):
    checks = validate(spec)
    outputs = {}
    for pattern in [None] + spec['variants']:
        number = pattern['number'] if pattern else 0
        name = spec['card_type'] + (f'-{number:02}' if number else '') + '.txt'
        line_ending = (pattern or {}).get('line_ending', spec['canonical_line_ending'])
        assert line_ending in ['LF', 'CRLF']
        newline = '\r\n' if line_ending == 'CRLF' else '\n'
        outputs[name] = (newline.join(render(spec, pattern)) + newline).encode('utf-8')
    assert len({'\n'.join(raw.decode('utf-8').splitlines()[spec['canvas']['header_rows']:])
                for raw in outputs.values()}) == len(outputs), 'Duplicate notation variant'
    return outputs, checks


def write_protected(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    old_mode = path.stat().st_mode if path.exists() else None
    try:
        if old_mode is not None and not old_mode & stat.S_IWRITE:
            path.chmod(old_mode | stat.S_IWRITE)
        path.write_bytes(raw)
    finally:
        if old_mode is not None:
            path.chmod(old_mode)


def record_generation(spec, path, outputs, checks):
    card = spec['card_type']
    receipt = {'schema': 'card-ald-generation-v1', 'card_type': card,
               'canonical': f'Card-ALD/{card}.txt', 'diagram_sha256': digest(outputs[card+'.txt']),
               'definition': {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(path.read_bytes())},
               'renderer': {'path': Path(__file__).relative_to(ROOT).as_posix(), 'sha256': digest(Path(__file__).read_bytes())},
               'source_evidence': spec['provenance'], 'validation': checks,
               'files': [{'path': 'Card-ALD/' + name, 'sha256': digest(raw)} for name, raw in outputs.items()]}
    raw = (json.dumps(receipt, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    for destination in [f'Generation/{card}.json', f'{card} drawing provenance.json', f'{card} diagram publication receipt.json']:
        write_protected(ROOT/'notes/Card-ALD'/destination, raw)
    model_path = ROOT/f'json/Card-ALD/{card}.json'
    model = read(model_path) if model_path.exists() else {'schema':'card-ald-generated-model-v1','card_type':card}
    model.update(drawing=receipt['canonical'], drawing_sha256=receipt['diagram_sha256'],
                 render_definition=receipt['definition'], generation_receipt=f'notes/Card-ALD/Generation/{card}.json')
    write_protected(model_path, (json.dumps(model, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    index_path = ROOT/'csv/Card-ALD/Notation variants.csv'
    if index_path.exists():
        with index_path.open(encoding='utf-8-sig', newline='') as source:
            reader = csv.DictReader(source)
            fields, entries = reader.fieldnames, list(reader)
        for entry in entries:
            if entry['file'] in outputs:
                entry['sha256'] = digest(outputs[entry['file']])
        import io
        buffer = io.StringIO(newline='')
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        writer.writerows(entries)
        write_protected(index_path, b'\xef\xbb\xbf'+buffer.getvalue().encode('utf-8'))
    inventory_path = ROOT/'notes/Card-ALD/Universal card diagrams publication.json'
    if inventory_path.exists():
        inventory = read(inventory_path)
        if inventory['schema'] == 'shared-card-renderer-publication-v1':
            inventory['published_files'] = [e for e in inventory['published_files']
                                           if Path(e['path']).name not in outputs] + receipt['files']
            entries = [e for e in inventory['cards'] if e['card_type'] == card]
            if not entries:
                entries = [{'card_type':card,'canonical':receipt['canonical']}]
                inventory['cards'].extend(entries)
            entries[0].update(diagram_sha256=receipt['diagram_sha256'],variant_count=len(spec['variants']),
                              generation_receipt=f'notes/Card-ALD/Generation/{card}.json')
            write_protected(inventory_path,(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('card_type', help='Four-digit card type, for example 4191')
    parser.add_argument('--definitions', type=Path, default=ROOT/'json/Card-ALD/definitions')
    parser.add_argument('--output-dir', type=Path, help='Private build directory; default publishes to Card-ALD')
    parser.add_argument('--check', action='store_true', help='Validate definition without writing files')
    args = parser.parse_args()
    if not re.fullmatch(r'\d{4}', args.card_type):
        parser.error('Use a four-digit card type, for example 0141 or 4191.')
    path = args.definitions/(args.card_type + '.json')
    if not path.is_file():
        parser.error(f'No reviewed rendering definition for {args.card_type}. Add a reviewed JSON definition first.')
    spec = read(path)
    assert spec['card_type'] == args.card_type
    outputs, checks = build(spec)
    if not args.check:
        target = args.output_dir or ROOT/'Card-ALD'
        stale = [p.name for p in target.glob(args.card_type+'-[0-9]*.txt')
                 if re.fullmatch(args.card_type+r'-\d+\.txt', p.name) and p.name not in outputs]
        assert not stale, 'Unlisted older variants require review before replacement: '+', '.join(stale)
        for name, raw in outputs.items():
            write_protected(target/name, raw)
        if args.output_dir is None:
            record_generation(spec, path, outputs, checks)
    print(json.dumps({'card_type': args.card_type, 'files': len(outputs), **checks, 'check_only': args.check}))


if __name__ == '__main__':
    main()

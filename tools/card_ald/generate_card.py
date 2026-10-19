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
from display_direction import exterior_display_side
from card_source import ordinary_slt_identity_issue

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
                     change.get('circuit_identifier',box['circuit_identifier']), box['portion']])


def port_label(box, port):
    """Physical contacts stay separate from their explicitly placed source marks."""
    symbols = port.get('pin_symbols', {})
    assert isinstance(symbols, dict) and set(symbols) <= {'prefix', 'suffix'}, 'Unknown pin symbol placement'
    for side in ('prefix', 'suffix'):
        assert isinstance(symbols.get(side, []), list), 'Pin symbols require ordered literal arrays'
        assert all(mark == '✲' for mark in symbols.get(side, [])), 'Unsupported intrinsic pin symbol'
    assert port.get('pin') or not any(symbols.values()), 'A pin symbol requires a physical contact'
    role=port.get('contact_role','logical');control=port.get('border_control')
    assert role in ('logical','nonlogical_common'), 'Unknown physical contact role'
    assert (control=='K') == (role=='nonlogical_common'), 'Nonlogical contact requires an explicit K control'
    assert role!='nonlogical_common' or port.get('pin'), 'Nonlogical K contact requires a physical pin'
    assert not (control=='K' and (port.get('border_symbol') or port['triangle'])), 'K cannot share one border cell with a triangle or X'
    text = ''.join(symbols.get('prefix', [])) + (port.get('pin') or '') + ''.join(symbols.get('suffix', []))
    start = box['x'] - len(text) if port['side'] == 'input' else box['x'] + 8
    return start, port['row'], text


def put_port_label(rows, box, port):
    x, y, label = port_label(box, port)
    assert 0 <= x <= len(rows[y]) - len(label), 'Pin label exceeds canvas'
    original_start = box['x'] - 3 if port['side'] == 'input' else box['x'] + 8
    for offset, char in enumerate(label):
        xx = x + offset
        expected = ' ' if original_start <= xx < original_start + 3 else '─'
        assert rows[y][xx] == expected, ('Pin symbol needs a straight wire label slot', xx, y)
        rows[y][xx] = char


def notation_ports(box, change):
    """Notation overrides may replace decorations, never terminal identity/geometry."""
    ids = {port['id'] for port in box['ports']}
    for key in ('port_triangles', 'border_symbols', 'port_symbols'):
        assert isinstance(change.get(key, {}), dict) and set(change.get(key, {})) <= ids, 'Unknown port decoration override'
    result = []
    for original in box['ports']:
        port = dict(original)
        for source, target in (('port_triangles', 'triangle'), ('border_symbols', 'border_symbol'), ('port_symbols', 'pin_symbols')):
            if port['id'] in change.get(source, {}):
                port[target] = change[source][port['id']]
        assert port.get('border_symbol') in (None, 'X'), 'Unsupported source border symbol'
        assert not (port.get('border_symbol') and port['triangle']), 'A port cannot combine a triangle and X'
        port_label(box, port)
        result.append(port)
    return result


def _header_lines_v1(spec, variant=None):
    """Format every reviewed card and notation variant from the same factual fields."""
    facts = spec['header']
    assert facts['schema'] == 'card-ald-header-v1'
    assert re.fullmatch(r'\d{7}', facts['part_number'])
    assert facts['card_width'] in ['SINGLE CARD', 'DOUBLE CARD']
    assert spec['canvas']['header_rows'] == 7, 'The shared heading requires seven reserved lines'
    for key in ['reviewed_occurrences', 'reviewed_pages']:
        assert isinstance(facts[key], int) and facts[key] >= 0
    assert facts['reviewed_pages'] <= facts['reviewed_occurrences']
    banks = 'BD' if facts['card_width'] == 'SINGLE CARD' else 'BDGJ'
    authority=spec.get('component_power_authority', {'role':'ordinary_slt'})
    role=authority.get('role')
    assert role in ('ordinary_slt','reviewed_special','not_established'), 'Unknown power authority'
    if role=='ordinary_slt':assert {p[0] for p in spec['power_contacts']} == set(banks)
    if role=='not_established':assert not spec['power_contacts'], 'Unknown rails must remain unassigned'
    signal = {p['pin'] for p in spec['exterior_pins']}
    possible = {f'{bank}{n:02}' for bank in banks for n in range(2, 14)}
    unconnected = sorted(possible - set(spec['power_contacts']) - signal)
    inputs = sum(p['side'] == 'input' for p in spec['exterior_pins'])
    outputs = sum(p['side'] == 'output' for p in spec['exterior_pins'])
    power = []
    levels = ['GROUND', '+3V', '-3V', '+6V']
    assert set(spec['power_contacts'].values()) <= set(levels)
    for level in levels:
        pins = sorted(p for p, value in spec['power_contacts'].items() if value == level)
        if pins:
            power.append(level + ' ' + ' '.join(pins))
    boxes = {b['portion']: b for b in spec['boxes']}
    provisional = defaultdict(list)
    seen = set()
    for entry in facts['provisional_forms']:
        portion, circuit = entry['portion'], entry['circuit_identifier']
        assert portion not in seen and boxes[portion]['circuit_identifier'] == circuit
        seen.add(portion)
        provisional[circuit].append(portion)
    provisional_text = ', '.join('/'.join(sorted(portions)) + ' ' + circuit
                                 for circuit, portions in sorted(provisional.items())) or 'NONE'
    number = (variant or {}).get('number', 0)
    identity = f'VARIANT {number:02}' if variant else 'CANONICAL'
    standard=facts.get('symbol_standard','SLT MANUAL STANDARD')
    assert standard in ('SLT MANUAL STANDARD','PRINTED ALD FORMS','MIXED MANUAL AND PRINTED ALD FORMS')
    symbols = f'OBSERVED NOTATION VARIANT {number:02}' if variant else standard
    power_text='; '.join(power) if power and role!='not_established' else 'NOT ESTABLISHED'
    power_heading='RESERVED SYSTEM CONTACTS: ' if authority.get('source_contact_role')=='reserved_system_contact_positions' else 'POWER: '
    contact_text=(', '.join(unconnected)+' (POSSIBLY UNUSED)' if unconnected else 'NONE')
    if role!='ordinary_slt' and authority.get('contact_set_complete')is not True:contact_text='NOT ESTABLISHED'
    lines = [
        f"CARD-ALD {facts['part_number']}  {facts['card_width']}  {identity}",
        f"PORTIONS: {len(boxes)}; SIGNAL CONTACTS: {len(signal)} ({inputs} INPUT, {outputs} OUTPUT)",
        power_heading + power_text,
        'UNCONNECTED SIGNAL CONTACTS: ' + contact_text,
        'PROVISIONAL CIRCUIT FORMS: ' + provisional_text,
        'SYMBOLS: ' + symbols,
        f"SOURCE: {facts['reviewed_occurrences']} REVIEWED OCCURRENCES ON {facts['reviewed_pages']} PAGES",
    ]
    assert all(len(line) <= spec['canvas']['width'] for line in lines), 'Shared heading exceeds the reserved width'
    return lines


def _header_lines_v2(spec, variant=None):
    """Format every reviewed card and notation variant from the same factual fields."""
    facts = spec['header']
    assert facts['schema'] == 'card-ald-header-v2'
    assert 'part_number' not in facts, 'V2 cannot also declare a scalar part number'
    parts=facts['part_numbers']
    assert isinstance(parts,list) and all(isinstance(p,str) and re.fullmatch(r'\d{7}',p) for p in parts), 'Only exact full part numbers may be listed'
    assert len(parts)==len(set(parts)), 'Duplicate full part-number observations'
    assert len(parts)!=1, 'Use the exact V1 schema for one full part number'
    assert re.fullmatch(r'\d{4}',spec['card_type']), 'Card type identity is required'
    part_text='PART NUMBER NOT ESTABLISHED' if not parts else 'PART NUMBERS '+', '.join(sorted(parts))
    assert facts['card_width'] in ['SINGLE CARD', 'DOUBLE CARD']
    assert spec['canvas']['header_rows'] == 7, 'The shared heading requires seven reserved lines'
    for key in ['reviewed_occurrences', 'reviewed_pages']:
        assert isinstance(facts[key], int) and facts[key] >= 0
    assert facts['reviewed_pages'] <= facts['reviewed_occurrences']
    banks = 'BD' if facts['card_width'] == 'SINGLE CARD' else 'BDGJ'
    authority=spec.get('component_power_authority', {'role':'ordinary_slt'})
    role=authority.get('role')
    assert role in ('ordinary_slt','reviewed_special','not_established'), 'Unknown power authority'
    if role=='ordinary_slt':assert {p[0] for p in spec['power_contacts']} == set(banks)
    if role=='not_established':assert not spec['power_contacts'], 'Unknown rails must remain unassigned'
    signal = {p['pin'] for p in spec['exterior_pins']}
    possible = {f'{bank}{n:02}' for bank in banks for n in range(2, 14)}
    unconnected = sorted(possible - set(spec['power_contacts']) - signal)
    inputs = sum(p['side'] == 'input' for p in spec['exterior_pins'])
    outputs = sum(p['side'] == 'output' for p in spec['exterior_pins'])
    power = []
    levels = ['GROUND', '+3V', '-3V', '+6V']
    assert set(spec['power_contacts'].values()) <= set(levels)
    for level in levels:
        pins = sorted(p for p, value in spec['power_contacts'].items() if value == level)
        if pins:
            power.append(level + ' ' + ' '.join(pins))
    boxes = {b['portion']: b for b in spec['boxes']}
    provisional = defaultdict(list)
    seen = set()
    for entry in facts['provisional_forms']:
        portion, circuit = entry['portion'], entry['circuit_identifier']
        assert portion not in seen and boxes[portion]['circuit_identifier'] == circuit
        seen.add(portion)
        provisional[circuit].append(portion)
    provisional_text = ', '.join('/'.join(sorted(portions)) + ' ' + circuit
                                 for circuit, portions in sorted(provisional.items())) or 'NONE'
    number = (variant or {}).get('number', 0)
    identity = f'VARIANT {number:02}' if variant else 'CANONICAL'
    standard=facts.get('symbol_standard','SLT MANUAL STANDARD')
    assert standard in ('SLT MANUAL STANDARD','PRINTED ALD FORMS','MIXED MANUAL AND PRINTED ALD FORMS')
    symbols = f'OBSERVED NOTATION VARIANT {number:02}' if variant else standard
    power_text='; '.join(power) if power and role!='not_established' else 'NOT ESTABLISHED'
    power_heading='RESERVED SYSTEM CONTACTS: ' if authority.get('source_contact_role')=='reserved_system_contact_positions' else 'POWER: '
    contact_text=(', '.join(unconnected)+' (POSSIBLY UNUSED)' if unconnected else 'NONE')
    if role!='ordinary_slt' and authority.get('contact_set_complete')is not True:contact_text='NOT ESTABLISHED'
    lines = [
        f"CARD-ALD {spec['card_type']}  {part_text}  {facts['card_width']}  {identity}",
        f"PORTIONS: {len(boxes)}; SIGNAL CONTACTS: {len(signal)} ({inputs} INPUT, {outputs} OUTPUT)",
        power_heading + power_text,
        'UNCONNECTED SIGNAL CONTACTS: ' + contact_text,
        'PROVISIONAL CIRCUIT FORMS: ' + provisional_text,
        'SYMBOLS: ' + symbols,
        f"SOURCE: {facts['reviewed_occurrences']} REVIEWED OCCURRENCES ON {facts['reviewed_pages']} PAGES",
    ]
    assert all(len(line) <= spec['canvas']['width'] for line in lines), 'Shared heading exceeds the reserved width'
    return lines


def header_lines(spec, variant=None):
    """Keep the V1 format exact; V2 records absent or multiple exact identities."""
    if spec['header'].get('schema')=='card-ald-header-v2':
        return _header_lines_v2(spec,variant)
    return _header_lines_v1(spec,variant)



def caption_locations(spec):
    """Captions have one geometry shared by canonical and notation variants."""
    boxes={box['portion']:box for box in spec['boxes']}
    seen=set();result=[]
    for caption in spec.get('box_captions',[]):
        assert set(caption)=={'portion','text'}, 'Caption may not override geometry'
        portion=caption['portion'];label=caption['text']
        assert portion in boxes and portion not in seen, 'Unknown or duplicate caption portion'
        assert isinstance(label,str) and label and '\n' not in label and '\r' not in label
        box=boxes[portion];assert 'compact_termination' not in box
        x,y=box['x'],box['top']-1
        assert y>=spec['canvas']['header_rows'] and 0<=x<x+len(label)<=spec['canvas']['width']
        result.append((x,y,label));seen.add(portion)
    return result


def render(spec, variant=None):
    width, height = spec['canvas']['width'], spec['canvas']['height']
    rows = [[' '] * width for _ in range(height)]
    for segment in spec['wiring']['horizontal_segments']:
        put(rows, segment['x1'], segment['y'], '─' * (segment['x2'] - segment['x1'] + 1))
    for point in spec['wiring']['marks']:
        assert point['symbol'] in ARMS and point['symbol'] != '─'
        put(rows, point['x'], point['y'], point['symbol'])
    import multicircuit_variants as multi
    multi.check_spec(spec)
    if variant:multi.check_variant(spec,variant)
    replacements = (variant or {}).get('box_overrides', {})
    assert set(replacements) <= {b['portion'] for b in spec['boxes']}
    for box in spec['boxes']:
        x, y, h = box['x'], box['top'], box['height']
        change = replacements.get(box['portion'], {})
        assert set(change) <= {'function', 'port_triangles', 'border_symbols', 'port_symbols', 'circuit_identifier'}, 'A variant may not move geometry'
        displayed_ports = notation_ports(box, change)
        function = change.get('function', box['function'])
        assert isinstance(function, str) and 0 < len(function) <= 6
        if 'compact_termination' in box:
            compact = box['compact_termination']
            xx, yy = compact['point']
            label = termination_label(box, variant)
            assert len(label) <= compact['label_width'], 'Compact termination label exceeds its reserved space'
            triangles = change.get('port_triangles', {})
            assert set(triangles) <= {p['id'] for p in box['ports']}
            port = displayed_ports[0]
            assert not port.get('border_symbol') and not any(port.get('pin_symbols', {}).values()), 'Compact R cannot hide source pin decorations'
            if port['triangle']:
                assert rows[yy][xx] in ('└','┌'), 'Compact input decoration requires its terminal corner'
                rows[yy][xx] = '◺' if rows[yy][xx]=='└' else '◸'
            put(rows, xx + 1, yy, label.ljust(compact['label_width']))
            continue
        put(rows, x, y, '┌──────┐')
        put(rows, x, y + h - 1, '└──────┘')
        for yy in range(y + 1, y + h - 1):
            put(rows, x, yy, '│')
            put(rows, x + 7, yy, '│')
        put(rows, x + 1, y + 1, function)
        put(rows, x + 1, y + 3, change.get('circuit_identifier',box['circuit_identifier']))
        put(rows, x + 1, y + 4, spec['card_type'] + box['portion'])
        triangles = change.get('port_triangles', {})
        assert set(triangles) <= {p['id'] for p in box['ports']}
        for port in displayed_ports:
            border = x if port['side'] == 'input' else x + 7
            triangle = port['triangle']
            symbol = port.get('border_symbol')
            assert symbol in (None, 'X'), 'Unsupported source border symbol'
            assert not (symbol and triangle), 'A port cannot combine a triangle and X'
            rows[port['row']][border] = ('K' if port.get('border_control')=='K' else symbol or ('◺' if triangle else '│'))
            if port['pin']:
                put_port_label(rows, box, port)
    for x,y,label in caption_locations(spec):put(rows,x,y,label)
    for pin in spec['exterior_pins']:
        put(rows, pin['x'], pin['row'], pin['pin'])
    for annotation in spec['annotations']:
        if 'header' in spec:
            assert annotation['row'] >= spec['canvas']['header_rows'], 'Literal headings cannot override the shared template'
        put(rows, annotation['x'], annotation['row'], annotation['text'])
    if 'header' in spec:
        assert not (variant or {}).get('annotation_overrides'), 'Variants use the same shared heading template'
        for y, text in enumerate(header_lines(spec, variant)):
            put(rows, 0, y, text)
    else:
        # Historical definitions and small wiring fixtures retain their literal annotations.
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


def validate_compact_support(box, net, marks):
    """A real branch junction, or an unbranched two-contact existing stem elbow."""
    x,y=box['compact_termination']['point'];endpoint=marks.get((x,y),{}).get('symbol')
    assert endpoint in ('└','┌'), 'Compact R endpoint must be a dangling corner'
    dy=1 if endpoint=='└' else -1
    support=marks.get((x,y-dy),{});symbol=support.get('symbol')
    vertical='S' if dy==1 else 'N'
    arms=set(support.get('arms','')) if symbol=='◇' else set(ARMS.get(symbol,''))
    if symbol=='◇':
        assert set('EW'+vertical)<=arms, 'Compact R junction lacks its reviewed trunk/stub directions'
        return
    terminal='PORT:'+box['portion']+':'+box['ports'][0]['id']
    assert len(net)==2 and all(t.startswith('PORT:') for t in net) and terminal in net, 'Compact elbow requires exactly two block contacts'
    assert symbol in ('┌','┐','└','┘') and len(arms)==2 and vertical in arms and len(arms&set('EW'))==1, 'Compact R must adjoin its existing stem elbow'


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
        assert ordinary_slt_identity_issue({'card_type':spec['card_type'],'portion':b.get('portion'),'unit':b.get('circuit_identifier')}) is None, 'Unresolved ordinary SLT portion identity'
        functions=[b['function']]+[v.get('box_overrides',{}).get(b['portion'],{}).get('function',b['function'])
                                  for v in spec.get('variants',[])]
        if any(str(label).strip().lstrip('✲*').split()[:1]==['AR'] for label in functions):
            inputs={p['pin'] for p in b['ports'] if p['side']=='input' and p.get('pin')}
            assert not any(p['side']=='output' and p.get('pin') in inputs for p in b['ports']), \
                'AR repeated input contact must be input-only; remove the duplicate output port'
        assert b['height'] == max(7, len([p for p in b['ports'] if p['side'] == 'input']) + 2)
        assert (b['top'] - spec['canvas']['grid_origin']) % grid_step == 0
        assert len(b['circuit_identifier']) == 5
        assert len({p['id'] for p in b['ports']}) == len(b['ports'])
        assert all(p['side'] in ['input', 'output'] and b['top'] < p['row'] < b['top'] + b['height'] - 1 for p in b['ports'])
        for p in b['ports']:
            assert p['pin'] is None or PIN.fullmatch(p['pin']) and p['pin'] not in power
            port_label(b, p)
            assert p.get('border_symbol') in (None, 'X'), 'Unsupported source border symbol'
            assert not (p.get('border_symbol') and p['triangle']), 'A port cannot combine a triangle and X'
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
            validate_compact_support(b, nets[0], marks)
            assert 0 <= x < x + compact['label_width'] < spec['canvas']['width'] and 0 < y < spec['canvas']['height']
            compact_labels[(x, y)] = {(xx, y) for xx in range(x + 1, x + 1 + compact['label_width'])}
            continue
        area = {(x, y) for x in range(b['x'], b['x'] + 8) for y in range(b['top'], b['top'] + b['height'])}
        assert not occupied & area, 'Overlapping boxes'
        occupied |= area
    assert {p['pin'] for b in boxes for p in b['ports'] if p['pin']} == {p['pin'] for p in spec['exterior_pins']}, 'Exterior and block pin coverage differ'
    assert wiring_graph(spec) == spec['nets'], 'Wiring differs from reviewed terminal connections'
    by_terminal={'PORT:'+b['portion']+':'+p['id']:p for b in boxes for p in b['ports']}
    by_pin={p['pin']:p for p in spec['exterior_pins']}
    for net in spec['nets']:
        contacts=[by_terminal[t] for t in net if t in by_terminal]
        if not any(p.get('contact_role')=='nonlogical_common' for p in contacts):continue
        # Display direction is distinct from a Boolean gate-driver claim.
        expected_side=exterior_display_side(contacts, next((t[4:] for t in net if t.startswith('PIN:')),None))
        for terminal in net:
            if terminal.startswith('PIN:'):
                assert by_pin[terminal[4:]]['side']==expected_side, \
                    'Nonlogical K exterior display direction differs from its isolated/shared contact context'
    base = render(spec)
    occupied |= {(x+i,y) for x,y,label in caption_locations(spec) for i in range(len(label))}
    box_and_label = occupied | {(x, y) for b in boxes if 'compact_termination' not in b
                                for pattern in [None] + spec['variants']
                                for p in notation_ports(b, (pattern or {}).get('box_overrides', {}).get(b['portion'], {})) if p['pin']
                                for start, y, text in [port_label(b, p)]
                                for x in range(start, start + len(text))}
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
        assert set(variant) <= {'number', 'box_overrides', 'annotation_overrides', 'line_ending', 'predecessor_sha256', 'circuit_witness'}, 'A variant cannot define geometry'
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
    witness_path = ROOT/f'notes/Card-ALD/Notation witnesses/{card}.json'
    witness_index = read(witness_path) if witness_path.exists() else None
    if witness_index is not None:
        assert witness_index.get('card_type') == card, 'Witness index escaped card namespace'
    receipt = {'schema': 'card-ald-generation-v1', 'card_type': card,
               'canonical': f'Card-ALD/{card}.txt', 'diagram_sha256': digest(outputs[card+'.txt']),
               'definition': {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(path.read_bytes())},
               'renderer': {'path': Path(__file__).relative_to(ROOT).as_posix(), 'sha256': digest(Path(__file__).read_bytes())},
               'source_evidence': {'source_status_ref':'notes/Source status.json',
                   'reviewed_occurrences':spec.get('header',{}).get('reviewed_occurrences'),
                   'reviewed_pages':spec.get('header',{}).get('reviewed_pages')}, 'validation': checks,
               'files': [{'path': 'Card-ALD/' + name, 'sha256': digest(raw)} for name, raw in outputs.items()]}
    if witness_index is not None:
        receipt['notation_witness_index'] = {'path': witness_path.relative_to(ROOT).as_posix(),
                                            'sha256': digest(witness_path.read_bytes())}
    raw = (json.dumps(receipt, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    write_protected(ROOT/f'notes/Card-ALD/Generation/{card}.json', raw)
    model_path = ROOT/f'json/Card-ALD/{card}.json'
    model = read(model_path) if model_path.exists() else {'schema':'card-ald-generated-model-v1','card_type':card}
    model.update(drawing=receipt['canonical'], drawing_sha256=receipt['diagram_sha256'],
                 render_definition=receipt['definition'], generation_receipt=f'notes/Card-ALD/Generation/{card}.json')
    write_protected(model_path, (json.dumps(model, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    index_path = ROOT/'csv/Card-ALD/Notation variants.csv'
    fields = ['card_type', 'file', 'kind', 'source_pages', 'source_locations', 'sha256']
    entries = []
    if index_path.exists():
        with index_path.open(encoding='utf-8-sig', newline='') as source:
            reader = csv.DictReader(source)
            fields, entries = reader.fieldnames, list(reader)
        assert fields and set(['card_type', 'file', 'sha256']) <= set(fields), 'Unsupported notation index'
    witnesses = spec.get('provenance', {}).get('variant_witnesses', [])
    if not witnesses and witness_index is not None:
        witnesses = witness_index.get('variants', [])
    if isinstance(witnesses, dict):
        witnesses = [dict(value, number=int(number)) for number, value in witnesses.items()]
    by_number = {int(w.get('number', w.get('variant_number', 0))): w for w in witnesses}
    def witness_text(witness, key):
        value = witness.get(key, [])
        if isinstance(value, str):
            return value
        return '; '.join(sorted(set(str(v) for v in value)))
    assert not any(e['file'] in outputs and e['card_type'] != card for e in entries), 'Notation index namespace collision'
    def notation_kind(number):
        if number == 0:
            return 'canonical'
        witness = by_number.get(number, {})
        if witness.get('partial_witnesses') and not witness.get('complete_witnesses'):
            return 'partial observed notation; canonical-filled'
        return 'observed notation variant'
    known = {e['file']: e for e in entries if e['card_type'] == card}
    assert len(known) == len([e for e in entries if e['card_type'] == card]), 'Duplicate card notation index row'
    for name, content in outputs.items():
        match = re.fullmatch(re.escape(card) + r'(?:-(\d+))?\.txt', name)
        assert match, 'Generated output escaped card namespace'
        number = int(match.group(1) or 0)
        if name not in known:
            entry = {field: '' for field in fields}
            entry.update(card_type=card, file=name, sha256=digest(content))
            for key, value in [('kind', notation_kind(number)),
                               ('source_pages', witness_text(by_number.get(number, {}), 'source_pages')),
                               ('source_locations', witness_text(by_number.get(number, {}), 'source_locations'))]:
                if key in fields:
                    entry[key] = value
            entries.append(entry)
            known[name] = entry
        else:
            known[name]['sha256'] = digest(content)
            if number in by_number:
                if 'kind' in fields:
                    known[name]['kind'] = notation_kind(number)
                for key in ['source_pages', 'source_locations']:
                    if key in fields:
                        known[name][key] = witness_text(by_number[number], key)
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

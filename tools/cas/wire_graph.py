"""Read-only CAS wire traversal, extracted from the historical QZ checker.

Four-way crossings without O remain separate. Original wire_shapes recover
three-arm direction lost when the approved basic glyph set replaced T glyphs.
This helper reports visible reachability; it does not establish source truth.
"""
from collections import deque
import re

DIRS = [(0, -1, 1, 2), (0, 1, 2, 1), (-1, 0, 4, 8), (1, 0, 8, 4)]
MASK = {'│': 3, '─': 12, '┘': 5, '└': 9, '┐': 6, '┌': 10,
        '┤': 7, '├': 11, '┴': 13, '┬': 14, '┼': 15,
        'O': 15, '*': 15, '✲': 15}
RANK = {label: index for index, label in enumerate('ACEGJLNQS')}
RANK['F'] = 2


def position(node, legacy=False):
    if 'grid' in node:
        return node['grid']
    return [25+22*(int(node['box'][1:])-1)+(6 if legacy else 0),
            11*RANK[node['box'][0]]+(5 if legacy else 0)]


def terminals(page, spec, legacy=False):
    targets, blocked, outputs = {}, set(), {}
    for node in spec['nodes']:
        col, row = position(node, legacy)
        separate_R = node.get('R_line') is not None or bool(node.get('selector'))
        label_row = node.get('label_row', max(7, len(node['fields'])+1+int(separate_R)))
        for rr in range(row, row+label_row+1):
            for cc in range(col, col+15):
                blocked.add((cc, rr))
        for rr in range(row+1, row+label_row):
            targets[(col, rr)] = (page, node['box'], node['address'].zfill(4))
        outputs[node['box']] = (col+15, row+node.get('output_port_row', 3))
    # Footer page/version fields are identifiers, never diagram portals. The
    # newly structured footer stores the page code separately, unlike older
    # combined title strings; parsing it as an exit creates phantom targets.
    texts = spec.get('text', [])
    caption_refs = {tuple(point) for point in spec.get('caption_reference_positions', [])}
    for col, row, text in texts:
        if (col, row) in caption_refs:
            continue
        match = re.match(r'([AQ][A-Z]\d{3})(?:[.─]+([ACEFGJLNQS][A-I][A-Z]))?', text)
        if not match:
            continue
        serial = match[2]
        if not serial:
            serial = next((item[2] for item in texts if item[1]==row and item[0]>col
                           and re.fullmatch(r'[ACEFGJLNQS][A-I][A-Z]', item[2])), '')
        # Portal serials may name the source exit rather than a destination box.
        targets[(col, row)] = (match[1], serial, '')
    return targets, blocked, outputs


def reachable(lines, start, targets, blocked, shapes=None):
    height = len(lines)
    found, seen = set(), set()
    queue = deque([(start[0], start[1], 8)])

    def char(col, row):
        return lines[row][col] if 0<=row<height and 0<=col<len(lines[row]) else ' '

    def original_shape(col, row):
        glyph = char(col, row)
        return (shapes or {}).get(f'{col},{row}') if glyph == '┼' or glyph not in MASK else None

    def cell_mask(col, row):
        return MASK.get(original_shape(col, row) or char(col, row), 0)

    while queue:
        col, row, arrival = queue.popleft()
        if (col, row, arrival) in seen:
            continue
        seen.add((col, row, arrival))
        glyph = char(col, row)
        original = original_shape(col, row)
        mask = MASK.get(original or glyph, 0)
        if (col, row)==start:
            mask = 8
        if original=='┼':
            mask = 12 if arrival in [4, 8] else 3
        elif glyph=='┼' and not original:
            connected = sum(bool(cell_mask(col+dc, row+dr)&opposite)
                            or ((col+dc, row+dr) in targets and dc==1)
                            for dc, dr, bit, opposite in DIRS)
            if connected==4:
                mask = 12 if arrival in [4, 8] else 3
        for dc, dr, bit, opposite in DIRS:
            if not mask&bit:
                continue
            neighbour = (col+dc, row+dr)
            if neighbour in targets and dc==1:
                found.add(targets[neighbour])
                continue
            if neighbour in blocked:
                continue
            if cell_mask(*neighbour)&opposite:
                queue.append((*neighbour, bit))
    return sorted(found)


def page_reachability(page, spec, lines, shapes=None, legacy=False):
    targets, blocked, outputs = terminals(page, spec, legacy)
    effective_shapes = dict(shapes or {})
    for point, evidence in spec.get('wire_text_overlays', {}).items():
        shape = evidence.get('underlying_shape') if isinstance(evidence, dict) else evidence
        if shape in MASK:
            effective_shapes[point] = shape
    return {box: reachable(lines, start, targets, blocked, effective_shapes)
            for box, start in outputs.items()}

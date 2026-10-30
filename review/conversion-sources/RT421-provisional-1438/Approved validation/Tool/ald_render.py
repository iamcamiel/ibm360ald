"""Render the ALD format trial using functional records and layout rules.

render_page() receives only the new page dictionary. It never reads the old
page, text-layout rows, source observations, or comparison evidence. The CLI's
optional reference file is used only AFTER rendering, for byte comparison.
Review sidecars provide visible legacy text only for explicitly unresolved
fields. They are content-bound; they never contribute routes or text-layout
rows. This is a format prototype, not a production format release.
"""
from collections import defaultdict
from pathlib import Path
import argparse
import hashlib
import json


GRID_LETTERS = 'ABCDEFGHJKLMN'
PAGE_COLUMNS = 245
PAGE_ROWS = 103
SINK_COLUMNS = (205, 215, 224, 234)


def wire_graph(polylines):
    graph = defaultdict(set)
    for points in polylines:
        for first, last in zip(points, points[1:]):
            if first[0] != last[0] and first[1] != last[1]:
                raise ValueError('A wire segment must be horizontal or vertical')
            dx = (last[0] > first[0]) - (last[0] < first[0])
            dy = (last[1] > first[1]) - (last[1] < first[1])
            point = tuple(first)
            while point != tuple(last):
                following = (point[0] + dx, point[1] + dy)
                graph[point].add(following)
                graph[following].add(point)
                point = following
    return dict(graph)


def singleton_output_hanging_row(output, graph):
    """Return the printed sink row only for one unique recorded own-net hanger.

    The route must leave the output label row downward at one x-coordinate,
    continue horizontally to the first sink column on the next row, and remain
    connected to the right-going output lead. No route or display defaults are
    synthesized here.
    """
    sinks = output.get('sinks', [])
    if len(sinks) != 1:
        return None
    row = output.get('line')
    if type(row) is not int:
        return None
    arms = []
    for x in range(195, 205):
        if (x, row + 1) not in graph.get((x, row), set()):
            continue
        if any((column + 1, row + 1) not in graph.get((column, row + 1), set())
               for column in range(x, 204)):
            continue
        if any((column + 1, row) not in graph.get((column, row), set())
               for column in range(x, 241)):
            continue
        arms.append(x)
    if len(arms) > 1:
        raise ValueError('Ambiguous own-net hanging route for singleton output')
    return row + 1 if len(arms) == 1 else None


def input_display_literal(value):
    # Input identifiers may have damaged glyphs or source-observed internal
    # spaces, but padding/control strings are not positional display evidence.
    return (isinstance(value,str) and bool(value) and value==value.strip()
            and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789?� ' for c in value))


def input_reference_display(identity, details):
    field='inputs/'+identity+'/net number'
    matches=[u for u in (details or {}).get('uncertainties',[])
             if u.get('field')==field and u.get('status')=='unresolved']
    if len(matches)!=1:return identity
    observation=matches[0]
    literal=observation.get('visible text')
    return literal if (observation.get('kind') in ('illegible','conflicting')
                       and input_display_literal(literal)) else identity


def render_page(data, details=None, trim_trailing_spaces=False, line_ending='\n'):
    if line_ending not in ('\n','\r\n'):
        raise ValueError('Line ending must be LF or CRLF')
    page = data['page']
    masks = {item['field']:item['visible text'] for item in (details or {}).get('uncertainties', [])
             if item['status']=='unresolved' and isinstance(item.get('visible text'), str)}
    def display(field, value):
        if value is None:
            if field not in masks:
                raise ValueError('No literal display evidence for unresolved field '+field)
            return masks[field]
        return value
    def printed_serial(block):
        field = 'blocks/'+block['serial']+'/serial'
        entries = [item for item in (details or {}).get('uncertainties', [])
                   if item.get('field') == field and item.get('status') == 'unresolved']
        if not entries:
            return block['serial']
        if data.get('review', {}).get('unresolved discrepancies') is not True:
            raise ValueError('Active printed serial uncertainty requires compact discrepancy true')
        if len(entries) != 1:
            raise ValueError('Several unresolved printed serial records for '+field)
        entry = entries[0]
        literal = entry.get('visible text')
        if (entry.get('kind') != 'illegible' or not isinstance(literal, str)
                or len(literal) != 2 or '\ufffd' not in literal):
            raise ValueError('Printed serial requires exact damaged two-cell literal for '+field)
        return literal
    # Socket location carries its own frame identity, independent of an erased
    # printed title-frame value. The printed socket convention omits its first
    # two digits; no semantic frame is guessed from the title display mask.
    def local_location(value):
        return value[2:] if value and len(value)>=2 and value[:2].isdigit() else value
    grid = [[' '] * PAGE_COLUMNS for _ in range(PAGE_ROWS)]

    def put(column, row, text):
        if not (0 <= row < PAGE_ROWS and 0 <= column <= column + len(text) <= PAGE_COLUMNS):
            raise ValueError(('Text outside page', column, row, text))
        grid[row][column:column + len(text)] = text

    deviations = data.get('column deviations', [])
    block_offsets = {item['num']: item['deviation'] for item in deviations if item['type'] == 'block'}
    reference_offset = sum(item['deviation'] for item in deviations if item['type'] == 'entry-reference')
    annotations = {}
    for net in data['nets']:
        for item in net.get('annotations', []):
            if not isinstance(item['at'], str):
                continue
            if item['at'] in annotations:
                raise ValueError('Multiple uncomposed annotations at one terminal')
            annotations[item['at']] = item['text']
    terminal_points = {}
    terminal_directions = {}
    blocks = {}
    for block in data['blocks']:
        column = int(block['grid position'][:-1])
        letter = block['grid position'][-1]
        x = 27 + 23 * column + block_offsets.get(column, 0)
        y = 2 + 7 * GRID_LETTERS.index(letter)
        height = block.get('height', 6)
        right = x + 7
        blocks[block['serial']] = (x, y, right, height)
        for pin in block['pins']:
            node = f"blocks/{block['serial']}/pins/{pin['side']}/{pin['line']}"
            mark = annotations.get(node, '')
            number = display(node+'/pin', pin.get('pin',''))
            printed = mark + number if pin['side'] == 'L' else number + mark
            endpoint = x - len(printed) - 1 if pin['side'] == 'L' else right + len(printed) + 1
            terminal_points[node] = (endpoint, y + pin['line'] - 1)
            terminal_directions[node] = 1 if pin['side'] == 'L' else -1

    graphs = {net['net number']: wire_graph(net['routing']) for net in data['nets']}
    outputs = {item['net number']: item for item in data['outputs']}
    if len(outputs)!=len(data['outputs']):raise ValueError('Duplicate explicit output net record')
    for number, output in outputs.items():
        sinks = output['sinks']
        if len(sinks) <= 1:
            continue
        row = output['line']
        length = output.get('hanging wire length', 1)
        generated = []
        for index in range(0, len(sinks), 4):
            below = row + 1 + index // 4
            corner = SINK_COLUMNS[0] - length - 1
            generated.append([[corner, row], [corner, below], [SINK_COLUMNS[0], below]])
        combined = defaultdict(set, {p: set(v) for p, v in graphs[number].items()})
        for point, neighbors in wire_graph(generated).items():
            combined[point].update(neighbors)
        graphs[number] = dict(combined)

    diamonds = set()
    union = defaultdict(set)
    for net in data['nets']:
        graph = graphs[net['net number']]
        attachments = defaultdict(set)
        for node in net['nodes']:
            if node in terminal_points:
                attachments[terminal_points[node]].add(node)
        output_arms = defaultdict(set)
        output = outputs.get(net['net number'])
        if output and 'outputs/'+net['net number'] in net['nodes']:
            row = output['line']
            if type(row) is not int:raise ValueError('Explicit output line must be integer')
            if (204,row) in graph:
                output_arms[204,row].add((205,row))
        for point, neighbors in graph.items():
            incidents = set(neighbors)
            x,y = point
            for node in attachments[point]:
                incidents.add((x + terminal_directions[node],y))
            incidents.update(output_arms[point])
            if len(incidents) >= 3:
                diamonds.add(point)
            union[point].update(neighbors)
            union[point].update(output_arms[point])
        # A terminal is also an incident edge for drawing the corner at the
        # end of its lead. Its label occupies the following cell, so this
        # stroke is functional terminal geometry rather than another route.
        for node in net['nodes']:
            if node in terminal_points:
                x, y = terminal_points[node]
                union[x, y].add((x + terminal_directions[node], y))
    # T-shaped wire forms use the approved diamond glyph.
    corners = {
        frozenset(((1, 0), (0, 1))): '┌',
        frozenset(((-1, 0), (0, 1))): '┐',
        frozenset(((1, 0), (0, -1))): '└',
        frozenset(((-1, 0), (0, -1))): '┘',
        frozenset(((1,0),(0,1),(0,-1))): '◇',
        frozenset(((-1,0),(0,1),(0,-1))): '◇',
        frozenset(((1,0),(-1,0),(0,1))): '◇',
        frozenset(((1,0),(-1,0),(0,-1))): '◇',
    }
    for (x, y), neighbors in union.items():
        directions = frozenset((nx-x, ny-y) for nx, ny in neighbors)
        if (x, y) in diamonds:
            glyph = '◇'
        elif all(dy == 0 for dx, dy in directions):
            glyph = '─'
        elif all(dx == 0 for dx, dy in directions):
            glyph = '│'
        else:
            glyph = corners.get(directions, '┼')
        put(x, y, glyph)

    for block in data['blocks']:
        x, y, right, height = blocks[block['serial']]
        put(x, y, '┌' + '─' * 6 + '┐')
        for row in range(y+1, y+height+1):
            put(x, row, '│' + ' ' * 6 + '│')
        put(x+1+block.get('function offset', 0), y+1, block['function'])
        put(x+1, y+3, display('blocks/'+block['serial']+'/circuit',block['circuit']))
        put(x+1, y+4, block.get('card','') + block.get('portion',''))
        socket = block.get('socket',block.get('board',''))
        if socket is None:
            key='socket' if 'socket' in block else 'board'
            socket=display('blocks/'+block['serial']+'/'+key,socket)
        put(x+1, y+5, local_location(socket))
        footer = block['grid position'] + '──' + printed_serial(block)
        if len(footer) != 6:
            raise ValueError('Block footer does not fit the ordinary template')
        put(x+1, y+height, footer)
        if 'annotation' in block:
            offset=block.get('annotation offset',[0,-1])
            put(x+offset[0], y+offset[1], block['annotation'])
        for pin in block['pins']:
            node = f"blocks/{block['serial']}/pins/{pin['side']}/{pin['line']}"
            mark = annotations.get(node, '')
            number = display(node+'/pin',pin.get('pin',''))
            printed = mark + number if pin['side'] == 'L' else number + mark
            row = y + pin['line'] - 1
            border = x if pin['side'] == 'L' else right
            edge = pin.get('edge')
            if edge:
                put(border, row, {'negative': '◺', 'extension': 'E', 'aux': 'K', 'non-logic': 'X'}[edge])
            put(x-len(printed) if pin['side'] == 'L' else right+1, row, printed)

    for entry in data['inputs']:
        row = entry['line']
        put(0,row,' ')
        put(1+len(entry['name']),row,'─'*max(0,31-len(entry['name'])))
        put(1, row, entry['name'])
        identity = entry['net number']
        reference = input_reference_display(identity, details)
        style = entry.get('reference style', 'inline')
        if style == 'inline':
            put(32+reference_offset, row, reference)
        elif style == 'hanging':
            put(1, row+1, '✲' + entry.get('real net number', identity))
            put(32+reference_offset, row+1, reference)
        else:
            raise ValueError('Unknown input reference style')

    for output in data['outputs']:
        row = output['line']
        local = output['net number']
        if not local.startswith(page['page']):
            raise ValueError('A nonlocal output needs a defined printed ID rule')
        printed = masks.get('outputs/'+local+'/net number',local[len(page['page']):])
        put(210, row, ' ' + output['name'].ljust(31, '─') + printed)
        sinks = output['sinks']
        if len(sinks) == 1:
            sink_row = singleton_output_hanging_row(output, graphs.get(local, {}))
            put(205, row if sink_row is None else sink_row, sinks[0])
        else:
            for index, sink in enumerate(sinks):
                column = SINK_COLUMNS[index % 4]
                below = row + 1 + index // 4
                if index % 4:
                    put(column-1, below, '└')
                put(column, below, sink)

    footer_rows = []
    for net in sorted(data['nets'], key=lambda item: item['net number'] or ''):
        if not net.get('connectors'):
            continue
        if not net['net number'].startswith(page['page']):
            raise ValueError('Nonlocal footer reference display not defined')
        printed = masks.get('outputs/'+net['net number']+'/net number',net['net number'][len(page['page']):])
        for index, connector in enumerate(net['connectors']):
            footer_rows.append(printed + ' ' + local_location(connector)
                               if index == 0 else '  ' + connector)
    for index, text in enumerate(footer_rows):
        put(35 + 14*(index//9), 94 + index % 9, text)

    for index,text in enumerate(data.get('note',[])):
        put(4,93+index,text)
    for net in data['nets']:
        for annotation in net.get('annotations',[]):
            at=annotation['at']
            if isinstance(at,str):continue
            point=net['routing'][at['polyline']][at['point']]
            offset=annotation.get('offset',[0,0])
            put(point[0]+offset[0],point[1]+offset[1],annotation['text'])

    put(235, 0, page.get('version', '000') + '  ' + page['page'])
    for index, character in enumerate(page['page']):
        put(2, 95+index, character)
        put(243, 95+index, character)
    put(1, 101, page.get('version', '000'))
    put(242, 101, page.get('version', '000'))
    for index, revision in enumerate(page.get('revisions', [])):
        put(175, 93+index, revision['date'] + ' ' + revision['num'])
    put(210, 93, '┌' + '─'*30 + '┐')
    for row in range(94, PAGE_ROWS):
        put(210, row, '│' + ' '*30 + '│')
    for index, title in enumerate(page['title']):
        put(211, 94+index, title.center(30))
    put(211, 96, f"DATE   {display('page/date',page['date'])} MACH. {display('page/machine',page['machine'])}".ljust(30))
    put(211, 98, 'LOG' + display('page/log',page['log']).rjust(11) + '  FRAME' + display('page/frame',page['frame']).rjust(9))
    put(211, 100, (' '*16 + 'P.N.  ' + display('page/p/n',page['p/n'])).ljust(30))
    put(211, 102, 'IBM CORP.   ' + display('page/ibm division',page['ibm division']).ljust(3) + ' BLK.' + display('page/next block',page['next block']).rjust(10))
    lines=[''.join(row) for row in grid]
    if trim_trailing_spaces:lines=[line.rstrip() for line in lines]
    # Literal annotations and labels follow the same approved wire-glyph rule.
    return (line_ending.join(lines) + line_ending).translate(
        str.maketrans('├┤┬┴', '◇◇◇◇')).encode('utf-8')


def load_page(path):
    data=json.loads(path.read_text('utf-8'))
    ref=data.get('review',{}).get('details')
    details=None
    if ref:
        target=(path.parent/ref).resolve()
        if not target.is_relative_to(path.parent.resolve()):
            raise ValueError('Review details must stay within the trial directory')
        details=json.loads(target.read_text('utf-8'))
        content={k:v for k,v in data.items() if k!='review'}
        digest=hashlib.sha256(json.dumps(content,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
        if details['content sha256']!=digest:
            raise ValueError('Review content hash does not match this page')
    return data,details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('page_json', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--comparison', type=Path)
    parser.add_argument('--trim-trailing-spaces',action='store_true')
    parser.add_argument('--line-ending',choices=('lf','crlf'),default='lf')
    args = parser.parse_args()
    data,details = load_page(args.page_json)
    result = render_page(data,details,args.trim_trailing_spaces,'\r\n' if args.line_ending=='crlf' else '\n')
    args.output.write_bytes(result)
    if args.reference:
        original = args.reference.read_bytes()
        rows = original.decode('utf-8').splitlines(keepends=True)
        expected = ''.join(rows).encode('utf-8')
        actual_rows = result.decode('utf-8').splitlines()
        wanted_rows = expected.decode('utf-8').splitlines()
        differences = []
        for y, (actual, wanted) in enumerate(zip(actual_rows, wanted_rows)):
            for x in range(max(len(actual),len(wanted))):
                left=actual[x] if x<len(actual) else ''
                right=wanted[x] if x<len(wanted) else ''
                if left != right:
                    differences.append({'column': x, 'row': y, 'actual': left, 'expected': right})
        report = {
            'passed': result == expected,
            'blocks_in_ascending_serial_order': [b['serial'] for b in data['blocks']] == sorted(b['serial'] for b in data['blocks']),
            'allowed_correction_only': None,
            'source_sha256': hashlib.sha256(original).hexdigest(),
            'expected_corrected_sha256': hashlib.sha256(expected).hexdigest(),
            'rendered_sha256': hashlib.sha256(result).hexdigest(),
            'draft_sha256': hashlib.sha256(args.page_json.read_bytes()).hexdigest(),
            'source_bytes': len(original), 'rendered_bytes': len(result),
            'unexpected_different_cells': len(differences), 'first_differences': differences[:80],
            'renderer_consumes_new_JSON_and_template_only': True,
            'source_used_only_for_comparison_after_rendering': True,
        }
        if args.comparison:
            args.comparison.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
        if result != expected:
            raise SystemExit(1)


if __name__ == '__main__':
    main()

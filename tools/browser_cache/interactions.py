"""Lean interactions derived from explicit published source data, never wire inference."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from copy import deepcopy
import re

PAGE_REF = re.compile(r"^(?:(?i:external)(?:[.:][ \t]*|[ \t]+))?([A-Z]{2}\d{3})(?:[.-]?([A-Z]{2,3})(\d+))?(?:[ \t]+[+-][^\r\n]+)?$")
PIN = re.compile(r"[A-Z]\d{2}")
BOARD_SITE = re.compile(r"^(?:02)?([A-Z])-([A-Z]\d)([A-Z]\d+[BT]?)$")


def _display(value):
    """Render source null as empty text; retain other existing string casts."""
    return '' if value is None else str(value)


def _coalesce(*values):
    """Choose the first non-null source value without discarding empty values."""
    return next((value for value in values if value is not None), None)

def _lines(text):
    if text.startswith("\ufeff"):
        text = text[1:]
    result = re.split(r"\r\n|\n|\r", text)
    if result and text.endswith(("\n", "\r")):
        result.pop()
    return result


def extract_legacy(model):
    """Detach the source view and retain only interaction input fields.

    This helper reconstructs source literals, never the normalized facts view.
    The caller must validate its source envelope before invoking the helper.
    """
    from .normalization import source_view
    raw = source_view(model)
    if not any(k in raw for k in ('nodes', 'nets', 'wire_paths', 'sockets', 'records')):
        raw = raw.get('current_extensions', {})
    return {k: deepcopy(raw[k]) for k in
            ('nodes', 'nets', 'wire_paths', 'sockets', 'records', 'board') if k in raw}


def _raw(model):
    return extract_legacy(model)

def _box(lines, node):
    """Only exact own top border plus exact own grid/identifier footer anchors."""
    x, y = node.get("column"), node.get("row")
    if not isinstance(x, int) or not isinstance(y, int) or not 0 <= y < len(lines):
        return None
    top = re.match(r"┌[─━]+┐", lines[y][x:]) if x >= 0 else None
    if not top:
        return None
    right = x + len(top[0]) - 1
    identifier, grid = _display(node.get("id")), _display(node.get("grid"))
    if not identifier or not grid:
        return None
    expected = re.compile(re.escape(re.sub(r"\s+", "", grid)) + r"[─━-]*" + re.escape(identifier))
    for row in range(y + 2, min(y + 33, len(lines))):
        line = lines[row]
        if row > y + 2 and line[x:x + 1] == "┌":
            break
        if len(line) > right and line[x] in "│|" and line[right] in "│|":
            if expected.fullmatch(re.sub(r"\s+", "", line[x + 1:right])):
                return [x, y, right, row]
    return None


def _socket_name(value):
    value = str(value or "").upper().strip()
    return re.sub(r"(?<=[0-9])[BT]$", "", value)


def _site(node):
    raw = _display(_coalesce(node.get("location"), node.get("site"), ""))
    match = BOARD_SITE.fullmatch(raw.upper())
    board, sockets = ("02" + match[1] + "-" + match[2], [match[3]]) if match else (None, [])
    evidence = node.get("socket_listing_evidence") or {}
    # Some source pages retain several evidence candidates. They are not a
    # unique physical location; retain the explicitly printed site instead.
    if not isinstance(evidence, dict):
        evidence = {}
    evidence_board = _display(evidence.get("board")).upper()
    if evidence_board and not evidence_board.startswith("02"):
        evidence_board = "02" + evidence_board
    if not board:
        board = evidence_board or None
    if board == evidence_board:
        more = _coalesce(evidence.get("sockets"), [evidence["socket"]] if evidence.get("socket") is not None else [], [])
        sockets.extend(more)
    return raw, board, sorted({_socket_name(s) for s in sockets if s})


def _reference(value):
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return None
    if value.get("object_identifier") == "external":
        return value.get("port_reference_text")
    if value.get("page") and value.get("designation"):
        return str(value["page"]) + str(value["designation"])
    for key in ("reference", "text", "value", "raw"):
        found = _reference(value.get(key))
        if found:
            return found
    return None


def _refs(value):
    if isinstance(value, (list, tuple)):
        return [ref for v in value for ref in _refs(v)]
    ref = _reference(value)
    return [ref] if ref else []


def _driver_spans(net, record, rows):
    """Locate an explicit driver label only where it touches its own route."""
    driver = _reference(record.get("driver"))
    match = PAGE_REF.fullmatch(driver) if driver else None
    if not match:
        return []
    token = ''.join(part or '' for part in match.groups())
    pattern = re.compile(r"(?<![A-Z0-9])" + re.escape(token) + r"(?![A-Z0-9])")
    spans = set()
    for x1, y1, x2, y2 in net.get("segments", []):
        if y1 != y2 or not 0 <= y1 < len(rows):
            continue
        for found in pattern.finditer(rows[y1]):
            if max(x1, x2) >= found.start() - 1 and min(x1, x2) <= found.end():
                spans.add((y1, found.start(), found.end()))
    return [list(span) for span in sorted(spans)]


def _pin(value):
    found = PIN.findall(str(value or ""))
    return found[0] if len(found) == 1 else None


def _annotate_nets(nets, raw, rows):
    """Display ownership only: no new wire geometry or electrical joins."""
    owners, blocked = {}, set()
    for net in nets:
        for x1, y1, x2, y2 in net.get('segments', []):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                for x in range(min(x1, x2), max(x1, x2) + 1):
                    key = (x, y)
                    owners[key] = net['id'] if key not in owners or owners[key] == net['id'] else None
    for node in raw.get('nodes', []):
        box = _box(rows, node)
        if box:
            blocked.update((x, y) for y in range(box[1], box[3] + 1) for x in range(box[0] + 1, box[2]))
    stops = set('\t\r\n│┃┌┐└┘┼┬┴├┤◇◊')
    for net in nets:
        spans = {tuple(span) for span in net.get('spans', [])}
        for x1, y1, x2, y2 in net.get('segments', []):
            if y1 != y2 or not 0 <= y1 < len(rows):
                continue
            chars = rows[y1]
            for start, step in ((min(x1, x2), -1), (max(x1, x2), 1)):
                end, spaces, x = start, 0, start + step
                while 0 <= x < len(chars):
                    char, key = chars[x], (x, y1)
                    if key in blocked or char in stops or (key in owners and owners[key] != net['id']):
                        break
                    if char == ' ':
                        spaces += 1
                        if spaces >= 2:
                            break
                    else:
                        spaces, end = 0, x
                    x += step
                if end != start:
                    spans.add((y1, min(start + step, end), max(start + step, end) + 1))
        if spans:
            net['spans'] = [list(span) for span in sorted(spans)]


def _output_designations(node, terminal):
    pins = [p for p in node.get("pins", []) if p.get("side") == "output"]
    if terminal not in (None, "output", "out"):
        physical = _pin(terminal)
        pins = [p for p in pins if physical is not None and _pin(p.get("pin")) == physical]
    elif terminal in ("output", "out"):
        pins = [p for p in pins if not _pin(p.get("pin"))]
    if terminal in (None, "output", "out") and len(pins) != 1:
        # An unspecified output cannot identify one of several distinct ports.
        return set()
    top = node.get("row")
    return {p["row"] - top + 1 for p in pins
            if isinstance(top, int) and isinstance(p.get("row"), int) and p["row"] >= top}


def _card_portions(entry, text):
    lines = _lines(text)
    card = _display(entry.get("cardType"))
    found = []
    for row, line in enumerate(lines):
        for match in re.finditer(r"(?<![A-Z0-9])" + re.escape(card) + r"([A-Z0-9]{1,3})(?![A-Z0-9])", line):
            # A portion code has to be inside its own actually drawn rectangle.
            candidates = []
            for top in range(max(0, row - 20), row):
                for border in re.finditer(r"┌[─━]+┐", lines[top]):
                    left, right = border.start(), border.end() - 1
                    if left < match.start() and match.end() <= right:
                        if any(lines[r][left:left + 1] in ("┌", "└") for r in range(top + 1, row + 1)):
                            continue
                        for bottom in range(row + 1, min(row + 22, len(lines))):
                            if lines[bottom][left:right + 1] == "└" + "─" * (right - left - 1) + "┘":
                                candidates.append([left, top, right, bottom])
                                break
            if len(candidates) == 1:
                found.append({"portion": match[1], "cardType": card,
                              "spans": [[row, match.start(), match.end()]], "box": candidates[0]})
        for match in re.finditer(r'[└┌]R\s+(?:[A-Z0-9]{1,3}\s+)?[UST]\d{2}[A-Z]{2}\s+([A-Z0-9]{2})(?![A-Z0-9])',line):
            if not any(p['portion'] == match[1] for p in found):
                found.append({'portion':match[1], 'cardType':card,
                              'spans':[[row,match.start(),match.end()]]})
    return found


def _socket_payload(entry, model, lines):
    ext = model
    records = _coalesce(ext.get("sockets"), ext.get("records"), [])
    if isinstance(records, dict):
        records = list(records.values())
    result = []
    for ordinal, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        raw_sockets = _coalesce(record.get("sockets"), [record["socket"]] if record.get("socket") is not None else [], [])
        if isinstance(raw_sockets, str):
            raw_sockets = [raw_sockets]
        sockets = sorted({_socket_name(v) for v in raw_sockets})
        board = _display(_coalesce(record.get("board"), ext.get("board"), "")).upper()
        if board and not board.startswith("02"):
            board = "02" + board
        card = _display(_coalesce(record.get("card_type"), record.get("cardType"), ""))
        if not sockets or not board:
            continue
        headers = []
        for raw_socket in raw_sockets:
            token = re.escape(_display(raw_socket))
            header = re.compile(r"(?:^|[│|])\s{0,2}(" + token + r")(?=\s|[│|]|$)")
            for row, line in enumerate(lines):
                for match in header.finditer(line):
                    left = match.start()
                    right = line.find("│", max(left + 1, match.end()))
                    if right < 0:
                        right = len(line)
                    headers.append((row, left, right, match.start(1), match.end(1)))
        declared_row = record.get("layout_row")
        if isinstance(declared_row, int):
            headers = [h for h in headers if h[0] == declared_row]
        def end_of_header(header):
            top, left, right, _, _ = header
            for row in range(top + 1, len(lines)):
                content = lines[row][left:right]
                next_header = re.match(r"[│|]?\s{0,2}([A-Z]\d{1,2}[BT]?)(?=\s|[│|])", content)
                if next_header and _socket_name(next_header[1]) not in sockets:
                    return row
                if len(re.sub(r"[│|\s]", "", content)) >= 12 and re.fullmatch(r"[│|\s─━-]+", content):
                    return row
            return len(lines)
        # A continued socket can have its title at the bottom of one column
        # and its actual card/portion list at the top of the next. The exact
        # card code uniquely anchors the content-bearing occurrence.
        headers = list(dict.fromkeys(headers))
        if len(headers) > 1 and card:
            headers = [h for h in headers if any(re.search(r'(?<![A-Z0-9])'+re.escape(card)+r'(?![A-Z0-9])',lines[r][h[1]:h[2]])
                                                  for r in range(h[0],end_of_header(h)))]
        if len(headers) != 1:
            continue
        top, left, right, c0, c1 = headers[0]
        bottom = end_of_header(headers[0])
        if card and not any(re.search(r"(?<![A-Z0-9])" + re.escape(card) + r"(?![A-Z0-9])", lines[r][left:right]) for r in range(top, bottom)):
            continue
        portions = []
        for reference in _coalesce(record.get("references"), []):
            page = _coalesce(reference.get("ALD_page"), reference.get("page"))
            values = _coalesce(reference.get("printed_portions"), reference.get("portions"), [])
            if isinstance(values, str):
                values = values.split()
            if not isinstance(page, str) or not isinstance(values, list):
                continue
            starts = [r for r in range(top, bottom) if re.search(r"(?<![A-Z0-9])" + re.escape(page) + r"(?![A-Z0-9])", lines[r][left:right])]
            if len(starts) > 1 and values:
                starts = [r for r in starts if re.search(r"(?<![A-Z0-9])" + re.escape(_display(values[0])) + r"(?![A-Z0-9])", lines[r][left:right])]
            declared = reference.get("layout_row")
            if isinstance(declared, int):
                starts = [r for r in starts if r == declared]
            if len(starts) != 1:
                continue
            first = starts[0]
            candidates = [first]
            for row in range(first + 1, bottom):
                content = lines[row][left + 1:right].strip()
                if not content or not re.fullmatch(r"[A-Z0-9]{1,3}(?:\s+[A-Z0-9]{1,3})*", content):
                    break
                if not set(content.split()) <= set(map(_display, values)):
                    break
                candidates.append(row)
            for value in values:
                spans = []
                for row in candidates:
                    segment = lines[row][left:right]
                    for match in re.finditer(r"(?<![A-Z0-9])" + re.escape(_display(value)) + r"(?![A-Z0-9])", segment):
                        spans.append([row, left + match.start(), left + match.end()])
                if spans:
                    portions.append({"portion": _display(value), "page": page, "spans": spans})
        item = {"id": f"socket-{ordinal}", "label": board + " " + "/".join(sockets),
                "board": board, "sockets": sockets, "cardType": card,
                "spans": [[top, c0, c1]]}
        if portions:
            item["portions"] = portions
        result.append(item)
    return result


def enrich_interactions(entries, models_by_id, text_by_id, native_views_by_id,
                        native_outputs_by_id=None):
    """Emit every page's typed payload and mutate its interaction asset fields.

    Inputs are validated compact legacy source views and exact installed v4_view
    outputs. Native output identities must separately come from model outputs;
    they cannot be inferred from geometry. One graph covers both source forms.
    All assets are relative; the static builder may remap them after hashing.
    """
    native_outputs_by_id = native_outputs_by_id or {}
    by_id = {e['id']: e for e in entries}
    if len(by_id) != len(entries):
        raise ValueError('Duplicate catalogue identity')
    pages = defaultdict(list)
    for entry in entries:
        # Native installed lookup includes every page; legacy excludes cards.
        pages[entry.get('page')].append(entry['id'])
    payloads, raws, nodes_by_page, nets_by_key = {}, {}, {}, {}
    socket_index, card_index, output_index = defaultdict(list), {}, defaultdict(set)
    destinations, pending, source_edges = defaultdict(list), {}, set()
    graph_labels = {}
    for entry in entries:
        eid = entry['id']
        if entry.get('_sourcePairCurrent') is False:
            raise ValueError('The page JSON/text publication is incomplete: ' + eid)
        text = text_by_id[eid]
        payload = {'schema': 'aldbrowser-interactions-v1', 'textSha256': entry['textSha256']}
        if eid in native_views_by_id:
            if eid not in native_outputs_by_id:
                raise ValueError('Missing exact native output identities: ' + eid)
            view = native_views_by_id[eid]
            payload.update(format='v4', modelSha256=entry['modelSha256'],
                           nets=deepcopy(view['nets']), blocks=deepcopy(view['blocks']))
            for net in payload['nets']:
                key = eid, net['id']
                nets_by_key[key] = (net, {})
                graph_labels[key] = net['label']
                destinations[key] = list(net['destinationPages'])
                if len(net['sourceReferences']) == 1:
                    pending[key] = net['sourceReferences'][0]
            for number in native_outputs_by_id[eid]:
                match = PAGE_REF.fullmatch(number)
                if match and match[2]:
                    output_index[match[1], match[2], int(match[3])].add((eid, number))
        elif entry.get('type') == 'card-ald':
            portions = _card_portions(entry, text)
            if portions:
                payload['portions'] = portions
            if entry.get('variant') is None:
                card_index[_display(entry.get('cardType'))] = eid
        elif eid in models_by_id:
            raw = _raw(models_by_id[eid])
            if entry.get('type') == 'socket-listing':
                sockets = _socket_payload(entry, raw, _lines(text))
                if sockets:
                    payload['sockets'] = sockets
                    for item in sockets:
                        for socket in item['sockets']:
                            socket_index[item['board'], socket, item['cardType']].append((eid, item))
            elif entry.get('type') == 'ald' and (raw.get('nodes') or raw.get('wire_paths')):
                raws[eid] = raw
                nodes_by_page[eid] = {_display(n.get('id')): n for n in raw.get('nodes', []) if isinstance(n, dict)}
        payloads[eid] = payload

    # Build local legacy nets and register the same output/pending graph used by
    # native pages. Duplicate records retain installed last-record driver rules.
    for eid, raw in raws.items():
        nets = {}
        records = {}
        for ordinal, record in enumerate(raw.get('nets', [])):
            if not isinstance(record, dict):
                continue
            literal = _display(_coalesce(record.get('id'), record.get('net_id'), f'net-{ordinal}'))
            net = nets.setdefault(literal, {'id': literal, 'label': _display(_coalesce(record.get('label'), record.get('name'), literal)), 'segments': []})
            key = eid, literal
            records[literal] = record
            nets_by_key[key] = net, record
            driver = _reference(record.get('driver'))
            if driver:
                if PAGE_REF.fullmatch(driver):
                    pending[key] = driver
                    graph_labels[key] = _display(_coalesce(record.get('label'), record.get('name'), literal))
                else:
                    local = driver.split('.', 1)
                    node = nodes_by_page[eid].get(local[0])
                    if node:
                        for designation in _output_designations(node, local[1] if len(local) > 1 else None):
                            output_index[by_id[eid]['page'], local[0], designation].add(key)
                            graph_labels[key] = _display(_coalesce(record.get('label'), record.get('name'), literal))
            for ref in _refs(record.get('external')) + _refs(record.get('targets')):
                match = PAGE_REF.fullmatch(ref)
                if match and match[1] not in destinations[key]:
                    destinations[key].append(match[1])
        for ordinal, path in enumerate(raw.get('wire_paths', [])):
            if not isinstance(path, dict) or path.get('net') == 'title':
                continue
            literal = _display(_coalesce(path.get('net'), f'route-{ordinal}'))
            net = nets.setdefault(literal, {'id': literal, 'label': literal, 'segments': []})
            nets_by_key.setdefault((eid, literal), (net, {}))
            points = path.get('points', [])
            for a, b in zip(points, points[1:]):
                if (len(a) == len(b) == 2 and all(type(v) is int for v in [*a, *b])
                        and a != b and (a[0] == b[0] or a[1] == b[1])):
                    segment = [*a, *b]
                    if segment not in net['segments']:
                        net['segments'].append(segment)
        if nets:
            payloads[eid]['nets'] = list(nets.values())

    parent = {}
    def find(key):
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]
    for key, ref in pending.items():
        match = PAGE_REF.fullmatch(ref)
        candidates = output_index.get((match[1], match[2], int(match[3])), set()) if match and match[2] else set()
        if len(candidates) == 1:
            source = next(iter(candidates))
            # Outputs in vetted native descriptors refer to rendered net ids.
            if source not in nets_by_key:
                raise ValueError('Output identity has no rendered net: ' + str(source))
            aa, bb = find(source), find(key)
            if aa != bb:
                parent[bb] = aa
            source_edges.add((source, key))
        else:
            net = nets_by_key[key][0]
            net.setdefault('notes', []).append('Source reference ' + ref + ' has no unique published driving net.')
            if match and match[1] not in destinations[key]:
                destinations[key].append(match[1])
    components = defaultdict(list)
    for key in parent:
        components[find(key)].append(key)
    roots = {source for source, target in source_edges}
    for key, (net, record) in nets_by_key.items():
        native = key[0] in native_views_by_id
        if not native:
            spans = _driver_spans(net, record, _lines(text_by_id[key[0]]))
            if spans:
                net['spans'] = spans
        links, linked_pages = [], set()
        for other in sorted(components.get(find(key), [])):
            if other == key:
                continue
            target = by_id[other[0]]
            links.append({'pageId': other[0], 'selection': {'kind': 'net', 'id': other[1]},
                          'label': _coalesce(target.get('displayPage'), target['page']) + ' · ' + graph_labels[other],
                          'direction': 'source' if other in roots else 'destination'})
            linked_pages.add(target['page'])
        targets = list(dict.fromkeys(destinations[key]))
        if not native:
            targets.sort()
        for page in targets:
            if page in linked_pages:
                continue
            ids = pages.get(page, [])
            if not native:
                ids = [i for i in ids if by_id[i].get('type') != 'card-ald']
            if len(ids) == 1:
                links.append({'pageId': ids[0], 'selection': None, 'label': page, 'direction': 'destination',
                              'note': 'Explicit page reference; target net is not uniquely located.'})
            else:
                net.setdefault('notes', []).append('Referenced page ' + page + ' is unavailable or ambiguous.')
        if links:
            net['links'] = links
        if native:
            for field in ('identity', 'destinationPages', 'sourceReferences'):
                net.pop(field, None)
        elif not net.get('segments'):
            net.pop('segments', None)

    block_sites = {}
    for eid, raw in raws.items():
        rows = _lines(text_by_id[eid])
        _annotate_nets(payloads[eid].get('nets', []), raw, rows)
        blocks = []
        block_sites[eid] = []
        for node in raw.get('nodes', []):
            if not isinstance(node, dict):
                continue
            rectangle = _box(rows, node)
            if rectangle is None:
                continue
            card = _display(node.get('card_type'))
            portion = _display(node.get('portion'))
            site, board, sockets = _site(node)
            block = {'id': _display(node.get('id')), 'label': _display(node.get('id')) + ' · ' + _display(node.get('function')),
                     'cardType': card, 'portion': portion, 'site': site, 'box': rectangle}
            links, notes = [], []
            if card in card_index:
                target = card_index[card]
                if any(p['portion'] == portion for p in payloads[target].get('portions', [])):
                    links.append({'pageId': target, 'selection': {'kind': 'portion', 'cardType': card, 'portion': portion}, 'label': 'Card ' + card + ' · ' + portion})
                else:
                    links.append({'pageId': target, 'selection': None, 'label': 'Card ' + card, 'note': 'Portion is not located in the published card drawing.'})
            elif card:
                notes.append('Card ALD ' + card + ' is not published.')
            matches = {(sid, item['id']): item for socket in sockets for sid, item in socket_index.get((board, socket, card), [])}
            for (sid, socket_id), item in sorted(matches.items()):
                links.append({'pageId': sid, 'selection': {'kind': 'socket', 'id': socket_id, 'portion': portion, 'page': by_id[eid]['page']}, 'label': _coalesce(by_id[sid].get('displayPage'), by_id[sid]['page']) + ' · ' + item['label']})

            if board and not matches:
                notes.append('No exact published socket/card match is located for ' + site + '.')
            if links:
                block['links'] = links
            if notes:
                block['notes'] = notes
            blocks.append(block)
            block_sites[eid].append((block, board, sockets))
        if blocks:
            payloads[eid]['blocks'] = blocks

    # Match installed socket-listing traversal order: printed references choose
    # candidate pages before their basic legacy blocks are considered.
    for payload in payloads.values():
        items = payload.get('sockets', [])
        candidates = {}
        for item in items:
            for portion in item.get('portions', []):
                for eid in pages.get(portion['page'], []):
                    if by_id[eid].get('type') == 'ald':
                        candidates[eid] = None
        for eid in candidates:
            for block, board, sockets in block_sites.get(eid, []):
                for item in items:
                    if board != item['board'] or block['cardType'] != item['cardType'] or not set(sockets).intersection(item['sockets']):
                        continue
                    for portion in item.get('portions', []):
                        if portion['portion'] == block['portion'] and portion['page'] == by_id[eid]['page']:
                            item.setdefault('links', []).append({'pageId': eid, 'selection': {'kind': 'block', 'id': block['id']}, 'label': portion['page'] + ' · ' + portion['portion']})
    assets = {}
    for entry in entries:
        payload = payloads[entry['id']]
        data = (json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
        sha = hashlib.sha256(data).hexdigest()
        url = 'interactions/page-' + entry['id'] + '-' + sha + '.json'
        assets[url] = data
        entry['interactionURL'], entry['interactionSha256'] = url, sha
    return assets

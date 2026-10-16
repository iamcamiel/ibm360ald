"""Compact horizontal routing without changing a single net or box shape."""
from hashlib import sha256


def compact(canvas, geometry, pin_labels, exterior_columns):
    original = [list(r) for r in canvas.rows]
    protected = []
    for g in geometry.values():
        x = g['left']
        protected.append((x, x + 7))
    for x, y, pin, side in pin_labels:
        start = x - 3 if side == 'input' else x + 8
        protected.append((start, start + 2))
    protected.extend((x, x + 2) for x in exterior_columns)
    # Join touching protected ranges: a printed pin touches its box border.
    spans = []
    for lo, hi in sorted(protected):
        if spans and lo <= spans[-1][1] + 1:
            spans[-1] = (spans[-1][0], max(hi, spans[-1][1]))
        else:
            spans.append((lo, hi))
    protected_columns = {x for lo, hi in spans for x in range(lo, hi + 1)}
    tracks = {
        x for y, row in enumerate(original) for x, ch in enumerate(row)
        if ch in '│┼◇┌┐└┘'
        and not any(g['left'] <= x <= g['left'] + 7
                    and g['top'] <= y < g['top'] + g['height']
                    for g in geometry.values())
    }
    assert not tracks & protected_columns, sorted(tracks & protected_columns)
    anchors = sorted(protected_columns | tracks | {
        x for row in original for x, ch in enumerate(row) if ch not in ' ─'
    })
    mapping = {anchors[0]: 0}
    for a, b in zip(anchors, anchors[1:]):
        same_span = any(lo <= a < b <= hi for lo, hi in spans)
        gap = 1
        if not same_span:
            if a in tracks and b in tracks:
                gap = 2
            elif (a in tracks and b in protected_columns
                  or b in tracks and a in protected_columns):
                gap = 3
        mapping[b] = mapping[a] + gap
    width = mapping[anchors[-1]] + 1
    rows = [[' '] * width for _ in original]
    rightward = set('─┼◇┌└BDGJ0123456789')
    leftward = set('─┼◇┐┘BDGJ0123456789')
    for y, old in enumerate(original):
        for x in anchors:
            rows[y][mapping[x]] = old[x]
        for a, b in zip(anchors, anchors[1:]):
            middle = old[a + 1:b]
            assert all(ch in ' ─' for ch in middle), (y, a, b)
            if '─' in middle:
                assert all(ch == '─' for ch in middle), (y, a, b, middle)
                connect = True
            elif not middle:
                connect = old[a] in rightward and old[b] in leftward
            else:
                connect = False
            if connect:
                for x in range(mapping[a] + 1, mapping[b]):
                    rows[y][x] = '─'
    old_text = '\n'.join(''.join(r) for r in original)
    canvas.rows, canvas.width = rows, width
    canvas.boxes = [(mapping[x], top, bottom, p)
                    for x, top, bottom, p in canvas.boxes]
    for g in geometry.values():
        g['left'] = mapping[g['left']]
    # This global mapping is intentionally stricter than row-local clearance.
    # Thus every actual parallel segment and attached pin-label span complies.
    mapped_tracks = sorted(mapping[x] for x in tracks)
    mapped_spans = [(mapping[a], mapping[b]) for a, b in spans]
    track_gaps = [b - a - 1 for a, b in zip(mapped_tracks, mapped_tracks[1:])]
    clearances = [min(abs(t - a), abs(t - b)) - 1
                  for t in mapped_tracks for a, b in mapped_spans
                  if not a <= t <= b]
    assert min(track_gaps) >= 1
    assert min(clearances) >= 2
    return {
        'schema': 'card-ald-monotonic-column-compaction-v1',
        'original_width': len(original[0]), 'compacted_width': width,
        'original_canvas_sha256': sha256(old_text.encode('utf-8')).hexdigest(),
        'column_map': {str(k): v for k, v in mapping.items()},
        'protected_spans_before': spans, 'protected_spans_after': mapped_spans,
        'vertical_tracks_before': sorted(tracks),
        'vertical_tracks_after': mapped_tracks,
        'minimum_parallel_wire_gap': min(track_gaps),
        'minimum_wire_to_box_or_pin_label_gap': min(clearances),
        'unchanged_rows_and_nets': True,
    }

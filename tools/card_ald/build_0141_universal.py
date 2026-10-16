"""Build the complete 5800141 pinout and a source-bound composite evidence file.

The twenty signal contacts exhaust both twelve-contact rows after the four
power contacts are removed. Page-level supply ties and polarity variants are
not extra physical inputs to the card's gates.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
ORDER = [
    ('A1', 'A2', 'A3', ('D13', 'B13'), ('D09', 'B08'), 'B10'),
    ('B1', 'B2', 'B3', ('D10', 'B09'), ('D11', 'D12'), 'B12'),
    ('C1', 'C2', 'C3', ('D02', 'B02'), ('D07', 'D05'), 'B04'),
    ('D1', 'D2', 'D3', ('D04', 'B05'), ('B07', 'D06'), 'B03'),
]
POWER = {'D08': 'GROUND / 0V', 'D03': '+3V', 'B06': '-3V', 'B11': '+6V'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Canvas:
    def __init__(self):
        self.rows = [[' '] * 83 for _ in range(56)]
        self.boxes = []

    def put(self, x, y, text):
        for i, char in enumerate(text):
            self.rows[y][x+i] = char

    def horizontal(self, x1, x2, y):
        for x in range(x1, x2+1):
            assert self.rows[y][x] in (' ', '─'), (x, y, self.rows[y][x])
            self.put(x, y, '─')

    def vertical(self, x, y1, y2):
        for y in range(y1, y2+1):
            assert self.rows[y][x] in (' ', '│'), (x, y, self.rows[y][x])
            self.put(x, y, '│')

    def box(self, x, y, portion, function, circuit):
        assert y % 7 == 0
        self.put(x, y, '┌──────┐')
        self.put(x, y+6, '└──────┘')
        for row in range(y+1, y+6):
            self.put(x, row, '│      │')
        self.put(x+1, y+1, function)
        self.put(x+1, y+3, circuit)
        self.put(x+1, y+4, '0141'+portion)
        self.boxes.append({'portion': portion, 'left': x, 'top': y, 'width': 8, 'height': 7})

    def render(self):
        return '\n'.join(''.join(row).rstrip() for row in self.rows)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    outdir = args.output_dir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    catalog_path = ROOT/'json/Card types current/0141.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    occurrences = catalog['diagram_occurrences']
    assert all(o['source_reviewed'] for o in occurrences)
    expected_pins = {}
    for a, b, c, pa, pb, out in ORDER:
        expected_pins[a] = {'input': set(pa), 'output': set()}
        expected_pins[b] = {'input': set(pb), 'output': set()}
        expected_pins[c] = {'input': set(), 'output': {out}}
    signals = [p for row in ORDER for p in (*row[3], *row[4], row[5])]
    assert len(signals) == len(set(signals)) == 20
    all_contacts = {f'{letter}{n:02}' for letter in 'BD' for n in range(2, 14)}
    assert set(signals) | set(POWER) == all_contacts
    assert not set(signals) & set(POWER)

    pin_evidence = defaultdict(list)
    variations = []
    circuit_counts = defaultdict(Counter)
    source_models = {}
    pages = {}
    for item in occurrences:
        portion = item['portion']
        circuit_counts[portion][item['circuit_identifier']] += 1
        model_rel = Path(item['source_text']).with_suffix('.json')
        model_rel = Path('json')/Path(*model_rel.parts[1:])
        if model_rel.as_posix() not in source_models:
            model_path = ROOT/model_rel
            doc = json.loads(model_path.read_text(encoding='utf-8'))
            source_models[model_rel.as_posix()] = {'sha256': digest(model_path), 'model': doc}
            pages[item['page']] = model_rel.as_posix()
        for pin in item['pins']:
            literal = pin.get('printed_pin') or pin.get('pin')
            if not literal:
                continue
            match = re.fullmatch(r'\d*([BD]\d{2})(?:✲?T?|✲)', literal)
            physical = match.group(1) if match else None
            record = {'page': item['page'], 'block': item['node'], 'portion': portion,
                      'side': pin['side'], 'literal': literal, 'row': pin.get('row')}
            if physical in expected_pins[portion].get(pin['side'], set()):
                pin_evidence[(portion, pin['side'], physical)].append(record)
            else:
                variations.append({**record, 'physical_contact': physical,
                    'category': 'power_tie_annotation' if physical in POWER else 'nonmodal_source_or_model_reading'})
    assert all(pin_evidence[(p, side, pin)] for p, sides in expected_pins.items()
               for side, pins in sides.items() for pin in pins)

    # Review every modeled same-card link. Page models sometimes omit a drawn
    # continuation or a target. Count only links actually represented and retain
    # the remaining topology separately; absence is not evidence of disconnection.
    expected_edges = {(a, c) for a, b, c, *_ in ORDER} | {(b, c) for a, b, c, *_ in ORDER}
    edge_evidence = defaultdict(list)
    other_edges = []
    installations = set()
    for rel, entry in source_models.items():
        doc = entry['model']
        nodes = {n['id']: n for n in doc.get('nodes', []) if n.get('card_type') == '0141'}
        for n in nodes.values():
            installations.add((rel, n.get('location')))
        for net in doc.get('nets', []):
            driver = str(net.get('driver') or '').split('.', 1)[0]
            if driver not in nodes:
                continue
            for target in net.get('targets', []):
                target_id = str(target).split('.', 1)[0]
                if target_id not in nodes or nodes[driver].get('location') != nodes[target_id].get('location'):
                    continue
                edge = (nodes[driver].get('portion'), nodes[target_id].get('portion'))
                record = {'model': rel, 'from_block': driver, 'to_block': target_id,
                          'location': nodes[driver].get('location'), 'net': net.get('id')}
                if edge in expected_edges:
                    edge_evidence[edge].append(record)
                else:
                    source_contacts = [p.get('pin') for p in nodes[driver].get('pins', [])
                                       if p.get('side') == 'output' and p.get('pin')]
                    target_contacts = [p.get('pin') for p in nodes[target_id].get('pins', [])
                                       if p.get('side') == 'input' and p.get('pin')]
                    assert source_contacts and target_contacts, record
                    other_edges.append({**record, 'from_portion': edge[0], 'to_portion': edge[1],
                        'source_physical_output_labels': source_contacts,
                        'target_physical_input_labels': target_contacts,
                        'disposition': 'Installation wiring between exposed card contacts; not an additional fixed internal card link.'})
    assert set(edge_evidence) == expected_edges

    canvas = Canvas()
    for index, (a, b, c, pa, pb, output) in enumerate(ORDER):
        base = index*14
        canvas.box(23, base, a, 'A', 'U03AA')
        canvas.box(23, base+7, b, 'A', 'U03AA')
        canvas.box(52, base+7, c, 'OR', 'U03AE')
        for top, pins in ((base, pa), (base+7, pb)):
            for row, pin in ((top+1, pins[0]), (top+5, pins[1])):
                canvas.put(0, row, pin)
                canvas.horizontal(3, 19, row)
                canvas.put(20, row, pin)
        canvas.horizontal(31, 35, base+3)
        canvas.put(36, base+3, '┐')
        canvas.vertical(36, base+4, base+7)
        canvas.put(36, base+8, '└')
        canvas.horizontal(37, 51, base+8)
        canvas.horizontal(31, 41, base+10)
        canvas.put(42, base+10, '┐')
        canvas.vertical(42, base+11, base+11)
        canvas.put(42, base+12, '└')
        canvas.horizontal(43, 51, base+12)
        canvas.put(59, base+10, '◺')
        canvas.put(60, base+10, output)
        canvas.horizontal(63, 79, base+10)
        canvas.put(80, base+10, output)
    text = (
        'CARD-ALD  5800141  SINGLE CARD  COMPLETE SIGNAL PINOUT\n'
        '12 PORTIONS   16 INPUT PINS   4 OUTPUT PINS   8 INTERNAL CONNECTIONS\n'
        'POWER PINS: D08 GROUND / 0V; D03 +3V; B06 -3V; B11 +6V\n'
        'U03AA = AND; U03AE = OR WITH INVERTED OUTPUT (◺).\n\n'
    ) + canvas.render()
    diagram = outdir/'0141.txt'
    diagram.write_text(text, encoding='utf-8', newline='\n')
    provenance = {
        'schema': 'card-ald-universal-composite-v1', 'card_type': '0141',
        'full_part_number': '5800141', 'card_width': 'SINGLE CARD',
        'diagram': {'path': str(diagram), 'sha256': digest(diagram)},
        'catalog': {'path': str(catalog_path), 'sha256': digest(catalog_path)},
        'counts': {'occurrences': len(occurrences), 'pages': len(pages),
                   'page_socket_installations': len(installations), 'portions': 12,
                   'signal_pins': 20, 'power_pins': 4, 'all_physical_contacts': 24,
                   'internal_connections': 8},
        'checks': {'all_24_contacts_accounted_for': True, 'all_signal_pins_have_reviewed_evidence': True,
                   'all_internal_links_have_model_evidence': True, 'power_pins_separate_from_logic': True,
                   'no_page_specific_wire_annotations': True, 'no_extra_signal_pins_inferred': True,
                   'seven_row_eight_column_boxes': True, 'canonical_files_modified': False},
        'signal_pins': [{'portion': p, 'side': side, 'pin': pin, 'occurrences': len(ev),
                         'evidence': ev} for (p, side, pin), ev in sorted(pin_evidence.items())],
        'internal_links': [{'from_portion': a, 'to_portion': b, 'occurrences': len(ev),
                            'evidence': ev} for (a, b), ev in sorted(edge_evidence.items())],
        'power_pins': POWER,
        'circuits_observed': {p: dict(c) for p, c in circuit_counts.items()},
        'nonmodal_circuit_readings': [
            {'page': o['page'], 'block': o['node'], 'portion': o['portion'],
             'circuit_identifier': o['circuit_identifier'],
             'disposition': 'Retained page-level circuit-label variant; normalized card circuits follow the direct owner instruction.'}
            for o in occurrences
            if o['circuit_identifier'] != ('U03AE' if o['portion'].endswith('3') else 'U03AA')
        ],
        'page_model_sources': [{'path': rel, 'sha256': e['sha256']} for rel, e in sorted(source_models.items())],
        'page_level_label_variants': variations,
        'other_modeled_same_card_links': other_edges,
        'interpretation': [
            'All 20 nonpower contacts are observed repeatedly; no additional signal contact remains available.',
            'The universal view shows available gate inputs even where an installation uses only one.',
            'Power-contact labels in ALDs denote page-specific ties, not additional logic inputs.',
            'U03AA is drawn with plain inputs; U03AE is drawn with inverted output by direct owner instruction.',
            'XX input wedges and equivalent page-level logic representations remain in original ALDs and the existing wedge variation audit.',
            'Modeled nonmodal labels, supply ties and between-portion page wiring remain evidence, not extra universal card pins.'
        ],
        'prior_review_sources': [
            {'path': str(p.relative_to(ROOT)), 'sha256': digest(p)} for p in [
                ROOT/'notes/Card-ALD/0141 all-occurrence audit.json',
                ROOT/'notes/Card-ALD/0141 physical-page confirmations.json',
                ROOT/'notes/Card-ALD/0141 function presentation answer.json',
                ROOT/'notes/Card-ALD/0141 input wedge variation audit.json',
            ]
        ],
    }
    (outdir/'0141 universal provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'diagram': str(diagram), 'counts': provenance['counts'],
                      'other_modeled_same_card_links': len(other_edges),
                      'page_level_label_variants': len(variations)}, indent=2))


if __name__ == '__main__':
    main()

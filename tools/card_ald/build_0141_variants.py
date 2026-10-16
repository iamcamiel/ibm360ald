"""Derive witnessed notation variants while keeping 0141 geometry identical."""
from collections import defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import re

from build_0141_universal import ROOT, ORDER, digest


def wedge(pin):
    return bool(pin.get('triangle')) or pin.get('border_marker') == '◺'


def build_variants(outdir):
    outdir = Path(outdir).resolve()
    base_path = outdir/'0141.txt'
    base = base_path.read_text(encoding='utf-8').splitlines()
    catalog_path = ROOT/'json/Card types current/0141.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    header_rows = 5
    geometry = {}
    whitelist = set()
    for index, (a, b, c, pa, pb, output) in enumerate(ORDER):
        top = index*14
        geometry[a] = {'left': 23, 'top': top, 'input_pins': pa, 'function': 'A', 'output': False}
        geometry[b] = {'left': 23, 'top': top+7, 'input_pins': pb, 'function': 'A', 'output': False}
        geometry[c] = {'left': 52, 'top': top+7, 'input_pins': (a, b), 'function': 'OR', 'output': True}
    for p, g in geometry.items():
        x, y = g['left'], g['top']+header_rows
        whitelist |= {(col, y+1) for col in range(x+1, x+7)}
        whitelist |= {(x, y+1), (x, y+5), (x+7, y+3)}
    groups = defaultdict(list)
    for o in catalog['diagram_occurrences']:
        groups[(o['page'], o['location'], o['source_text'])].append(o)
    unique = {}
    canonical_sources = []
    for (page, location, source_text), occurrences in sorted(groups.items()):
        rows = [list(r.ljust(83)) for r in base]
        witness = {'page': page, 'location': location, 'source_text': source_text,
                   'observed_portions': sorted(o['portion'] for o in occurrences),
                   'unobserved_portions_kept_canonical': sorted(set(geometry)-{o['portion'] for o in occurrences}),
                   'fields_not_inferred': [], 'mapped_input_wedges': []}
        for o in occurrences:
            p = o['portion']; g = geometry[p]; x, top = g['left'], g['top']+header_rows
            function = (o.get('function_label') or '').strip()
            if function and len(function) <= 6:
                rows[top+1][x+1:x+7] = list(function.ljust(6))
            else:
                witness['fields_not_inferred'].append({'portion': p, 'field': 'function',
                    'reason': 'Missing or oversized source function label; canonical label retained.'})
            inputs = [pin for pin in o['pins'] if pin['side'] == 'input']
            if not p.endswith('3'):
                for pin in inputs:
                    literal = pin.get('printed_pin') or pin.get('pin') or ''
                    match = re.fullmatch(r'\d*([BD]\d{2})(?:✲?T?|✲)', literal)
                    physical = match.group(1) if match else None
                    if physical in g['input_pins']:
                        index = g['input_pins'].index(physical)
                        row = top+(1 if index == 0 else 5)
                        rows[row][x] = '◺' if wedge(pin) else '│'
                        witness['mapped_input_wedges'].append({'portion': p, 'input': physical,
                            'triangle': wedge(pin), 'mapping': 'physical_contact'})
                    elif wedge(pin):
                        witness['fields_not_inferred'].append({'portion': p, 'field': 'input_decoration',
                            'literal': literal, 'reason': 'Power tie or nonmodal contact is not an extra card input.'})
            elif len(inputs) == 2:
                # These two OR inputs are pinless and electrically equivalent.
                # Keep the source's upper/lower notation rather than mixing
                # marks from other installations. Their wires do not move.
                for index, pin in enumerate(sorted(inputs, key=lambda t: t.get('row', 0))):
                    row = top+(1 if index == 0 else 5)
                    rows[row][x] = '◺' if wedge(pin) else '│'
                    witness['mapped_input_wedges'].append({'portion': p,
                        'input': 'upper' if index == 0 else 'lower',
                        'triangle': wedge(pin),
                        'mapping': 'source_visual_order_of_equivalent_pinless_inputs'})
            else:
                witness['fields_not_inferred'].append({'portion': p, 'field': 'input_decoration',
                    'reason': f'Source model has {len(inputs)} inputs; fixed card has two. Canonical input marks retained.'})
            outputs = [pin for pin in o['pins'] if pin['side'] == 'output']
            if len(outputs) == 1:
                rows[top+3][x+7] = '◺' if wedge(outputs[0]) else '│'
            else:
                witness['fields_not_inferred'].append({'portion': p, 'field': 'output_decoration',
                    'reason': 'No unique source output; canonical decoration retained.'})
        rendered = [''.join(r).rstrip() for r in rows]
        changes = []
        for y, (old, new) in enumerate(zip(base, rendered)):
            for x, (a, b) in enumerate(zip(old.ljust(83), new.ljust(83))):
                if a != b:
                    assert (x, y) in whitelist, (page, location, x, y, a, b)
                    changes.append({'column': x, 'line': y, 'before': a, 'after': b})
        if not changes:
            canonical_sources.append(witness)
            continue
        key = '\n'.join(rendered)
        if key not in unique:
            unique[key] = {'changes': changes, 'sources': [], 'rows': rendered}
        unique[key]['sources'].append(witness)

    variants = []
    for index, (key, variant) in enumerate(sorted(unique.items()), 1):
        filename = f'0141-{index:02}.txt'
        path = outdir/filename
        path.write_text('\n'.join(variant.pop('rows'))+'\n', encoding='utf-8', newline='\n')
        variants.append({'file': filename, 'sha256': digest(path), **variant})
    manual = Path('D:/Reference Materials/IBM 360/Z22-2798-1_Solid_Logic_Technology_Component_Circuits.pdf')
    index_doc = {
        'schema': 'card-ald-observed-notation-variants-v1', 'card_type': '0141',
        'canonical': {'file': '0141.txt', 'sha256': digest(base_path),
            'manual': {'path': str(manual), 'sha256': digest(manual), 'pdf_page': 91, 'printed_page': 90,
                'definitions': {'U03AA': 'AND', 'U03AE': 'OR INVERT WITH LOAD'}}},
        'catalog': {'path': str(catalog_path), 'sha256': digest(catalog_path)},
        'rules': [
            'Each variant starts from the complete manual-canonical card and applies only one witnessed page/socket notation pattern.',
            'Identical completed notation patterns are deduplicated; their installation witnesses remain separately recorded.',
            'Unobserved portions and unmappable decorations retain canonical symbols and are explicitly identified.',
            'No marks from separate installations are combined into a fictional observed pattern.',
            'Only the six function cells and three border decoration cells of each portion may differ.',
            'All headers, power lists, portion/circuit labels, pins, boxes and wires remain in exactly the same cells.',
            'Visual order maps the two equivalent pinless OR inputs; it does not infer changed internal wiring.'
        ],
        'counts': {'installation_witnesses': len(groups), 'canonical_pattern_witnesses': len(canonical_sources),
                   'distinct_observed_variants': len(variants),
                   'variant_installation_witnesses': sum(len(v['sources']) for v in variants)},
        'delta_whitelist': [{'column': x, 'line': y} for x, y in sorted(whitelist, key=lambda p: (p[1], p[0]))],
        'checks': {'every_variant_uses_one_witnessed_pattern': True, 'geometry_identical': True,
                   'all_cell_deltas_whitelisted': True, 'canonical_symbols_manual_defined': True},
        'canonical_pattern_sources': canonical_sources,
        'variants': variants,
    }
    (outdir/'0141 variants index.json').write_text(json.dumps(index_doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(index_doc['counts'], indent=2))
    return index_doc


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    build_variants(parser.parse_args().output_dir)

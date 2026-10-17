"""Rebuild uniform socket-listing JSON from the current accepted UTF-8 pages.

Writes a candidate dataset, never the legacy page models or transcriptions.
Only standard-library modules and the adjacent socket_text_parser are used.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re

SCHEMA = 'ibm360-socket-listings-v1'
ROOT = Path(__file__).resolve().parents[2]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def binding(path, repo):
    path = Path(path).resolve()
    return {'path': path.relative_to(repo).as_posix(), 'sha256': digest(path.read_bytes())}


def accepted_text_path(repo, entry):
    # Export receipts preserve the original host's absolute checkout path.
    # Locate its ALD-relative suffix so a cloned repository can also rebuild.
    stored = str(entry['destination']).replace('\\', '/')
    parts = stored.split('/ALD/', 1)
    if len(parts) != 2:
        raise ValueError('No ALD-relative destination: ' + stored)
    target = (repo / 'ALD' / parts[1]).resolve()
    if not target.is_relative_to(repo / 'ALD'):
        raise ValueError('Text target escapes ALD: ' + stored)
    return target


def load_pages(repo):
    """The accepted TXT is authoritative; heterogeneous old models are not read."""
    repo = Path(repo).resolve()
    provenance_path = repo / 'notes/Reviewed export provenance.json'
    doc = read(provenance_path)
    pages = []
    bindings = [binding(provenance_path, repo)]
    seen = set()
    for entry in doc['exported']:
        path = accepted_text_path(repo, entry)
        if not re.search(r'\bSOCKET LISTING\b', path.stem, re.I):
            continue
        if path in seen:
            raise ValueError('Duplicate accepted socket-listing text: ' + str(path))
        seen.add(path)
        raw = path.read_bytes()
        if digest(raw) != entry['text_sha256']:
            raise ValueError('TXT changed after acceptance: ' + str(path))
        text = raw.decode('utf-8-sig')
        lines = text.splitlines()
        boards = sorted(set(re.findall(r'\bBOARD\s+(\d{2}[A-Z]-[A-Z]\d)\b', text)))
        if len(boards) != 1:
            raise ValueError('Socket listing needs one readable BOARD field: ' + str(path))
        ends = re.findall(r'\r\n|\r|\n', text)
        newline = ends[0] if ends and len(set(ends)) == 1 else 'mixed' if ends else ''
        text_format = {'encoding': 'UTF-8', 'bom': raw.startswith(b'\xef\xbb\xbf'),
                       'newline': newline, 'trailing_newline': text.endswith(('\n', '\r'))}
        if newline == 'mixed':
            text_format['line_endings'] = ends
        pages.append({'page': path.stem.split()[0], 'printed_page': entry['page'],
            'scan_id': str(entry['source_scan_id']),
            'board': boards[0], 'lines': lines,
            'source_relative': str(entry['source_relative']).replace('\\', '/'),
            'text_path': path.relative_to(repo).as_posix(), 'text_sha256': digest(raw),
            'text_format': text_format,
            'board_proof': [{'row': row, 'column': match.start(1), 'literal': match[1],
                             'page': path.stem.split()[0], 'scan_id': str(entry['source_scan_id'])}
                            for row, line in enumerate(lines)
                            for match in re.finditer(r'\bBOARD\s+(\d{2}[A-Z]-[A-Z]\d)\b', line)]})
        bindings.append(binding(path, repo))
    if not pages:
        raise ValueError('No accepted socket-listing TXT files found')
    return pages, bindings


def physical_socket(value):
    return re.sub(r'(?<=\d)[BT]$', '', str(value))


def kind_name(value):
    literal = str(value or '')
    upper = literal.upper()
    if 'DOUBLE' in upper:
        return 'double_card'
    if 'SINGLE' in upper:
        return 'single_card'
    if 'CABL' in upper or 'CABLE' in upper:
        return 'cable'
    if 'XOVR' in upper or 'CROSSOVER' in upper:
        return 'crossover'
    if 'EMPTY' in upper:
        return 'empty'
    if 'CONN' in upper:
        return 'connector'
    return 'unspecified'


def evidence_page(value, page_by_scan, page_by_name):
    if not isinstance(value, dict):
        return None
    if value.get('scan_id') is not None:
        return page_by_scan.get(str(value['scan_id']))
    return page_by_name.get(value.get('page'))


def normalize_record(record, ordinal):
    references = []
    for ref in record.get('references', []):
        references.append({'page': ref.get('page', ref.get('ald_page')),
            'portions': [str(x) for x in ref.get('portions', [])],
            'source_spans': ref.get('evidence', [])})
    pins = [{'pin': pin.get('pin'), 'printed_socket': pin.get('printed_socket'),
             'listing_socket': pin.get('listing_socket'),
             'ALD_reference': pin.get('ALD_reference'),
             'reference_status': pin.get('reference_status',
                 'listed' if pin.get('ALD_reference') else 'no_reference_printed'),
             'evidence': pin.get('evidence')} for pin in record.get('pins', [])]
    return {'id': str(record.get('id', f'record-{ordinal:05d}')),
        'board': record.get('board'),
        'sockets': [str(x) for x in record.get('sockets', [])],
        'physical_sockets': sorted({physical_socket(x) for x in record.get('sockets', [])}),
        'kind': kind_name(record.get('kind')), 'kind_literal': record.get('kind'),
        'part_number': record.get('part_number'), 'card_type': record.get('card_type'),
        'ambiguous_fields': record.get('ambiguous_fields', {}),
        'references': references, 'pin_references': pins,
        'unused_portions': record.get('unused_portions', []),
        'unused_pins': record.get('unused_pins', []),
        'unused_sockets': record.get('unused_sockets', []),
        'connector_listing': record.get('connector_listing'),
        'wire_code': record.get('wire_code'), 'destination': record.get('destination'),
        'header_source': record.get('header_source'),
        'source_spans': record.get('source_spans', []),
        'raw_lines': record.get('raw_lines', []), 'issues': record.get('issues', [])}


def reconstruct_text(page):
    fmt = page['text_format']
    if fmt['newline'] == 'mixed':
        endings = fmt['line_endings']
        text = ''.join(line + (endings[i] if i < len(endings) else '')
                       for i, line in enumerate(page['lines']))
    else:
        text = fmt['newline'].join(page['lines'])
        if fmt['trailing_newline']:
            text += fmt['newline']
    return (b'\xef\xbb\xbf' if fmt['bom'] else b'') + text.encode('utf-8')


def build(pages, parser_result):
    by_scan = {p['scan_id']: p for p in pages}
    by_name = {p['page']: p for p in pages}
    if len(by_scan) != len(pages):
        raise ValueError('Duplicate input scan IDs')
    # Multiple separately scanned sheets can have the same printed page number.
    # Such evidence must use its scan ID, never an arbitrary page-name match.
    for name, count in Counter(p['page'] for p in pages).items():
        if count > 1:by_name.pop(name, None)
    records = [normalize_record(r, i) for i, r in enumerate(parser_result['records'], 1)]
    ids = [r['id'] for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError('Parser emitted duplicate record IDs')
    page_records = defaultdict(list)
    page_continuations = defaultdict(list)
    spans_checked = set()
    def check_evidence(span, context):
        page = evidence_page(span, by_scan, by_name)
        if page is None:
            raise ValueError('Unknown source-span page: ' + context)
        if span.get('page') is not None and span['page'] != page['page']:
            raise ValueError('Source page and scan ID disagree: ' + context)
        row, column = span['row'], span['column']
        literal = span['literal']
        if not (isinstance(row, int) and isinstance(column, int) and 0 <= row < len(page['lines']) and column >= 0):
            raise ValueError('Invalid source coordinates: ' + context)
        if page['lines'][row][column:column+len(literal)] != literal:
            raise ValueError('Source span does not reproduce accepted TXT: ' + context)
        spans_checked.add((page['scan_id'], row, column, literal))
        return page
    def nested_evidence(value, context):
        if isinstance(value, dict):
            if {'row','column','literal'}.issubset(value):
                check_evidence(value, context)
            else:
                for child in value.values():nested_evidence(child, context)
        elif isinstance(value, list):
            for child in value:nested_evidence(child, context)
    for record in records:
        header = evidence_page(record['header_source'], by_scan, by_name)
        if header is None:
            raise ValueError('Record has no attributable header page: ' + record['id'])
        page_records[header['scan_id']].append(record)
        nested_evidence(record, record['id'])
        members = set()
        for span in record['source_spans']:
            page = evidence_page(span, by_scan, by_name)
            members.add(page['scan_id'])
        for member in sorted(members - {header['scan_id']}):
            page_continuations[member].append(record['id'])
    output_pages = []
    tables = parser_result.get('tables', [])
    nested_evidence(tables, 'supplementary tables')
    nested_evidence(parser_result.get('issues', []), 'parser issues')
    tables_by_scan = defaultdict(list)
    for table in tables:
        tables_by_scan[evidence_page(table['evidence'], by_scan, by_name)['scan_id']].append(table)
    for page in pages:
        nested_evidence(page.get('board_proof', []), 'board field')
        raw = reconstruct_text(page)
        if raw is not None and digest(raw) != page['text_sha256']:
            raise ValueError('Source grid cannot reconstruct exact TXT: ' + page['page'])
        output_pages.append({'schema': SCHEMA, 'document_kind': 'socket_listing_page',
            'page': page['page'], 'printed_page': page.get('printed_page', page['page']), 'board': page['board'],
            'board_source_spans': page.get('board_proof', []),
            'source': {k: page[k] for k in ['scan_id', 'source_relative', 'text_path', 'text_sha256', 'text_format']},
            'grid': {'rows': len(page['lines']), 'columns': max(map(len, page['lines']), default=0),
                     'lines': page['lines']},
            'records': page_records[page['scan_id']],
            'supplementary_tables': tables_by_scan[page['scan_id']],
            'continuation_record_ids': page_continuations[page['scan_id']]})
    counts = {'source_pages': len(pages), 'boards': len({p['board'] for p in pages}),
        'logical_records': len(records), 'record_kinds': dict(Counter(r['kind'] for r in records)),
        'card_instances': sum(r['card_type'] is not None and 'CARD' in str(r['kind_literal']) for r in records),
        'portion_references': sum(len(ref['portions']) for r in records for ref in r['references']),
        'source_spans_verified': len(spans_checked), 'parser_issues': len(parser_result.get('issues', []))}
    index = {'schema': SCHEMA, 'document_kind': 'socket_listing_collection', 'counts': counts,
        'policy': 'Rebuilt only from current accepted TXT. Legacy JSON is not used to infer or fill values. Unknown print remains literal. Record fields have one schema for all source formats.',
        'records': records, 'issues': parser_result.get('issues', []),
        'supplementary_tables': tables,
        'parser_coverage': parser_result.get('coverage', {})}
    return index, output_pages


def write_dataset(repo, output, pages, index, output_pages, bindings):
    files = []
    def put(relative, raw):
        relative = Path(relative)
        if relative.is_absolute() or '..' in relative.parts or relative.drive:
            raise ValueError('Output path must be relative: ' + str(relative))
        path = (output / relative).resolve()
        if not path.is_relative_to(output.resolve()):
            raise ValueError('Output path escapes build root: ' + str(relative))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        files.append({'path': Path(relative).as_posix(), 'sha256': digest(raw)})
    root = Path('json/Socket listings uniform')
    put(root/'Socket listings.json', encoded(index))
    for source, page in zip(pages, output_pages):
        relative = Path(source['source_relative']).with_suffix('.json')
        put(root/'pages'/relative, encoded(page))
    rows = []
    for record in index['records']:
        for ref in record['references']:
            for portion in ref['portions']:
                rows.append({'record_id': record['id'], 'board': record['board'],
                    'sockets': ' '.join(record['sockets']), 'kind': record['kind'],
                    'part_number': record['part_number'], 'card_type': record['card_type'],
                    'ALD_page': ref['page'], 'portion': portion})
    stream = io.StringIO(newline='')
    cols = ['record_id','board','sockets','kind','part_number','card_type','ALD_page','portion']
    writer = csv.DictWriter(stream, fieldnames=cols);writer.writeheader();writer.writerows(rows)
    put('csv/Socket listings uniform/Portion references.csv', stream.getvalue().encode('utf-8-sig'))
    put('notes/Socket listings uniform/README.txt', (
        'UNIFORM SOCKET-LISTING DATA\n\n'
        'Socket listings.json is the single collection of logical records. Each\n'
        'record has the same fields, regardless of the older JSON schema. Values\n'
        'come from the current accepted UTF-8 text; no legacy value is substituted.\n'
        'Literal sockets retain B/T suffixes; physical_sockets removes only those\n'
        'suffixes for matching. Unknown print remains U+FFFD.\n\n'
        'Each record is owned by its header scan. A per-scan JSON file contains\n'
        'its records and IDs for continuations whose headers are on other scans.\n'
        'The source grid and exact text hashes are retained. Source spans use\n'
        'zero-based rows and columns. All records can be traced to these spans.\n\n'
        'Parser issues remain explicit review items; this build does not change\n'
        'transcriptions, old models, scans or acceptance receipts.\n').encode('utf-8'))
    manifest = {'schema': 'uniform-socket-listing-build-v1',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'counts': index['counts'],
        'inputs': bindings, 'files': files, 'legacy_models_modified': False,
        'original_scans_read_or_modified': False}
    put('notes/Socket listings uniform/Build manifest.json', encoded(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args();repo = args.repo.resolve()
    if not Path(__file__).resolve().is_relative_to(repo):
        parser.error('Run the installed copy of this tool in the selected repository')
    output = (args.output or repo.parent/'tmp/ald-text/ald/uniform-socket-listings').resolve()
    if output == repo or any(output.is_relative_to(repo/p) for p in ['ALD','json','csv','notes']):
        parser.error('Choose a separate output root, not a canonical data subtree')
    from socket_text_parser import parse_listings
    pages, bindings = load_pages(repo)
    parsed = parse_listings(pages)
    index, output_pages = build(pages, parsed)
    bindings.extend([binding(Path(__file__), repo), binding(Path(__file__).with_name('socket_text_parser.py'), repo)])
    manifest = write_dataset(repo, output, pages, index, output_pages, bindings)
    print(json.dumps({'output': str(output), 'counts': manifest['counts'],
                      'legacy_models_modified': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()

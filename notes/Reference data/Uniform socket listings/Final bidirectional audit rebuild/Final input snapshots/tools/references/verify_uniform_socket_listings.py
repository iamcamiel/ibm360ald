"""Independently verify a uniform socket dataset against current accepted TXT.

Does not import or execute the builder/parser, infer missing fields, or modify
source/data files. Mechanical proof and unresolved parser diagnostics are separate.
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

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'ibm360-socket-listings-v1'
MANIFEST = 'notes/Socket listings uniform/Build manifest.json'
INDEX = 'json/Socket listings uniform/Socket listings.json'
CSV = 'csv/Socket listings uniform/Portion references.csv'
RECORD_KEYS = set('id board sockets physical_sockets kind kind_literal part_number card_type ambiguous_fields references pin_references unused_portions unused_pins unused_sockets connector_listing wire_code destination header_source source_spans raw_lines issues'.split())
PAGE_KEYS = set('schema document_kind page printed_page board board_source_spans source grid records supplementary_tables continuation_record_ids'.split())
COLLECTION_KEYS = set('schema document_kind counts policy records issues supplementary_tables parser_coverage'.split())
SOURCE_KEYS = set('scan_id source_relative text_path text_sha256 text_format'.split())
CSV_FIELDS = ['record_id','board','sockets','kind','part_number','card_type','ALD_page','portion']


def sha(raw): return hashlib.sha256(raw).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def exact(a, b): return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


class Invalid(ValueError): pass


def need(ok, message):
    if not ok: raise Invalid(message)


def inside(root, relative):
    relative = str(relative)
    need('\\' not in relative and not re.match(r'^[A-Za-z]:', relative), 'Nonportable manifest path: ' + relative)
    path = Path(relative)
    need(not path.is_absolute() and path.parts and '..' not in path.parts, 'Unsafe relative path: ' + relative)
    result = (root/path).resolve()
    need(result.is_relative_to(root), 'Path escapes root: ' + relative)
    return result


def reconstruct(lines, fmt):
    need(isinstance(fmt, dict) and fmt.get('encoding') == 'UTF-8', 'Unsupported text encoding')
    need(type(fmt.get('bom')) is bool and type(fmt.get('trailing_newline')) is bool, 'Invalid text format flags')
    newline = fmt.get('newline')
    need(newline in {'', '\n', '\r', '\r\n', 'mixed'}, 'Invalid newline mode')
    need(set(fmt) == {'encoding','bom','newline','trailing_newline'} | ({'line_endings'} if newline == 'mixed' else set()), 'Text format keys differ')
    if newline == 'mixed':
        endings = fmt.get('line_endings')
        need(isinstance(endings, list) and all(e in {'\n','\r','\r\n'} for e in endings), 'Invalid mixed line endings')
        need(len(endings) == len(lines) - (not fmt['trailing_newline']), 'Wrong line-ending inventory')
        text = ''.join(line + (endings[i] if i < len(endings) else '') for i, line in enumerate(lines))
    else:
        need('line_endings' not in fmt, 'Unexpected per-line endings')
        need(newline or len(lines) <= 1, 'Multiple rows without a newline')
        text = newline.join(lines) + (newline if fmt['trailing_newline'] else '')
    return (b'\xef\xbb\xbf' if fmt['bom'] else b'') + text.encode('utf-8')


def verify(repo, dataset=None):
    repo = Path(repo).resolve(); dataset = Path(dataset or repo).resolve()
    report = {'schema':'uniform-socket-listing-verification-v1', 'created_utc':datetime.now(timezone.utc).isoformat(),
              'passed':False, 'failures':[], 'proof_counts':Counter(),
              'parser_diagnostics':{'status':'not_read'}, 'source_or_dataset_writes':False}
    report['verification_tools'] = [{'path':str(path),'sha256':sha(path.read_bytes())}
        for path in [Path(__file__).resolve(),Path(__file__).with_name('test_verify_uniform_socket_listings.py').resolve()]
        if path.is_file()]
    count = report['proof_counts']
    try:
        manifest_path = inside(dataset, MANIFEST); manifest = read(manifest_path)
        need(manifest.get('schema') == 'uniform-socket-listing-build-v1', 'Unsupported build manifest schema')
        need(manifest.get('legacy_models_modified') is False and manifest.get('original_scans_read_or_modified') is False,
             'Build claims unsupported source/model mutation')
        report['manifest'] = {'path':str(manifest_path),'sha256':sha(manifest_path.read_bytes())}
        input_paths, output_paths = set(), set()
        for links, base, seen, label in [(manifest['inputs'],repo,input_paths,'input'), (manifest['files'],dataset,output_paths,'output')]:
            need(isinstance(links,list), 'Missing '+label+' bindings')
            for link in links:
                path = inside(base,link['path']); key = path.relative_to(base).as_posix()
                need(key not in seen, 'Duplicate '+label+' path: '+key); seen.add(key)
                need(path.is_file() and sha(path.read_bytes()) == link['sha256'], 'Stale/missing '+label+' binding: '+key)
                count[label+'_hashes_verified'] += 1
        provenance_name = 'notes/Reviewed export provenance.json'
        need(provenance_name in input_paths, 'Accepted export provenance is unbound')
        provenance = read(repo/provenance_name); accepted = {}
        for entry in provenance['exported']:
            stored = str(entry['destination']).replace('\\','/')
            need('/ALD/' in stored, 'No ALD suffix in accepted destination')
            rel = 'ALD/'+stored.split('/ALD/',1)[1]
            if not re.search(r'\bSOCKET LISTING\b', Path(rel).stem, re.I): continue
            path = inside(repo,rel)
            need(rel not in accepted, 'Duplicate accepted socket TXT: '+rel)
            need(path.is_file() and sha(path.read_bytes()) == entry['text_sha256'], 'Accepted TXT is stale: '+rel)
            accepted[rel] = entry
        need(accepted, 'No accepted socket-listing pages')
        tools = {'tools/references/build_uniform_socket_listings.py','tools/references/socket_text_parser.py'}
        need(input_paths == {provenance_name,*accepted,*tools}, 'Input binding inventory differs from accepted TXT and tools')
        need(all((repo/p).is_file() for p in tools), 'Missing bound builder/parser tool')
        index = read(inside(dataset,INDEX))
        need(set(index) == COLLECTION_KEYS and index['schema'] == SCHEMA and index['document_kind'] == 'socket_listing_collection', 'Collection schema/keys differ')
        need(isinstance(index['policy'],str) and isinstance(index['parser_coverage'],dict), 'Invalid collection metadata')
        for key in ['records','issues','supplementary_tables']: need(isinstance(index[key],list), 'Collection list missing: '+key)
        report['parser_diagnostics'] = {'status':'unresolved' if index['issues'] else 'none', 'count':len(index['issues']),
                                        'by_kind':dict(Counter(str(x.get('kind','unspecified')) for x in index['issues'])),
                                        'coverage':index['parser_coverage'], 'affects_mechanical_pass':False}
        pages, by_name, page_files = {}, defaultdict(list), {}
        expected_outputs = {INDEX,CSV,'notes/Socket listings uniform/README.txt'}
        for rel, entry in accepted.items():
            source_rel = str(entry['source_relative']).replace('\\','/')
            output = 'json/Socket listings uniform/pages/'+str(Path(source_rel).with_suffix('.json')).replace('\\','/')
            need(output not in expected_outputs, 'Duplicate per-page output path'); expected_outputs.add(output)
            page = read(inside(dataset,output))
            need(set(page) == PAGE_KEYS and page['schema'] == SCHEMA and page['document_kind'] == 'socket_listing_page', 'Page schema/keys differ: '+output)
            source = page['source']; need(set(source) == SOURCE_KEYS, 'Page source keys differ')
            scan = str(entry['source_scan_id']); name = Path(rel).stem.split()[0]
            need(source['scan_id'] == scan and scan not in pages, 'Duplicate/mismatched scan ID: '+scan)
            need(page['page'] == name and page['printed_page'] == entry['page'], 'Page/printed-page identity differs: '+output)
            need(source['source_relative'] == source_rel and source['text_path'] == rel and source['text_sha256'] == entry['text_sha256'], 'Page source binding differs: '+output)
            grid = page['grid']; need(set(grid) == {'rows','columns','lines'}, 'Grid keys differ')
            lines = grid['lines']; need(isinstance(lines,list) and all(isinstance(x,str) and not any(c in x for c in '\r\n') for x in lines), 'Invalid source grid rows')
            need(type(grid['rows']) is int and type(grid['columns']) is int and grid['rows'] == len(lines) and grid['columns'] == max(map(len,lines),default=0), 'Grid dimensions differ')
            need(reconstruct(lines, source['text_format']) == (repo/rel).read_bytes(), 'Grid does not roundtrip exact accepted TXT: '+name)
            boards = {m[1] for line in lines for m in re.finditer(r'\bBOARD\s+(\d{2}[A-Z]-[A-Z]\d)\b',line)}
            need(boards == {page['board']}, 'Board field differs from source grid: '+name)
            for key in ['records','supplementary_tables','continuation_record_ids','board_source_spans']: need(isinstance(page[key],list), 'Invalid page list: '+key)
            pages[scan] = page; by_name[name].append(page); page_files[scan] = output
            count['accepted_grids_roundtripped'] += 1
        need(output_paths == expected_outputs, 'Build output inventory is missing or unexpected')
        actual_outputs = {p.relative_to(dataset).as_posix() for branch in ['json/Socket listings uniform','csv/Socket listings uniform','notes/Socket listings uniform'] for p in (dataset/branch).rglob('*') if p.is_file()}
        need(actual_outputs == expected_outputs | {MANIFEST}, 'Unlisted files in managed dataset subtrees')
        spans = set()
        def evidence(span, context, counted=True):
            need(isinstance(span,dict) and {'row','column','literal'} <= set(span), 'Incomplete evidence: '+context)
            if span.get('scan_id') is not None:
                page = pages.get(str(span['scan_id']))
            else:
                candidates = by_name.get(span.get('page'),[]); page = candidates[0] if len(candidates) == 1 else None
            need(page is not None, 'Unknown/ambiguous evidence scan: '+context)
            need(span.get('page',page['page']) == page['page'], 'Evidence page/scan disagree: '+context)
            row,col,literal = span['row'],span['column'],span['literal']; lines = page['grid']['lines']
            need(type(row) is int and type(col) is int and isinstance(literal,str) and 0 <= row < len(lines) and 0 <= col <= len(lines[row]), 'Invalid evidence coordinates: '+context)
            need(col+len(literal) <= len(lines[row]) and lines[row][col:col+len(literal)] == literal, 'Evidence literal differs from exact source cells: '+context)
            if 'end_column' in span: need(type(span['end_column']) is int and col+len(literal) <= span['end_column'] <= page['grid']['columns'], 'Invalid evidence end column')
            if 'socket_column' in span: need(type(span['socket_column']) is int and col <= span['socket_column'] < col+len(literal), 'Invalid socket column')
            if counted: spans.add((page['source']['scan_id'],row,col,literal))
            return page['source']['scan_id']
        def nested(value, context, counted=True):
            if isinstance(value,dict):
                if 'row' in value or 'column' in value: evidence(value,context,counted)
                else:
                    for key,child in value.items(): nested(child,context+'/'+key,counted)
            elif isinstance(value,list):
                for i,child in enumerate(value): nested(child,context+'/'+str(i),counted)
        record_map, owners, members = {}, defaultdict(list), defaultdict(set)
        for record in index['records']:
            need(isinstance(record,dict) and set(record) == RECORD_KEYS, 'Nonuniform logical record keys')
            rid = record['id']; need(isinstance(rid,str) and rid and rid not in record_map, 'Duplicate/invalid logical record ID')
            record_map[rid] = record
            for key in ['sockets','physical_sockets','unused_portions','unused_sockets']:
                need(isinstance(record[key],list) and all(isinstance(v,str) for v in record[key]), 'Invalid string list '+rid+'/'+key)
            physical = sorted({re.sub(r'(?<=\d)[BT]$','',x) for x in record['sockets']})
            need(record['physical_sockets'] == physical, 'Physical socket normalization differs: '+rid)
            need(record['kind'] in {'single_card','double_card','cable','crossover','empty','connector','unspecified'}, 'Unknown normalized record kind')
            for key in ['board','kind_literal','part_number','card_type','connector_listing','wire_code','destination']:
                need(record[key] is None or isinstance(record[key],str), 'Nonuniform scalar '+rid+'/'+key)
            need(isinstance(record['ambiguous_fields'],dict), 'Missing ambiguous-field map')
            for key in ['references','pin_references','unused_pins','source_spans','raw_lines','issues']: need(isinstance(record[key],list), 'Nonuniform record list '+rid+'/'+key)
            for ref in record['references']:
                need(isinstance(ref,dict) and set(ref) == {'page','portions','source_spans'}, 'Reference schema differs')
                need(isinstance(ref['page'],str) and isinstance(ref['portions'],list) and all(isinstance(x,str) for x in ref['portions']) and isinstance(ref['source_spans'],list), 'Invalid reference values')
            for pin in record['pin_references']:
                need(isinstance(pin,dict) and set(pin) == {'pin','printed_socket','listing_socket','ALD_reference','reference_status','evidence'}, 'Pin-reference schema differs')
                need(isinstance(pin['pin'],str) and all(pin[k] is None or isinstance(pin[k],str) for k in ['printed_socket','listing_socket','ALD_reference']), 'Invalid pin-reference scalar')
                need(pin['reference_status'] == ('listed' if pin['ALD_reference'] else 'no_reference_printed'), 'Pin-reference status differs')
                need(isinstance(pin['evidence'],dict), 'Pin reference lacks cell evidence')
            owner = evidence(record['header_source'],rid+'/header')
            need(record['board'] == pages[owner]['board'], 'Record/header board differ: '+rid)
            owners[owner].append(rid)
            nested(record,rid)
            for span in record['source_spans']: members[rid].add(evidence(span,rid+'/member'))
            need(owner in members[rid], 'Record source spans omit owning header scan: '+rid)
        nested(index['issues'],'issues'); nested(index['supplementary_tables'],'tables')
        tables_by_scan = defaultdict(list)
        for table in index['supplementary_tables']:
            need(isinstance(table,dict) and 'evidence' in table, 'Supplementary table lacks evidence')
            tables_by_scan[evidence(table['evidence'],'table')].append(table)
        owned_ids = []
        for scan,page in pages.items():
            expected_owned = [record_map[rid] for rid in owners[scan]]
            need(exact(page['records'],expected_owned), 'Per-scan records differ from collection/header ownership: '+scan)
            owned_ids.extend(r['id'] for r in page['records'])
            expected_cont = [rid for rid in record_map if scan in members[rid] and rid not in owners[scan]]
            need(page['continuation_record_ids'] == expected_cont, 'Continuation record IDs differ: '+scan)
            need(exact(page['supplementary_tables'],tables_by_scan[scan]), 'Supplementary table ownership differs: '+scan)
            expected_board = [{'row':row,'column':m.start(1),'literal':m[1],'page':page['page'],'scan_id':scan} for row,line in enumerate(page['grid']['lines']) for m in re.finditer(r'\bBOARD\s+(\d{2}[A-Z]-[A-Z]\d)\b',line)]
            need(exact(page['board_source_spans'],expected_board), 'Board proof inventory differs: '+scan)
            nested(page['board_source_spans'],'board/'+scan)
        need(Counter(owned_ids) == Counter(record_map.keys()), 'Collection record ownership is not exactly once')
        expected_csv = Counter()
        for r in record_map.values():
            for ref in r['references']:
                for portion in ref['portions']:
                    expected_csv[tuple('' if x is None else str(x) for x in [r['id'],r['board'],' '.join(r['sockets']),r['kind'],r['part_number'],r['card_type'],ref['page'],portion])] += 1
        with inside(dataset,CSV).open(encoding='utf-8-sig',newline='') as stream:
            reader = csv.DictReader(stream); need(reader.fieldnames == CSV_FIELDS, 'CSV column schema differs')
            rows = list(reader); need(all(set(r) == set(CSV_FIELDS) and all(isinstance(v,str) for v in r.values()) for r in rows), 'Malformed CSV reference row')
        need(Counter(tuple(r[k] for k in CSV_FIELDS) for r in rows) == expected_csv, 'CSV reference multiset differs from collection')
        expected_counts = {'source_pages':len(pages),'boards':len({p['board'] for p in pages.values()}),
            'logical_records':len(record_map),'record_kinds':dict(Counter(r['kind'] for r in record_map.values())),
            'card_instances':sum(r['card_type'] is not None and 'CARD' in str(r['kind_literal']) for r in record_map.values()),
            'portion_references':sum(expected_csv.values()),'source_spans_verified':len(spans),'parser_issues':len(index['issues'])}
        need(exact(index['counts'],expected_counts) and exact(manifest['counts'],expected_counts), 'Collection/build counts differ from independent recomputation')
        count.update({'logical_records_verified':len(record_map),'unique_source_spans_verified':len(spans),
                      'csv_reference_rows_verified':sum(expected_csv.values()),'source_pages_expected':len(accepted),
                      'pin_references_verified':sum(len(r['pin_references']) for r in record_map.values()),
                      'continuation_links_verified':sum(len(p['continuation_record_ids']) for p in pages.values())})
        report['passed'] = True
        report['scope'] = 'Exact accepted text/hash/grid, uniform schema, ownership, recursive cell evidence and CSV consistency; parser interpretations remain independently reviewable diagnostics.'
    except (Invalid, ValueError, KeyError, TypeError, OSError) as error:
        report['failures'].append(str(error))
    report['proof_counts'] = dict(count)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=ROOT)
    parser.add_argument('--dataset',type=Path)
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    if args.report:
        if args.report.resolve().is_relative_to(args.repo.resolve()): parser.error('--report must be outside the repository')
        if args.report.exists(): parser.error('--report must name a new file')
    report = verify(args.repo,args.dataset)
    raw = json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True); args.report.write_text(raw,encoding='utf-8')
    print(raw,end='')
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__': main()

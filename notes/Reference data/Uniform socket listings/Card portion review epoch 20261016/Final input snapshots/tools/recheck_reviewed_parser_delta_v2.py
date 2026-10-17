"""Recheck an independently accepted parser delta on a fresh accepted TXT epoch.

The acceptance is semantic: later accepted source corrections may change the
epoch, but the two fixed parser versions must still differ in exactly the
reviewed records, claims, source spans and raw lines. Nothing is written here.
"""
from collections import Counter
from pathlib import Path
import hashlib
import importlib.util
import json


def need(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(link):
    path = Path(link['path']).resolve()
    need(path.is_file() and bind(path)['sha256'] == link['sha256'], 'Stale delta binding: ' + str(path))
    return path


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def added_dropped(before, after):
    left, right = Counter(map(canon, before)), Counter(map(canon, after))
    return {'added': [json.loads(x) for x, n in sorted((right-left).items()) for _ in range(n)],
            'dropped': [json.loads(x) for x, n in sorted((left-right).items()) for _ in range(n)]}


def signature(change):
    """Use exact source coordinates/literals, preserving duplicate evidence."""
    return {key: change[key] for key in ('record_id', 'board', 'sockets', 'card_type',
            'claim_delta', 'source_span_delta', 'raw_line_delta', 'reference_delta')}


def compare(before, after):
    left = {r['id']: r for r in before['records']}
    right = {r['id']: r for r in after['records']}
    need(len(left) == len(before['records']) and len(right) == len(after['records']), 'Duplicate parser record ID')
    need(left.keys() == right.keys(), 'Parser added or dropped records')
    need(before['tables'] == after['tables'], 'Parser changed supplementary tables')
    need(not before['issues'] and not after['issues'], 'Parser issues require independent review')
    changes = []
    claims = lambda r: [{'page': x['page'], 'portion': p} for x in r['references'] for p in x['portions']]
    variable = {'references', 'source_spans', 'raw_lines'}
    for rid in sorted(left):
        a, b = left[rid], right[rid]
        if a == b:
            continue
        need({k:v for k,v in a.items() if k not in variable} ==
             {k:v for k,v in b.items() if k not in variable}, 'Parser changed record identity/other field: ' + rid)
        changes.append({'record_id': rid, 'board': b['board'], 'sockets': b['sockets'], 'card_type': b['card_type'],
            'claim_delta': added_dropped(claims(a), claims(b)),
            'reference_delta': added_dropped(a['references'], b['references']),
            'source_span_delta': added_dropped(a['source_spans'], b['source_spans']),
            'raw_line_delta': added_dropped(a['raw_lines'], b['raw_lines'])})
    return changes


def accepted_summary(parsed):
    """The signed review summarizes coverage and separately counted evidence.

    Keep the full coverage (including per-scan column maps) independently below;
    do not compare these deliberately different schemas as if interchangeable.
    """
    coverage = parsed['coverage']
    keys = ('scans', 'logical_records', 'card_records', 'portion_claims',
            'unparsed_significant_lines', 'orphan_significant_lines')
    return {**{key: coverage[key] for key in keys},
            'source_spans': sum(len(r['source_spans']) for r in parsed['records']),
            'pins': sum(len(r['pins']) for r in parsed['records'])}


def recheck(repo, acceptance_path, build_path):
    repo = Path(repo).resolve()
    acceptance = read(acceptance_path)
    need(acceptance.get('schema') == 'independent-dotted-continuation-parser-delta-acceptance-v1' and
         acceptance.get('independent_review') is True and acceptance.get('passed') is True and
         not acceptance.get('failures'), 'Missing independent parser delta acceptance')
    delta_path = checked(acceptance['delta']); delta = read(delta_path)
    need(delta.get('schema') == 'independent-dotted-continuation-parser-delta-v1' and delta.get('passed') is True,
         'Unsupported reviewed parser delta')
    old_path, new_path = checked(acceptance['old_parser']), checked(acceptance['new_parser'])
    need(delta['old_parser'] == acceptance['old_parser'] and delta['new_parser'] == acceptance['new_parser'],
         'Acceptance/parser version disagreement')
    need(new_path == (repo/'tools/references/socket_text_parser.py').resolve(), 'New parser is not installed parser')
    old_manifest = read(checked(delta['old_parser_manifest']))
    need(any(x['path'] == 'tools/references/socket_text_parser.py' and x['sha256'] == bind(old_path)['sha256']
             for x in old_manifest['inputs']), 'Old parser not bound to preserved build')
    checked(delta['reviewer'])
    checked(acceptance['before_parse']); checked(acceptance['after_parse'])
    expected_before, expected_after = read(checked(delta['before_parse'])), read(checked(delta['after_parse']))
    need(expected_before['coverage'] == delta['before_counts'] and expected_after['coverage'] == delta['after_counts'],
         'Reviewed raw parse/full coverage disagreement')
    need(accepted_summary(expected_before) == acceptance['before_counts'] and
         accepted_summary(expected_after) == acceptance['after_counts'], 'Acceptance/summary count disagreement')
    expected = compare(expected_before, expected_after)
    need([signature(x) for x in expected] == [signature({**x, 'reference_delta': added_dropped(x['before']['references'], x['after']['references'])})
         for x in delta['changed_records']], 'Frozen delta does not reproduce reviewed parse pair')
    builder = module('reviewed_delta_accepted_builder', build_path)
    pages, inputs = builder.load_pages(repo)
    before = module('reviewed_delta_old_parser', old_path).parse_listings(pages)
    after = module('reviewed_delta_new_parser', new_path).parse_listings(pages)
    changes = compare(before, after)
    need(changes == expected, 'Current parser delta differs from independently reviewed semantic delta')
    need(before['coverage'] == delta['before_counts'] and after['coverage'] == delta['after_counts'],
         'Current full parser coverage differs from reviewed raw coverage')
    need(accepted_summary(before) == acceptance['before_counts'] and
         accepted_summary(after) == acceptance['after_counts'],
         'Current summary counts differ from independent acceptance')
    by_scan = {str(p['scan_id']): p for p in pages}
    for change in changes:
        for span in change['source_span_delta']['added']:
            need(by_scan[str(span['scan_id'])]['lines'][span['row']][span['column']:span['end_column']] == span['literal'],
                 'Added source span differs from current accepted TXT')
    old_index, _ = builder.build(pages, before)
    new_index, _ = builder.build(pages, after)
    native_cases=acceptance.get('native_cases', [])
    need(len(native_cases)==len(changes) and
         {c['record_id'] for c in native_cases}=={c['record_id'] for c in changes},
         'Native crop review does not cover exact changed records')
    native_inputs=[]
    for case in native_cases:
        need(case.get('socket_header_and_portion_visually_confirmed') is True,
             'Native crop lacks accepted visual confirmation')
        # TIFF path/hash/coordinates remain in the accepted receipt. Preserve
        # only its small reviewed crop; never copy original scans into notes.
        need(case.get('native_source', {}).get('path') and case['native_source'].get('sha256'),
             'Native crop lacks original source binding')
        crop=case['native_crop'];path=Path(crop['path'])
        if not path.is_absolute():path=repo.parent/path
        link={'path':str(path.resolve()),'sha256':crop['sha256']}
        checked(link);native_inputs.append(link)
    private_evidence=[dict(delta[key],evidence_role=key,
        storage='retained-private-not-copied',reason='Bulky raw parser snapshot; exact reviewed hash still guarded')
        for key in ('before_parse','after_parse')]
    links = [{'path': str(repo/x['path']), 'sha256': x['sha256']} for x in inputs]
    links += [bind(build_path), bind(old_path), bind(new_path), bind(acceptance_path), bind(delta_path),
              bind(delta['old_parser_manifest']['path']), bind(delta['reviewer']['path']),
              bind(__file__), *native_inputs]
    for link in [*links,*private_evidence]:
        checked(link)
    return {'schema': 'reviewed-parser-delta-current-epoch-recheck-v2', 'passed': True,
            'acceptance': bind(acceptance_path), 'reviewed_delta': bind(delta_path),
            'before_counts': old_index['counts'], 'expected_counts': new_index['counts'],
            'parse_before_counts': before['coverage'], 'parse_after_counts': after['coverage'],
            'accepted_before_summary': accepted_summary(before), 'accepted_after_summary': accepted_summary(after),
            'changes': changes, 'inputs': links, 'native_crop_inputs':native_inputs,
            'retained_private_evidence':private_evidence,'source_writes': 0}

"""Build one external current uniform collection at the original model paths."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json

from accepted_inputs import load_accepted_inputs, _inside, _sha, _json

MANIFEST = 'Build manifest.json'


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def page_encoded(value):
    """Compact current page facts; avoid repeating indentation at every level."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def put(root, relative, raw):
    path = _inside(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
    return {'path': relative, 'sha256': _sha(raw), 'bytes': len(raw)}


def tool_bindings():
    root = Path(__file__).resolve().parent
    return [{'path': p.name, 'sha256': _sha(p.read_bytes())} for p in sorted(root.glob('*')) if p.is_file() and p.suffix in ('.py', '.json')]


def page_counts(data):
    result = Counter(pages=1, objects=len(data['objects']), nets=len(data['nets']), junctions=len(data['junctions']))
    result['terminals'] = sum(len(obj.get('terminals', [])) for obj in data['objects'])
    result['objects_with_explicit_geometry'] = sum(bool(obj.get('geometry')) for obj in data['objects'])
    result['nets_with_explicit_route_claims'] = sum(bool(net.get('routes')) for net in data['nets'])
    result['explicit_route_claims'] = sum(len(net.get('routes', [])) for net in data['nets'])
    result['explicit_junction_claims'] = sum(len(net.get('junctions', [])) for net in data['nets'])
    result['page_kind:' + data['page']['kind']] = 1
    return result


def projection(page):
    from pages import normalize_page, restore_page, SCHEMA
    raw = page['model']
    if raw.get('schema') == SCHEMA:
        raw = restore_page(raw)
    return normalize_page(raw, page['model_relative'], page['source_scan_id'], context=page['context'])['data']


def build(repo, output, expected_count=None, progress=None, resume=False):
    from pages import SCHEMA
    repo = Path(repo).resolve(strict=True); output = Path(output).resolve()
    if output == repo or output.is_relative_to(repo) or repo.is_relative_to(output):
        raise ValueError('Build into a separate candidate directory outside the repository')
    if output.exists() and not resume:
        raise ValueError('Candidate directory must be fresh')
    if resume and (not output.is_dir() or (output / MANIFEST).exists()):
        raise ValueError('Resume requires an incomplete candidate directory without a manifest')
    accepted = load_accepted_inputs(repo, expected_count)
    tools = tool_bindings(); counts = Counter()
    output.mkdir(parents=True, exist_ok=resume)
    manifest = {'schema': 'ibm360-ald-uniform-pages-build-v2', 'page_schema': SCHEMA,
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'candidate-awaiting-independent-validation',
                'policy': 'Current representation only. One model per original path; no histories, raw copies, mapping ledgers or per-page sidecars. Existing review status is retained, not reissued.',
                'input_bindings': accepted.globals_bindings, 'tools': tools, 'pages': [], 'counts': {}}
    for index, page in enumerate(accepted.pages):
        data = projection(page); raw = page_encoded(data)
        existing = _inside(output, page['model_relative'])
        if resume and existing.exists():
            if existing.read_bytes() != raw:
                raise ValueError('Incomplete candidate differs from fresh current projection: ' + page['model_relative'])
            record = {'path': page['model_relative'], 'sha256': _sha(raw), 'bytes': len(raw)}
        else:
            record = put(output, page['model_relative'], raw)
        manifest['pages'].append({'page_id': page['page_id'], 'scan_reference': page['scan_reference'],
                                  'source_model': page['context']['source_model'], 'text': page['context']['text'],
                                  'normalized': record, 'kind': data['page']['kind']})
        counts.update(page_counts(data))
        if progress and (index + 1) % 250 == 0:
            progress({'pages_built': index + 1, 'total': len(accepted.pages)})
    manifest['counts'] = dict(counts)
    manifest['unmodeled_accepted_texts'] = len(accepted.unmodeled_exports)
    manifest['source_recheck'] = accepted.recheck()
    current_files = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
    if current_files != {p['model_relative'] for p in accepted.pages}:
        raise ValueError('Incomplete candidate contains unlisted files')
    if tool_bindings() != tools:
        raise ValueError('Normalization tools changed during build')
    record = put(output, MANIFEST, encoded(manifest))
    return {'build_manifest': record, 'counts': dict(counts), 'source_recheck': manifest['source_recheck']}


def reencode_current(repo, output, expected_count=None, progress=None):
    """Re-encode a private candidate only after a complete fresh projection check.

    This repairs serialization ordering without changing any JSON values.
    It never writes into the repository and retains only one current manifest.
    """
    repo = Path(repo).resolve(strict=True); output = Path(output).resolve(strict=True)
    if output == repo or output.is_relative_to(repo) or repo.is_relative_to(output):
        raise ValueError('Candidate re-encoding must stay outside the repository')
    accepted = load_accepted_inputs(repo, expected_count); tools = tool_bindings()
    old_manifest = (output / MANIFEST).read_bytes(); manifest = _json(old_manifest, MANIFEST)
    if manifest.get('schema') != 'ibm360-ald-uniform-pages-build-v2' or manifest.get('input_bindings') != accepted.globals_bindings:
        raise ValueError('Candidate input bindings do not match current sources')
    if not isinstance(manifest.get('pages'), list) or len(manifest['pages']) != len(accepted.pages):
        raise ValueError('Candidate page membership differs')
    plans = []; counts = Counter()
    for index, (page, record) in enumerate(zip(accepted.pages, manifest['pages'])):
        relative = page['model_relative']; norm = record.get('normalized', {})
        if norm.get('path') != relative or record.get('source_model') != page['context']['source_model'] or record.get('text') != page['context']['text'] or record.get('scan_reference') != page['scan_reference'] or record.get('page_id') != page['page_id']:
            raise ValueError('Candidate source/model membership differs: ' + relative)
        actual = _inside(output, relative).read_bytes()
        if _sha(actual) != norm.get('sha256') or len(actual) != norm.get('bytes'):
            raise ValueError('Candidate file changed: ' + relative)
        parsed = _json(actual, relative); expected = projection(page)
        canonical = page_encoded(parsed)
        if canonical != page_encoded(expected) or record.get('kind') != expected['page']['kind']:
            raise ValueError('Candidate logical data differs from fresh projection: ' + relative)
        plans.append((relative, norm['sha256'], _sha(canonical), len(canonical)))
        counts.update(page_counts(expected))
        if progress and (index + 1) % 250 == 0:
            progress({'current_pages_replayed': index + 1, 'total': len(accepted.pages)})
    actual_files = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
    if actual_files != {r[0] for r in plans} | {MANIFEST} or dict(counts) != manifest.get('counts'):
        raise ValueError('Candidate membership or totals differ')
    accepted.recheck()
    if tool_bindings() != tools or (output / MANIFEST).read_bytes() != old_manifest:
        raise ValueError('Tools or candidate manifest changed during complete replay')
    for record, (relative, before, after, size) in zip(manifest['pages'], plans):
        path = _inside(output, relative); actual = path.read_bytes()
        if _sha(actual) != before:
            raise ValueError('Candidate changed before re-encoding: ' + relative)
        canonical = page_encoded(_json(actual, relative))
        if _sha(canonical) != after or len(canonical) != size:
            raise ValueError('Canonical encoding changed after replay: ' + relative)
        path.write_bytes(canonical)
        record['normalized'] = {'path': relative, 'sha256': after, 'bytes': size}
    manifest['tools'] = tools; manifest['source_recheck'] = accepted.recheck()
    if tool_bindings() != tools or (output / MANIFEST).read_bytes() != old_manifest:
        raise ValueError('Tools or candidate manifest changed before current manifest update')
    raw = encoded(manifest); (output / MANIFEST).write_bytes(raw)
    return {'build_manifest': {'path': MANIFEST, 'sha256': _sha(raw), 'bytes': len(raw)},
            'counts': dict(counts), 'source_recheck': manifest['source_recheck'], 'current_pages_replayed': len(plans),
            'logical_values_unchanged': True, 'repository_writes': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--expected-count', type=int)
    parser.add_argument('--resume-current', action='store_true', help='Replay every current source and compare existing incomplete outputs exactly; never overwrite')
    parser.add_argument('--reencode-current', action='store_true', help='Replay every current source before canonical key-order-only re-encoding of a private candidate')
    args = parser.parse_args()
    if args.reencode_current:
        if args.resume_current:
            parser.error('Choose either resume or re-encoding')
        print(json.dumps(reencode_current(args.repo, args.output_dir, args.expected_count, lambda v: print(json.dumps(v), flush=True)), ensure_ascii=False), flush=True)
        return
    print(json.dumps(build(args.repo, args.output_dir, args.expected_count, lambda v: print(json.dumps(v), flush=True), args.resume_current), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

"""Verify current bindings, exact candidate membership and mapper determinism.

This complements the independent literal/terminal semantic reviewer; it does
not turn mapper agreement into new electrical or visual acceptance.
"""
import argparse
from collections import Counter
from pathlib import Path
import json
from accepted_inputs import load_accepted_inputs, _inside, _json, _sha
from build_uniform_pages import MANIFEST, encoded, page_encoded, page_counts, tool_bindings, projection


def verify(repo, candidate, expected_count=None, progress=None):
    from pages import SCHEMA
    candidate = Path(candidate).resolve(strict=True)
    accepted = load_accepted_inputs(repo, expected_count)
    raw = (candidate / MANIFEST).read_bytes(); manifest = _json(raw, MANIFEST)
    if manifest.get('schema') != 'ibm360-ald-uniform-pages-build-v2' or manifest.get('page_schema') != SCHEMA:
        raise ValueError('Unsupported candidate manifest/schema')
    if manifest.get('input_bindings') != accepted.globals_bindings:
        raise ValueError('Current input bindings no longer match candidate')
    if manifest.get('tools') != tool_bindings():
        raise ValueError('Current normalization tools differ from build')
    pages = manifest.get('pages')
    if not isinstance(pages, list) or len(pages) != len(accepted.pages):
        raise ValueError('Candidate page membership differs')
    seen = set(); counts = Counter()
    for index, (page, record) in enumerate(zip(accepted.pages, pages)):
        expected = projection(page)
        norm = record.get('normalized', {}); relative = norm.get('path')
        if relative != page['model_relative'] or relative in seen:
            raise ValueError('Candidate model path/multiplicity differs')
        seen.add(relative); actual = _inside(candidate, relative).read_bytes()
        if _sha(actual) != norm.get('sha256') or len(actual) != norm.get('bytes') or actual != page_encoded(expected):
            raise ValueError('Candidate output/hash/current projection differs: ' + relative)
        if record.get('source_model') != page['context']['source_model'] or record.get('text') != page['context']['text'] or record.get('scan_reference') != page['scan_reference'] or record.get('page_id') != page['page_id'] or record.get('kind') != expected['page']['kind']:
            raise ValueError('Candidate source facts differ: ' + relative)
        counts.update(page_counts(expected))
        if progress and (index + 1) % 250 == 0:
            progress({'pages_verified': index + 1, 'total': len(accepted.pages)})
    actual_files = {p.relative_to(candidate).as_posix() for p in candidate.rglob('*') if p.is_file()}
    if actual_files != seen | {MANIFEST}:
        raise ValueError('Candidate contains missing or unlisted files')
    if dict(counts) != manifest.get('counts') or manifest.get('unmodeled_accepted_texts') != len(accepted.unmodeled_exports):
        raise ValueError('Candidate totals differ')
    guards = accepted.recheck()
    if (candidate / MANIFEST).read_bytes() != raw or manifest['tools'] != tool_bindings():
        raise ValueError('Manifest/tools changed during verification')
    return {'schema': 'ibm360-ald-uniform-build-verification-v1', 'passed': True,
            'scope': 'Exact current source bindings, output membership, hashes and deterministic page projection; semantic/source review is separate.',
            'build_manifest': {'path': MANIFEST, 'sha256': _sha(raw)}, 'counts': dict(counts), 'source_recheck': guards,
            'repository_writes': 0, 'history_replayed': False, 'scan_bytes_read': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path); parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--expected-count', type=int); parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = verify(args.repo, args.candidate, args.expected_count, lambda v: print(json.dumps(v), flush=True))
    if args.report:
        args.report.write_bytes(encoded(result))
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

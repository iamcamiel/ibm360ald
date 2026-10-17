"""Validate an ordered registry of exact, independently accepted source releases.

Registration and verification are separate from repository mirroring. Missing or
stale registered evidence raises; it must never revive historical acceptance.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

import source_review as sr
import current_checkpoint

SCHEMA = 'source-review-successor-registry-v1'


def inside(path, root):
    path = Path(path).resolve()
    sr.require(path.is_relative_to(Path(root).resolve()), 'Path outside declared root: ' + str(path))
    return path


def accepted_successors(registry_path, workspace, exports, source_root, *, document=None):
    """Return current exact-target exporter proofs, plus the complete evidence list.

    All registered immutable stages are replayed. Only the latest release for a
    target is compared to live artifacts, so successive reviewed fixes retain
    their earlier evidence without requiring obsolete live hashes to match.
    """
    registry_path = Path(registry_path).resolve()
    workspace, exports, source_root = map(lambda p: Path(p).resolve(), (workspace, exports, source_root))
    inside(registry_path, workspace)
    registry = sr.read_json(registry_path) if document is None else deepcopy(document)
    sr.require(registry.get('schema') == SCHEMA, 'Unsupported successor registry')
    releases = registry.get('releases')
    sr.require(isinstance(releases, list), 'Missing release inventory')
    latest, seen_releases, preserved = {}, set(), {registry_path} if document is None else set()
    for release in releases:
        release_id = release.get('release_id')
        sr.require(isinstance(release_id, str) and release_id and release_id not in seen_releases, 'Duplicate/missing release ID')
        seen_releases.add(release_id)
        pubpath, raw = sr.checked(release['publication'], registry_path.parent)
        inside(pubpath, workspace); pub = json.loads(raw.decode('utf-8-sig'))
        sr.require(pub.get('schema') == 'source-review-publication-v1' and pub.get('passed') is True,
                   'Release is not a successful generic publication')
        sr.require(pub.get('review_id') == release_id and pub.get('original_scan_writes') == 0, 'Publication identity/scope differs')
        manifest_path, manifest_raw = sr.checked(pub['manifest'], pubpath.parent)
        acceptance_path, _ = sr.checked(pub['independent_acceptance'], pubpath.parent)
        inside(manifest_path, workspace); inside(acceptance_path, workspace)
        manifest = json.loads(manifest_raw.decode('utf-8-sig'))
        sr.require(manifest.get('schema') == sr.STAGE, 'Registry requires declarative generic stages')
        sr.require(manifest.get('review_id') == release_id, 'Manifest review ID differs')
        sr.verify_stage(manifest_path, 'snapshots', acceptance_path)
        records = manifest['records']
        sr.require(pub.get('published_pages') == [r['page'] for r in records], 'Published page inventory differs')
        expected_pages = []
        preserved.update([pubpath, manifest_path, acceptance_path])
        for link in [*manifest.get('inputs', []), manifest['tool'], manifest['guard_tool'], manifest['intent_snapshot']]:
            path, _ = sr.checked(link, manifest_path.parent); inside(path, workspace); preserved.add(path)
        for record in records:
            source, _ = sr.checked(record['source'], manifest_path.parent); inside(source, source_root)
            current = {kind: {
                'path': str(inside(sr.resolve(record['prior_quartet'][kind]['path'], manifest_path.parent), exports)),
                'sha256': record['staged_quartet'][kind]['sha256']
            } for kind in sorted(sr.KINDS)}
            key = current['txt']['path']
            if key in latest:
                prior = latest[key]
                sr.require(prior['page'] == record['page'] and prior['source'] == record['source'], 'Successor changes page/source identity')
                for kind in sr.KINDS:
                    sr.require(record['prior_quartet'][kind]['sha256'] == prior['current_quartet'][kind]['sha256'],
                               'Broken predecessor quartet chain: ' + record['page'] + '/' + kind)
                    sr.require(sr.resolve(record['prior_quartet'][kind]['path'], manifest_path.parent) == Path(prior['current_quartet'][kind]['path']),
                               'Successor changes quartet target')
            for group in ['before_saved', 'staged_quartet']:
                for link in record[group].values():
                    path, _ = sr.checked(link, manifest_path.parent); inside(path, workspace); preserved.add(path)
            expected_pages.append({'page': record['page'], 'eligible': True,
                'artifact_schema': 'reviewed-current-quartet-v1', 'source': record['source'],
                'current_quartet': current,
                'checks': {'source_binding': True, 'exact_declarative_replay': True,
                           'independent_acceptance': True, 'current_quartet': True}})
            latest[key] = {'page': record['page'], 'release_id': release_id,
                'receipt': str(pubpath.relative_to(workspace)), 'hashes': [current['txt']['sha256']],
                'text_path': key, 'source_path': str(source), 'source': record['source'],
                'current_quartet': current, 'publication': sr.binding(pubpath),
                'manifest': sr.binding(manifest_path), 'independent_acceptance': sr.binding(acceptance_path)}
        sr.require(sr.json_equal(pub.get('pages'), expected_pages), 'Publication current-quartet claims differ from verified stage')
    for item in latest.values():
        for link in item['current_quartet'].values():
            sr.checked(link, workspace)
    return {'passed': True, 'registry': sr.binding(registry_path) if document is None else None,
            'release_count': len(releases), 'records': list(latest.values()),
            'preservation_files': [sr.binding(path) for path in sorted(preserved)]}


def register(registry_path, publication_path, workspace, exports, source_root):
    registry_path, publication_path = map(lambda p: Path(p).resolve(), (registry_path, publication_path))
    with sr.locked(registry_path.with_name(registry_path.name + '.lock')):
        original = registry_path.read_bytes() if registry_path.exists() else None
        doc = sr.read_json(registry_path) if original is not None else {'schema': SCHEMA, 'releases': []}
        pub = sr.read_json(publication_path)
        release = {'release_id': pub['review_id'], 'publication': sr.binding(publication_path)}
        previous = next((r for r in doc['releases'] if r['release_id'] == release['release_id']), None)
        if previous is not None:
            sr.require(sr.json_equal(previous, release), 'Existing release ID has different publication bytes')
        else:
            doc['releases'].append(release)
        result = accepted_successors(registry_path, workspace, exports, source_root, document=doc)
        if original is not None and previous is None:
            history = registry_path.parent / (registry_path.name + '.history') / (sr.digest(original) + '.json')
            if not history.exists(): sr.atomic_write(history, original)
            else: sr.require(history.read_bytes() == original, 'Registry history was altered')
        if previous is None: sr.atomic_write(registry_path, sr.encode(doc))
        return {**result, 'registry': sr.binding(registry_path),
                'preservation_files': [*result['preservation_files'], sr.binding(registry_path)],
                'idempotent_retry': previous is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['verify', 'register', 'verify-current'])
    parser.add_argument('registry', type=Path, nargs='?')
    parser.add_argument('--repo', type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--publication', type=Path)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--exports', type=Path)
    parser.add_argument('--source-root', type=Path)
    args = parser.parse_args()
    if args.command == 'verify-current':
        result=current_checkpoint.load_checkpoint(args.repo).report()
    elif args.command == 'register':
        sr.require(args.registry is not None and all((args.workspace,args.exports,args.source_root)), 'Legacy registry and its roots are required')
        sr.require(args.publication is not None, '--publication is required')
        result = register(args.registry, args.publication, args.workspace, args.exports, args.source_root)
    else:
        sr.require(args.registry is not None and all((args.workspace,args.exports,args.source_root)), 'Legacy registry and its roots are required')
        result = accepted_successors(args.registry, args.workspace, args.exports, args.source_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()

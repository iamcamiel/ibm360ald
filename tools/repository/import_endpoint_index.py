"""Import an independently audited endpoint index without refreshing diagram sources."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--resolutions', type=Path)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    repo, bundle = args.repo.resolve(), args.bundle.resolve()
    manifest_path = repo/'notes/Repository records manifest.json'
    manifest_raw = manifest_path.read_bytes()
    manifest = read(manifest_path)
    owned = {x['path']: x for x in manifest['files']}
    inventory = read(bundle/'Endpoint inventory.json')
    audit_path = bundle/'Independent endpoint coverage audit.json'
    audit = read(audit_path)
    assert audit['passed'] is True and not audit['failures'], 'Endpoint audit has not passed'
    fixtures = read(bundle/'Independent endpoint parser fixtures.json')
    assert fixtures['passed'] is True and not fixtures['failed_checks'], 'Parser fixtures have not passed'
    assert digest(Path(fixtures['builder']['path'])) == fixtures['builder']['sha256']
    native = read(bundle/'Independent native High proposal evidence.json')
    assert native['passed'] is True, 'Native proposal review has not passed'
    for proposal in native['proposals']:
        for source in proposal['source_bindings']:
            for kind in ['source', 'current_text', 'current_repository_model', 'current_canonical_model']:
                item = source.get(kind)
                if item:
                    assert digest(Path(item['path'])) == item['sha256'], ('Native proof changed', item['path'])
    for item in audit['inputs']:
        assert digest(Path(item['path'])) == item['sha256'], item['path']
    for item in inventory['inputs']:
        assert digest(Path(item['path'])) == item['sha256'], ('Index input changed', item['path'])
    pages = list(inventory['pages'].values()) if isinstance(inventory['pages'], dict) else inventory['pages']
    assert len(pages) == len({p['source_scan_id'] for p in pages}) == 2307
    if isinstance(inventory['pages'], dict):
        assert set(inventory['pages']) == {p['source_scan_id'] for p in pages}
    for page in pages:
        for kind in ['text', 'model']:
            item = page['binding'][kind]
            if item:
                path = Path(item['path'])
                path = path if path.is_absolute() else repo/path
                path = path.resolve()
                assert path.is_relative_to(repo)
                relative = path.relative_to(repo).as_posix()
                assert digest(path) == item['sha256'] == owned[relative]['sha256'], relative
    # Verify the complete previous snapshot before recording new derived files.
    for item in manifest['files']:
        path = (repo/item['path']).resolve()
        assert path.is_relative_to(repo) and digest(path) == item['sha256'], item['path']
    notes = Path('notes/A1 Socket Listing/Endpoint reference index')
    planned = {}

    def add(source, relative, role):
        relative = relative.as_posix()
        raw = source.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        target = repo/relative
        assert target.resolve().is_relative_to(repo)
        if target.exists():
            assert digest(target) in {sha, owned.get(relative, {}).get('sha256')}, ('Independent edit', relative)
        assert relative not in planned
        planned[relative] = {'path': relative, 'sha256': sha, 'role': role,
                             'source': str(source), '_raw': raw}

    add(bundle/'Endpoint inventory.json', Path('json/A1 Socket Listing/ALD endpoint reference index.json'),
        'Accepted-text physical endpoint index; normalized matching keys and literal provenance')
    add(bundle/'Endpoint inventory.csv', Path('csv/A1 Socket Listing/ALD endpoint reference index.csv'),
        'Physical endpoint index for tabular inspection')
    add(bundle/'build_endpoint_reference_index.py', Path('tools/references/build_endpoint_reference_index.py'),
        'Reusable endpoint extraction and reciprocal matching tool')
    for path in sorted(bundle.rglob('*')):
        if path.is_file() and path.suffix in {'.json', '.png', '.py', '.txt'} and path.name not in {
                'Endpoint inventory.json', 'build_endpoint_reference_index.py'}:
            add(path, notes/path.relative_to(bundle), 'Endpoint matching evidence, human normalization authority or independent review')
    # These two input manifests change as derived records/resolutions are added.
    # Preserve their exact prior bytes for historic audit reproduction.
    prior_overlay = repo/'notes/Manual verification/Pending inventory after V4.json'
    assert (bundle/'Initial input snapshots/Repository records manifest.json').read_bytes() == manifest_raw
    assert (bundle/'Initial input snapshots/Pending inventory before endpoint index.json').read_bytes() == prior_overlay.read_bytes()
    if args.resolutions:
        next_overlay = read(args.resolutions)
        prior = read(prior_overlay)
        assert next_overlay['issued_manifest_sha256'] == prior['issued_manifest_sha256']
        previous = {x['id']: x for x in prior['source_derived_resolutions']}
        current = {x['id']: x for x in next_overlay['source_derived_resolutions']}
        assert len(current) == len(next_overlay['source_derived_resolutions'])
        assert all(current[k] == v for k, v in previous.items()), 'Existing answers changed'
        high = {x['id']: x for x in read(bundle/'A1 endpoint matching results.json')['results']
                if x['confidence'] == 'High'}
        for key in current.keys()-previous.keys():
            assert key in high and current[key]['recovered_reading'] == high[key]['candidate']
        add(args.resolutions, Path('notes/Manual verification/Pending inventory after V4.json'),
            'Question closures queued after issued V4; human answers and issued workbook preserved')
    receipt = {'created_utc': datetime.now(timezone.utc).isoformat(),
               'scope': 'Derived endpoint library and queued questions only; diagram TXT/models unchanged',
               'input_records_manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
               'independent_audit_sha256': digest(audit_path),
               'audited_inventory_delivery': {'original_path': str(bundle/'Endpoint inventory.json'),
                   'repository_path': 'json/A1 Socket Listing/ALD endpoint reference index.json',
                   'sha256': digest(bundle/'Endpoint inventory.json'),
                   'note': 'Resolve historic matching-result inventory paths through this exact-byte delivery mapping.'},
               'files': [{k: v for k, v in x.items() if k != '_raw'} for x in planned.values()]}
    if args.write:
        assert manifest_path.read_bytes() == manifest_raw, 'Ownership manifest changed before import'
        for relative, item in planned.items():
            target = repo/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item['_raw'])
            owned[relative] = {k: v for k, v in item.items() if k != '_raw'}
        receipt_path = repo/notes/'Root endpoint import receipt.json'
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        relative = receipt_path.relative_to(repo).as_posix()
        owned[relative] = {'path': relative, 'sha256': digest(receipt_path), 'role': 'Guarded endpoint library import receipt'}
        # Include this importer itself in the integrity inventory.
        tool = Path(__file__).resolve()
        if tool.is_relative_to(repo):
            relative = tool.relative_to(repo).as_posix()
            owned[relative] = {'path': relative, 'sha256': digest(tool), 'role': 'Guarded derived endpoint library importer'}
        manifest['updated_utc'] = receipt['created_utc']
        manifest['files'] = list(owned.values())
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'write': args.write, 'planned_files': len(planned), 'accepted_pages': len(inventory['pages']),
                      'literal_endpoints': len(inventory['endpoints'])}))


if __name__ == '__main__':
    main()

"""Copy current machine-readable content for the reviewed text snapshot."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    repo, workspace = args.repo.resolve(), args.workspace.resolve()
    audit = workspace/'tmp/ald-text/ald/repository-export'
    export = read(workspace/'tmp/ald-text/ald/repository-export/last export manifest.json')
    assert not export.get('export_in_progress')
    planned = {}
    missing_models = []
    migrated_CAS_pages = []
    kt_receipts = {}
    for receipt_name in ['kt/recoveries-v2/Frozen recovery acceptance receipts.json',
                         'kt/recoveries-v3/Frozen V3 recovery acceptance receipts.json']:
        kt_receipt_path = workspace/'tmp/ald-text'/receipt_name
        if kt_receipt_path.is_file():
            kt_batch = read(kt_receipt_path)
            if kt_batch.get('passed') is True and kt_batch.get('published') is True:
                kt_receipts.update({r['page']: r for r in kt_batch.get('acceptance_receipts', [])
                                    if r.get('passed') is True})

    def add(source, destination, role):
        raw = source.read_bytes()
        raw.decode('utf-8-sig')
        relative = destination.relative_to(repo).as_posix()
        record = {'path': relative, 'source': str(source), 'sha256': sha(raw),
                  'role': role, '_raw': raw}
        if relative in planned:
            assert planned[relative]['sha256'] == record['sha256'], relative
        planned[relative] = record

    content_keys = {'nodes', 'boxes', 'nets', 'wire_paths', 'wire_shapes', 'annotations',
                    'sections', 'records', 'cards', 'connectors', 'cells'}
    for entry in export['exported']:
        text = Path(entry['transcription_source'])
        published = Path(entry['destination'])
        assert sha(published.read_bytes()) == entry['text_sha256']
        assert sha(text.read_bytes()) == entry['text_sha256'], ('Working TXT changed; refresh accepted export before content import', entry['page'])
        key = text.name.split(' ', 1)[0]
        folder = Path(entry['source_relative']).parent
        candidates = [text.with_suffix('.json'),
                      text.with_name(text.stem+' verification.json'),
                      text.with_name(key+' verification.json')]
        found = None
        for candidate in candidates:
            if candidate.is_file():
                data = read(candidate)
                if isinstance(data, dict) and set(data) & content_keys:
                    found = candidate
                    break
        if found:
            add(found, repo/'json'/folder/(text.stem+'.json'), 'Published page content model')
        else:
            missing_models.append({'page': key, 'text_file': published.relative_to(repo).as_posix(),
                                   'reason': 'No separate published content model found'})
        # KT's independently accepted recovery sets also bind their literal
        # source-facts companion. Preserve those machine-readable fields beside
        # the current page model, with the exact frozen text/source association.
        kt = kt_receipts.get(key)
        if kt and kt.get('accepted_hashes', {}).get('text_sha256') == entry['text_sha256']:
            fact = next((a for a in kt.get('artifacts', [])
                         if a.get('name') == key+' source facts.json'), None)
            if fact:
                fact_path = Path(fact['accepted_path'])
                source_path = Path(kt['source_tiff'])
                assert sha(source_path.read_bytes()) == kt['source_sha256']
                assert sha(fact_path.read_bytes()) == fact['sha256'] == kt['accepted_hashes']['facts_sha256']
                add(fact_path, repo/'json'/folder/fact['name'], 'Accepted literal page source facts')
        # Reviewed CAS specifications retain fields and explicit current layout
        # that supplement the published QZ/diagram verification records.
        if key == 'AA001' or (key.startswith('Q') and not key.startswith('QZ')):
            spec = workspace/'tmp/ald-text/cas'/(key+' reviewed.json')
            if spec.is_file():
                add(spec, repo/'json'/folder/(text.stem+' source layout.json'),
                    'Reviewed CAS control fields and source layout; explicit current grid where migrated')
                acceptance=read(spec).get('root_grid_migration_review', {})
                if acceptance.get('accepted') is True and acceptance.get('text_sha256')==entry['text_sha256']:
                    migrated_CAS_pages.append(key)

    exports = workspace/'ALD_Visual_Transcriptions'
    aggregates = [
        ('A1 Socket Listing/Socket reference.json', 'json/A1 Socket Listing/Socket reference.json'),
        ('A1 Socket Listing/ALD references.json', 'json/A1 Socket Listing/ALD references.json'),
        ('QZ ROS Listing/ROS words.json', 'json/QZ ROS Listing/ROS words.json'),
        ('QZ ROS Listing/ROS words.csv', 'csv/QZ ROS Listing/ROS words.csv'),
    ]
    for source, destination in aggregates:
        path = exports/source
        if path.is_file():
            add(path, repo/destination, 'Reviewed collection content table')
    # Structured storage maps are useful independently of their printed layout.
    accepted = {Path(entry['source_relative']).name.split(' ', 1)[0]: entry for entry in export['exported']}
    for source in (workspace/'tmp/ald-text/a6').glob('* storage records.json'):
        entry = accepted.get(source.name.split(' ', 1)[0])
        if entry:
            add(source, repo/'json'/Path(entry['source_relative']).parent/source.name,
                'Reviewed storage assignment data')

    manifest_path = repo/'notes/Content data manifest.json'
    prior = read(manifest_path) if manifest_path.exists() else {}
    owned = dict(prior.get('managed_files', {}))
    owned.update({entry['path']: entry['sha256'] for entry in prior.get('files', [])})
    for relative, entry in planned.items():
        path = repo/relative
        assert not path.exists() or sha(path.read_bytes()) in {entry['sha256'], owned.get(relative)}, relative
    retired = []
    archive = audit/'held accepted snapshots'/('content-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    for entry in prior.get('files', []):
        relative = entry['path']; path = (repo/relative).resolve()
        if relative in planned or entry.get('role') not in {'Published page content model', 'Accepted literal page source facts'} or not path.exists():
            continue
        assert path.is_relative_to(repo/'json') and sha(path.read_bytes()) == owned.get(relative), relative
        destination = (archive/relative).resolve()
        assert destination.is_relative_to(audit.resolve()) and not destination.exists()
        retired.append({'old_path': str(path), 'preserved_path': str(destination),
                        'sha256': sha(path.read_bytes()),
                        'reason': 'Page absent from current accepted TXT snapshot; prior owned content model preserved'})
    report = {'updated_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Machine-readable content matching the existing reviewed text snapshot',
              'original_model_bytes_preserved': True,
              'CAS_grid_migration': {'accepted_current_grid_pages': sorted(migrated_CAS_pages),
                                     'scope': 'Remaining source layouts retain their earlier reviewed form until grid migration is accepted.'},
              'managed_files': {**owned, **{k:entry['sha256'] for k,entry in planned.items()}},
              'retired_page_models': prior.get('retired_page_models', []) + retired,
              'files': [{key: value for key, value in entry.items() if key != '_raw'}
                        for entry in planned.values()],
              'pages_without_separate_published_models': missing_models}
    if args.write:
        folders = [path.relative_to(repo/'ALD') for path in (repo/'ALD').rglob('*') if path.is_dir()]
        for branch in ['json', 'csv']:
            for folder in folders:
                (repo/branch/folder).mkdir(parents=True, exist_ok=True)
        for relative, entry in planned.items():
            path = repo/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or sha(path.read_bytes()) != entry['sha256']:
                path.write_bytes(entry['_raw'])
        for entry in retired:
            path, destination = Path(entry['old_path']), Path(entry['preserved_path'])
            assert sha(path.read_bytes()) == entry['sha256']
            destination.parent.mkdir(parents=True, exist_ok=True)
            path.rename(destination)
            assert sha(destination.read_bytes()) == entry['sha256']
        for branch in ['json', 'csv']:
            for folder in (repo/branch).rglob('*'):
                if folder.is_dir() and not any(folder.iterdir()):
                    (folder/'.gitkeep').write_bytes(b'')
        manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'content_files': len(planned),
                      'JSON_files': sum(entry['path'].endswith('.json') for entry in planned.values()),
                      'CSV_files': sum(entry['path'].endswith('.csv') for entry in planned.values()),
                      'pages_without_separate_models': len(missing_models), 'write': args.write}))


if __name__ == '__main__':
    main()

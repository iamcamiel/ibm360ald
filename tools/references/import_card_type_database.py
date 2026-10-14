"""Import an independently reviewed card database against its accepted inputs."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import argparse
import hashlib
import json


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def bound(value):
    path = Path(value.get('path', value.get('file', ''))).resolve()
    assert path.is_file() and digest(path) == value['sha256'], str(path)
    return path


def allowed(relative):
    parts = PurePosixPath(relative).parts
    return ('..' not in parts and not PurePosixPath(relative).is_absolute()
            and (parts[:2] in [('json', 'Card types'), ('csv', 'Card types'),
                               ('notes', 'Card types')]
                 or relative == 'tools/references/build_card_type_database.py'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--independent-audit', required=True, type=Path)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    repo, source_root = args.repo.resolve(), args.source_root.resolve()
    assert source_root != repo and not source_root.is_relative_to(repo)
    manifest_path = source_root/'notes/Card types/Build manifest.json'
    audit_path = args.independent_audit.resolve()
    audit, manifest = read(audit_path), read(manifest_path)
    assert audit.get('passed') is True and not audit.get('failures')
    assert bound(audit['build_manifest']) == manifest_path.resolve()
    for item in manifest['input_manifests']:
        relative = PurePosixPath(item['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        path = (repo/relative).resolve()
        assert path.is_relative_to(repo) and digest(path) == item['sha256'], str(path)

    receipt_path = repo/'notes/Card types/Database import receipt.json'
    previous = read(receipt_path) if receipt_path.is_file() else {'files': []}
    prior = {item['path']: item['sha256'] for item in previous['files']}
    planned = {}
    for item in manifest['outputs']:
        relative = item['path']
        assert allowed(relative), relative
        source = (source_root/relative).resolve()
        assert source.is_relative_to(source_root) and source.is_file()
        assert digest(source) == item['sha256'], str(source)
        assert relative not in planned, relative
        planned[relative] = {'path': relative, 'sha256': item['sha256'], 'source': str(source)}
    for source, relative in [(manifest_path, 'notes/Card types/Build manifest.json'),
                             (audit_path, 'notes/Card types/Independent database audit.json')]:
        planned[relative] = {'path': relative, 'sha256': digest(source), 'source': str(source)}

    # Check every destination before changing any. Independently edited files
    # are never replaced by a new derived database.
    for relative, item in planned.items():
        destination = (repo/relative).resolve()
        assert destination.is_relative_to(repo), relative
        if destination.exists():
            current = digest(destination)
            assert current == item['sha256'] or current == prior.get(relative), relative
    retired = sorted(set(prior)-set(planned))
    for relative in retired:
        assert allowed(relative), relative
        destination = (repo/relative).resolve()
        assert destination.is_relative_to(repo)
        if destination.exists():
            assert digest(destination) == prior[relative], relative

    result = {'passed': True, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'build_manifest_sha256': digest(manifest_path),
              'independent_audit_sha256': digest(audit_path),
              'input_manifests': manifest['input_manifests'],
              'files': list(planned.values()), 'retired_paths': retired,
              'written': args.write}
    if args.write:
        archive = repo/'notes/Card types/Retired database outputs'/result['created_utc'].replace(':', '-')
        for relative in retired:
            destination = repo/relative
            if destination.exists():
                saved = archive/relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(destination.read_bytes())
                destination.unlink()
        for relative, item in planned.items():
            destination = repo/relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.is_file() or digest(destination) != item['sha256']:
                destination.write_bytes(Path(item['source']).read_bytes())
        assert all(digest(repo/item['path']) == item['sha256'] for item in result['files'])
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'files': len(planned), 'retired': len(retired), 'written': args.write}))


if __name__ == '__main__':
    main()

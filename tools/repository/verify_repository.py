"""Check preserved UTF-8 files and snapshot hashes, without changing files."""
from pathlib import Path
import argparse
import hashlib
import json
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path,
                        default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    repo = args.repo.resolve()
    manifest = json.loads((repo/'notes/Repository records manifest.json').read_text(encoding='utf-8'))
    failures = []
    for entry in manifest['files']:
        path = (repo/entry['path']).resolve()
        if not path.is_relative_to(repo) or not path.is_file():
            failures.append({'path': entry['path'], 'problem': 'Missing file or path outside repository'})
            continue
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            failures.append({'path': entry['path'], 'problem': 'Changed since recorded snapshot'})
        if path.suffix.lower() in {'.txt', '.csv', '.json', '.py'}:
            try:
                raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                failures.append({'path': entry['path'], 'problem': 'Invalid UTF-8'})
    result = {'checked_files': len(manifest['files']), 'failures': failures,
              'passed': not failures,
              'scope': 'Encoding and snapshot integrity; native scan, wiring and semantic review are separate'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())

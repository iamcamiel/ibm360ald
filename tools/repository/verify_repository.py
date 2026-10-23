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
    if (repo/'notes/Source status.json').is_file():
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reviews'))
        import current_checkpoint
        try:
            result['current_source_status']=current_checkpoint.load_checkpoint(repo,inventory=manifest).report()
        except (ValueError,OSError,UnicodeError) as exc:
            failures.append({'path':'notes/Source status.json','problem':str(exc)})
        sys.path[:0]=[str(repo/'tools/normalization'),str(repo/'tools/page_text')]
        from check_format import check_file, loads
        schema=loads((repo/'tools/normalization/ALD page schema.json').read_bytes())
        for record in json.loads((repo/'notes/Source status.json').read_bytes())['records']:
            if 'json' not in record['repository']:continue
            rel=record['repository']['json']['path']
            try:check_file(repo/rel,schema)
            except (ValueError,OSError,KeyError,TypeError) as exc:failures.append({'path':rel,'problem':str(exc)})
        result['passed']=not failures
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())

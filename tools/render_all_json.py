#!/usr/bin/env python3
"""Regenerate current JSON-owned diagram TXT files (V4 and typed/legacy layouts).

Defaults to the repository json/ and ALD/ trees. Archives and review sidecars
are excluded. Unchanged files are not rewritten. --check reports changes only.
"""
import argparse
import json
from pathlib import Path
import sys

from page_maintenance import (apply_changes, encode, models, review, safe,
                              strict_json, writer_lock)
from build_progress import Progress


def render(document, details=None):
    if '$schema' in document:
        from ald_render import render_page
        options = (details or {}).get('writer options', {})
        ending = options.get('line ending', 'LF')
        trim = options.get('trim trailing spaces', False)
        if ending not in ('LF', 'CRLF') or type(trim) is not bool:
            raise ValueError('Invalid V4 writer options')
        return render_page(document, details, trim, '\r\n' if ending == 'CRLF' else '\n')
    # Established V3/legacy JSON-owned character projection; no V4 conversion.
    tools = Path(__file__).resolve().parent
    for folder in ('normalization', 'page_text'):
        path = str(tools / folder)
        if path not in sys.path:
            sys.path.insert(0, path)
    import layout
    return layout.render(document)


def run(root, check=False, backup_root=None):
    root = Path(root).resolve(strict=True)
    with writer_lock(root):
        status = strict_json((root / 'notes/Source status.json').read_bytes())
        pairs = {r['repository']['json']['path']: r['repository']['txt']['path'] for r in status['records']}
        changes, pages, failures, counts = [], [], [], {'v4': 0, 'layout': 0}
        # Keep only paths, not thousands of parsed models, while counting the
        # actual renderable pages (card definitions are not diagram layouts).
        paths = [(path, kind) for path, _, _, kind in models(root)]
        with Progress(f'Generating {len(paths)} UTF-8 pages') as progress:
            for completed, (path, kind) in enumerate(paths, 1):
                before = path.read_bytes()
                document = strict_json(before)
                counts[kind] += 1
                try:
                    _, _, details = review(root, path, document) if kind == 'v4' else (None, None, None)
                    text = render(document, details)
                    relative = pairs.get(path.relative_to(root).as_posix())
                    target = safe(root, root / relative if relative else root / 'ALD' / path.relative_to(root / 'json').with_suffix('.txt'))
                    old = target.read_bytes()
                    if path.read_bytes() != before:
                        raise ValueError('Model changed while rendering')
                    if text != old:
                        changes.append((target, old, text))
                        pages.append({'model': str(path), 'text': str(target)})
                except (OSError, ValueError, KeyError, TypeError, IndexError, AssertionError) as error:
                    failures.append({'path': str(path), 'error': str(error)})
                progress.update(completed, len(paths))
            # Retain the batch's existing failure report; don't announce success.
            progress.failed = bool(failures)
        report = {'rendered': counts, 'textFilesChanged': len(changes), 'pages': pages,
                  'failures': failures, 'applied': not check}
        # A rendering failure leaves the complete batch untouched.
        if failures or check:
            return report
        return apply_changes(root, changes, 'render-json', report, backup_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--backup-root', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = run(args.source_root, args.check, args.backup_root)
    if args.report:
        args.report.write_bytes(encode(result))
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result['failures'] or (args.check and result['textFilesChanged']) else 0


if __name__ == '__main__':
    raise SystemExit(main())

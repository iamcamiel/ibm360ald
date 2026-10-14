"""Publish only hash-bound CAS grid candidates explicitly accepted by root.

This tool does not perform source review or infer acceptance. Its input receipt
must list accepted pages, artifact hashes and the independent review scope.
Original scans are read and hashed, never modified. Old working artifacts are
saved before replacement. Repository mirrors are refreshed separately.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--acceptance', required=True, type=Path)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    receipt = read(args.acceptance)
    assert receipt['reviewer'] == 'root'
    selected = [p for p in receipt['pages'] if p.get('accepted') is True]
    plans = []
    for page in selected:
        assert page['mechanical_pass'] is True and page['source_review_scope']
        staged = Path(page['text'])
        old = Path(page['original_text'])
        content, verification = Path(page['content']), Path(page['verification'])
        for path in [staged, old, content, verification]:
            assert path.resolve().is_relative_to(workspace), str(path)
        assert sha(staged) == page['text_sha256'], ('staged text changed', staged)
        assert sha(content) == page['content_sha256'], ('staged model changed', content)
        assert sha(verification) == page['verification_sha256'], ('staged review changed', verification)
        assert sha(old) == page['old_sha256'], ('working text changed', old)
        assert sha(Path(page['source'])) == page['source_sha256'], ('source changed', page['source'])
        lines = staged.read_text(encoding='utf-8').splitlines()
        assert len(lines) == 102 and all(len(line) == 245 for line in lines)
        vp = old.parent / (page['page']+' verification.json')
        cp = workspace/'tmp/ald-text/cas'/(page['page']+' reviewed.json')
        note = old.with_name(old.stem+' review notes.txt')
        plans.append((page, staged, old, content, verification, vp, cp, note))
    if args.write:
        # Validate every page before beginning the batch. Each saved before-file
        # is immutable, so rerunning cannot disguise an intervening edit.
        for page, staged, old, content, verification, vp, cp, note in plans:
            folder = Path(page.get('backup_directory', str(staged.parent))).resolve()
            assert folder.is_relative_to(workspace), str(folder)
            folder.mkdir(parents=True, exist_ok=True)
            for path, name in [(old, 'before.txt'), (vp, 'before verification.json'),
                               (cp, 'before content.json'), (note, 'before notes.txt')]:
                backup = folder/name
                if path.exists():
                    if backup.exists():
                        assert sha(backup) == sha(path), ('backup does not match current input', path)
                    else:
                        backup.write_bytes(path.read_bytes())
            model, review = read(content), read(verification)
            acceptance = {k: v for k, v in page.items()
                          if k not in ['content', 'verification', 'text', 'original_text']}
            review['status'] = 'Visually reviewed reconstruction; printer grid migration reviewed'
            review['root_grid_migration_review'] = acceptance
            review['root_independent_acceptance'] = True
            review['staged_complete'] = True
            review.setdefault('grid_migration', {})['status'] = 'Root accepted layout migration'
            model['status'] = review['status']
            model['root_grid_migration_review'] = acceptance
            cp.parent.mkdir(parents=True, exist_ok=True)
            old.write_bytes(staged.read_bytes())
            vp.write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            cp.write_text(json.dumps(model, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            previous = note.read_text(encoding='utf-8-sig').rstrip() if note.exists() else ''
            addition = '\n'.join([
                'CAS PRINTER GRID MIGRATION',
                '245 columns by102 lines; zero-based box positions and title separators checked.',
                'Printed fields, headers, selectors, QZ comparisons and any source-supported corrections are documented in the acceptance receipt.',
                'Review scope: '+page['source_review_scope'],
                'Current text SHA256: '+page['text_sha256'],
                'Previous text SHA256: '+page['old_sha256'],
                'Root acceptance receipt: '+str(args.acceptance),
                *page.get('retained_notes', []),
            ])
            note.write_text((previous+'\n\n' if previous else '')+addition+'\n', encoding='utf-8')
    print(json.dumps({'accepted_pages': len(plans), 'written': args.write,
                      'pages': [p[0]['page'] for p in plans]}, indent=2))


if __name__ == '__main__':
    main()

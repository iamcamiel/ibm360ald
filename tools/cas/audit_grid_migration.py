"""Plan CAS grid changes from existing reviewed text; do not rewrite diagrams.

The audit distinguishes current text geometry from genuine source exceptions.
Native route/field review remains necessary before accepting a reflowed page.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import argparse
import json
import re

HEADER = re.compile(r'([01X✲]{2,6}) +─+ +([0-9A-FX]{3,4})')
LABEL = re.compile(r'(?<![A-Z0-9])([A-Z][1-9])─{1,3}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    repo = args.repo.resolve()
    pages = []
    for path in sorted((repo/'ALD').rglob('*.txt')):
        page = path.name.split(' ', 1)[0]
        if not (page=='AA001' or re.fullmatch(r'Q[B-Y]\d{3}', page)):
            continue
        lines = path.read_text(encoding='utf-8-sig').splitlines()
        labels = []
        for row, line in enumerate(lines):
            for match in LABEL.finditer(line):
                if match.start() in {31+22*i for i in range(9)}:
                    labels.append({'box': match[1], 'column': match.start(), 'row': row})
        headers = []
        for row, line in enumerate(lines):
            for match in HEADER.finditer(line):
                left = match.end()-15
                if left not in {31+22*i for i in range(9)}:
                    continue
                choices = [label for label in labels if label['column']==left
                           and row+1 <= label['row'] <= row+15]
                label = min(choices, key=lambda value: value['row']) if choices else None
                headers.append({'branch': match[1], 'printed_address': match[2],
                                'old_left': left, 'old_top': row,
                                'box': label['box'] if label else None,
                                'old_height': label['row']-row+1 if label else None})
        phase = Counter(header['old_top'] % 11 for header in headers).most_common(1)
        phase = phase[0][0] if phase else None
        for header in headers:
            # AA001's earlier manual return separation inserted one extra row
            # after its first A box. That area needs explicit route review.
            origin = 5 if page=='AA001' and header['old_top']==5 else phase
            header['proposed_left'] = header['old_left']-6
            header['proposed_top'] = header['old_top']-origin if origin is not None else None
        footer = [row for row, line in enumerate(lines) if 'MACH' in line and 'DATE' in line]
        issues = []
        if any(header['old_height'] not in {None, 8} for header in headers):
            issues.append('Existing text has non-eight-line boxes; inspect source before changing their bodies')
        if page=='AA001':
            issues.append('Explicitly retain separate FAA/FBD returns while correcting the extra old row')
        if not footer:
            issues.append('No combined MACH/DATE footer line recognized; footer needs separate extraction')
        if len(footer)>1:
            issues.append('Multiple possible footer rows; inspect source')
        target_tops = {header['proposed_top'] for header in headers}
        if 88 in target_tops:
            issues.append('Source has S row; ninth row position awaiting user decision')
        if any(top is not None and top not in {11*i for i in range(9)} for top in target_tops):
            issues.append('Nonstandard proposed header top; inspect source')
        pages.append({'page': page, 'text_file': path.relative_to(repo).as_posix(),
                      'current_rows': len(lines), 'current_maximum_columns': max(map(len, lines), default=0),
                      'current_header_phase': phase, 'recognized_boxes': len(headers),
                      'headers': headers, 'old_footer_rows': footer,
                      'proposed_footer_top': 97, 'issues': issues})
    report = {'updated_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'AA001 and Q* except QZ; existing reviewed transcriptions',
              'target': {'columns': 245, 'rows': 102},
              'page_count': len(pages), 'pages': pages,
              'notes': ['This is a migration plan, not source acceptance or a diagram rewrite.',
                        'Do not crop nonblank cells or force extended source boxes to eight rows.',
                        'Entry wire position and S row exception remain user clarification items.']}
    if args.write:
        (repo/'notes/CAS grid migration audit.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'pages': len(pages),
                      'recognized_boxes': sum(page['recognized_boxes'] for page in pages),
                      'pages_with_geometry_issues': sum(bool(page['issues']) for page in pages),
                      'diagrams_changed': False}))


if __name__=='__main__':
    main()

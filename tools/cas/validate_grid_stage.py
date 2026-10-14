"""Independently check private CAS grid candidates; never publish them.

Usage: python validate_grid_stage.py --workspace D:/Github/IBM360 --report PATH
The report distinguishes mechanical checks from source review. Wiring equality
is a regression diagnostic, not proof that either drawing matches its scan.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import string

from cas_characters import printed_text
from wire_graph import page_reachability

ROWS = {label: index * 11 for index, label in enumerate('ACEGJLNQS')}
ROWS['F'] = 22
ALLOWED = set(string.ascii_uppercase + string.digits + ' .,+-/=():?<>')
ALLOWED.update('─│┌┐└┘┼✲→◺∀Ω≠¬�')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first_existing(*paths):
    return next((path for path in paths if path.exists()), None)


def label_offset(node, spec):
    if 'label_row' in node:
        return node['label_row']
    # A larger gap between banks does not make individual boxes taller.
    minimum = 7
    return max(minimum, len(node['fields']) + 1 + int(
        node.get('R_line') is not None or bool(node.get('selector'))))


def check(folder, workspace):
    page = folder.name
    canonical = workspace / 'ALD_Visual_Transcriptions/CAS Diagrams'
    content = first_existing(folder / f'{page} content.json', folder / 'content.json')
    verification = first_existing(folder / f'{page} verification.json', folder / 'verification.json')
    txt = next(path for path in folder.glob(f'{page} *.txt')
               if 'notes' not in path.name.lower())
    oldtxt = first_existing(folder / 'before.txt', canonical / txt.name)
    new = read(content)
    report = read(verification)
    oldverification = read(first_existing(folder / 'before verification.json', canonical / f'{page} verification.json'))
    oldcontent = first_existing(folder / 'before content.json',
                                workspace / 'tmp/ald-text/cas' / f'{page} reviewed.json')
    old = read(oldcontent) if oldcontent else copy.deepcopy(new)
    oldrecords = {n.get('CAS_box', n.get('box')): n for n in oldverification.get('nodes', [])}
    oldnodes = {n['box']: n for n in old['nodes']}
    newnodes = {n['box']: n for n in new['nodes']}
    lines = txt.read_text(encoding='utf-8').splitlines()
    before = oldtxt.read_text(encoding='utf-8').splitlines()
    errors, differences, source_discrepancies = [], [], []
    if len(lines) != 102 or any(len(line) != 245 for line in lines):
        errors.append('Page is not exactly 102 rows of 245 characters')
    bad = sorted(set(''.join(lines)) - ALLOWED)
    if bad:
        errors.append({'unapproved_characters': bad})
    if len(lines) != 102 or any(len(line) != 245 for line in lines):
        return dict(page=page, errors=errors, mechanical_pass=False)
    if ''.join(lines[94+k][1] for k in range(5)) != page:
        errors.append('Vertical page reference is not at column1 rows94..98')
    # Real entry lists/legends may occupy this margin. Detect a repeated vertical
    # ID rather than incorrectly prohibiting all other print there.
    duplicate_ids = [(c, r) for c in range(11) for r in range(90, 98)
                     if (c, r) != (1, 94)
                     and ''.join(lines[r+k][c] for k in range(5)) == page]
    if duplicate_ids:
        errors.append({'duplicate_vertical_page_reference': duplicate_ids})
    missing_separators = [(c, r) for r in range(97, 102)
                          for c in [150, 173, 195, 237] if lines[r][c] != '│']
    if missing_separators:
        errors.append({'title_separator_errors': missing_separators})
    for node in new['nodes']:
        box = node['box']
        expected = [25 + 22 * (int(box[1:])-1), ROWS.get(box[0], -999)]
        if node.get('grid') != expected:
            errors.append({'box': box, 'incorrect_grid': node.get('grid'), 'expected': expected})
        oldnode = oldnodes.get(box)
        if oldnode is None:
            matches = [n for n in old['nodes'] if n['address'] == node['address']]
            if len(matches) != 1:
                errors.append({'box': box, 'unmatched_original_node': True})
                continue
            oldnode = matches[0]
            errors.append({'box_identifier_changed': [oldnode['box'], box], 'address': node['address']})
        oldgrid = node.get('previous_grid') or oldnode.get('grid') or oldrecords.get(oldnode['box'], {}).get('grid')
        if page == 'AA001':
            oldgrid = [expected[0]+6, expected[1]+5+int(expected[1] >= 11)]
        if not oldgrid:
            errors.append({'box': box, 'missing_old_position': True})
            continue
        oldnode['grid'] = oldgrid
        nc, nr = node['grid']
        oc, oldrow = oldgrid
        newlabel, oldlabel = label_offset(node, new), label_offset(oldnode, old)
        if newlabel < 7 or nr+newlabel >= 97:
            errors.append({'box': box, 'invalid_height': newlabel+1})
        if node['address'] != oldnode['address']:
            errors.append({'box': box, 'address_changed': [oldnode['address'], node['address']]})
        header = lines[nr][nc:nc+20]
        # Many native headers omit the leading zero. Preserve that typography.
        address_present = any(token.lstrip('0') == node['address'].lstrip('0')
                              for token in re.findall(r'(?<![A-Z0-9])[0-9A-F]{3,4}(?![A-Z0-9])', header))
        if not address_present and node['address'] != 'XXX':
            discrepancy = {'box': box, 'model_address': node['address'], 'printed_header': header}
            if before[oldrow][oc:oc+15] == lines[nr][nc:nc+15]:
                # Keep an inherited unreadable/different source header visible;
                # this layout migration must not manufacture a readable digit.
                source_discrepancies.append(discrepancy)
            else:
                errors.append({'missing_header_address': discrepancy})
        # Compare actual printed control/header/selector/label cells with the
        # current approved text, allowing compression of synthetic blank rows.
        pairs = [(0, 0, 'header'), (oldlabel, newlabel, 'label')]
        pairs += [(k+1, k+1, 'control') for k in range(len(node['fields']))]
        if node.get('R_line') is not None or node.get('selector'):
            pairs.append((oldlabel-1, newlabel-1, 'selector'))
        for orow, nrow, kind in pairs:
            a = printed_text(before[oldrow+orow][oc:oc+15])
            b = lines[nr+nrow][nc:nc+15]
            if a != b:
                differences.append(dict(box=box, kind=kind, old=a, new=b,
                                        old_position=[oc, oldrow+orow], new_position=[nc, nr+nrow]))
    for box, record in oldrecords.items():
        newrecord = next((n for n in report.get('nodes', [])
                          if n.get('CAS_box', n.get('box')) == box), None)
        if newrecord is None:
            errors.append({'box': box, 'QZ_review_record_missing': True})
        else:
            for key in ['QZ_controls', 'QZ_next_base', 'control_field_differences']:
                if record.get(key) != newrecord.get(key):
                    errors.append({'box': box, 'QZ_review_changed': key})
    oldreach = page_reachability(page, old, before, oldverification.get('wire_shapes'), legacy=True)
    newreach = page_reachability(page, new, lines, report.get('wire_shapes'))
    graph = {box: dict(old=oldreach.get(box), new=newreach.get(box))
             for box in sorted(set(oldreach) | set(newreach)) if oldreach.get(box) != newreach.get(box)}
    entries = []
    caption_refs = {tuple(point) for point in new.get('caption_reference_positions', [])}
    for r, line in enumerate(lines[:94]):
        match = re.match(r'  ([AQ][A-Z]\d{3}\.[A-Z0-9]{2,4})', line)
        if match and (2, r) not in caption_refs:
            wirecol = match.end()
            entries.append(dict(row=r, label=match[1], wire_column=wirecol))
            if line[wirecol] not in '─┼O':
                errors.append({'entry_gap': [wirecol, r], 'label': match[1], 'character': line[wirecol]})
    return dict(page=page, text=str(txt), content=str(content), verification=str(verification),
                original_text=str(oldtxt), old_sha256=digest(oldtxt), new_sha256=digest(txt),
                content_sha256=digest(content), nodes=len(new['nodes']), errors=errors,
                printed_node_differences=differences, reachability_changes=graph,
                inherited_header_discrepancies=source_discrepancies,
                entry_references=entries, F_row_manual_check_pending=page=='QQ451',
                mechanical_pass=not errors and not differences,
                source_review_required=True, accepted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    pages = []
    for group in ['cas-grid-main', 'cas-grid-qq', 'cas-grid-tail']:
        for folder in sorted((args.workspace/'tmp/ald-text/ald'/group).iterdir()):
            if folder.is_dir() and re.fullmatch(r'[AQ][A-Z]\d{3}', folder.name):
                try:
                    pages.append(check(folder, args.workspace))
                except Exception as exc:
                    pages.append(dict(page=folder.name, mechanical_pass=False, error=str(exc)))
    result = dict(status='Independent mechanical audit; source review remains separate', pages=pages)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(pages=len(pages), mechanical_pass=sum(p['mechanical_pass'] for p in pages),
                         flagged=[dict(page=p['page'], errors=len(p.get('errors', [])) if 'errors' in p else p.get('error'),
                                       printed_differences=len(p.get('printed_node_differences', [])),
                                       graph_changes=len(p.get('reachability_changes', {})))
                                  for p in pages if not p['mechanical_pass'] or p.get('reachability_changes')]),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

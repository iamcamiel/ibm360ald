"""Validate the current reviewed text files and collect the readable deliverables."""
import csv, json, zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
base = root / 'ALD_Visual_Transcriptions'
out = base / 'CAS Diagrams'
inventory = list(csv.DictReader((base / 'CAS inventory.csv').open(encoding='utf-8-sig')))
summary = json.loads((out / 'CAS review summary.json').read_text(encoding='utf-8'))
assert len(inventory) == 104
assert not summary['character_policy_errors']
assert not summary['visual_review_pending'], summary['visual_review_pending']
overlaps = json.loads((out / 'Layout overlap checks.json').read_text(encoding='utf-8'))
assert not overlaps, overlaps

aa = (out / 'AA001 RESIDENT MICRODIAGNOSTIC.txt').read_text(encoding='utf-8').splitlines()
assert aa[14][27] == '└' and aa[15][27] == ' ' and aa[16][27] == '┌'
qy = (out / 'QY041 STOP LOOP AND STORE DISPLAY AND LOAD REG MANUAL CONTROLS.txt').read_text(encoding='utf-8').splitlines()
title_columns = [line.index(text) for line in qy for text in ['STOP LOOP AND STORE DISPLAY', 'AND LOAD REG MANUAL CONTROLS'] if text in line]
assert len(title_columns) == 2 and len(set(title_columns)) == 1
font = json.loads((root / 'tmp/ald-text/CAS font verification.json').read_text(encoding='utf-8'))[0]
assert not font['missing'] and len(font['advance_widths']) == 1

files = [out / (Path(item['filename']).stem + '.txt') for item in inventory]
validation = {
    'CAS_text_files': len(files),
    'approved_character_check': 'passed',
    'printed_text_overlap_check': 'passed for the 102 reconstructed specifications; two legacy pages separately reviewed',
    'AA001_FAA_FBD_separation': 'passed',
    'QY041_title_alignment': 'passed',
    'unreadable_markers': summary['unreadable_markers'],
    'pages_with_unreadable_markers': sum(bool(v['unreadable_characters']) for v in summary['records']),
    'JuliaMono': font,
    'control_field_scope': 'Printed symbolic fields visually read; QZ control bits provided alongside boxes. Complete independent numeric encoding of every symbolic field is not asserted.',
}
(out / 'CAS export validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding='utf-8')
package = base / 'CAS UTF-8 text.zip'
with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for file in files + [out / 'CAS review notes.txt', out / 'Unreadable characters.csv']:
        archive.write(file, arcname=file.name)
print(f'{len(files)} reviewed CAS text files packaged; {summary["unreadable_markers"]} unreadable markers. {package}')

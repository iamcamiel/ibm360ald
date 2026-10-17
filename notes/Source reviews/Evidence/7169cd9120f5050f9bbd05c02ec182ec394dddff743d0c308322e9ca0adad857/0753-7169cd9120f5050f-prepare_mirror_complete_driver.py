"""Create a new explicit preparer including the independent mirror addendum.

The earlier intent, tools and mechanically valid but unaccepted stage remain
untouched. This adds no contact decisions, TXT cells or coordinate changes.
"""
from pathlib import Path
import hashlib, json

BASE = Path(__file__).resolve().parent
source = BASE / 'prepare_reviewed_stage_v2.py'
target = BASE / 'prepare_reviewed_stage_v3.py'
assert not target.exists()
text = source.read_text('utf-8')
anchor = "    need(len(effective) == 629 and {c['case_id'] for c in effective} == set(requests),"
assert text.count(anchor) == 1
insertion = '''    addendum_path = BASE / 'Group 2 peer review/All active pin mirrors addendum v3.json'
    addendum = read(addendum_path)
    need(addendum.get('passed') is True and not addendum.get('failures'), 'Incomplete mirror addendum')
    need(addendum['selection'] == sr.binding(selection_path), 'Addendum binds another selection')
    add_evidence(sr.binding(addendum_path))
    preflight_path = BASE / 'Group 2 peer review/All LITERAL_FIELDS mirror preflight v3.json'
    preflight = read(preflight_path)
    need(preflight['settled_cases'] == 550 and not preflight['issues'], 'Contact mirrors remain inconsistent')
    add_evidence(sr.binding(preflight_path))
    add_evidence(sr.binding(BASE / 'prepare_mirror_complete_driver.py'))
    add_evidence(sr.binding(BASE / 'Superseded stage 1.json'))
    index = {c['case_id']: c for c in effective}
    for extra in addendum['cases']:
        case = index[extra['case_id']]
        need(case['status'].startswith(('confident', 'resolved')), 'Mirror patch targets a held pin')
        need(extra['already_accepted_contact'] == case['proposed_contact'], 'Mirror addendum changes a decision')
        need(not extra['text_edits'], 'Mirror addendum changes TXT')
        sr.checked(extra['model'], BASE)
        case['json_patches'].extend(extra['json_patches'])
'''
text = text.replace(anchor, insertion + anchor)
for old, new in [("'Intent.json'", "'Intent v3.json'"),
                 ("'Final review merge.json'", "'Final review merge v3.json'")]:
    assert old in text
    text = text.replace(old, new)
target.write_text(text, 'utf-8')
manifest = BASE / 'stage/manifest.json'
addendum = BASE / 'Group 2 peer review/All active pin mirrors addendum v3.json'
receipt = BASE / 'Superseded stage 1.json'
assert not receipt.exists()
def bind(p):
    return {'path': str(p.resolve()), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
receipt.write_text(json.dumps({
    'schema': 'unaccepted-stage-supersession-v1',
    'manifest': bind(manifest), 'accepted': False, 'published': False,
    'reason': 'Mechanical grid/render replay passed, but independent full-field preflight found14 omitted current JSON label mirrors. A new intent/stage includes these mirrors; no contact decisions or TXT edits change.',
    'superseding_addendum': bind(addendum), 'canonical_changes_applied': False,
}, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print(str(target))

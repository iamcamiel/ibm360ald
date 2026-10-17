"""Prepare a fresh intent with all independently checked active-reference mirrors."""
from pathlib import Path
import hashlib, json
BASE = Path(__file__).resolve().parent
source = BASE / 'prepare_reviewed_stage_v3.py'
target = BASE / 'prepare_reviewed_stage_v4.py'
assert not target.exists()
text = source.read_text('utf-8')
for old, new in [
    ("'Intent v3.json'", "'Intent v4.json'"),
    ("'Final review merge v3.json'", "'Final review merge v4.json'"),
    ("'Group 2 peer review/All active pin mirrors addendum v3.json'",
     "'Group 2 peer review/Complete active pin mirrors and references addendum v4.json'"),
]:
    assert old in text
    text = text.replace(old, new)
anchor = '    index = {c[\'case_id\']: c for c in effective}'
assert text.count(anchor) == 1
text = text.replace(anchor, '''    add_evidence(addendum['review_tool'])
    refs_path = BASE / 'Group 2 peer review/All stale active references v2.json'
    refs = read(refs_path)
    need(refs['stale_count'] == 0 and not refs['issues'], 'Active qualified-reference mirrors remain stale')
    need(refs['virtual_addendum'] == sr.binding(addendum_path), 'Reference check binds another addendum')
    add_evidence(sr.binding(refs_path))
    add_evidence(sr.binding(BASE / 'prepare_reference_complete_driver.py'))
    add_evidence(sr.binding(BASE / 'Superseded stage 3.json'))
''' + anchor)
target.write_text(text, 'utf-8')
def bind(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
receipt = BASE / 'Superseded stage 3.json'
assert not receipt.exists()
receipt.write_text(json.dumps({
    'schema': 'unaccepted-stage-supersession-v1', 'accepted': False, 'published': False,
    'manifest': bind(BASE / 'stage-v3/manifest.json'),
    'reason': 'Independent full active-reference census found18 additional mechanical operations (ten qualified-reference values and four coordinate-key rename pairs). All source contact decisions, TXT cells, coordinates and routing remain unchanged.',
    'superseding_addendum': bind(BASE / 'Group 2 peer review/Complete active pin mirrors and references addendum v4.json'),
    'canonical_changes_applied': False,
}, ensure_ascii=False, indent=2) + '\n', 'utf-8')
creator = BASE / 'create_complete_stage_v4.py'
assert not creator.exists()
creator.write_text((BASE / 'create_complete_stage.py').read_text('utf-8')
                   .replace("'Intent v3.json'", "'Intent v4.json'")
                   .replace("'stage-v3'", "'stage-v4'")
                   .replace("'Staging verification v3.json'", "'Staging verification v4.json'"), 'utf-8')
print(str(target))

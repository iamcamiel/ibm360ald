"""Create explicit new preparation drivers; retain frozen first-attempt tools."""
from pathlib import Path
BASE = Path(__file__).resolve().parent
for name, destination, replacements in [
    ('prepare_reviewed_stage.py', 'prepare_reviewed_stage_v2.py', {
        "'Final reviewed selection.json'": "'Final reviewed selection v2.json'"}),
    ('select_final_reviews.py', 'select_final_reviews_v2.py', {
        "'Final reviewed selection.json'": "'Final reviewed selection v2.json'",
        "'Group 2 review/Peer-reviewed findings.json'": "'Group 2 review/Peer-reviewed findings v2.json'",
        "'Group 2 peer review/Independent peer review.json'": "'Group 2 peer review/Independent peer review v2.json'"}),
]:
    source = BASE / name
    target = BASE / destination
    assert not target.exists(), 'Do not replace an existing driver'
    text = source.read_text('utf-8')
    for old, new in replacements.items():
        assert text.count(old) == 1, 'Ambiguous driver replacement'
        text = text.replace(old, new)
    target.write_text(text, 'utf-8')
    print(str(target))

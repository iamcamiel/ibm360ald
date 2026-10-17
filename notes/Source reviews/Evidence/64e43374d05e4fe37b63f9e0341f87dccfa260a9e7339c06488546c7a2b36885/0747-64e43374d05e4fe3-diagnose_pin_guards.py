"""Read-only annotation/contact-mirror guard diagnostics for peer proposals."""
from pathlib import Path
from collections import defaultdict
import json, sys
ROOT = Path('D:/Github/IBM360')
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'ibm360ald/tools/reviews'))
import source_review as sr

selection = sr.read_json(BASE / 'Final reviewed selection.json')
results = []
for g in selection['groups']:
    doc = sr.read_json(g['findings']['path'])
    bypage = defaultdict(list)
    for c in doc.get('cases', doc.get('findings', [])):
        bypage[c['page']].append(c)
    for page, cases in bypage.items():
        m = cases[0].get('model', cases[0].get('model_preimage'))
        before = sr.read_json(m['path'])
        unique = {}
        for c in cases:
            plans = [c] + c.get('context_corrections', [])
            for plan in plans:
                for p in plan.get('json_patches', []):
                    p = dict(p)
                    p['pointer'] = p.pop('path', p.get('pointer'))
                    unique[p['pointer']] = p
        patches = list(unique.values())
        after = sr.patch_model(before, patches)
        for issue in sr.validate_pin_edits(before, after, {'json_patches': patches, 'evidence': [1]}):
            results.append({'group': g['group'], 'page': page, **issue})
out = {'source_changes_applied': False, 'issues': results}
sr.atomic_write(BASE / 'Stage preparation guard diagnostics.json', sr.encode(out))
print(json.dumps(out, ensure_ascii=False, indent=2))

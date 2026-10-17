import hashlib
import json
from pathlib import Path

BASE = Path(__file__).parent / '0611 C1 pin source review'
OUT = BASE / 'Accepted D09 source correction'
WORK = Path('D:/Github/IBM360/ALD_Visual_Transcriptions/ALD Diagrams')
STEM = 'RF701 F REGISTER INPUT SWITCHCARDS'

def binding(p):
    p = Path(p)
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}

def save(p, data):
    if p.exists():
        raise FileExistsError(p)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

OUT.mkdir(exist_ok=False)
quartet = {k: binding(WORK / (STEM + s)) for k, s in {
    'txt': '.txt', 'json': '.json', 'notes': ' review notes.txt',
    'preview': ' preview.png'}.items()}
model = json.loads(Path(quartet['json']['path']).read_text(encoding='utf-8-sig'))
assert model['nodes'][19]['id'] == 'AR'
assert model['nodes'][19]['card_type'] == '0611'
assert model['nodes'][19]['portion'] == 'C1'
pin = model['nodes'][19]['pins'][1]
assert pin['pin'] == pin['physical_pin'] == 'D05'
assert pin['reference'] == 'AR.D05' and pin['row'] == 35
assert model['nets'][8]['targets'][4] == 'AR.D05'
lines = Path(quartet['txt']['path']).read_text(encoding='utf-8-sig').splitlines()
assert lines[35][139:142] == 'D05'
prior = Path('D:/Github/IBM360/tmp/ald-text/ald/socket-ald-audit/card-portion-visual-20261016/Combined ALD identity correction stage/stage')
pub = json.loads((prior / 'publication.json').read_text(encoding='utf-8'))
accepted = next(x for x in pub['pages'] if x['page'] == 'RF701')
assert accepted['current_quartet'] == quartet
save(OUT / 'Human authorization.json', {
    'schema': 'direct-human-source-correction-authorization-v1',
    'date': '2026-10-17',
    'prior_human_request': 'Looking at the 0611 diagram, I think that the D05 pin on C1 is probably a misread D09; can you check that?',
    'coordinator_finding': 'RF701 AR is the sole observed C1 lower input; native scan supports worn D09. C2 below clearly D09. Other four C1 uses omit this input.',
    'human_authorization': 'Please fix that. How is the routing change coming?',
    'scope': 'Only RF701 AR 0611C1 D05 to D09 and its exact aliases; preserve all other D05 uses, wires, functions and geometry.'})
evidence = [binding(__file__), binding(BASE / 'Native comparison receipt.json'),
    binding(BASE / 'RF701 AR C1 and AS C2 pin comparison native.png'),
    binding(OUT / 'Human authorization.json')]
evidence += [binding(prior / f) for f in ['publication.json', 'manifest.json', 'independent-acceptance.snapshot.json']]
old_intent = json.loads(Path('D:/Github/IBM360/tmp/ald-text/ald/socket-ald-audit/routing-review-20261017/DS111 BB source correction/Intent.json').read_text(encoding='utf-8'))
preview = old_intent['pages'][0]['preview_config']
patches = [
    {'pointer': '/nodes/19/pins/1/pin', 'before': 'D05', 'after': 'D09'},
    {'pointer': '/nodes/19/pins/1/physical_pin', 'before': 'D05', 'after': 'D09'},
    {'pointer': '/nodes/19/pins/1/reference', 'before': 'AR.D05', 'after': 'AR.D09'},
    {'pointer': '/nets/8/targets/4', 'before': 'AR.D05', 'after': 'AR.D09'}]
intent = {'schema': 'source-review-intent-v1', 'review_id': 'RF701-AR-0611C1-D09-20261017',
    'card_type': '0611', 'target_root': str(WORK.parent), 'unresolved_questions': [],
    'evidence': evidence, 'pages': [{
        'page': 'RF701', 'model_schema': 'ald-page-nodes-v1',
        'source': binding(model['source']), 'prior_quartet': quartet,
        'grid': {'width': 245, 'height': 103},
        'cell_edits': [{'row': 35, 'column': 141, 'before': '5', 'after': '9'}],
        'json_patches': patches,
        'notes_append': 'RF701 AR 0611C1 PIN REVIEW 2026-10-17\nThe native TIFF lower input is a worn D09, previously transcribed D05. User identified the likely misread and explicitly requested correction after seeing the native C1/C2 comparison. Change exactly row 35 column 141 and the four paired model/endpoint aliases. C2 below clearly reads D09; the other four C1 occurrences omit this contact. Preserve all other D05 pins, source wiring and geometry. Original scans are unchanged.\n',
        'preview_config': preview, 'evidence': evidence}]}
save(OUT / 'Intent.json', intent)
print(json.dumps({'intent': str(OUT / 'Intent.json'), 'patches': len(patches), 'txt_cells': 1}))

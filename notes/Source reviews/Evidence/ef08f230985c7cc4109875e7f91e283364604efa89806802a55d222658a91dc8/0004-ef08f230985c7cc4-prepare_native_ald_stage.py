"""Prepare an exact private generic stage; never publish or edit live sources."""
from copy import deepcopy
import json
from pathlib import Path
import sys

WORKSPACE = Path('D:/Github/IBM360')
REPO = WORKSPACE/'ibm360ald'
BASE = WORKSPACE/'tmp/ald-text/ald/socket-ald-audit'
NATIVE = BASE/'reverse-systemic-analysis/native'
OUT = BASE/'native-eleven-ald-review'
OUT.mkdir(exist_ok=False)
sys.path.insert(0,str(REPO/'tools/reviews'))
import source_review as sr

findings = sr.read_json(NATIVE/'Ten findings.json')['cases']
ap = next(x for x in findings if x['page']=='AP781')
extra = {k:deepcopy(ap[k]) for k in ('page','source','model_path','model_sha256','text_path','text_sha256')}
extra.update(node_id='3E',node_pointer='/nodes/9',status='confirmed_native_and_listing_source_repair',
    crop=sr.binding(NATIVE/'AP781 3E native.png'),
    proposed_json_changes=[{'field':'card_type','before':'33�8','after':'3388'},
                           {'field':'printed_card_portion','before':'33�8H1','after':'3388H1'}],
    text_changes=[{'before':'33�8H1','after':'3388H1'}],
    note='Native AP781 3E reads 3388H1 at B-D1C3. A1241-01 C3 native listing independently prints 5803388 3388. Existing F1 at the same socket already reads 3388F1 and remains unchanged.',
    additional_listing_native_proof=sr.read_json(NATIVE/'A1241-01 C3 finding.json'))
sr.atomic_write(OUT/'AP781 3E source finding.json',sr.encode(extra))
findings.append(extra)

last = WORKSPACE/'tmp/ald-text/ald/repository-export/last export manifest.json'
baseline = sr.read_json(last)
content = sr.read_json(REPO/'notes/Content data manifest.json')
models = {x['path']:x for x in content['files'] if x.get('role')=='Published page content model'}
grouped = {}
for case in findings: grouped.setdefault(case['page'],[]).append(case)
pages = []; summaries = []
for page,cases in grouped.items():
    entry = next(x for x in baseline['exported'] if x['page']==page)
    text = Path(entry['transcription_source']); model_path = text.with_suffix('.json')
    notes = text.with_name(text.stem+' review notes.txt')
    previews = [p for p in text.parent.glob(text.stem+'*.png') if p.name.endswith((' preview.png',))]
    sr.require(len(previews)==1,'Ambiguous current preview: '+page)
    quartet = {'txt':sr.binding(text),'json':sr.binding(model_path),
               'notes':sr.binding(notes),'preview':sr.binding(previews[0])}
    sr.require(quartet['txt']['sha256']==entry['text_sha256'],'Working TXT not current accepted preimage: '+page)
    sr.require(quartet['json']['sha256']==models[cases[0]['model_path']]['sha256'],'Working JSON not current repository model: '+page)
    model = sr.read_json(model_path); lines = text.read_text(encoding='utf-8-sig').splitlines()
    patches=[]; edits=[]; evidence=[]; descriptions=[]
    for case in cases:
        ni=int(case['node_pointer'].split('/')[-1]); node=model['nodes'][ni]
        sr.require(node['id']==case['node_id'],'Node index identity changed')
        sr.require(quartet['json']['sha256']==case['model_sha256'],'Native finding binds another model epoch')
        sr.require(quartet['txt']['sha256']==case['text_sha256'],'Native finding binds another text epoch')
        evidence.append(case['crop'])
        for change in case['proposed_json_changes']:
            patches.append({'pointer':case['node_pointer']+'/'+change['field'],
                            'before':change['before'],'after':change['after']})
        if page in {'CS011','DS131'}:
            # Native K is in the right-border cell, not the six-cell interior.
            row=node['row']+4; column=node['column']+7
            sr.require(lines[row][column]=='K','Expected retained K border cell')
            pins=[(i,pin) for i,pin in enumerate(node['pins']) if pin['side']=='output' and pin['row']==row]
            sr.require(len(pins)==1,'Expected one output at K border')
            pi,pin=pins[0]
            for field,value in [('border_marker','K'),('marker_column',column)]:
                if field in pin:
                    sr.require(pin[field] in (None,value),'Existing conflicting border marker')
                    if pin[field]!=value: patches.append({'pointer':case['node_pointer']+f'/pins/{pi}/'+field,'before':pin[field],'after':value})
                else: patches.append({'op':'add','pointer':case['node_pointer']+f'/pins/{pi}/'+field,'after':value})
            descriptions.append(node['id']+': '+node['printed_card_portion']+' identifies '+node['card_type']+node['portion']+' plus the separately retained K output-border marker at row '+str(row)+', column '+str(column)+'.')
        else:
            descriptions.append(node['id']+': '+', '.join(x['field']+' '+x['before']+' → '+x['after'] for x in case['proposed_json_changes'])+'.')
        for change in case.get('text_changes',[]):
            # All requested labels are on the card/portion row inside the box.
            row=node['row']+4; column=node['column']+1
            sr.require(lines[row][column:column+len(change['before'])]==change['before'],'Card label text preimage changed')
            edits.append({'row':row,'column':column,'before':change['before'],'after':change['after']})
    note='NATIVE SOCKET–ALD CROSS-REFERENCE REVIEW 2026-10-16\n'+'\n'.join(descriptions)
    if page in {'CS011','DS131'}:
        note+='\nThe K marks remain byte-for-byte in the UTF-8 diagram and preview. Only the semantic card/portion extraction is shortened; output-pin border_marker/marker_column retain the printed control mark. No pin identity, wire or shape is changed.'
    elif page=='AP781':
        note+='\nAll masked card-type occurrences at B-D1C3 are resolved as 3388: A1, B1 and H1. F1 already reads 3388 and is unchanged. The native A1241-01 C3 listing prints 5803388 3388; its previous 3368 transcription is documented for a separate source-bound socket-table correction. Earlier review notes and provenance ledgers remain historical observations and are retained unchanged.'
    else:
        note+='\nThe accepted UTF-8 card label already has the resolved digits; only the masked active JSON card_type mirror is repaired. Other existing uncertainties and historical evidence remain unchanged.'
    item={'page':page,'model_schema':'ald-page-nodes-v1','source':cases[0]['source'],
          'prior_quartet':quartet,'grid':{'width':245,'height':103},'cell_edits':edits,
          'json_patches':patches,'notes_append':note,'evidence':evidence}
    if edits:
        item['preview_config']={'font':sr.binding(WORKSPACE/'tmp/ald-text/JuliaMono-Regular.ttf'),
            'width':2940,'height':1854,'font_size':20,'cell_width':12,'row_height':18,'origin':[0,0]}
    pages.append(item)
    summaries.append({'page':page,'cases':len(cases),'json_patches':len(patches),'cell_edits':edits,
                      'working_quartet':quartet,'prior_review_record':entry['review_record']})

evidence=[sr.binding(NATIVE/'Ten findings.json'),sr.binding(NATIVE/'Ten crop bindings.json'),
          sr.binding(NATIVE/'A1241-01 C3 finding.json'),sr.binding(NATIVE/'A1241-01 C3 native.png'),
          sr.binding(OUT/'AP781 3E source finding.json'),sr.binding(last),
          sr.binding(REPO/'notes/Content data manifest.json'),sr.binding(Path(__file__))]
intent={'schema':sr.INTENT,'review_id':'socket-ald-native-eleven-20261016','target_root':str(WORKSPACE/'ALD_Visual_Transcriptions'),
        'unresolved_questions':[],'evidence':evidence,'pages':pages}
sr.atomic_write(OUT/'Intent.json',sr.encode(intent))
sr.atomic_write(OUT/'Predecessor proof.json',sr.encode({'schema':'private-native-eleven-predecessor-proof-v1',
    'source_changes_applied':False,'pages':summaries,'case_count':sum(x['cases'] for x in summaries),
    'separate_socket_table_plan':sr.binding(NATIVE/'A1241-01 C3 finding.json')}))
report=sr.create_stage(OUT/'Intent.json',OUT/'stage')
sr.atomic_write(OUT/'Stage verification.json',sr.encode(report))
print(json.dumps({'output':str(OUT),'verification':report},ensure_ascii=False,indent=2))

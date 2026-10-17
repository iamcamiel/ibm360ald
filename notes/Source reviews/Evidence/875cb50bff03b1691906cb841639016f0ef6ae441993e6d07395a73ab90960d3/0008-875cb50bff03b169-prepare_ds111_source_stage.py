"""Prepare the explicitly reviewed DS111 BB correction; no publication/acceptance."""
from pathlib import Path
from copy import deepcopy
import json, sys
from PIL import Image

ROOT = Path('D:/Github/IBM360')
REPO = ROOT/'ibm360ald'
BASE = ROOT/'tmp/ald-text/ald/socket-ald-audit/routing-review-20261017'
OUT = BASE/'DS111 BB source correction'
sys.path.insert(0, str(REPO/'tools/reviews'))
import source_review as sr

def need(ok, message):
    if not ok: raise ValueError(message)

def main():
    need(not OUT.exists(), 'Fresh private output required')
    source = Path('D:/Reference Materials/IBM 360/IBM_360_ALD/DS ROS Branching/DS111 NORMAL AND FAST BR SET ROSAR BIT 11.tif')
    stem = 'DS111 NORMAL AND FAST BR SET ROSAR BIT 11'
    model = ROOT/'ALD_Visual_Transcriptions/ALD Diagrams'/(stem+'.json')
    txt = model.with_suffix('.txt')
    notes = model.with_name(stem+' review notes.txt')
    preview = model.with_name(stem+' preview.png')
    repo_model = REPO/'json/DS ROS Branching'/(stem+'.json')
    repo_txt = REPO/'ALD/DS ROS Branching'/(stem+'.txt')
    predecessor = ROOT/'tmp/ald-text/ald/socket-ald-audit/card-portion-visual-20261016/Combined ALD identity correction stage/stage/publication.json'
    crop_receipt = BASE/'0479 portion source review/Native crop receipt.json'
    crop = BASE/'0479 portion source review/DS111 BB 0479A6 and K B13 native.png'
    probe = ROOT/'tmp/ald-text/ald/socket-ald-audit/pin-letter-visual-20261016/Predecessor preview configuration probe.json'
    expected = {
        source:'4af812cbbaf4ce48db69be6044447a3cab12d20addde1ae80813cbe24d78d26a',
        model:'d9fa8623792c869e99dc1f35311b3e26b9fffc147e346b73a441e55e856fdb97',
        txt:'10cb25d8ae44d149e54767d59244545cf204e09463a5cf650d0ea843d5bd53e0',
        notes:'7b280528b95316afcf8d9e193f1fa170feec4afc9b2f97bd8bba746f69a56d7d',
        preview:'e1ea2ff22eb0bb156203aca6dbfa69fe1478e00bf416e8c0585190ff8ea96c01',
        crop:'84126d5d2825ab1dc83fa2f8939509e0f5356ed3d7515f7942e9191ac50b4280'}
    for p, sha in expected.items(): need(sr.binding(p)['sha256']==sha, 'Preimage drift: '+str(p))
    need(model.read_bytes()==repo_model.read_bytes() and txt.read_bytes()==repo_txt.read_bytes(), 'Working/repository mismatch')
    accepted = sr.read_json(predecessor)
    need(accepted.get('passed') is True, 'Predecessor publication failed')
    page = next(p for p in accepted['pages'] if p['page']=='DS111')
    need(page['eligible'] is True and all(page['checks'].values()), 'Prior accepted quartet not eligible')
    for k,p in [('txt',txt),('json',model),('notes',notes),('preview',preview)]:
        need(page['current_quartet'][k]==sr.binding(p), 'Accepted quartet mismatch: '+k)
    for link in [accepted['manifest'],accepted['independent_acceptance']]: sr.checked(link, predecessor.parent)
    receipt = sr.read_json(crop_receipt)
    need(receipt['crop_box']==[7650,1240,8750,1750], 'Crop bounds differ')
    with Image.open(source) as native, Image.open(crop) as tile:
        need(native.convert('RGB').crop(receipt['crop_box']).tobytes()==tile.convert('RGB').tobytes(), 'Native crop pixels differ')
    before = sr.read_json(model)
    need(before['nodes'][26]['id']=='BB', 'Block position differs')
    bb = before['nodes'][26]
    need(bb['card_type']=='0479' and bb['unit']=='U03AE' and bb['portion']=='A6KB139' and bb['printed_card_portion']=='0479A6KB139', 'Unexpected BB identity')
    need(len(bb['pins'])==6 and bb['pins'][-1]=={'pin':'D02','row':19,'side':'output','triangle':True,'reference':'BB.output-D02','point':[199,19]}, 'Unexpected original output')
    net_index = next(i for i,n in enumerate(before['nets']) if n['id']=='BBterm')
    need(before['nets'][net_index]=={'id':'BBterm','driver':'BB.output-D02','targets':['DS101.BB4'],'source_reviewed':True}, 'Unexpected net preimage')
    need([w for w in before['wire_paths'] if w.get('net')=='BBterm']==[{'net':'BBterm','points':[[199,19],[242,19]]}], 'Unexpected net wire')
    need(not any(j.get('column')==199 and j.get('row')==19 for j in before['junctions']), 'Junction already represented')
    pins = deepcopy(bb['pins'])+[{'pin':'B13','row':20,'side':'output','triangle':False,'reference':'BB.output-B13','point':[199,20],'border_marker':'K','marker_column':195}]
    patches = [
        {'op':'replace','pointer':'/nodes/26/portion','before':bb['portion'],'after':'A6'},
        {'op':'replace','pointer':'/nodes/26/printed_card_portion','before':bb['printed_card_portion'],'after':'0479A6'},
        {'op':'replace','pointer':'/nodes/26/pins','before':bb['pins'],'after':pins},
        {'op':'add','pointer':f'/nets/{net_index}/declared_physical_output_drivers','after':['BB.output-D02','BB.output-B13']},
        {'op':'replace','pointer':'/wire_paths','before':before['wire_paths'],'after':deepcopy(before['wire_paths'])+[{'net':'BBterm','points':[[199,20],[199,19]]}]},
        {'op':'replace','pointer':'/junctions','before':before['junctions'],'after':deepcopy(before['junctions'])+[{'net':'BBterm','column':199,'row':19}]}]
    cells = [{'row':19,'column':199,'before':'─','after':'◇'},{'row':20,'column':199,'before':'9','after':'┘'}]
    rows = txt.read_text(encoding='utf-8-sig').splitlines()
    need(rows[20][188:200]=='│0479A6KB139', 'Exact portion/K/corner span differs')
    grid = {'width':max(map(len,rows)),'height':len(rows)}
    config = next(deepcopy(c['configuration']) for c in sr.read_json(probe)['configurations'] if tuple(c['dimensions'])==Image.open(preview).size)
    after = sr.patch_model(before, patches)
    need(not sr.validate_pin_edits(before,after,{'json_patches':patches,'evidence':[sr.binding(crop)]}), 'Pin mirror guard rejected')
    need(all(a==b for i,(a,b) in enumerate(zip(before['nodes'],after['nodes'])) if i!=26), 'Other block changed')
    need(after['nodes'][26]['pins'][:-1]==bb['pins'], 'Original pins changed')
    need(after['wire_paths'][:-1]==before['wire_paths'] and after['junctions'][:-1]==before['junctions'], 'Original geometry changed')
    scope = {
        'schema':'source-bound-DS111-BB-literal-correction-proposal-v1','created_utc':sr.now(),
        'source_changes_applied':False,'independent_acceptance_generated':False,
        'authorization':{'raw':'Please fix that','origin':'Direct user request relayed by coordinator /root on 2026-10-17','kind':'Authorization to correct the shown transcription; not a fabricated glyph answer'},
        'native_reading':'0479A6; separate K-marked B13 output at row20 turns upward into the diamond on the D02 output net. The final printed stroke is a wire corner, not digit9.',
        'source':sr.binding(source),'native_crop':{**sr.binding(crop),'box':receipt['crop_box'],'pixel_exact_reproduced':True},
        'predecessor_publication':sr.binding(predecessor),'predecessor_stage':accepted['manifest'],'predecessor_acceptance':accepted['independent_acceptance'],
        'repository_model':sr.binding(repo_model),'repository_text':sr.binding(repo_txt),
        'text_edits':cells,'json_patches':patches,
        'unchanged':'K remains col195, all original physical pins/portions other than malformed BB portion, wires, net driver/targets and historical observations retained. No inferred net unions, builder/routing changes, acceptance, publication or inventory updates.'}
    OUT.mkdir(parents=True)
    sr.atomic_write(OUT/'Exact source correction proposal.json',sr.encode(scope))
    evidence=[sr.binding(p) for p in [Path(__file__),crop_receipt,crop,probe,predecessor,OUT/'Exact source correction proposal.json']]+[accepted['manifest'],accepted['independent_acceptance']]
    note = ('NATIVE DS111 BB PORTION AND K-OUTPUT REVIEW 2026-10-17\n'
            'The original TIFF shows portion 0479A6, a separate K-marked B13 output, and its short upward branch joining the D02 output at the diamond. Earlier A6KB139/0479A6KB139 concatenated card portion, border marker, physical pin and a misread wire corner.\n'
            'Correct only the two declared TXT glyphs (row19 col199 diamond; row20 col199 corner), the paired portion fields, and the missing explicit B13 output/commoned branch. K remains col195 and B13 is not an additional portion. Existing D02 inversion, all other pins, driver/target, paths, geometry and historical observations are preserved.\n'
            'Source-bound native inspection by audit_independent_review and coordinator; direct user authorization was Please fix that. This is a precise source transcription correction, not a change to generic internal-net assembly. Independent acceptance and publication remain separate.\n')
    intent={'schema':'source-review-intent-v1','review_id':'DS111-BB-0479A6-K-B13-20261017','target_root':str(ROOT/'ALD_Visual_Transcriptions'),'unresolved_questions':[],
            'scope_note':'Native-bound exact two-cell correction and missing same-net K output; no canonical writes during preparation.','evidence':evidence,
            'pages':[{'page':'DS111','model_schema':'ald-page-nodes-v1','source':sr.binding(source),'prior_quartet':{k:sr.binding(p) for k,p in [('txt',txt),('json',model),('notes',notes),('preview',preview)]},'grid':grid,'cell_edits':cells,'json_patches':patches,'notes_append':note,'preview_config':config,'evidence':evidence}]}
    sr.atomic_write(OUT/'Intent.json',sr.encode(intent))
    result=sr.create_stage(OUT/'Intent.json',OUT/'stage')
    sr.atomic_write(OUT/'Staging verification.json',sr.encode(result))
    print(json.dumps({'passed':True,'manifest':sr.binding(OUT/'stage/manifest.json'),'verification':sr.binding(OUT/'Staging verification.json'),'proposal':sr.binding(OUT/'Exact source correction proposal.json'),'text_cells':2,'JSON_operations':6,'source_changes_applied':False},ensure_ascii=False,indent=2))

if __name__=='__main__': main()

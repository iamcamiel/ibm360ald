"""Independent exact replay of this private, directly confirmed A1 correction."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFont

BASE=Path(__file__).resolve().parent
WORK=Path('D:/Github/IBM360')
MANIFEST=BASE/'Stage manifest.json'
EXPECTED='4b49f7f81faf5ad37778857794ef466eda6ff291f0fc75a58cf3894f62d0494e'
OLD,NEW='REC41AY4','RE041AY4'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def bind(path):return {'path':str(Path(path).resolve()),'sha256':sha(Path(path).read_bytes())}
checks=[]
def need(ok,name):
    if not ok:raise ValueError(name)
    checks.append(name)
def checked(link):
    path=Path(link['path']);raw=path.read_bytes();need(sha(raw)==link['sha256'],'Current bound bytes: '+str(path));return raw
def pointer(root, key):
    node=root
    for token in key.split('/')[1:]:
        token=token.replace('~1','/').replace('~0','~');node=node[int(token)] if isinstance(node,list) else node[token]
    return node
def replace(root,key,before,after):
    tokens=key.split('/')[1:];node=root
    for token in tokens[:-1]:
        token=token.replace('~1','/').replace('~0','~');node=node[int(token)] if isinstance(node,list) else node[token]
    token=tokens[-1].replace('~1','/').replace('~0','~');token=int(token) if isinstance(node,list) else token
    need(node[token]==before,'JSON pointer exact preimage '+key);node[token]=deepcopy(after)


report={'schema':'socket-table-literal-correction-independent-acceptance-v1','created_utc':datetime.now(timezone.utc).isoformat(),
        'reviewer':'/root/universal_release_review','independent_review':True,'passed':False,'failures':[],
        'manifest_sha256':sha(MANIFEST.read_bytes()),'stage_manifest':bind(MANIFEST),'source_or_repository_publication':False}
try:
    need(report['manifest_sha256']==EXPECTED,'Exact supplied stage manifest')
    m=load(MANIFEST)
    need(m['schema']=='socket-table-literal-correction-private-stage-v1','Declared A1 stage schema')
    need(m['page']=='A1232-01' and m['source_scan_id']=='119','Exact page and scan identity')
    for key in ['source','human_authority','source_crop','predecessor_acceptance','historical_repository_acceptance','render_font','preparation_script']:checked(m[key])
    checked(m['corroboration']['text'])
    answer=load(m['human_authority']['path'])
    need(answer['raw_answer']=='Yes, certainly RE041AY4' and answer['normalized_answer']==NEW,'Literal direct human authority preserved')
    need(answer['source']==m['source'] and answer['crop']==m['source_crop'],'Human authority binds the reviewed original and crop')
    source=Image.open(m['source']['path']).convert('L');crop=Image.open(m['source_crop']['path']).convert('L')
    need(ImageChops.difference(source.crop((1500,950,2750,1570)),crop).getbbox() is None,'Displayed target crop is exact native TIFF rectangle 1500,950,2750,1570')
    need(m['predecessor_acceptance']['sha256']==m['historical_repository_acceptance']['sha256'],'Historical columns and repository receipt remain byte-identical')
    historical=load(m['predecessor_acceptance']['path'])
    retext=Path(m['corroboration']['text']['path']).read_text(encoding='utf-8-sig').splitlines()
    for row in m['corroboration']['footer']:
        need(retext[row['row']]==row['literal'] and 'AY4 B-C2A2B03' in row['literal'],'Accepted RE041 AY4 matches normalized 02B-C2 A2 B03 connector endpoint')
    need(m['exact_meaningful_cell_changes']==[{'row':8,'column':24,'before':'C','after':'0'}] and m['trailing_space_padding']==[],'Only authorized C to 0 cell change')
    files=m['files'];need(len(files)==11 and len({f['target'] for f in files})==11,'Exactly eleven unique declared targets')
    protected={Path(m[key]['path']).resolve() for key in ['source','predecessor_acceptance','historical_repository_acceptance','source_crop','human_authority']}
    targetset={Path(f['target']).resolve() for f in files}
    need(not targetset&protected and all(p.is_relative_to(WORK) and p.suffix.lower() not in {'.tif','.tiff'} for p in targetset),'All targets exclude scans, immutable acceptance and authority')
    txt_after=[];created=[];json_changes=[]
    for f in files:
        target=Path(f['target']);candidate=checked(f['candidate'])
        need(Path(f['candidate']['path']).resolve().is_relative_to(BASE),'Candidate confined to private stage')
        if f['before'] is None:
            need(not target.exists(),'New target genuinely absent: '+str(target));created.append(f['role'])
            if f['role']=='successor columns proof':
                expected=deepcopy(historical);replace(expected,'/0/6','            A2 B03 '+OLD,'            A2 B03 '+NEW)
                need(load(f['candidate']['path'])==expected,'Successor columns differ only at confirmed literal; original array not rewritten')
            continue
        old=checked(f['before']);need(target.read_bytes()==old,'Live target still exact preimage: '+str(target))
        if target.suffix=='.txt':
            need(old.count(OLD.encode())==1 and candidate==old.replace(OLD.encode(),NEW.encode()),'TXT exact one-byte replacement, no newline or unrelated byte changes')
            before_lines=old.decode('utf-8-sig').splitlines();after_lines=candidate.decode('utf-8-sig').splitlines()
            need(len(before_lines)==len(after_lines)==105 and set(map(len,before_lines))==set(map(len,after_lines))=={248},'TXT 105 by 248 grid, trailing spaces and line endings preserved')
            need(before_lines[8][24]=='C' and after_lines[8][24]=='0','TXT row8 column24 exact confirmed cell')
            txt_after.append(candidate);continue
        expected=json.loads(old.decode('utf-8-sig'));after=json.loads(candidate.decode('utf-8-sig'))
        for change in f['changes']:
            if 'pointer' in change:
                need(change['before']==OLD and change['after']==NEW,'Auxiliary reference pointer changes exact confirmed token')
                replace(expected,change['pointer'],OLD,NEW);json_changes.append(change['pointer'])
            else:
                need(change=={'operation':'move_bucket_entries','before_key':'REC41','after_key':'RE041','count':1},'Only confirmed bucket migration declared')
                buckets=expected.get('ALD_pages',expected);moved=buckets.pop('REC41')
                need(len(moved)==1 and moved[0]['ALD_reference']==NEW and moved[0]['board']=='02B-C2' and moved[0]['sockets']==['A2T'] and moved[0]['pin']=='B03','Moved bucket contains only exact confirmed connector entry')
                buckets.setdefault('RE041',[]).extend(moved)
        need(expected==after,'Auxiliary JSON exact declared pointer/bucket replay; all other fields preserved')
        if 'socket_records' in after:
            r=after['socket_records'][0];need(r['board']=='02B-C2' and r['sockets']==['A2T'] and r['pin_references'][1]['printed_socket']=='A2' and r['pin_references'][1]['pin']=='B03','Active board target is exact A2T A2 B03 record')
        if 'records' in after and 'logical_records' in after:
            for group,index in [('records',6527),('logical_records',6327)]:
                r=after[group][index];need(r['board']=='02B-C2' and r['sockets']==['A2T'] and r['pins'][1]['pin']=='B03' and r['pins'][1]['ALD_reference']==NEW,'Socket-reference '+group+' exact connector ownership')
    need(len(txt_after)==2 and txt_after[0]==txt_after[1],'Working and repository TXT candidate bytes agree')
    need(sorted(created)==['new source preview','new source review notes','successor columns proof'],'Only three honest first-created artifacts')
    need(len(json_changes)==8,'Exactly eight auxiliary pointer changes including bucketed fields')
    font=ImageFont.truetype(m['render_font']['path'],18);cw=round(font.getlength('M'));rows=txt_after[0].decode('utf-8').splitlines()
    expected_image=Image.new('RGB',(32+248*cw,32+105*25),'white');draw=ImageDraw.Draw(expected_image)
    for y,line in enumerate(rows):draw.text((16,16+y*25),line,font=font,fill='black')
    preview=next(f for f in files if f['role']=='new source preview')
    need(ImageChops.difference(expected_image,Image.open(preview['candidate']['path']).convert('RGB')).getbbox() is None,'New preview exactly renders full corrected grid with bound font')
    notes=next(f for f in files if f['role']=='new source review notes');note=Path(notes['candidate']['path']).read_text('utf-8')
    need('first-created review artifacts' in note and 'historical acceptance receipt remain unchanged' in note and answer['raw_answer'] in note,'New notes honestly distinguish current correction from retained history')
    # Recheck all live preimages and immutable sources after the complete review.
    for f in files:
        need((not Path(f['target']).exists()) if f['before'] is None else sha(Path(f['target']).read_bytes())==f['before']['sha256'],'Publication preimage remains current: '+str(f['target']))
    for key in ['source','predecessor_acceptance','historical_repository_acceptance']:checked(m[key])
    report['passed']=True
    report['accepted_targets']=[f['target'] for f in files]
    report['candidate_bindings']=[bind(MANIFEST),bind(Path(__file__)),*[f['candidate'] for f in files],*[m[k] for k in ['source','human_authority','source_crop','predecessor_acceptance','historical_repository_acceptance','render_font','preparation_script']],m['corroboration']['text']]
except Exception as error:
    report['failures'].append(str(error))
report['checks_completed']=len(checks);report['checks']=checks
out=BASE/'Independent acceptance.json'
if out.exists():raise ValueError('Refusing to replace prior independent acceptance')
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'failures':report['failures'],'checks':len(checks),'acceptance':bind(out)},indent=2))

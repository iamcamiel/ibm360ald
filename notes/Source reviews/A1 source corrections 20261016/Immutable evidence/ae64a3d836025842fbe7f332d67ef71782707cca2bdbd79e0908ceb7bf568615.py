"""Read-only independent exact-scope review of the bound A1122 native repair."""
from pathlib import Path
import copy,json,hashlib
from datetime import datetime,timezone
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).parent
STAGE=ROOT/'A1 source stages/A1122-01-v2'
MANIFEST=STAGE/'Stage manifest.json'
EXPECTED='21d493ef3d09024a9858f88d65a29fe006bece4c365700455f5a905d0007df49'
checks=0
def need(ok,why):
    global checks
    checks+=1
    if not ok:raise AssertionError(why)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def checked(link):need(sha(link['path'])==link['sha256'],'Exact evidence hash '+link['path']);return Path(link['path'])
def pointer(doc,p):
    for part in p.strip('/').split('/'):
        part=part.replace('~1','/').replace('~0','~')
        doc=doc[int(part)] if isinstance(doc,list) else doc[part]
    return doc
def replace(doc,p,value):
    parent,key=p.rsplit('/',1);item=pointer(doc,parent)
    item[int(key) if isinstance(item,list) else key]=value
def diff(a,b,p=''):
    if type(a)!=type(b):return [(p,a,b)]
    if isinstance(a,dict):
        need(a.keys()==b.keys(),'JSON key topology unchanged '+p)
        return [r for k in a for r in diff(a[k],b[k],p+'/'+k.replace('~','~0').replace('/','~1'))]
    if isinstance(a,list):
        need(len(a)==len(b),'JSON array topology unchanged '+p)
        return [r for i,(x,y) in enumerate(zip(a,b)) for r in diff(x,y,p+'/'+str(i))]
    return [] if a==b else [(p,a,b)]
need(sha(MANIFEST)==EXPECTED,'Frozen stage manifest')
m=read(MANIFEST)
need(m['page']=='A1122-01' and m['board']=='02A-B2' and m['source_scan_id']=='70','Exact reviewed source identity')
need(m['published'] is False and m['independent_acceptance_required'] is True,'Private staged state')
need(m['exact_meaningful_cell_changes']==[dict(row=44,column=113,before='5',after='3')] and not m['trailing_space_padding'],'Single native character scope')
for key in ['source','human_authority','predecessor_acceptance','historical_repository_acceptance','historical_repository_original','font','preparation_script','predecessor_adapter','registry_predecessor','registration_helper']:
    checked(m[key])
for link in m['metadata_preimages']:checked(link)
authority=read(m['human_authority']['path'])
need(authority['selected_records']==['70:89:43'],'Exact authority record')
for key in ['coordinator_native_readings','pin_publication_verification','active_entry_helper']:checked(authority[key])
register=ROOT/'Group 1 source review/A1 calibration/A1 crop candidates.json'
native=next(c for c in read(register)['cases'] if c['record_id']=='70:89:43')
need(native['source']==m['source'],'Native locator bound to same TIFF')
crop=checked(m['source_crop'])
need(sha(crop)==native['native_crop']['sha256'],'Native crop same reviewed occurrence')
with Image.open(m['source']['path']) as src,Image.open(crop) as tile:
    actual=src.crop(native['native_crop']['box']).convert('RGB')
    need(actual.size==tile.size and actual.tobytes()==tile.convert('RGB').tobytes(),'Native crop reproduced pixel-for-pixel')
need(Path(m['historical_repository_acceptance']['path']).read_bytes()==Path(m['historical_repository_original']['path']).read_bytes(),'Historical acceptance preserved byte-for-byte')
files=m['files'];need(len(files)==10 and len({f['target'] for f in files})==10,'Ten unique exact target files')
jsonops=0;txts=[];jsonmodels=[]
for f in files:
    target=Path(f['target']);after=checked(f['candidate'])
    if f['before'] is None:
        need(not target.exists(),'Previously absent companion guard '+str(target))
        need(f['role'] in ['source review notes','source preview'],'Only missing notes/preview may be created')
    else:
        before=checked(f['before']);need(target.is_file() and sha(target)==f['before']['sha256'],'Current exact preimage '+str(target))
        if target.suffix.lower()=='.txt':
            a,b=before.read_text(encoding='utf-8-sig').splitlines(),after.read_text(encoding='utf-8-sig').splitlines()
            need(len(a)==len(b) and list(map(len,a))==list(map(len,b)),'TXT grid unchanged')
            delta=[dict(row=y,column=x,before=c,after=d) for y,(row1,row2) in enumerate(zip(a,b)) for x,(c,d) in enumerate(zip(row1,row2)) if c!=d]
            need(delta==f['changes']==m['exact_meaningful_cell_changes'],'TXT only exact source character')
            need('5800483 0483' in b[44],'Correct source part and type literal')
            txts.append(after.read_bytes())
        elif target.suffix.lower()=='.json':
            a,b=read(before),read(after);changes=diff(a,b)
            need(sorted(changes,key=lambda x:x[0])==sorted([(p['pointer'],p['before'],p['after']) for p in f['changes']],key=lambda x:x[0]),'JSON exact patch list has no hidden mutation')
            rebuilt=copy.deepcopy(a)
            for p in f['changes']:
                need(pointer(a,p['pointer'])==p['before'],'JSON before token')
                replace(rebuilt,p['pointer'],p['after'])
                # All identity replacements must belong to the same source physical record.
                base=p['pointer'].rsplit('/',1)[0]
                if '/printed_lines/' in p['pointer']:base=base.rsplit('/',1)[0]
                physical=pointer(b,base)
                need(physical.get('card_type')=='0483' and physical.get('part_number')=='5800483','Same exact native card identity')
                if 'board' in physical:need(physical['board']=='02A-B2' and physical['sockets']==['D3'],'Same exact physical site')
                else:need(physical['socket']=='D3','Main socket model physical site')
            need(rebuilt==b,'Complete independent JSON patch replay')
            jsonops+=len(f['changes'])
            if 'sockets' in b:jsonmodels.append(b)
need(len(txts)==2 and txts[0]==txts[1],'Working and repository TXT identical')
need(len(jsonmodels)==2 and jsonmodels[0]==jsonmodels[1],'Working and repository source model identical')
need(jsonops==30,'Thirty scoped active identity mirror fields')
need(jsonmodels[0]['sockets'][21]['references']==[
    {'ALD_page':'MC071','printed_portions':['A1','A2','A3','A4']},
    {'ALD_page':'MC066','printed_portions':['B1','B2','B3','B4']},
    {'ALD_page':'MC071','printed_portions':['C1']}],'Source page/portion mapping retained')
visible=txts[0].decode('utf-8-sig').splitlines()
font=ImageFont.truetype(m['font']['path'],18);cw=round(font.getlength('M'))
im=Image.new('RGB',(32+max(map(len,visible))*cw,32+len(visible)*25),'white');draw=ImageDraw.Draw(im)
for y,line in enumerate(visible):draw.text((16,16+y*25),line,font=font,fill='black')
preview=next(f for f in files if f['role']=='source preview')
with Image.open(preview['candidate']['path']) as tile:need(tile.size==im.size and tile.convert('RGB').tobytes()==im.tobytes(),'Candidate preview is exact rendering of corrected grid')
notes=Path(next(f for f in files if f['role']=='source review notes')['candidate']['path']).read_text(encoding='utf-8-sig')
need('02A-B2 D3: 5800483 0485 -> 5800483 0483' in notes and 'Acceptance and publication are separate receipts.' in notes,'New review note describes exact correction without inventing prior acceptance')
need(sha(MANIFEST)==EXPECTED,'Stage epoch unchanged at final check')
for f in files:
    checked(f['candidate'])
    if f['before'] is not None:need(sha(f['target'])==f['before']['sha256'],'Final target preimage epoch')
for key in ['source','historical_repository_original','predecessor_adapter','registry_predecessor']:checked(m[key])
for link in m['metadata_preimages']:checked(link)
receipt={'schema':'independent-native-a1-stage-acceptance-v1','passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'check_count':checks,
 'stage_manifest':{'path':str(MANIFEST),'sha256':EXPECTED},'reviewer':{'path':str(Path(__file__)),'sha256':sha(__file__)},
 'native_reading':'A1122-01 02A-B2 D3, SINGLE CARD, 5800483 0483. Last type glyph matches the native part number and source header; independently viewed.',
 'file_count':len(files),'meaningful_txt_cells':1,'active_json_fields':jsonops,
 'candidate_bindings':[dict(target=f['target'],role=f['role'],before=f['before'],candidate=f['candidate']) for f in files],
 'source_or_canonical_writes':False,'acceptance_scope':'Only this frozen stage, exact same-site source literal correction and active mirrors; no generic nodes schema, no historical ledger rewrite, no publication performed.'}
dest=STAGE/'Independent stage acceptance.json';need(not dest.exists(),'Acceptance receipt must not overwrite history')
dest.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':True,'checks':checks,'receipt':str(dest),'sha256':sha(dest)},indent=2))

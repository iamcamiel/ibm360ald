"""Read-only mechanical check of the private A1241 exact-site stage."""
import hashlib, importlib.util, json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald'
OUT=ROOT/'tmp/ald-text/ald/uniform-socket-listings/source-review/A1241-C3-3388-addendum'
sys.path.insert(0,str(REPO/'tools/reviews'))
import source_review as sr
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(v,m):
    if not v:raise ValueError(m)
manifest=OUT/'Stage manifest.json';stage=read(manifest);count=0
for name in ('source','human_authority','source_crop','predecessor_acceptance','historical_repository_acceptance',
             'historical_repository_original','preparation_script','font','predecessor_adapter','registry_predecessor','registration_helper'):
    sr.checked(stage[name],OUT);count+=1
for link in stage['metadata_preimages']:sr.checked(link,OUT);count+=1
check(stage['artifact_schema']=='reviewed-current-A1-socket-table-quartet-v1'and stage['model_schema']=='socket-page-records-v1','False table schema')
check(stage['exact_meaningful_cell_changes']==[{'row':88,'column':68,'before':'6','after':'8'},{'row':88,'column':73,'before':'6','after':'8'}],'Changed source delta')
check(len(stage['files'])==10,'Unexpected file count')
json_fields=0;text_files=0
for item in stage['files']:
    target=Path(item['target']);_,before=sr.checked(item['before'],OUT);_,after=sr.checked(item['candidate'],OUT)
    check(target.read_bytes()==before,'Live predecessor changed');count+=3
    if item['role']in{'working accepted TXT','repository accepted TXT'}:
        before_rows=before.decode('utf-8-sig').splitlines(keepends=True);after_rows=after.decode('utf-8-sig').splitlines(keepends=True)
        check(len(before_rows)==len(after_rows),'Text row count changed')
        deltas=[]
        for row,(a,b)in enumerate(zip(before_rows,after_rows)):
            check(len(a)==len(b),'Text line width changed')
            deltas.extend({'row':row,'column':i,'before':x,'after':y}for i,(x,y)in enumerate(zip(a,b))if x!=y)
        check(deltas==stage['exact_meaningful_cell_changes'],'Undeclared text cells or line endings changed');text_files+=1;count+=2
    elif target.suffix=='.json':
        a=json.loads(before.decode('utf-8-sig'));b=json.loads(after.decode('utf-8-sig'))
        actual=sr.json_delta_paths(a,b);expected=[x['pointer']for x in item['changes']]
        check(set(actual)==set(expected)and len(actual)==len(expected),'Undeclared JSON semantic delta')
        for change in item['changes']:
            parts=sr.pointer_parts(change['pointer']);old=a;new=b
            for part in parts[:-1]:old=old[int(part)]if isinstance(old,list)else old[part];new=new[int(part)]if isinstance(new,list)else new[part]
            field=parts[-1]
            check(field in{'part_number','card_type'},'JSON field beyond part/card type')
            check(old[field]==change['before']and new[field]==change['after'],'Wrong JSON preimage/value')
            board=old.get('board',a.get('board'));sockets=old.get('sockets')or[old.get('socket')]
            check(board=='02B-D1'and sockets==['C3'],'Changed another socket')
            check((old[field],new[field])in{('5803368','5803388'),('3368','3388')},'Wrong code replacement');json_fields+=1;count+=4
    elif item['role']=='source review notes':
        check(after.startswith(before.rstrip(b'\r\n')),'Existing notes not retained');count+=1
check(text_files==2 and json_fields==36,'Unexpected correction counts')
text=next(sr.checked(x['candidate'],OUT)[1]for x in stage['files']if x['role']=='working accepted TXT')
rows=text.decode('utf-8-sig').splitlines();font=ImageFont.truetype(stage['font']['path'],18);cw=round(font.getlength('M'))
im=Image.new('RGB',(32+max(map(len,rows))*cw,32+len(rows)*25),'white');draw=ImageDraw.Draw(im)
for y,line in enumerate(rows):draw.text((16,16+y*25),line,font=font,fill='black')
preview=next(sr.checked(x['candidate'],OUT)[0]for x in stage['files']if x['role']=='source preview')
with Image.open(preview)as expected:check(im.size==expected.size and im.tobytes()==expected.convert('RGB').tobytes(),'Candidate preview differs from exact text render');count+=1
native=read(ROOT/'tmp/ald-text/ald/socket-ald-audit/reverse-systemic-analysis/native/A1241-01 C3 finding.json')
with Image.open(stage['source']['path'])as original,Image.open(stage['source_crop']['path'])as crop:
    check(original.convert('RGB').crop(native['native_crop']['box']).tobytes()==crop.convert('RGB').tobytes(),'Native crop pixels differ');count+=1
report={'schema':'private-a1241-preparation-mechanical-verification-v1','passed':True,'independent_acceptance':False,
        'manifest':sr.binding(manifest),'tool':sr.binding(__file__),'checks':count,'source_cells':2,'text_artifacts':2,
        'json_fields':json_fields,'candidate_files':10,'source_scan_writes':0,'source_changes_applied':False}
sr.atomic_write(OUT/'Mechanical verification.json',sr.encode(report));print(json.dumps(report,indent=2))

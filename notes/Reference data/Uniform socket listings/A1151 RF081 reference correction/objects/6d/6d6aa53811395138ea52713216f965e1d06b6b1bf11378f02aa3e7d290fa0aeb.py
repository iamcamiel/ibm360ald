"""Mechanical read-only scope verification; independent acceptance is separate."""
from pathlib import Path
import json,sys
from PIL import Image,ImageDraw,ImageFont
from prepare_rf081_addendum import fix_rf_json,ROOT,REPO,OUT,read,sha,bind
sys.path.insert(0,str(REPO/'tools/reviews'));import source_review as sr
def need(v,m):
    if not v:raise ValueError(m)
manifest=OUT/'Stage manifest.json';stage=read(manifest);checks=0;json_ops=0;new=[]
for key in ('source','human_authority','source_crop','predecessor_acceptance','historical_repository_acceptance',
            'historical_repository_original','preparation_script','font','predecessor_adapter','registry_predecessor','registration_helper'):
    sr.checked(stage[key],OUT);checks+=1
for link in stage['metadata_preimages']:sr.checked(link,OUT);checks+=1
need(stage['artifact_schema']=='reviewed-current-A1-socket-table-quartet-v1'and stage['model_schema']=='socket-page-sockets-v1','Actual schema differs')
need(stage['exact_meaningful_cell_changes']==[{'row':93,'column':98,'before':'9','after':'8'}],'Source authority differs')
for item in stage['files']:
    target=Path(item['target']);_,after=sr.checked(item['candidate'],OUT)
    if item['before']:
        _,before=sr.checked(item['before'],OUT);need(target.read_bytes()==before,'Stale source predecessor');checks+=2
    else:
        need(not target.exists(),'New artifact already exists');before=None;new.append(item['role']);checks+=1
    if target.suffix=='.json':
        expected,changes=fix_rf_json(json.loads(before.decode('utf-8-sig')))
        need(expected==json.loads(after.decode('utf-8-sig')),'JSON candidate does not replay exact-site transform')
        need(changes==item['changes'],'JSON scope declaration differs');json_ops+=len(changes);checks+=2
        # No change may touch the unrelated N6 connector endpoint.
        old_count=before.decode('utf-8-sig').count('RF091BH4');new_count=after.decode('utf-8-sig').count('RF091BH4')
        need(old_count==new_count,'Unrelated connector RF091BH4 changed');checks+=1
    elif item['role']in{'working accepted TXT','repository accepted TXT'}:
        a=before.decode('utf-8-sig').splitlines(keepends=True);b=after.decode('utf-8-sig').splitlines(keepends=True)
        need(len(a)==len(b),'Text height changed');delta=[]
        for row,(x,y)in enumerate(zip(a,b)):
            need(len(x)==len(y),'Line width or ending changed')
            delta.extend({'row':row,'column':i,'before':l,'after':r}for i,(l,r)in enumerate(zip(x,y))if l!=r)
        need(delta==stage['exact_meaningful_cell_changes'],'Undeclared source cells');checks+=2
need(sorted(new)==['source preview','source review notes'],'Only explicitly absent companions may be created')
text=next(sr.checked(x['candidate'],OUT)[1]for x in stage['files']if x['role']=='working accepted TXT')
rows=text.decode('utf-8-sig').splitlines();font=ImageFont.truetype(stage['font']['path'],18);cw=round(font.getlength('M'))
image=Image.new('RGB',(32+max(map(len,rows))*cw,32+len(rows)*25),'white');draw=ImageDraw.Draw(image)
for y,line in enumerate(rows):draw.text((16,16+y*25),line,font=font,fill='black')
preview=next(sr.checked(x['candidate'],OUT)[0]for x in stage['files']if x['role']=='source preview')
with Image.open(preview)as expected:need(image.size==expected.size and image.tobytes()==expected.convert('RGB').tobytes(),'Preview differs from text');checks+=1
need(json_ops==19 and len(stage['files'])==11,'Candidate inventory differs')
report={'schema':'private-rf081-preparation-mechanical-verification-v1','passed':True,'independent_acceptance':False,
    'manifest':bind(manifest),'tool':bind(__file__),'checks':checks,'source_cells':1,'json_operations':19,'candidate_files':11,
    'new_companions':new,'source_changes_applied':False,'source_scan_writes':0,'unrelated_N6_reference_preserved':True}
sr.atomic_write(OUT/'Mechanical verification.json',sr.encode(report));print(json.dumps(report,indent=2))

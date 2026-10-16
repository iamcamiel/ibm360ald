"""Independently inspect the one-cell C3 F1/H1 reference successor."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';BASE=ROOT/'tmp/ald-text/ald/socket-ald-audit'
OUT=ROOT/'tmp/ald-text/ald/uniform-socket-listings/source-review/A1241-C3-AP781-reference-addendum'
sys.path.insert(0,str(REPO/'tools/reviews'));import source_review as sr
checks=0
def check(value,message):
 global checks
 checks+=1
 if not value:raise ValueError(message)
def read(path):return json.loads(Path(path).read_text('utf-8-sig'))
def raw_json(raw):return json.loads(raw.decode('utf-8-sig'))
def binding(path):return {'path':str(Path(path).resolve()),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}
def bound(link):
 path=Path(link['path']);check(binding(path)['sha256']==link['sha256'],'Changed binding '+str(path));return path
def site(item,board=None):
 sockets=item.get('sockets')or([item.get('socket')]if item.get('socket')else[])
 return item.get('board',board)=='02B-D1'and sockets==['C3']
def independently_expected(before):
 expected=deepcopy(before);count=0
 for collection in ('records','logical_records','sockets','sections'):
  for item in expected.get(collection,[])if isinstance(expected.get(collection),list)else[]:
   if not isinstance(item,dict)or not site(item,expected.get('board')):continue
   for ref in item.get('references',[]):
    if ref.get('portions',ref.get('printed_portions'))!=['F1','H1']:continue
    for key in ('ALD_page','ald_page','page'):
     if ref.get(key)=='AP741':
      check(item.get('part_number')=='5803388'and item.get('card_type')=='3388','Reference on wrong physical card')
      ref[key]='AP781';count+=1
 buckets=expected.get('ALD_pages')
 if buckets is None and expected and all(isinstance(x,list)for x in expected.values()):buckets=expected
 if isinstance(buckets,dict):
  moved=[];remaining=[]
  for item in buckets.get('AP741',[]):
   if isinstance(item,dict)and item.get('kind')=='card portion'and site(item,expected.get('board'))and item.get('portion')in('F1','H1'):
    check(item.get('part_number')=='5803388'and item.get('card_type')=='3388','Bucket entry on wrong card');moved.append(item)
   else:remaining.append(item)
  if moved:
   check(sorted(x['portion']for x in moved)==['F1','H1'],'Wrong moved portions')
   if remaining:buckets['AP741']=remaining
   else:del buckets['AP741']
   buckets.setdefault('AP781',[]).extend(moved);count+=2
 return expected,count

def main():
 manifest_path=OUT/'Stage manifest.json';stage=read(manifest_path)
 check(stage['page']=='A1241-01'and stage['source_scan_id']=='126'and stage['board']=='02B-D1','Wrong source page')
 check(stage['artifact_schema']=='reviewed-current-A1-socket-table-quartet-v1'and stage['model_schema']=='socket-page-records-v1','Wrong actual table schema')
 edit=[{'row':92,'column':59,'before':'4','after':'8'}]
 check(stage['exact_meaningful_cell_changes']==edit,'Wrong source cell')
 for key in ('source','source_crop','human_authority','predecessor_acceptance','historical_repository_acceptance','historical_repository_original','preparation_script','font','predecessor_adapter','registry_predecessor','registration_helper','preceding_RF_publication','native_finding'):bound(stage[key])
 for link in stage['metadata_preimages']:bound(link)
 prior=read(stage['preceding_RF_publication']['path']);check(prior['passed']is True and prior['published']is True,'RF release incomplete')
 finding=read(stage['native_finding']['path']);check(finding['reading']=='AP781 F1 H1','Wrong native source finding')
 with Image.open(stage['source']['path'])as original,Image.open(stage['source_crop']['path'])as tile:
  actual=original.convert('RGB').crop(finding['native_crop']['box']);check(actual.size==tile.size and actual.tobytes()==tile.convert('RGB').tobytes(),'Native source crop changed')
 txt=[];json_count=0;semantic_changes=0;targets=set()
 for item in stage['files']:
  target=Path(item['target']).resolve();check(target.is_relative_to(ROOT)and target.suffix.lower()not in('.tif','.tiff'),'Target scope')
  check(target not in targets,'Duplicate target');targets.add(target)
  before=bound(item['before']).read_bytes();after=bound(item['candidate']).read_bytes();check(target.read_bytes()==before,'Current predecessor changed')
  if item['role']in('working accepted TXT','repository accepted TXT'):
   a=before.decode('utf-8-sig').splitlines(keepends=True);b=after.decode('utf-8-sig').splitlines(keepends=True)
   check(len(a)==len(b),'Source row count')
   delta=[]
   for row,(left,right)in enumerate(zip(a,b)):
    check(len(left)==len(right),'Source line width changed')
    delta.extend({'row':row,'column':col,'before':x,'after':y}for col,(x,y)in enumerate(zip(left,right))if x!=y)
   check(delta==edit and len(before)==len(after),'Text changed beyond one native cell')
   check('5803388 3388'in b[88]and b[92][56:61]=='AP781','Corrected card identity not retained');txt.append(after)
  elif target.suffix.lower()=='.json':
   old=raw_json(before);actual=raw_json(after);expected,count=independently_expected(old)
   check(count>0 and actual==expected,'JSON differs beyond exact C3 F1/H1 references')
   json_count+=1;semantic_changes+=count
  elif item['role']=='source review notes':check(after.startswith(before.rstrip(b'\r\n')),'Historical notes changed')
  else:check(item['role']=='source preview','Unexpected staged artifact')
 check(len(stage['files'])==10 and len(txt)==2 and txt[0]==txt[1]and json_count==6,'Wrong file scope')
 rows=txt[0].decode('utf-8-sig').splitlines();font=ImageFont.truetype(stage['font']['path'],18);cw=round(font.getlength('M'))
 im=Image.new('RGB',(32+max(map(len,rows))*cw,32+len(rows)*25),'white');draw=ImageDraw.Draw(im)
 for y,line in enumerate(rows):draw.text((16,16+y*25),line,font=font,fill='black')
 preview=next(Path(x['candidate']['path'])for x in stage['files']if x['role']=='source preview')
 with Image.open(preview)as expected:check(im.size==expected.size and im.tobytes()==expected.convert('RGB').tobytes(),'Preview does not render exact candidate text')
 result=subprocess.run([sys.executable,'-X','utf8',str(BASE/'test_a1241_reference_scope.py')],cwd=ROOT,capture_output=True,text=True)
 (OUT/'Independent scope tests.txt').write_text(result.stdout+result.stderr,encoding='utf-8');check(result.returncode==0,'Scope tests failed')
 report={'schema':'socket-table-literal-correction-independent-acceptance-v1','passed':True,'independent_review':True,'failures':[],
  'manifest_sha256':binding(manifest_path)['sha256'],'manifest':binding(manifest_path),'reviewer':'/root/reverse_socket_audit',
  'reviewed_utc':datetime.now(timezone.utc).isoformat(),'checks':checks,'source_cells':1,'json_files':json_count,'json_reference_entries':semantic_changes,
  'native_visual_reading':'C3 F1/H1 line clearly prints AP781. Native crop independently viewed before review; crop pixels also verified against the source TIFF.',
  'scope':'Only C3 F1/H1 AP741 -> AP781; existing 5803388/3388 remains unchanged; no direct human glyph answer claimed.',
  'review_tool':binding(__file__),'scope_tests':binding(OUT/'Independent scope tests.txt'),'source_changes_applied':False}
 sr.atomic_write(OUT/'Independent acceptance.json',sr.encode(report));print(json.dumps(report,indent=2))
if __name__=='__main__':main()

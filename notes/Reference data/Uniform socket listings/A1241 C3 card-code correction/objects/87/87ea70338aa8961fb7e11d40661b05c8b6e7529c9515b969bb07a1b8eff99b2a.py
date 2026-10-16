"""Independent exact-source and physical-site review; no publication."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import csv,hashlib,importlib.util,json,os,subprocess,sys
from PIL import Image,ImageDraw,ImageFont

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).resolve().parent
MANIFEST=HERE/'Stage manifest.json';TOOLS=ROOT/'tmp/ald-text/ald/socket-ald-audit'
EXPECTED='ea9d5e27128e09f5c7ba9ce957cee8a546cbc5d7539d7114c3c2091aca69eaaf'
checks=[];bindings={}
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def digest(b):return hashlib.sha256(b).hexdigest()
def need(v,m):
 if not v:raise ValueError(m)
 checks.append(m)
def bind(p,expected=None):
 p=Path(p).resolve();h=digest(p.read_bytes())
 if expected:need(h==expected,'Exact bound hash '+str(p))
 if str(p)in bindings:need(bindings[str(p)]==h,'Single review epoch '+str(p))
 bindings[str(p)]=h;return {'path':str(p),'sha256':h}
def checked(b):return Path(bind(b['path'],b['sha256'])['path'])
def pointer(v,path):
 for t in path.split('/')[1:]:t=t.replace('~1','/').replace('~0','~');v=v[int(t)]if isinstance(v,list)else v[t]
 return v
def delta(a,b,path=''):
 if type(a)is type(b)and a==b:return []
 if isinstance(a,dict)and isinstance(b,dict):
  result=[]
  for k in sorted(set(a)|set(b)):
   p=path+'/'+k.replace('~','~0').replace('/','~1');result+=delta(a[k],b[k],p)if k in a and k in b else[p]
  return result
 if isinstance(a,list)and isinstance(b,list)and len(a)==len(b):return[p for i,(x,y)in enumerate(zip(a,b))for p in delta(x,y,path+'/'+str(i))]
 return[path]
report={'schema':'socket-table-literal-correction-independent-acceptance-v1','independent_review':True,'reviewer':'/root/promote_continuation_fix','passed':False,'failures':[],'created_utc':datetime.now(timezone.utc).isoformat(),'source_or_repository_publication':False,'manifest_sha256':digest(MANIFEST.read_bytes())}
try:
 bind(MANIFEST,EXPECTED);stage=load(MANIFEST)
 need(stage['page']=='A1241-01'and stage['board']=='02B-D1'and stage['source_scan_id']=='126','Exact source page/board/scan')
 need(stage['artifact_schema']=='reviewed-current-A1-socket-table-quartet-v1'and stage['model_schema']=='socket-page-records-v1','Actual records-list table schema')
 need(stage['exact_meaningful_cell_changes']==[{'row':88,'column':68,'before':'6','after':'8'},{'row':88,'column':73,'before':'6','after':'8'}]and not stage['trailing_space_padding'],'Two source cells only; no padding')
 for k in ['source','human_authority','source_crop','predecessor_acceptance','historical_repository_acceptance','historical_repository_original','preparation_script','font','predecessor_adapter','registry_predecessor','registration_helper']:checked(stage[k])
 for b in stage['metadata_preimages']:checked(b)
 expected_meta={REPO/'notes/Content data manifest.json',REPO/'notes/Reviewed export provenance.json',ROOT/'tmp/ald-text/ald/repository-export/last export manifest.json',REPO/'notes/A1 Socket Listing/A1241-01 SOCKET LISTING review notes.txt',REPO/'notes/A1 Socket Listing/A1241-01 SOCKET LISTING review record.json'}
 need({Path(b['path'])for b in stage['metadata_preimages']}==expected_meta,'Frozen metadata inventory exactly five scoped files')
 need((REPO/'notes/Reviewed export provenance.json').read_bytes()==(ROOT/'tmp/ald-text/ald/repository-export/last export manifest.json').read_bytes(),'Current export/provenance baseline bytes agree')
 authority=load(stage['human_authority']['path']);plan=load(checked(authority['exact_cell_plan']));finding=load(checked(authority['native_finding']))
 need('no invented direct-human glyph answer'in authority['scope'],'Native resolution authority does not claim a human glyph answer')
 need(stage['source']==plan['native_source']and stage['source_crop']['sha256']==plan['native_crop']['sha256'],'Native source/crop match source-cell plan')
 with Image.open(stage['source']['path'])as original,Image.open(stage['source_crop']['path'])as crop:
  need(original.convert('RGB').crop(plan['native_crop']['box']).tobytes()==crop.convert('RGB').tobytes(),'Exact native crop pixels')
 need(stage['source']['sha256']=='67a13b47ef667d0f42e0d78d1702d2ab8e6d4b6b12616c5ee66211b2653ed2d7','Reviewed original TIFF epoch')
 # Visual review was performed directly on the native C3 crop in this agent turn.
 report['native_visual_review']={'reading':'5803388 3388','printed_kind':'SINGLE CARD','socket':'C3','crop_visually_inspected':True,'handwriting_used':False,'page_references_not_changed':True}
 text=ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing/A1241-01 SOCKET LISTING.txt';model=text.with_suffix('.json')
 expected_targets={text,model,REPO/'ALD/A1 Socket Listing'/text.name,REPO/'json/A1 Socket Listing'/model.name,text.with_name(text.stem+' review notes.txt'),text.with_name(text.stem+' preview.png')}
 for folder in[ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing',REPO/'json/A1 Socket Listing']:
  expected_targets|={folder/'Socket reference.json',folder/'ALD references.json'}
 need(len(stage['files'])==10 and {Path(f['target'])for f in stage['files']}==expected_targets,'Exact ten source/model/current-mirror/note/preview targets')
 newtexts=[];json_fields=0
 for f in stage['files']:
  p=Path(f['target']);before=checked(f['before']).read_bytes();after=checked(f['candidate']).read_bytes();need(p.read_bytes()==before,'Current publication preimage '+str(p))
  need(p.is_relative_to(ROOT)and p.suffix.lower()not in{'.tif','.tiff'},'Write target confined outside native scans')
  if f['role']in{'working accepted TXT','repository accepted TXT'}:
   need(before.startswith(b'\xef\xbb\xbf')==after.startswith(b'\xef\xbb\xbf'),'TXT BOM preserved')
   a=before.decode('utf-8-sig').splitlines(keepends=True);b=after.decode('utf-8-sig').splitlines(keepends=True);need(len(a)==len(b),'TXT row count preserved');changes=[]
   for y,(s,t)in enumerate(zip(a,b)):
    need(len(s)==len(t)and s[len(s.rstrip('\r\n')):]==t[len(t.rstrip('\r\n')):],'TXT row width/end preserved '+str(y))
    changes += [{'row':y,'column':x,'before':c,'after':d}for x,(c,d)in enumerate(zip(s,t))if c!=d]
   need(changes==stage['exact_meaningful_cell_changes'],'TXT only declared two cells');need('5803368 3368'in a[88]and'5803388 3388'in b[88],'Complete literal part/card numbers corrected');newtexts.append(after)
  elif p.suffix=='.json':
   a=json.loads(before.decode('utf-8-sig'));b=json.loads(after.decode('utf-8-sig'));actual=delta(a,b);declared=[c['pointer']for c in f['changes']]
   need(set(actual)==set(declared)and len(actual)==len(declared),'Every JSON semantic change declared '+str(p))
   for c in f['changes']:
    field=c['pointer'].rsplit('/',1)[1];record=pointer(a,c['pointer'].rsplit('/',1)[0]);need(field in{'part_number','card_type'},'Only part/type field')
    need(pointer(a,c['pointer'])==c['before']and pointer(b,c['pointer'])==c['after'],'Exact JSON preimage/reading')
    need((c['before'],c['after'])in{('5803368','5803388'),('3368','3388')},'Only 3368/3388 reading change')
    need(record.get('board',a.get('board'))=='02B-D1'and record.get('sockets',[record.get('socket')])==['C3'],'Only exact physical socket C3')
    need(c['pointer'].split('/')[1]in{'records','logical_records','ALD_pages'},'Only active record/bucket entries, no history/prose')
    json_fields+=1
   need(set(a.get('ALD_pages',{}))==set(b.get('ALD_pages',{})),'ALD page buckets unchanged')
  elif f['role']=='source review notes':need(after.startswith(before.rstrip(b'\r\n'))and b'5803388 3388'in after,'Source notes extended, prior text retained')
 need(len(newtexts)==2 and newtexts[0]==newtexts[1],'Working/repository TXT agree');need(json_fields==36,'Exactly 36 current JSON fields')
 rows=newtexts[0].decode('utf-8-sig').splitlines();font=ImageFont.truetype(stage['font']['path'],18);cw=round(font.getlength('M'));image=Image.new('RGB',(32+max(map(len,rows))*cw,32+len(rows)*25),'white');draw=ImageDraw.Draw(image)
 for y,line in enumerate(rows):draw.text((16,16+y*25),line,font=font,fill='black')
 preview=next(f for f in stage['files']if f['role']=='source preview')
 with Image.open(preview['candidate']['path'])as actual:need(image.size==actual.size and image.tobytes()==actual.convert('RGB').tobytes(),'Full preview exactly renders corrected text')
 s=importlib.util.spec_from_file_location('independent_a1241_helper',stage['registration_helper']['path']);app=importlib.util.module_from_spec(s);s.loader.exec_module(app)
 actual_model=next(f['candidate']for f in stage['files']if Path(f['target'])==model);need(app.validate_table_model(Path(actual_model['path']),stage),'Actual candidate passes honest table/external-source guard')
 need(set(app.expected_artifacts(text,stage))=={'txt','json','notes','preview'},'True quartet inventory')
 for name,expected in [('publish_a1241_addendum.py','e9b3cc651c59f3f606dc534098c103dee7d9ec4ae30e2a1933455f013e345ef7'),('test_a1241_addendum_scope.py','57ec9f94b082383aa52e75d3451fc943dd799b8983a09c86e987288c42c39e67'),('prepare_a1241_addendum.py','41ef17bbcdf7490830aaa769dc07388ac9373ebe0ab78ba021ccdb86b28610ba')]:bind(TOOLS/name,expected)
 publisher=(TOOLS/'publish_a1241_addendum.py').read_text('utf-8')
 for safeguard in ["cli.add_argument('--publish',action='store_true')","for link in stage['metadata_preimages']:checked(link)","if key in frozen:need(old is not None and sha(old)==frozen[key]","'Unrelated adapter items changed'","'Unrelated registry entries changed'","'Unrelated export entry changed'","for key in reversed(list(dict.fromkeys(written)))","'uniform_rebuild_deferred':True"]:need(safeguard in publisher,'Publisher reviewed safeguard '+safeguard)
 report['publisher_review']={'default_read_only_preflight':True,'exact_source_and_metadata_preimage_guards':True,'adapter_registry_other_items_retained':True,'rollback_source_data_and_metadata':True,'transient_export_plan_log_not_rollback':True,'uniform_rebuild_intentionally_deferred_to_coordinator':True,'original_tiff_writes':False}
 env=dict(os.environ,TEMP=str(ROOT/'tmp/socket-uniform-test-temp'),TMP=str(ROOT/'tmp/socket-uniform-test-temp'))
 proc=subprocess.run([sys.executable,'-X','utf8','-m','unittest','discover','-s',str(TOOLS),'-p','test_a1241_addendum_scope.py','-v'],cwd=ROOT,env=env,capture_output=True,text=True)
 log=HERE/'Independent scope tests.txt';log.write_text(proc.stdout+proc.stderr,encoding='utf-8');need(proc.returncode==0 and'Ran 6 tests'in proc.stderr,'Six exact-site regression tests pass');bind(log)
 bind(__file__)
 for p,h in list(bindings.items()):need(digest(Path(p).read_bytes())==h,'Final bound epoch '+p)
 report.update(passed=True,checks_completed=len(checks),checks=checks,source_cells=2,json_fields=36,candidate_files=10,candidate_bindings=[{'path':p,'sha256':h}for p,h in sorted(bindings.items())],stage_manifest=bind(MANIFEST))
except Exception as e:report['failures'].append(str(e));report['checks_completed']=len(checks)
out=HERE/'Independent acceptance.json'
if out.exists():raise ValueError('Refusing to overwrite previous independent acceptance')
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'failures':report['failures'],'checks':report['checks_completed'],'acceptance':bind(out)},indent=2));raise SystemExit(not report['passed'])

"""Independent RF081 human-answer, exact-cell and cache/bucket scope review."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,importlib.util,json,os,subprocess,sys
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).resolve().parent;TOOLS=ROOT/'tmp/ald-text/ald/socket-ald-audit';MAN=HERE/'Stage manifest.json'
EXPECTED='a81f4e79081f0f37dee4f284452dbb3e25bc7af7d5759af0f7e8142abf1a490f'
checks=[];bindings={}
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def need(v,m):
 if not v:raise ValueError(m)
 checks.append(m)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bind(p,expected=None):
 p=Path(p).resolve();h=sha(p.read_bytes())
 if expected:need(h==expected,'Exact binding '+str(p))
 if str(p)in bindings:need(bindings[str(p)]==h,'Single epoch '+str(p))
 bindings[str(p)]=h;return {'path':str(p),'sha256':h}
def checked(link):return Path(bind(link['path'],link['sha256'])['path'])
def parts(p):return[x.replace('~1','/').replace('~0','~')for x in p.split('/')[1:]]
def at(v,p):
 for k in parts(p):v=v[int(k)]if isinstance(v,list)else v[k]
 return v
def setat(v,p,value):
 ts=parts(p);parent=v
 for k in ts[:-1]:parent=parent[int(k)]if isinstance(parent,list)else parent[k]
 parent[int(ts[-1])if isinstance(parent,list)else ts[-1]]=deepcopy(value)
def site(r,root):return r.get('board',root.get('board'))=='02A-E1'and(r.get('sockets')or[r.get('socket')])==['F5']
def primary_exists(root):
 return any(isinstance(r,dict)and site(r,root)and r.get('card_type')=='0512'for key in['sockets','records','logical_records']for r in root.get(key,[])if isinstance(root.get(key),list))
report={'schema':'socket-table-literal-correction-independent-acceptance-v1','independent_review':True,'reviewer':'/root/promote_continuation_fix','passed':False,'failures':[],'created_utc':datetime.now(timezone.utc).isoformat(),'manifest_sha256':sha(MAN.read_bytes()),'source_or_repository_publication':False}
try:
 bind(MAN,EXPECTED);stage=read(MAN)
 need(stage['page']=='A1151-01'and stage['board']=='02A-E1'and stage['source_scan_id']=='92','Exact page/board/scan')
 need(stage['model_schema']=='socket-page-sockets-v1'and stage['artifact_schema']=='reviewed-current-A1-socket-table-quartet-v1','Actual sockets-list quartet; no nodes assumption')
 need(stage['exact_meaningful_cell_changes']==[{'row':93,'column':98,'before':'9','after':'8'}]and not stage['trailing_space_padding'],'One exact source cell')
 for key in['source','human_authority','source_crop','predecessor_acceptance','historical_repository_acceptance','historical_repository_original','preparation_script','font','predecessor_adapter','registry_predecessor','registration_helper']:checked(stage[key])
 for x in stage['metadata_preimages']:checked(x)
 need(len(stage['metadata_preimages'])==5,'Five frozen metadata preimages')
 human=read(stage['human_authority']['path']);need(human['answer']=='RF081 is printed'and human['confirmed_reading']=='RF081'and human['previous_transcription']=='RF091'and human['source_page']=='A1151-01','Exact direct-human answer retained')
 need(human['source_crop']==stage['source_crop'],'Human answer binds the displayed native crop')
 finding=next(f for f in read(TOOLS/'absent-reference-review/Current absent reference findings.json')['findings']if f['unavailable_page']=='RF091');crop=finding['representative_crop'];need(crop['source']==stage['source']and crop['sha256']==stage['source_crop']['sha256'],'Native source/crop epoch')
 with Image.open(stage['source']['path'])as original,Image.open(stage['source_crop']['path'])as tile:need(original.convert('RGB').crop(crop['bounds']).tobytes()==tile.convert('RGB').tobytes(),'Crop is exact source pixels')
 report['reading_authority']={'raw_human_answer':human['answer'],'previous_AI_disagreement_superseded':True,'crop_visually_inspected':True,'accepted_literal':'RF081 C1','scope':'02A-E1 F5 card0512 C1 only; RF091BH4 connector reference retained'}
 text=ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing/A1151-01 SOCKET LISTING.txt';model=text.with_suffix('.json')
 expected={text,model,REPO/'ALD/A1 Socket Listing'/text.name,REPO/'json/A1 Socket Listing'/model.name,text.with_name(text.stem+' review notes.txt'),text.with_name(text.stem+' preview.png'),ROOT/'tmp/ald-text/a1/references without scan filename.json'}
 for folder in[ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing',REPO/'json/A1 Socket Listing']:expected|={folder/'Socket reference.json',folder/'ALD references.json'}
 need(len(stage['files'])==11 and{Path(f['target'])for f in stage['files']}==expected,'Exact eleven source/cache/lookup/companion targets')
 operations=0;new_targets=[];texts=[];continuations=0;buckets=0
 for f in stage['files']:
  target=Path(f['target']);candidate=checked(f['candidate']).read_bytes()
  if f['before']:
   before=checked(f['before']).read_bytes();need(target.read_bytes()==before,'Current live preimage '+str(target))
  else:
   need(not target.exists(),'Genuinely new artifact remains absent '+str(target));need(f['role']in{'source review notes','source preview'},'Only true new companions may lack preimages');new_targets.append(f['role']);before=None
  if f['role']in{'working accepted TXT','repository accepted TXT'}:
   a=before.decode('utf-8-sig').splitlines(keepends=True);b=candidate.decode('utf-8-sig').splitlines(keepends=True);need(len(a)==len(b),'TXT line count unchanged');need(before.startswith(b'\xef\xbb\xbf')==candidate.startswith(b'\xef\xbb\xbf'),'TXT BOM unchanged');delta=[]
   for y,(s,t)in enumerate(zip(a,b)):
    need(len(s)==len(t)and s[len(s.rstrip('\r\n')):]==t[len(t.rstrip('\r\n')):],'TXT widths/endings '+str(y));delta +=[{'row':y,'column':x,'before':c,'after':d}for x,(c,d)in enumerate(zip(s,t))if c!=d]
   need(delta==stage['exact_meaningful_cell_changes'],'Only9to8 at93:98');need(a[93][95:100]=='RF091'and b[93][95:100]=='RF081','Exact source token');need(before.count(b'RF091BH4')==candidate.count(b'RF091BH4'),'Unrelated connector reference retained in TXT');texts.append(candidate)
  elif target.suffix=='.json':
   a=json.loads(before.decode('utf-8-sig'));after=json.loads(candidate.decode('utf-8-sig'));expected_doc=deepcopy(a)
   for c in f['changes']:
    operations+=1
    if'pointer'in c:
     need(at(expected_doc,c['pointer'])==c['before'],'Declared exact JSON preimage');need((c['before'],c['after'])in{('RF091','RF081'),('RF091 C1','RF081 C1')},'Only exact RF page/literal correction')
     ts=parts(c['pointer']);record=at(a,'/'+ '/'.join(ts[:2]));need(site(record,a),'Only physicalF5 on02A-E1')
     typed=record.get('card_type')=='0512';cont=record.get('kind')=='continuation'and record.get('continues_socket')=='F5'and record.get('card_type')in{None,'0512'}and primary_exists(a)
     need(typed or cont,'Typed primary or explicit continuation with actual same-site0512 primary')
     if cont:continuations+=1
     if'/references/'in c['pointer']:
      ref=at(a,'/'+ '/'.join(ts[:-1]));need(ref.get('printed_portions',ref.get('portions'))==['C1'],'Only printedC1 group')
     else:need('/printed_lines/'in c['pointer']and c['before']=='RF091 C1','Only exact current source-line cache')
     setat(expected_doc,c['pointer'],c['after'])
    else:
     need(c['operation']=='move_exact_card_portion_bucket'and c['before_key']=='RF091'and c['after_key']=='RF081'and c['count']==1,'One exact card-portion bucket move')
     need(len(c['moved_entries'])==1,'Exactly one moved card entry');entry=c['moved_entries'][0]
     need(site(entry,{})and entry['card_type']=='0512'and entry['kind']=='card portion'and entry['portion']=='C1','Moved entry is exact physicalF5/0512/C1')
     root=at(expected_doc,c['bucket_root'])if c['bucket_root']else expected_doc;need(entry in root['RF091'],'Moved entry exact preimage');root['RF091'].remove(entry)
     if not root['RF091']:del root['RF091']
     root.setdefault('RF081',[]).append(entry);buckets+=1
   need(expected_doc==after,'Full JSON equality after only declared pointer/bucket replay '+str(target))
   need(before.count(b'RF091BH4')==candidate.count(b'RF091BH4'),'Unrelated RF091BH4 connector survives JSON')
 need(len(texts)==2 and texts[0]==texts[1],'Working/repo TXT agree');need(sorted(new_targets)==['source preview','source review notes'],'Only notes/preview are new; no false old quartet')
 need(operations==19 and continuations==4 and buckets==3,'Expected19 scoped ops /4 explicit continuation copies /3 bucket moves')
 predecessor=read(stage['predecessor_acceptance']['path']);need(predecessor['companion_predecessors']=={'notes_existed':False,'preview_existed':False},'Honest two-artifact predecessor recorded')
 rows=texts[0].decode('utf-8-sig').splitlines();font=ImageFont.truetype(stage['font']['path'],18);cw=round(font.getlength('M'));image=Image.new('RGB',(32+max(map(len,rows))*cw,32+len(rows)*25),'white');draw=ImageDraw.Draw(image)
 for y,line in enumerate(rows):draw.text((16,16+y*25),line,font=font,fill='black')
 preview=next(f for f in stage['files']if f['role']=='source preview')
 with Image.open(preview['candidate']['path'])as actual:need(image.size==actual.size and image.tobytes()==actual.convert('RGB').tobytes(),'Full new preview exact render')
 notes=next(f for f in stage['files']if f['role']=='source review notes');need(b'RF081 is printed'in checked(notes['candidate']).read_bytes(),'New notes retain raw human answer')
 spec=importlib.util.spec_from_file_location('rf_independent_helper',stage['registration_helper']['path']);app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app);actual_model=next(f['candidate']for f in stage['files']if Path(f['target'])==model);need(app.validate_table_model(Path(actual_model['path']),stage),'Actual candidate passes sockets/source guard')
 publisher=TOOLS/'publish_single_table_addendum.py';bind(publisher,'8d1aab5bfa2b7a804b6ae8208cb8fb87d730902751b5dcb3bafcbac8d5e37bf7')
 source=publisher.read_text('utf-8')
 for safeguard in["cli.add_argument('--stage-dir',required=True,type=Path)","cli.add_argument('--publish',action='store_true')","if record.get('before')else None","if backups[key]is None:Path(key).unlink(missing_ok=True)","for link in stage['metadata_preimages']:checked(link)","if key in frozen:need(old is not None and sha(old)==frozen[key]","'Unrelated export entry changed'","'uniform_rebuild_deferred':True"]:need(safeguard in source,'Reviewed generic publisher safeguard '+safeguard)
 report['publisher_review']={'default_preflight':True,'new_target_absence_rechecked':True,'rollback_deletes_only_new_targets':True,'frozen_metadata_guards':True,'other_adapter_registry_export_items_retained':True,'uniform_rebuild_intentionally_deferred':True,'transient_plan_and_logs_not_rollback':True}
 bind(TOOLS/'test_rf081_addendum_scope.py','8451b213ceee8513161f91a50e770256a1c0ef8efe0f24e1313390f17a1664c3');bind(TOOLS/'prepare_a1241_addendum.py');bind(TOOLS/'prepare_rf081_addendum.py')
 env=dict(os.environ,TEMP=str(ROOT/'tmp/socket-uniform-test-temp'),TMP=str(ROOT/'tmp/socket-uniform-test-temp'));proc=subprocess.run([sys.executable,'-X','utf8','-m','unittest','discover','-s',str(TOOLS),'-p','test_rf081_addendum_scope.py','-v'],cwd=ROOT,env=env,capture_output=True,text=True)
 log=HERE/'Independent scope tests.txt';log.write_text(proc.stdout+proc.stderr,encoding='utf-8');need(proc.returncode==0 and'Ran 7 tests'in proc.stderr,'Seven scope tests pass');bind(log);bind(__file__)
 for p,h in list(bindings.items()):need(sha(Path(p).read_bytes())==h,'Final bound review epoch '+p)
 report.update(passed=True,checks_completed=len(checks),checks=checks,source_cells=1,json_operations=19,candidate_files=11,new_artifacts=new_targets,candidate_bindings=[{'path':p,'sha256':h}for p,h in sorted(bindings.items())],stage_manifest=bind(MAN))
except Exception as e:report['failures'].append(str(e));report['checks_completed']=len(checks)
out=HERE/'Independent acceptance.json';need(not out.exists(),'Refuse prior acceptance overwrite');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'failures':report['failures'],'checks':report['checks_completed'],'acceptance':bind(out)},indent=2));raise SystemExit(not report['passed'])

"""Mechanical preparation assertions; this does not grant independent acceptance."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json
from PIL import Image,ImageChops,ImageDraw,ImageFont

HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
checks=[]
def need(v,m):
 if not v:raise ValueError(m)
 checks.append(m)
def checked(b):p=Path(b['path']);need(sha(p)==b['sha256'],'Exact binding '+str(p));return p
def tokens(p):return [x.replace('~1','/').replace('~0','~')for x in p.split('/')[1:]]
def node(v,p):
 for token in tokens(p):v=v[int(token)]if isinstance(v,list)else v[token]
 return v
def setnode(v,p,value):
 ts=tokens(p);parent=node(v,'/'+ '/'.join(x.replace('~','~0').replace('/','~1')for x in ts[:-1]))if len(ts)>1 else v;key=int(ts[-1])if isinstance(parent,list)else ts[-1];parent[key]=value
report={'schema':'socket-reference-preparation-mechanical-validation-v1','passed':False,'independent_review':False,'created_utc':datetime.now(timezone.utc).isoformat(),'source_or_canonical_writes':False,'failures':[]}
try:
 batch=read(HERE/'Batch manifest.json');prepared=read(HERE/'Prepared page stages.json');checked(prepared['batch_manifest'])
 need('RF091'not in batch['reference_aliases'],'Held RF091 excluded from aliases')
 for f in batch['files']:
  p=checked(f['candidate']);target=Path(f['target'])
  if f['before']:
   before=checked(f['before']);need(target.read_bytes()==before.read_bytes(),'Current live preimage '+str(target))
  else:need(not target.exists(),'New candidate target absent '+str(target))
  if f['role']=='current active JSON mirror candidate':
   old=read(before);expected=deepcopy(old)
   for c in f['changes']:
    if 'pointer'in c:
     need(node(expected,c['pointer'])==c['before'],'Exact JSON pointer preimage '+c['pointer']);setnode(expected,c['pointer'],c['after'])
    else:
     bucket=node(expected,c['bucket_path'])if c['bucket_path']else expected;need(c['operation']=='move_bucket_entries','Supported bucket operation')
     for item in c['moved_entries']:need(item in bucket[c['before_key']],'Exact moved bucket entry');bucket[c['before_key']].remove(item)
     if not bucket[c['before_key']]:del bucket[c['before_key']]
     bucket.setdefault(c['after_key'],[]).extend(c['moved_entries'])
   need(expected==read(p),'Exact declared JSON replay '+str(target))
 font=ImageFont.truetype(batch['font']['path'],18);cw=round(font.getlength('M'))
 for link in prepared['page_stages']:
  stage=read(checked(link));working=next(f for f in stage['files']if f['role']=='working accepted TXT')
  a=checked(working['before']).read_bytes();b=checked(working['candidate']).read_bytes();old=a.decode('utf-8-sig').splitlines(keepends=True);new=b.decode('utf-8-sig').splitlines(keepends=True)
  need(len(old)==len(new),'Row count preserved '+stage['page']);need(a.startswith(b'\xef\xbb\xbf')==b.startswith(b'\xef\xbb\xbf'),'BOM preserved '+stage['page'])
  delta=[]
  for y,(s,t)in enumerate(zip(old,new)):
   need(len(s)==len(t)and s[len(s.rstrip('\r\n')):]==t[len(t.rstrip('\r\n')):],'Row geometry and ending '+stage['page']+'/'+str(y))
   delta += [{'row':y,'column':x,'before':c,'after':d}for x,(c,d)in enumerate(zip(s,t))if c!=d]
  need(delta==stage['exact_meaningful_cell_changes'],'Declared source cells exact '+stage['page'])
  preview=next(f for f in stage['files']if f['role']=='source preview');rows=b.decode('utf-8-sig').splitlines()
  image=Image.new('RGB',(32+max(map(len,rows))*cw,32+len(rows)*25),'white');draw=ImageDraw.Draw(image)
  for y,line in enumerate(rows):draw.text((16,16+y*25),line,font=font,fill='black')
  with Image.open(preview['candidate']['path'])as actual:need(ImageChops.difference(image,actual.convert('RGB')).getbbox()is None,'Full preview exact '+stage['page'])
  for crop in stage['preview_crops']:
   with Image.open(crop['crop']['path'])as actual:need(image.crop(crop['rectangle']).tobytes()==actual.convert('RGB').tobytes(),'Exact rendered crop '+stage['page'])
  for key in ['source','human_authority','source_crop','predecessor_acceptance','historical_repository_acceptance']:checked(stage[key])
 for candidate in batch['tool_candidates']:
  if candidate['before']:checked(candidate['before'])
  else:need(not Path(candidate['target']).exists(),'New reusable table test target absent')
  checked(candidate['candidate'])
 for binding in batch['metadata_preimages']+batch['uniform_preimages']:checked(binding)
 need(sum(len(read(x['path'])['exact_meaningful_cell_changes'])for x in prepared['page_stages'])==63,'Total source cell count 63')
 report.update(passed=True,checks_completed=len(checks),checks=checks,batch_manifest=bind(HERE/'Batch manifest.json'),page_stage_index=bind(HERE/'Prepared page stages.json'),validation_tool=bind(__file__),independent_acceptance_still_required=True)
except Exception as e:report['failures'].append(str(e));report['checks_completed']=len(checks)
(HERE/'Preparation mechanical assertions.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'checks':report['checks_completed'],'failures':report['failures']}));raise SystemExit(not report['passed'])

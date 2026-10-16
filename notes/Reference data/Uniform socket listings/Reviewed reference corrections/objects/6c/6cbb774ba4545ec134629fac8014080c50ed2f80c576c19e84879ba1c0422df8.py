"""Private exact-span source correction stage; no live artifact is written."""
from pathlib import Path
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib, importlib.util, json, re, sys
from PIL import Image, ImageDraw, ImageFont

ROOT=Path('D:/Github/IBM360'); REPO=ROOT/'ibm360ald'; OUT=Path(__file__).resolve().parent
FINDINGS=ROOT/'tmp/ald-text/ald/socket-ald-audit/absent-reference-review/Current absent reference findings.json'
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def module(p,name):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def need(v,m):
 if not v:raise ValueError(m)
files=[]; skips=[]
def stage(target,raw,role,changes):
 target=Path(target).resolve();before=target.read_bytes() if target.exists() else None
 if before==raw:return
 idx=f'{len(files):03d}';candidate=OUT/'candidate'/idx/target.name;candidate.parent.mkdir(parents=True,exist_ok=True);candidate.write_bytes(raw)
 old=None
 if before is not None:
  old=OUT/'before'/idx/target.name;old.parent.mkdir(parents=True,exist_ok=True);old.write_bytes(before)
 files.append({'target':str(target),'role':role,'before':bind(old) if old else None,'candidate':bind(candidate),'changes':changes})

findings=load(FINDINGS);selected=[f for f in findings['findings'] if 'misread' in f['disposition'] and f['unavailable_page'] != 'RF091']
need(len(selected)==22,'Expected 22 reviewed aliases; RF091 is held')
mapping={f['unavailable_page']:f['proposed_reference'] for f in selected}
pages=defaultdict(list); authorities=[]
for f in selected:
 spans=f.get('source_reference_spans',[])+[c['text_span'] for c in f.get('crops',[]) if 'text_span'in c]
 unique={(s['page'],s['row'],s['token_column']):s for s in spans}
 if f['disposition'].startswith('probable'):
  need(f['confidence']=='high from native plus unique exact identity','Probable reading lacks exact support')
  for c in f['claims']:
   candidates=c['exact_identity_candidates'];need(candidates and {x['page'] for x in candidates}=={f['proposed_reference']},'RU candidate ambiguity')
   for x in candidates:need(sha(x['model_binding']['path'])==x['model_binding']['sha256'],'Stale RU node witness')
  for c in f['crops']:
   need(sha(c['source']['path'])==c['source']['sha256'] and sha(c['crop']['path'])==c['crop']['sha256'],'Stale RU native crop')
   with Image.open(c['source']['path']) as original,Image.open(c['crop']['path']) as crop:
    need(original.convert('RGB').crop(c['native_rect']).tobytes()==crop.convert('RGB').tobytes(),'RU crop is not exact source pixels')
 for s in unique.values():pages[s['page']].append({'old':f['unavailable_page'],'new':f['proposed_reference'],'span':s,'disposition':f['disposition']})
 authorities.append({'old':f['unavailable_page'],'new':f['proposed_reference'],'disposition':f['disposition'],'span_count':len(unique),'finding':f})
need(len(pages)==14 and sum(map(len,pages.values()))==62,'Expected 14 scans/62 spans; RF091 is held')
builder=module(REPO/'tools/references/build_uniform_socket_listings.py','stage_socket_builder')
parser=module(REPO/'tools/references/socket_text_parser.py','stage_socket_parser')
source_pages,source_bindings=builder.load_pages(REPO);source_by_page={p['page']:p for p in source_pages}
page_reports=[];fontpath=ROOT/'tmp/ald-text/JuliaMono-Regular.ttf';font=ImageFont.truetype(str(fontpath),18);cw=round(font.getlength('M'))
for page,changes in sorted(pages.items()):
 source=source_by_page[page];txt=REPO/source['text_path'];working=ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing'/txt.name
 raw=txt.read_bytes();need(working.read_bytes()==raw,'Working/repo text mismatch '+page)
 rows=raw.decode('utf-8-sig').splitlines(keepends=True);delta=[]
 for change in sorted(changes,key=lambda c:(c['span']['row'],c['span']['token_column'])):
  s=change['span'];y,x=s['row'],s['token_column'];old,new=change['old'],change['new']
  need(len(old)==len(new) and rows[y][x:x+len(old)]==old,'Source token mismatch '+page)
  need(rows[y][s['column']:s['column']+len(s['literal'])]==s['literal'],'Source span mismatch '+page)
  rows[y]=rows[y][:x]+new+rows[y][x+len(old):]
  delta.extend({'row':y,'column':x+i,'before':a,'after':b} for i,(a,b) in enumerate(zip(old,new)) if a!=b)
 corrected=(b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'')+''.join(rows).encode('utf-8')
 oldlines=raw.decode('utf-8-sig').splitlines();newlines=corrected.decode('utf-8-sig').splitlines()
 need(len(oldlines)==len(newlines) and list(map(len,oldlines))==list(map(len,newlines)),'Geometry changed '+page)
 need(sum(a!=b for a,b in zip(raw,corrected))==len(delta),'Unexpected text bytes changed '+page)
 stage(working,corrected,'working accepted TXT candidate',delta);stage(txt,corrected,'repository accepted TXT candidate',delta)
 source['lines']=newlines
 cols=ROOT/'tmp/ald-text/a1'/(page+' columns reviewed.json')
 page_json=working.with_suffix('.json')
 if cols.exists():
  data=load(cols);replacements=[]
  for ci,col in enumerate(data):
   for ri,line in enumerate(col):
    updated=line
    for change in changes:
     # Columns proof excludes global positioning; accept only exact reviewed row literal.
     if change['span']['literal'].strip()==line.strip() and change['old'] in line:
      updated=updated.replace(change['old'],change['new'])
    if updated!=line:replacements.append({'pointer':f'/{ci}/{ri}','before':line,'after':updated});data[ci][ri]=updated
  stage(ROOT/'tmp/ald-text/a1'/(page+' columns absent-reference correction.json'),enc(data),'successor columns proof candidate',replacements)
 note=(page+' - REVIEWED PAGE REFERENCE CORRECTIONS\n\n'
       'This private successor records native-scan and cross-reference review; it is not yet accepted or published.\n'
       'Historical acceptance and columns-reviewed files are retained unchanged.\n'+''.join(f"ROW {c['span']['row']} COLUMN {c['span']['token_column']}: {c['old']} -> {c['new']} ({c['disposition']})\n" for c in changes))
 notes=working.with_name(working.stem+' review notes.txt');existing=notes.read_text(encoding='utf-8-sig') if notes.exists() else ''
 stage(notes,(existing+('\n\n' if existing else '')+note).encode('utf-8'),'source review notes candidate',[])
 im=Image.new('RGB',(32+max(map(len,newlines))*cw,32+len(newlines)*25),'white');dr=ImageDraw.Draw(im)
 for y,line in enumerate(newlines):dr.text((16,16+y*25),line,font=font,fill='black')
 png=OUT/'previews'/(page+'.png');png.parent.mkdir(exist_ok=True);im.save(png)
 stage(working.with_name(working.stem+' preview.png'),png.read_bytes(),'source preview candidate',[])
 page_reports.append({'page':page,'scan_id':source['scan_id'],'source_relative':source['source_relative'],'working_txt':bind(working),'repository_txt':bind(txt),'exact_meaningful_cell_changes':delta,'reviewed_tokens':changes,'existing_page_json':str(page_json) if page_json.exists() else None,'historical_columns':bind(cols) if cols.exists() else None})

# Parse private successor grids in memory. Their values constrain every legacy mirror edit.
truth=parser.parse_listings(source_pages);need(not truth['issues'],'Corrected source creates parser diagnostics')
def physical(s):return re.sub(r'(?<=\d)[BT]$','',s)
def site_context(v,parent):
 c=dict(parent)
 if not isinstance(v,dict):return c
 if isinstance(v.get('board'),str):c['board']=v['board']
 if isinstance(v.get('socket'),str):c['sockets']=[v['socket']]
 if isinstance(v.get('sockets'),list) and all(isinstance(x,str) for x in v['sockets']):c['sockets']=v['sockets']
 if isinstance(v.get('card_type'),str):c['card_type']=v['card_type']
 if isinstance(v.get('pin'),str):c['pin']=v['pin']
 for key in ['printed_portions','portions']:
  if isinstance(v.get(key),list):c['portions']=v[key]
 if isinstance(v.get('portion'),str):c['portions']=[v['portion']]
 return c
def witnesses(c):
 ss={physical(s) for s in c.get('sockets',[])}
 if not c.get('board') or not ss:return []
 return [r for r in truth['records'] if r['board']==c['board'] and ss&{physical(s) for s in r['sockets']} and (not c.get('card_type') or r['card_type']==c['card_type'])]
def page_ok(page,c):
 portions=set(c.get('portions',[]))
 return any(q['page']==page and (not portions or portions<=set(q['portions'])) for r in witnesses(c) for q in r['references'])
def ref_ok(reference,c):
 return any(p['ALD_reference']==reference and (not c.get('pin') or p['pin']==c['pin']) for r in witnesses(c) for p in r['pins'])
def escape(s):return str(s).replace('~','~0').replace('/','~1')
def transform(v,path='',context=None):
 context=site_context(v,context or {});out=deepcopy(v);changes=[]
 if isinstance(v,dict):
  for key,value in v.items():
   pointer=path+'/'+escape(key)
   if key in ['ALD_page','ald_page','page'] and value in mapping if isinstance(value,str) else False:
    if page_ok(mapping[value],context):out[key]=mapping[value];changes.append({'pointer':pointer,'before':value,'after':out[key],'proof':'same site/card/portion in privately corrected current source'})
    else:skips.append({'pointer':pointer,'value':value,'reason':'no exact current-source record witness'})
   elif key in ['ALD_reference','reference'] and isinstance(value,str) and value[:5] in mapping:
    new=mapping[value[:5]]+value[5:]
    if ref_ok(new,context):out[key]=new;changes.append({'pointer':pointer,'before':value,'after':new,'proof':'exact site/pin and reference in current-source grid'})
    else:skips.append({'pointer':pointer,'value':value,'reason':'no exact current-source pin witness; unreviewed endpoint retained'})
   elif key=='text' and isinstance(value,str) and isinstance(v.get('row'),int) and current_page in pages:
    matches=[c for c in pages[current_page] if c['span']['row']==v['row'] and ' '.join(c['span']['literal'].split())==' '.join(value.split())]
    if matches:
     need(len(matches)==1,'Ambiguous source-bound annotation');c=matches[0];new=value.replace(c['old'],c['new']);out[key]=new;changes.append({'pointer':pointer,'before':value,'after':new,'proof':'exact reviewed source page, row and annotation literal'})
   else:
    out[key],extra=transform(value,pointer,context);changes+=extra
  # Bucket memberships are current indexes, not independent source evidence.
  buckets=out.get('ALD_pages') if isinstance(out.get('ALD_pages'),dict) else out if path=='' and any(k in mapping for k in out) else None
  if buckets is not None:
   for old,new in mapping.items():
    if old not in buckets or not isinstance(buckets[old],list):continue
    moved=[];retained=[]
    for entry in buckets[old]:
     c=site_context(entry,context)
     good=page_ok(new,c) if entry.get('kind')=='card portion' else ref_ok(entry.get('ALD_reference',''),c) and entry.get('ALD_reference','').startswith(new)
     (moved if good else retained).append(entry)
    if moved:
     buckets.setdefault(new,[]).extend(moved)
     if retained:buckets[old]=retained
     else:del buckets[old]
     changes.append({'operation':'move_bucket_entries','bucket_path':path+'/ALD_pages' if 'ALD_pages'in out else path,'before_key':old,'after_key':new,'moved_entries':moved,'count':len(moved)})
 elif isinstance(v,list):
  for i,value in enumerate(v):out[i],extra=transform(value,path+'/'+str(i),context);changes+=extra
 return out,changes
jsonpaths=[]
for folder in [ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing',REPO/'json/A1 Socket Listing']:
 jsonpaths += [p for p in folder.glob('*.json') if p.name.startswith('A') and ('BOARD 'in p.name or 'SOCKET LISTING'in p.name) or p.name in ['Socket reference.json','ALD references.json']]
jsonpaths.append(ROOT/'tmp/ald-text/a1/references without scan filename.json')
for p in sorted(jsonpaths):
 current_page=p.name.split(' ',1)[0];data=load(p);start=len(skips);after,changes=transform(data)
 for skip in skips[start:]:skip['file']=str(p)
 if changes:stage(p,enc(after),'current active JSON mirror candidate',changes)
report={'schema':'socket-reference-batch-private-stage-v1','created_utc':datetime.now(timezone.utc).isoformat(),'published':False,'independent_review_required':True,'reviewed_findings':bind(FINDINGS),'preparation_script':bind(__file__),'font':bind(fontpath),'source_bindings':source_bindings,'reference_aliases':mapping,'authority_records':authorities,'pages':page_reports,'files':files,'withheld_json_changes':skips,'counts':{'aliases':len(mapping),'source_pages':len(pages),'reviewed_tokens':sum(map(len,pages.values())),'text_cells':sum(len(p['exact_meaningful_cell_changes']) for p in page_reports),'candidate_files':len(files),'json_field_changes':sum(len(f['changes']) for f in files if f['role']=='current active JSON mirror candidate')},'publication_requirements':['Independent native/source-cell and JSON witness review','Schema-aware quartet acceptance for eight existing page models','A1 columns adapter registration for seven scans without per-page JSON','Guarded batch publication and repository provenance/content metadata update','Uniform socket rebuild only after accepted source/provenance publication'],'historical_acceptance_modified':False,'canonical_changes_applied':False}
(OUT/'Stage manifest.json').write_bytes(enc(report))
print(json.dumps({'manifest':bind(OUT/'Stage manifest.json'),'counts':report['counts'],'withheld_json_fields':len(skips),'published':False},indent=2))

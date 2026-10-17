"""Freeze read-only source decisions and exact candidate edits; never mutate sources."""
from pathlib import Path
from collections import Counter
import json,re,hashlib,copy
B=Path(__file__).parent;ROOT=Path('D:/Github/IBM360');O=B/'Frozen pin and site findings v3'
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
q=read(B/'pin_card_location focused current queue.json');s=read(B/'Supplementary wiring site endpoint queue.json');xr=read(B/'Exact current cross-reference corroboration.json');xrs={x['case_id']:x for x in xr['cases']}
notes=read(B/'Pin card location visual notes.json')['cases'];noteinputs=[B/'Pin card location visual notes.json']
for p in sorted(B.glob('visual_notes_batch*.json'),key=lambda p:int(p.stem.split('batch')[1])):
 notes.update(read(p));noteinputs.append(p)
for name in ['visual_notes_manual_successors.json','visual_notes_fixed_successors.json','site_visual_notes.json']:
 p=B/name;notes.update(read(p));noteinputs.append(p)
crops={}
for name in ['Pin card location native review v2/Native crop register.json','Supplementary site native review/Native crop register.json','Manual native successor crops/Manual crop successor register.json','Fixed manual native crops/Fixed crop successor register.json','Final identity-checked crop successors/Native crop register.json']:
 d=read(B/name)
 for c in d.get('cases',d.get('crops',[])):crops[c['case_id']]=c
pin={2:'B02',3:'D06',4:'D07',5:'D06',16:'3D04',20:'D06',21:'B05',22:'D11',58:'B02',59:'B10✲',62:'D06',65:'B07',73:'B13',99:'B02',104:'B04',105:'B13',106:'B10',110:'D04',113:'B12',114:'D11',115:'D05✲',153:'B03',154:'B04',157:'D10',158:'B05',159:'B03',169:'D04',171:'D11',172:'B05',173:'D06',174:'2D04',175:'B10',177:'B13',179:'KB08',180:'D04',181:'B04',182:'B04',183:'B04',185:'B04',189:'B09',190:'D05✲',192:'B04',193:'B07',194:'B09',195:'D11',196:'D10',197:'D02',198:'D02',199:'B04',200:'B12',201:'D08',215:'D11',217:'D02',220:'D02',221:'B07',222:'D02',223:'B10',224:'B04',225:'D09'}
loc={66:'E-C2G5',119:'E-B3E7',166:'E-B2J4',167:'E-B2J4',168:'E-B2J4',205:'E-C2K4',206:'E-C2M5',209:'E-C2K5'}
sitefix={26:'C-A4H6',44:'A-B3E4'}
pin.pop(62)
notes['focused-062']={'status':'unresolved_print','native':'D?6/D?5, middle0 C-shaped and finaldigit degraded','best_guess':'D06','note':'Expanded native successor now shows complete actualAA0473B1 block. Earlier cropped input-only readingD06 is held; exact sameportion witnesses supportD06 but the final glyph itself can resemble5.'}
overrides={
 'focused-058':'Fresh native review and exact0505A2 U03AA input corroboration support B02; other D04 input is independently clear. Earlier preliminary B03 guess withdrawn.',
 'focused-152':'Raw model already contains numbered D05 output and a separately documented K cathode input at the same point. Preserve this explicit annotation representation; do not invent a second D05 contact.',
 'focused-172':'B0 is readable; the source hole removes the last glyph. Same0483A4 U03AA same-side witnesses show B05 and D04; existing other input is D04, so B05 is unique and supported.',
 'focused-180':'Exact flagged row84 is the lower input; fresh native source shows D04. The4 control prefix belongs to the upper B04 input and is not copied onto this lower input. Same0503AB input witnesses D04 corroborate.',
 'focused-200':'Fresh enlarged native review shows a worn two-lobed B, not the initial preliminary D guess. Same0503A8 U03AA upper B12 with other input B13 corroborates; withdraw preliminary D12 proposal.',
 'focused-201':'D08 is the previously accepted ground-tie use; this repairs unreadable characters only, no new power policy or connectivity.',
 'site-021':'A1 claims exactE-B4M6. Source final5 is readable but could be degraded6; keep this side held, do not change the clearM6 counterpart.',
 'site-022':'Counterpart E-B4M6 agrees A1. Earlier preliminary M5 best guess withdrawn.',
 'site-030':'A1 claims exactA-B2F6. Source final5 is readable but may be degraded6; keep held rather than changing the clearF6 counterpart.',
 'site-031':'Counterpart A-B2F6 agrees A1. Earlier preliminary F5 best guess withdrawn.'}
excluded_keys={'evidence','notes','note','history','historical','provenance','acceptance','source_evidence','native_socket_discrepancy','socket_listing_discrepancy'}
def historical(k):return k in excluded_keys or any(x in k.lower() for x in ['review','history','provenance','evidence','discrepancy'])
def escape(s):return str(s).replace('~','~0').replace('/','~1')
def walk(v,p=''):
 if isinstance(v,dict):
  for k,x in v.items():
   if not historical(k):yield from walk(x,p+'/'+escape(k))
 elif isinstance(v,list):
  for i,x in enumerate(v):yield from walk(x,p+'/'+str(i))
 else:yield p,v
def physical(v):
 m=re.search(r'[BDGJ](?:0[2-9]|1[0-3])',v);return m.group(0) if m else v
def plan(c,new):
 mp=Path(c['model']['path']);assert bind(mp)==c['model'];m=read(mp);ptr=c['node_pointer'];n=m['nodes'][int(ptr.split('/')[-1])];assert n==c['current_raw_node'];old=c['observed'];patch=[];refmap={};pinidx=None
 if c['field']=='location':
  for key in ['location','printed_location','board_socket','card_location']:
   if n.get(key)==old:patch.append({'op':'replace','path':ptr+'/'+key,'before':old,'after':new})
 else:
  matches=[i for i,p in enumerate(n.get('pins',[])) if p.get('pin')==old]
  assert len(matches)==1,(c['case_id'],matches);pinidx=matches[0];p=n['pins'][pinidx]
  for k,v in p.items():
   if historical(k):continue
   if k in ['pin','printed_pin','printed_label','label','physical_pin','physical_pin_candidate','contact','pin_number'] and (isinstance(v,str) or (v is None and k in ['physical_pin','physical_pin_candidate'])):
    after=physical(new) if k in ['physical_pin','physical_pin_candidate','contact','pin_number'] else new
    if v==old or (k in ['physical_pin','physical_pin_candidate','contact','pin_number'] and (v in [physical(old),re.sub(r'^[0-9K]+','',old)] or v is None)):
     if after!=v:patch.append({'op':'replace','path':ptr+'/pins/'+str(pinidx)+'/'+k,'before':v,'after':after})
   if k in ['reference','ref','id'] and isinstance(v,str) and old in v:
    refmap[v]=v.replace(old,new)
  if p.get('source_unknown_pin') is True:patch.append({'op':'replace','path':ptr+'/pins/'+str(pinidx)+'/source_unknown_pin','before':True,'after':False})
  # Full reference aliases only: never rename another node or historical observation.
  for path,val in walk(m):
   if isinstance(val,str) and val in refmap:patch.append({'op':'replace','path':path,'before':val,'after':refmap[val]})
 tp=Path(str(mp).replace('\\json\\','\\ALD\\')).with_suffix('.txt');lines=tp.read_text('utf-8-sig').splitlines();col=n.get('column',0);text=[];found=[]
 if pinidx is not None:
  p=n['pins'][pinidx];r=p.get('absolute_row',p.get('row'));assert isinstance(r,int);rows=[r]
  # Some schemas have explicitly relative rows.
  if p.get('row_basis')=='relative' and 'absolute_row' not in p:rows=[n['row']+r]
 else:rows=range(max(0,n['row']),min(len(lines),n['row']+max(10,n.get('height',7)+3)))
 for r in rows:
  lo=max(0,col-15);hi=min(len(lines[r]),col+30);segment=lines[r][lo:hi]
  for match in re.finditer(re.escape(old),segment):
   x=lo+match.start()
   if pinidx is not None:
    side=n['pins'][pinidx].get('side')
    if side=='input' and x>=col:continue
    if side=='output' and x<col:continue
   elif not(col<=x<=col+2):continue
   found.append((r,x))
 if len(found)==1:
  r,x=found[0]
  textnew={'focused-157':'D10─','focused-174':'─2D04'}.get(c['case_id'],new)
  if len(old)!=len(textnew):return {'ready':False,'reason':'fixed-width text span needs explicit placement; no character shifting permitted','old_matches':found,'new_matches':[],'json_patches':patch,'text_binding':bind(tp),'text_edits':[],'coordinate_basis':'zero-based row/column'}
  for k,(a,z) in enumerate(zip(old,textnew)):
   if a!=z:text.append({'row':r,'column':x+k,'before':a,'after':z})
  textstatus='exact_cells'
 else:
  existing=[]
  for r in rows:
   for match in re.finditer(re.escape(new),lines[r][max(0,col-15):col+30]):existing.append((r,max(0,col-15)+match.start()))
  if len(existing)==1:textstatus='text_already_correct'
  else:textstatus='mechanical_text_locator_review';return {'ready':False,'reason':textstatus,'old_matches':found,'new_matches':existing,'json_patches':patch,'text_binding':bind(tp),'text_edits':[],'coordinate_basis':'zero-based row/column'}
 return {'ready':True,'json_binding':bind(mp),'text_binding':bind(tp),'coordinate_basis':'zero-based row/column','text_status':textstatus,'text_edits':text,'json_patches':list({x['path']:x for x in patch}.values()),'pin_index':pinidx,'current_pin':n['pins'][pinidx] if pinidx is not None else None}
rows=[]
for idx,raw in enumerate(q['cases']+s['cases']):
 c=copy.deepcopy(raw);cid=c.get('case_id') or 'focused-%03d'%(idx+1);c['case_id']=cid;note=notes[cid];cr=crops[cid];assert bind(c['model']['path'])==c['model'];assert bind(cr['native_crop']['path'])['sha256']==cr['native_crop']['sha256'];new=None
 if cid.startswith('focused-'):
  i=int(cid.split('-')[1]);new=(pin if c['field']=='pin_identity' else loc).get(i)
 else:new=sitefix.get(int(cid.split('-')[1]))
 c['visual_observation']=note;c['source_crop']=cr['native_crop'];c['native_source']=cr['source'];c['crop_identity_visually_checked']=True;c['cross_reference_evidence']=xrs[cid];c['review_note']=overrides.get(cid,'');c['text_edits']=[];c['json_patches']=[]
 if new:
  c['proposed']=new;d=plan(c,new);c['exact_plan']=d;c['status']='resolved_visual_and_exact_context' if d['ready'] else 'settled_reading_mechanical_plan_hold';c['text_edits']=d['text_edits'];c['json_patches']=d['json_patches'] if d['ready'] else []
 else:
  status=note['status']
  if c['field']=='location' and status not in ['literal_current','control_context','genuine_legacy_frame_context','native_literal_disagrees_current']:
   c['status']='human_source_reading_needed';c['best_guess']=note.get('best_guess')
   candidates=xrs[cid].get('exact_listing_candidates',[]);sites=sorted(set(x['board']+' '+','.join(x['physical_sockets']) for x in candidates));c['exact_listing_sites']=sites
   if len(sites)==1:c['best_guess']=sites[0]
  elif status in ['unresolved_print','needs_cross_reference']:
   c['status']='human_source_reading_needed';c['best_guess']=note.get('best_guess')
  else:c['status']='retain_source_context_or_current_literal'
 if cid=='focused-152':c['status']='retain_source_context_or_current_literal'
 if cid in ['site-021','site-030']:c['status']='human_source_reading_needed';c['best_guess']=('E-B4M6' if cid=='site-021' else 'A-B2F6')
 if cid in ['site-022','site-031']:c['status']='retain_source_context_or_current_literal'
 rows.append(c)
assert len(rows)==271 and len({r['case_id'] for r in rows})==271
assert not O.exists();O.mkdir();counts=Counter(r['status'] for r in rows)
out={'schema':'source-bound-frozen-pin-site-visual-findings-v2','helper':bind(__file__),'predecessor_findings':bind(B/'Frozen pin and site findings/Findings.json'),'inputs':[bind(B/'pin_card_location focused current queue.json'),bind(B/'Supplementary wiring site endpoint queue.json'),bind(B/'Exact current cross-reference corroboration.json')]+[bind(p) for p in noteinputs],'coverage':{'focused_fields':225,'additional_unique_wiring_endpoints':46,'wiring_site_pairs':len(s['pairs']),'total_reviewed':len(rows),'status_counts':dict(counts)},'source_writes':0,'cases':rows,'wiring_pairs':s['pairs'],'root_owned_0479_exclusions':[{'page':'RT727','node':'AW','fields':{'top_input':'B09','location':'B-B4G3'}},{'page':'XM012','node':'AB','fields':{'middle_input':'B03','lower_input':'B05'}},{'page':'XM061','node':'AH','fields':{'lower_input':'B03'}}]}
p=O/'Findings.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')
questions=[{k:r[k] for k in ['case_id','page','node','card_type','field','observed','best_guess','source_crop','native_source','model','node_pointer','visual_observation','review_note'] if k in r} for r in rows if r['status']=='human_source_reading_needed']
(O/'Unresolved native questions.json').write_text(json.dumps({'schema':'source-bound-pin-site-human-questions-v1','findings':bind(p),'questions':sorted(questions,key=lambda x:(x['page'],x['node'],x['field'])),'source_writes':0},ensure_ascii=False,indent=2)+'\n','utf-8')
print(bind(p));print(counts)
for r in rows:
 if r['status']=='settled_reading_mechanical_plan_hold':print('MECHANICAL',r['case_id'],r['page'],r['node'],r['exact_plan']['reason'],r['exact_plan']['old_matches'],r['exact_plan']['new_matches'])

"""Read-only physical card-function matching against accepted, literal A1 panels.
Retains cross-column/page continuation, raw locations, and all alias observations.
Never infers unit identity, pin labels, or card functions from spatial order.
"""
import argparse,collections,hashlib,json,re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "normalization"))
import read_page as page_reader
from datetime import datetime,timezone
UNITS={x:'02'+x for x in 'ABCEKL'}
LOC=re.compile(r'(?P<prefix>(?:[0-9�]{2})?[A-Z�])-(?P<gate>[A-Z�][0-9�])(?P<socket>[A-Z�][0-9�]{1,2}[BT]?)$')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def hashp(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p,root):return {'path':p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p),'sha256':hashp(p)}
def overlap(mask,value):return len(mask)==len(value) and all(a in '�?'or b in '�?'or a==b for a,b in zip(mask,value))
def normsocket(x):return re.sub(r'(?<=[0-9])[BT]$','',x)
def locparts(x):
 m=LOC.fullmatch(x)
 if not m:return None
 d=m.groupdict();p=d['prefix'];d['board']=(UNITS[p] if p in UNITS else p)+'-'+d['gate'];d['socket']=normsocket(d['socket']);return d
def location_compatible(mask,board,sockets):
 m=locparts(mask)
 if not m:return []
 pb=board if len(m['prefix'])==3 or m['prefix']in UNITS else board[2:] if board.startswith('02') else board
 # Damaged bare unit is only the six explicitly approved 02-unit abbreviations.
 if m['prefix']in '�?' and board[:3]not in UNITS.values():return []
 return [s for s in sockets if overlap(m['board'],pb)and overlap(m['socket'],normsocket(s))]
def sourcepath(e,repo):
 # The published provenance preserves archive paths, but copied repository
 # artefacts are addressed relative to ALD rather than the original checkout.
 parts=e['destination'].replace('\\','/').split('/');i=parts.index('ALD');return repo.joinpath(*parts[i:])
def fieldproof(page,node,value):
 if not value:return None
 out=[];c=node.get('column');r=node.get('row')
 if not isinstance(c,int)or not isinstance(r,int):return None
 for y in range(r,min(len(page['lines']),r+node.get('height',7)+1)):
  line=page['lines'][y];chunk=line[c:c+9]
  for m in re.finditer(r'(?<![A-Z0-9�])'+re.escape(value)+r'(?![A-Z0-9�])',chunk):out.append({'row':y,'column':c+m.start(),'literal':value,'excerpt':line})
 return out[0]if len(out)==1 else None
def boundaries(lines):
 cc=collections.Counter(tuple(i for i,ch in enumerate(l)if ch=='│')for l in lines if l.count('│')>=5)
 edges=max(cc,key=lambda t:(cc[t],len(t))) if cc else ()
 return [(a+1,b)for a,b in zip(edges,edges[1:])if b-a>20]
def parse_panels(pages):
 panels=[];active=None;ref=None;previousboard=None
 def close():
  nonlocal active,ref
  if active:panels.append(active)
  active=ref=None
 for p in sorted(pages,key=lambda x:(x['board'],x['page'])):
  if p['board']!=previousboard:close()
  previousboard=p['board']
  for col,end in boundaries(p['lines']):
   for row,line in enumerate(p['lines']):
    text=line[col:end]
    if not text.strip():continue
    if re.fullmatch(r'[─┼┌┐└┘ ]{8,}',text):close();continue
    header=re.match(r'^\s{0,3}([A-Z�][0-9�]{1,2}[BT]?)(?:\s+(.*))?$',text.rstrip())
    headergood=header and (not header[2] or bool(re.search(r'CARD|SINGLE|DOUBLE|CABL|XOVR|SOCKET|CONNECTOR|EMPTY|[0-9�]{7}\s+[0-9�]{4}',header[2])))
    evidence={'source_scan_id':p['scan_id'],'page':p['page'],'row':row,'column':col,'literal':text}
    if headergood:
     socket=header[1]
     second=active and 'DOUBLE'in active['kind'] and len(active['sockets'])==1 and active['header_scan_id']==p['scan_id'] and active['header_column']==col and row==active['header_row']+1
     if second:active['sockets'].append(socket);active['header_evidence'].append(evidence)
     else:
      close();active={'board':p['board'],'sockets':[socket],'kind':header[2]or'Unspecified socket heading','header_scan_id':p['scan_id'],'header_column':col,'header_row':row,'header_evidence':[evidence],'board_evidence':p['board_proof'],'part_type':[],'references':[],'source_scan_ids':[p['scan_id']]}
    if not active:continue
    if p['scan_id']not in active['source_scan_ids']:active['source_scan_ids'].append(p['scan_id'])
    for m in re.finditer(r'(?<![A-Z0-9�])([0-9�]{7})\s+([0-9�]{4})(?![A-Z0-9�])',text):active['part_type'].append({'part_number':m[1],'card_type':m[2],'evidence':{**evidence,'column':col+m.start()}})
    if re.search(r'UNUSED|GOES TO|CABL|XOVR|CONNECTOR',text):ref=None
    pg=re.search(r'(?<![A-Z0-9�])([A-Z�]{2}[0-9�]{3})(?![A-Z0-9�])\s+((?:[A-Z0-9�]{1,2}\s*)+)$',text.rstrip())
    if pg:
     ref={'page':pg[1],'portions':[],'evidence':[]};active['references'].append(ref)
    if ref and (pg or re.fullmatch(r'\s{6,}(?:[A-Z0-9�]{1,2}\s*)+',text)):
     tail=pg[2]if pg else text
     ref['portions']+=re.findall(r'(?<![A-Z0-9�])[A-Z0-9�]{1,2}(?![A-Z0-9�])',tail);ref['evidence'].append(evidence)
 close()
 for i,p in enumerate(panels):p['id']='panel-'+str(i+1)
 return panels
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repository-root',default='D:/Github/IBM360/ibm360ald');ap.add_argument('--output',default=str(Path(__file__).parent));ap.add_argument('--human-instruction');ap.add_argument('--native-review-overrides');a=ap.parse_args();repo=Path(a.repository_root).resolve();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
 authority=Path(a.human_instruction)if a.human_instruction else out/'Direct human socket function instructions.json'
 inputs=[repo/'notes/Reviewed export provenance.json',repo/'notes/Manual verification/Workbook binding manifest v4.json',repo/'notes/Manual verification/Pending inventory after V4.json',authority,repo/'notes/Repository records manifest.json'];export,issued,overlay=map(read,inputs[:3]);closed={x['id']for x in overlay['source_derived_resolutions']};records=read(inputs[4]);managed={x['path']:x['sha256']for x in records['files']}
 rules=repo/'notes/A1 Socket Listing/Endpoint reference index';inputs.extend(rules/n for n in ['Direct human abbreviated endpoint units instruction.json','Direct human bare A endpoint instruction.json','Direct human socket matching instruction.json']);bindings=[bound(p,repo)for p in inputs]
 bindings.extend(bound(path,repo)for path in page_reader.runtime_paths(repo))
 pages={};a1=[]
 for e in export['exported']:
  tp=sourcepath(e,repo);assert hashp(tp)==e['text_sha256'];sid=str(e['source_scan_id']);mp=repo/'json'/Path(e['source_relative'].replace('\\','/')).parent/(tp.stem+'.json')
  if mp.exists():assert hashp(mp)==managed[mp.relative_to(repo).as_posix()]
  page={'page':e['page'],'scan_id':sid,'lines':tp.read_text(encoding='utf-8').splitlines(),'text_binding':bound(tp,repo),'model_binding':bound(mp,repo)if mp.exists()else None,'source_relative':e['source_relative'],'review_record':e['review_record'],'model':page_reader.read(mp)if mp.exists()else{}}
  page['source_sha256']=page['model'].get('source_sha256')
  pages[sid]=page
  if 'A1 Socket Listing'in e['source_relative']:
   bs=[{'source_scan_id':sid,'page':e['page'],'row':i,'column':m.start(1),'literal':m[1],'excerpt':l}for i,l in enumerate(page['lines'])for m in re.finditer(r'BOARD\s+(0[12][A-Z]-[A-Z][0-9])',l)]
   if len({b['literal']for b in bs})==1:page['board']=bs[0]['literal'];page['board_proof']=bs;a1.append(page)
 panels=parse_panels(a1);cardpanels=[p for p in panels if re.search(r'SINGLE|DOUBLE',p['kind'])and p['part_type']]
 results=[];skip=collections.Counter()
 for q in issued['questions']:
  if q['id']in closed:skip['already_closed']+=1;continue
  kind=q.get('_kind')
  if not kind and re.search(r'\bblock\s+',q['location'],re.I):
   if LOC.fullmatch(q['current_reading']):kind='board/socket location'
   elif re.fullmatch(r'[0-9�]{4}[A-Z0-9�]{2}',q['current_reading']):kind='card and portion code'
  if kind not in ['board/socket location','card and portion code']or not re.search(r'\bblock\s+',q['location'],re.I):skip['outside_block_socket_function_scope']+=1;continue
  page=pages[str(q['source_scan_id'])];nodes=page['model'].get('nodes',[]);nodes=list(nodes.values())if isinstance(nodes,dict)else nodes
  nm=re.search(r'\bblock (\S+)',q['location'],re.I);name=nm[1].rstrip(',');choices=[n for n in nodes if overlap(name,n.get('id',n.get('printed_id','')))];row=q['row'];column=q['column']
  node=next((n for n in choices if isinstance(n.get('column'),int)and isinstance(n.get('row'),int)and n['column']<=column<=n['column']+9 and n['row']<=row<=n['row']+n.get('height',7)),choices[0]if len(choices)==1 else None)
  result={'id':q['id'],'page':q['page'],'source_scan_id':page['scan_id'],'current_reading':q['current_reading'],'kind':kind,'issued_question':q,'confidence':'Unresolved','candidate':'','possibilities':[],'eliminated':[],'human_confirmed':q['id']=='AP001-22f1584ecc'}
  if not node:result['reason']='Current accepted node absent';results.append(result);continue
  cp=node.get('printed_card_portion')or str(node.get('card_type',''))+str(node.get('portion',''));loc=node.get('location','');ce=fieldproof(page,node,cp);le=fieldproof(page,node,loc);result['subject']={'node':node['id'],'card_portion':cp,'location':loc,'literal_card_proof':ce,'literal_location_proof':le}
  if not ce or not le or len(cp)!=6 or not locparts(loc):result['reason']='Current literal node hardware fields could not be independently anchored';results.append(result);continue
  for p in cardpanels:
   sockets=location_compatible(loc,p['board'],p['sockets'])
   if not sockets:continue
   for pt in p['part_type']:
    for ref in p['references']:
     if not overlap(ref['page'],re.sub(r'-\d\d$','',q['page'])):continue
     for portion in ref['portions']:
      value=pt['card_type']+portion
      if len(value)!=6 or not overlap(cp,value):continue
      for socket in sockets:
       candidate_location=(p['board']if len(locparts(loc)['prefix'])==3 else p['board'][2:])+normsocket(socket)
       candidate=value if kind=='card and portion code'else candidate_location
       if not overlap(q['current_reading'],candidate):continue
       key=(p['board'],tuple(normsocket(s)for s in p['sockets']),value)
       competitors=[]
       for other in nodes:
        if other is node:continue
        ocp=other.get('printed_card_portion')or str(other.get('card_type',''))+str(other.get('portion',''));oloc=other.get('location','');olp=locparts(oloc)
        if ocp==value and olp and '�'not in oloc and olp['board']==p['board']and olp['socket']in key[1]:
         oce=fieldproof(page,other,ocp);ole=fieldproof(page,other,oloc)
         if oce and ole:competitors.append({'node':other.get('id'),'card_portion':ocp,'location':oloc,'card_proof':oce,'location_proof':ole})
       consistent_type=pt['part_number'][-4:]==pt['card_type']
       fully_readable=all('�'not in str(x)for x in [p['board'],*p['sockets'],pt['card_type'],pt['part_number'],ref['page'],portion])and consistent_type
       evidence={'candidate':candidate,'panel_id':p['id'],'board':p['board'],'physical_sockets':p['sockets'],'matched_socket':socket,'card_portion':value,'listing_page_reference':ref['page'],'part_type':pt,'reference':ref,'fully_readable':fully_readable,'part_type_consistent':consistent_type,'same_page_exact_occupants':competitors}
       if competitors:result['eliminated'].append(evidence)
       else:result['possibilities'].append(evidence)
  untyped=[]
  for p in panels:
   if p['part_type']or not re.search(r'SINGLE|DOUBLE|Unspecified',p['kind']):continue
   sockets=location_compatible(loc,p['board'],p['sockets'])
   if not sockets:continue
   refs=[ref for ref in p['references']if overlap(ref['page'],re.sub(r'-\d\d$','',q['page']))and any(len(v)==2 and overlap(cp[4:],v)for v in ref['portions'])]
   if refs:untyped.append({'panel_id':p['id'],'board':p['board'],'sockets':p['sockets'],'matching_references':refs,'reason':'Compatible physical/page/function observation has no readable card part/type; it remains a possible competing observation'})
  result['competing_untyped_panels']=untyped
  vals=sorted({x['candidate']for x in result['possibilities']});goodvals={x['candidate']for x in result['possibilities']if x['fully_readable']};unknowns=any(not x['fully_readable']for x in result['possibilities'])or bool(untyped);result['candidate_values']=vals
  result['confidence']='High'if len(vals)==1 and vals[0]in goodvals and not unknowns else'Tentative'if vals else'Unresolved';result['candidate']=vals[0]if len(vals)==1 else'';result['reason']='Unique literal A1 board/socket/card-function/page association after exact same-page function occupancy exclusions'if result['confidence']=='High'else'Competing or damaged literal physical associations retained'if vals else'No complete compatible A1 physical card-function-page association'
  if result['human_confirmed']:result['confidence']='Human confirmed';result['candidate']='B-E1K6'
  results.append(result)
 reviewpath=Path(a.native_review_overrides)if a.native_review_overrides else out/'Independent native recovery overrides.json';overrides={}
 if reviewpath.exists():
  rv=read(reviewpath);overrides={x['id']:x for x in rv['findings']};bindings.append(bound(reviewpath,repo))
  for x in results:
   if x['id']in overrides:
    ov=overrides[x['id']]
    for k in ['current_text','current_model']:
     binding=ov.get(k)
     if binding:assert hashp(repo/binding['path'])==binding['sha256'],f'Stale native override: {x["id"]} {k}'
    x['algorithmic_confidence']=x['confidence'];x['independent_native_review_override']=ov;x['confidence']=ov['confidence'];x['candidate']=ov.get('best_guess',x['candidate']);x['reason']=ov['reason'];x['candidate_values']=ov.get('candidate_values',x.get('candidate_values',[]))
 for x in results:
  x['best_guess']=x['candidate']if x['confidence']=='Tentative'else''
  x['alternative_values']=x.get('candidate_values',[])
 for x in bindings:
  p=repo/x['path']if not Path(x['path']).is_absolute()else Path(x['path']);assert hashp(p)==x['sha256']
 counts={'accepted_scans':len(pages),'A1_pages':len(a1),'literal_panels':len(panels),'card_panels':len(cardpanels),'questions_examined':len(results),'confidence':dict(collections.Counter(x['confidence']for x in results)),'skip':dict(skip)}
 output={'created_utc':datetime.now(timezone.utc).isoformat(),'inputs':bindings,'policy':{'bare_units':UNITS,'socket_terminal_aliases':['B','T'],'occupancy_key':'Explicit full board + same physical single/double card + exact card portion/function; different portions never eliminate','same_page_alias_caution':'Eliminated candidates retain all exact readable occupant evidence; root must review repeat-function/alias patterns before promotion','High_status':'An algorithmic High remains a private candidate until an independent native review passes; no native contradiction is overridden by listing inference','no_writes_to_canonical_repository_workbook':True},'counts':counts,'pages':{sid:{k:v for k,v in p.items()if k not in ['lines','model']}for sid,p in pages.items()},'panels':panels,'results':results}
 dest=out/'Socket function recovery candidates.json';dest.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8');print(json.dumps({'counts':counts,'output':str(dest),'sha256':hashp(dest)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

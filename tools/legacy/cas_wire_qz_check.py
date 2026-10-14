"""Compare text-rule reachability with historical QZ branch destinations.

Four-way crossings without an O are traversed straight. Box bodies are terminals,
not wires; their vertical boundaries never join control-field input traces.
Incomplete projected rules and historical CAS changes remain review findings.
"""
from pathlib import Path
from collections import deque
import json,re,csv
from cas_reviewed_renderer import D,OUT,SOURCES,ROW_RANK
DEC=json.loads((D.parent/'cas-qz-decode-candidates.json').read_text(encoding='utf-8'))
DIRS=[(0,-1,1,2),(0,1,2,1),(-1,0,4,8),(1,0,8,4)]
MASK={'│':3,'─':12,'┘':5,'└':9,'┐':6,'┌':10,'┤':7,'├':11,'┴':13,'┬':14,'┼':15,'+':15,'O':15,'*':15,'✲':15}
specs={p.name.split()[0]:json.loads(p.read_text(encoding='utf-8')) for p in D.glob('* reviewed.json')}
locs={(pg,n['box']):n['address'].zfill(4) for pg,s in specs.items() for n in s['nodes']}
incoming_legs={(pg,n['box']):n['leg'] for pg,s in specs.items() for n in s['nodes']}
for addr,r in DEC.items():locs.setdefault((r['QZ_page'],r['QZ_box']),addr)
def position(n):
 return n.get('grid',[31+22*(int(n['box'][1:])-1),round(5+11*ROW_RANK[n['box'][0]])])
def terminals(pg,s):
 t={};blocked=set();outputs={}
 for n in s['nodes']:
  c,r=position(n);R=n.get('R_line') is not None or bool(n.get('selector'))
  height=n.get('label_row',max(7,len(n['fields'])+1+int(R)))
  for rr in range(r,r+height+1):
   for cc in range(c,c+15):blocked.add((cc,rr))
  for rr in range(r+1,r+height):t[(c,rr)]=(pg,n['box'],n['address'].zfill(4))
  outputs[n['box']]=(c+15,r+n.get('output_port_row',3))
 texts=s.get('text',[])+s.get('footer',[])
 for c,r,text in texts:
  m=re.match(r'([AQ][A-Z]\d{3})(?:[.─]+([ACEGJLNQS][A-I][A-Z]))?',text)
  if not m:continue
  dest=m[1];serial=m[2]
  if not serial:
   serial=next((v[2] for v in texts if v[1]==r and v[0]>c and re.fullmatch('[ACEGJLNQS][A-I][A-Z]',v[2])),None)
  # A portal serial often identifies the source exit, not the destination box.
  # Keep it as printed; corroborate only destination-page membership below.
  t[(c,r)]=(dest,serial or '', '')
 return t,blocked,outputs
def reachable(lines,start,t,blocked,shapes=None):
 width=max(map(len,lines));height=len(lines);found=set();seen=set();q=deque([(start[0],start[1],8)])
 def char(c,r):return lines[r][c] if 0<=r<height and 0<=c<len(lines[r]) else ' '
 while q:
  c,r,arrival=q.popleft()
  if (c,r,arrival) in seen:continue
  seen.add((c,r,arrival));ch=char(c,r)
  original=(shapes or {}).get(f'{c},{r}') if ch=='┼' else None
  mask=MASK.get(original or ch,0)
  if (c,r)==start:mask=8
  if original=='┼':mask=12 if arrival in [4,8] else 3
  elif ch in '┼+' and not original:
   # Basic intersections have three connected arms, or four unjoined crossing arms.
   connected=sum(bool(MASK.get(char(c+dc,r+dr),0)&opposite) or ((c+dc,r+dr) in t and dc==1) for dc,dr,bit,opposite in DIRS)
   if connected==4:mask=12 if arrival in [4,8] else 3
  for dc,dr,bit,opposite in DIRS:
   if not mask&bit:continue
   v=(c+dc,r+dr)
   if v in t and dc==1:found.add(t[v]);continue
   if v in blocked:continue
   if MASK.get(char(*v),0)&opposite:q.append((*v,bit))
 return sorted(found)
rows=[];incoming=[]
for pg,s in sorted(specs.items()):
 filename=Path(SOURCES[pg]['newpath']).stem+'.txt';p=OUT/filename
 if not p.exists():continue
 lines=p.read_text(encoding='utf-8').splitlines();t,blocked,outputs=terminals(pg,s)
 verification=OUT/(pg+' verification.json')
 shapes=json.loads(verification.read_text(encoding='utf-8')).get('wire_shapes',{}) if verification.exists() else {}
 for n in s['nodes']:
  address=n['address'].zfill(4);qz=DEC.get(address);observed=reachable(lines,outputs[n['box']],t,blocked,shapes);geometric=list(observed);masked=[]
  if qz:
   c=qz['numeric_controls'];base=int(qz['QZ_next_base'],16)
   if c['J']>=96 or c['K']==24:expected=[];mode='functional branch: requires selector-specific review'
   else:
    ks=[c['K']] if c['K']<2 else [0,1];js=[c['J']] if c['J']<2 else [0,1]
    all_expected=[f'{base|(k<<1)|j:04X}' for k in ks for j in js]
    branch=n.get('exit','')
    if len(branch)>=2:
     if branch[0] in '01':ks=[k for k in ks if k==int(branch[0])]
     if branch[1] in '01':js=[j for j in js if j==int(branch[1])]
    excluded=n.get('impossible_branch_combinations',[])
    expected=[f'{base|(k<<1)|j:04X}' for k in ks for j in js if str(k)+str(j) not in excluded];mode='two low branch bits, restricted to printed exits'
    if excluded:mode+='; source-reviewed impossible selector combinations excluded'
    # A CAS rule can carry multiple branch outcomes. A destination's printed
    # incoming leg selects which outcomes enter that box on a shared rule.
    outcomes=[f'{int(a,16)&3:02b}' for a in expected]
    kept=[]
    for target in observed:
     leg=incoming_legs.get((target[0],target[1]),'')
     if re.fullmatch('[01X*]{2}',leg) and not any(all(l not in '01' or l==b for l,b in zip(leg,o)) for o in outcomes):masked.append(target)
     else:kept.append(target)
    observed=kept
    mode+='; destination incoming legs select outcomes on shared rules'
   expanded=[]
   for target in observed:
    if target[2]:expanded.append(target);continue
    candidates=[v for v in expected if v in {addr for (page,box),addr in locs.items() if page==target[0]}]
    expanded.extend((target[0],target[1],v) for v in candidates)
    if not candidates:expanded.append(target)
   observed=expanded
   absent=[v for v in expected if v not in {x[2] for x in observed}]
   extra=[list(v) for v in observed if v[2] and expected and v[2] not in expected]
  else:expected=[];absent=[];extra=[];mode='no QZ word / printed dummy'
  rows.append({'page':pg,'box':n['box'],'ROS_address':address,'mode':mode,'QZ_expected_addresses':expected,'text_wire_destinations':[list(v) for v in observed],
   'geometric_wire_destinations':[list(v) for v in geometric],'destinations_excluded_by_printed_incoming_leg':[list(v) for v in masked],
   'not_reached_in_text':absent,'unexpected_text_destinations':extra,'status':'review required' if absent or extra else 'corroborated' if expected else 'not checked'})
 for c,r,text in s.get('text',[]):
  m=re.match(r'([AQ][A-Z]\d{3})[.─]+([ACEGJLNQS])([A-I])[A-Z]',text)
  if c>=31 or not m:continue
  source_page=m[1];source_box=m[2]+str(ord(m[3])-64);source_address=locs.get((source_page,source_box))
  end=c+len(text)
  start=next(((cc,r) for cc in range(end,min(end+8,len(lines[r]))) if lines[r][cc] in MASK),None)
  observed=reachable(lines,start,t,blocked,shapes) if start else []
  incoming.append({'page':pg,'reference':text,'source_box':source_box,'source_address':source_address,'text_wire_destinations':[list(v) for v in observed], 'status':'no destination reached' if not observed else 'destination reached; selector and revision comparison pending'})
report={'method':'Historical QZ next base and constant/dynamic J/K bits compared to printed-rule reachability. Dynamic branches are candidates, not assertions every outcome is used. Revisions and partial masks require source review. No automatic edits.',
 'pages_checked':len(set(r['page'] for r in rows)),'nodes_checked':len(rows),'records':rows}
(OUT/'QZ wiring checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'Incoming wiring checks.json').write_text(json.dumps(incoming,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'QZ wiring checks.csv').open('w',newline='',encoding='utf-8-sig') as f:
 writer=csv.writer(f);writer.writerow(['Page','Box','ROS address','QZ destinations','Text destinations','Review status'])
 for r in rows:writer.writerow([r['page'],r['box'],r['ROS_address'],' '.join(r['QZ_expected_addresses']),'; '.join('.'.join(v) for v in r['text_wire_destinations']),r['status']])
print(report['pages_checked'],'pages,',len(rows),'nodes,',sum(r['status']=='corroborated' for r in rows),'corroborated routes,',sum(r['status']=='review required' for r in rows),'review findings')
for r in rows:
 if r['page'] in __import__('sys').argv[1:]:print(r['page'],r['box'],r['ROS_address'],r['QZ_expected_addresses'],r['text_wire_destinations'],r['status'])

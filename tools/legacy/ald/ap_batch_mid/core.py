import json
from pathlib import Path
from collections import defaultdict
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('D:/Github/IBM360')
OUT=ROOT/'ALD_Visual_Transcriptions/ALD Diagrams'
nodes={};paths=[];labels=[];junctions=[];nets={}
def raw_nodes(raw):
 for line in raw.splitlines():
  ident,x,y,func,unit,card,loc,grid,*extra=line.split()
  unit='' if unit=='_' else unit;card='' if card=='_' else card;loc='' if loc=='_' else loc
  nodes[ident]={'id':ident,'column':int(x),'row':int(y),'function':func.replace('.', ' '),'unit':unit,'card_type':card[:4],'portion':card[4:],'printed_card_portion':card,'location':loc,'grid':grid,'height':int(extra[0]) if extra else 7,'source_reviewed':True}
def text(x,y,s): labels.append((x,y,s))
def wire(net,*points):
    paths.append({'net':net,'points':[list(p) for p in points]})
def j(net,x,y): junctions.append({'net':net,'column':x,'row':y})
def terminal(node,pin,row,side='input',triangle=True,printed_label=None):
    n=nodes[node]; x=n['column']; printed_label=pin if printed_label is None else printed_label
    physical_pin=pin.replace('✲','')
    record={'pin':physical_pin or None,'printed_label':printed_label,'row':row,'side':side,'triangle':triangle,'source_reviewed':True}
    if record not in n.setdefault('pins',[]):n['pins'].append(record)
    if side=='input':
        text(x-len(printed_label),row,printed_label)
        if triangle:text(x,row,'◺')
        record['column']=x-len(printed_label)-1 if globals().get('EXACT_GRID',False) else x
        return (record['column'],row)
    if triangle:text(x+7,row,'◺')
    text(x+8,row,printed_label)
    record['column']=x+8+len(printed_label)
    return (record['column'],row)
def net(name,driver,targets,external=None):
    nets[name]={'id':name,'driver':driver,'targets':targets,'external':external,'source_reviewed':True}
def inp(id,pin,row,tri=True,label=None):return terminal(id,pin,row,'input',tri,label)
def out(id,pin,row,tri=True,label=None):return terminal(id,pin,row,'output',tri,label)
def ext(x,y,s):text(x,y,s)

def normalize_stem(name,old,new):
    for path in paths:
        if path['net']==name:
            for p in path['points']:
                if p[0]==old:p[0]=new
    for point in junctions:
        if point['net']==name and point['column']==old:point['column']=new

def source_plain_ports(identifiers,inputs=True,outputs=True):
    global labels
    for ident in identifiers:
        n=nodes[ident]
        for p in n.get('pins',[]):
            if not p['triangle'] or not((p['side']=='input' and inputs)or(p['side']=='output' and outputs)):continue
            p['triangle']=False;pin=p['pin']or'';x=n['column'];y=p['row']
            if p['side']=='input':
                labels=[(c,r,s)for c,r,s in labels if(c,r,s)!=(x,y,'◺')]
            else:
                labels=[(c,r,s)for c,r,s in labels if(c,r,s)!=(x+7,y,'◺')]

def finish(page,title,source,work,review_notes=None,status='source reviewed',width=263,height=110):
 review_notes=review_notes or []
 refs=json.loads((ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing/ALD references.json').read_text(encoding='utf-8'))['ALD_pages'].get(page,[])
 cards=[r for r in refs if r['kind']=='card portion'];matches=0
 for n in nodes.values():
  if not n['card_type']:n['kind']='printed logical connector block';continue
  m=[r for r in cards if r['card_type']==n['card_type'] and r['portion']==n['portion'] and n['location'][4:] in r['sockets']]
  if len(m)==1:n['socket_listing_evidence']=m[0];matches+=1
  else:n['socket_listing_match_status']='unmatched';print('A1 UNMATCHED',n['id'],n['printed_card_portion'],n['location'])
 owners=defaultdict(list);edges=defaultdict(set);cells=defaultdict(lambda:defaultdict(set));graphs=defaultdict(lambda:defaultdict(set))
 for name,n in nets.items():
  for target in n['targets']:owners[target].append(name)
 for path in paths:
  for a,b in zip(path['points'],path['points'][1:]):
   x,y=a;X,Y=b;assert x==X or y==Y,(a,b);dx=(X>x)-(X<x);dy=(Y>y)-(Y<y)
   while (x,y)!=(X,Y):
    xx,yy=x+dx,y+dy;edge=tuple(sorted(((x,y),(xx,yy))));edges[edge].add(path['net']);cells[(x,y)][path['net']].add((dx,dy));cells[(xx,yy)][path['net']].add((-dx,-dy));graphs[path['net']][(x,y)].add((xx,yy));graphs[path['net']][(xx,yy)].add((x,y));x,y=xx,yy
 duplicates={k:v for k,v in owners.items() if len(v)>1}
 shared=[{'edge':k,'nets':list(v)} for k,v in edges.items() if len(v)>1]
 # A physical output endpoint lies immediately after its printed pin label.
 # Include that implicit horizontal connection when selecting the endpoint glyph.
 for n in nodes.values():
  for p in n.get('pins',[]):
   if p['side']=='output' or globals().get('EXACT_GRID',False):
    by=cells.get((p['column'],p['row']),{})
    for name,dirs in by.items():dirs.add((-1,0) if p['side']=='output' else (1,0))
 disconnected=[]
 virtual_owner_links=[]
 for name,n in nets.items():
  driver=n.get('driver');owner=driver.split('.')[0] if isinstance(driver,str) else None
  if owner in nodes:
   ports=[(p['column'],p['row'])for p in nodes[owner].get('pins',[])if p['side']=='output' and (p['column'],p['row']) in graphs[name]]
   for a,b in zip(ports,ports[1:]):graphs[name][a].add(b);graphs[name][b].add(a);virtual_owner_links.append({'net':name,'owner':owner,'ports':[a,b],'kind':'same block output owner; not an external wire'})
 for name,graph in graphs.items():
  seen=set();todo=[next(iter(graph))]
  while todo:
   v=todo.pop()
   if v in seen:continue
   seen.add(v);todo.extend(graph[v]-seen)
  if len(seen)!=len(graph):disconnected.append(name)
 diamond_errors=[]
 for jt in junctions:
  by=cells.get((jt['column'],jt['row']),{})
  if set(by)!={jt['net']}:diamond_errors.append({'junction':jt,'owners':list(by)})
 checks={'A1_card_portions_matched':matches,'A1_total_card_portions':len(cards),'multiple_target_owners':duplicates,'different_net_shared_segments':shared,'disconnected_nets':disconnected,'diamond_owner_errors':diamond_errors,'same_block_output_owner_links':virtual_owner_links}
 assert not duplicates,duplicates
 assert not shared,shared
 assert not disconnected,disconnected
 assert not diamond_errors,diamond_errors
 g=[[' ']*width for _ in range(height)];corners={frozenset(((1,0),(0,1))):'┌',frozenset(((-1,0),(0,1))):'┐',frozenset(((1,0),(0,-1))):'└',frozenset(((-1,0),(0,-1))):'┘'};crossings=[]
 for (x,y),by in cells.items():
  dirs=set().union(*by.values())
  if len(by)>1:crossings.append({'column':x,'row':y,'nets':list(by),'joined':False})
  ch=corners.get(frozenset(dirs),'┼' if len(dirs)>2 else ('│' if any(d[1] for d in dirs) else '─'))
  if len(by)>1:ch='┼' if any(d[0] for d in dirs) and any(d[1] for d in dirs) else ch
  g[y][x]=ch
 for jt in junctions:g[jt['row']][jt['column']]='◇'
 for n in nodes.values():
  x,y=n['column'],n['row'];h=n['height'];g[y][x]='┌';g[y][x+7]='┐'
  for q in range(1,7):g[y][x+q]='─'
  for r in range(1,h):g[y+r][x]=g[y+r][x+7]='│'
  for row,s in ((y+1,n['function']),(y+3,n['unit']),(y+4,n['printed_card_portion']),(y+5,n.get('printed_location',n['location'])),(y+h-1,n['grid']+'──'+n['id'])):
   for q,ch in enumerate(s):g[row][x+1+q]=ch
 for x,y,s in labels:
  for q,ch in enumerate(s):g[y][x+q]=ch
 erased=[jt for jt in junctions if g[jt['row']][jt['column']]!='◇']
 assert not erased,{'rendered_junctions_erased':erased}
 erased_turns=[]
 for (x,y),by in cells.items():
  dirs=set().union(*by.values());shape=corners.get(frozenset(dirs))
  if shape and g[y][x] not in (shape,'◇','◺'):
   erased_turns.append({'column':x,'row':y,'expected':shape,'actual':g[y][x],'nets':list(by)})
 checks['rendered_wire_turns_erased']=erased_turns
 assert not erased_turns,{'rendered_wire_turns_erased':erased_turns}
 txt='\n'.join(''.join(r) if globals().get('EXACT_GRID',False) else ''.join(r).rstrip() for r in g)+'\n'
 allowed=json.loads((OUT/'Allowed characters.json').read_text(encoding='utf-8'))['allowed_characters'];assert not set(txt)-set(allowed),set(txt)-set(allowed)
 checks.update({'nodes':len(nodes),'nets':len(nets),'paths':len(paths),'unreadable_characters':txt.count('�'),'printed_input_terminals':sum(sum(p['side']=='input'for p in n.get('pins',[]))for n in nodes.values()),'driven_input_terminals':sum(sum(t.split('.')[0]in nodes for t in n['targets'])for n in nets.values()if n['driver']is not None),'undriven_or_isolated_input_terminals':sum(sum(t.split('.')[0]in nodes for t in n['targets'])for n in nets.values()if n['driver']is None)})
 assert checks['printed_input_terminals']==checks['driven_input_terminals']+checks['undriven_or_isolated_input_terminals'],checks
 if globals().get('EXACT_GRID',False):
  lattice=[n['id'] for n in nodes.values() if n['column'] not in (50,73,96,119,142,165,188) or n['row'] not in range(2,87,7)]
  interiors=[{'node':n['id'],'point':[x,y],'nets':list(by)} for (x,y),by in cells.items() for n in nodes.values() if n['column']<x<n['column']+7 and n['row']<y<n['row']+n['height']]
  ports=[];unattached=[]
  for n in nodes.values():
   for p in n.get('pins',[]):
    if p['side']!='input':continue
    name=n['id']+'.'+(p['pin'] or 'input'+str(1+sum(q['side']=='input' and not q['pin'] and q['row']<p['row'] for q in n['pins'])))
    possible=[key for key in owners if key==name or (not p['pin'] and key.startswith(n['id']+'.input'))]
    actual=set(cells.get((p['column'],p['row']),{}))
    expected={v for key in possible for v in owners[key]}
    if len(possible)>1:expected={v for v in expected if (p['column'],p['row']) in graphs[v]}
    if not expected or not expected<=actual:unattached.append({'node':n['id'],'pin':p,'expected':sorted(expected),'actual':sorted(actual)})
  assert not lattice,lattice
  assert not interiors,interiors
  assert not unattached,unattached
  checks.update(printer_grid_verified=True,exact_canvas=True,block_lattice_errors=lattice,wire_inside_block_errors=interiors,unattached_input_errors=unattached,passed=True)
 inv=json.loads((ROOT/'tmp/ald-text/ald/AP source inventory.json').read_text(encoding='utf-8'))
 entries=inv.get('pages',inv) if isinstance(inv,dict) else inv
 neighbor={}
 if isinstance(entries,list):
  for item in entries:
   if item.get('page')==page:neighbor=item;break
 work=Path(work);work.mkdir(parents=True,exist_ok=True);base=OUT/(page+' '+title)
 checks['rendered_junctions_checked']=len(junctions);checks['rendered_junctions_erased']=[]
 data={'page':page,'title':title,'source':source,'source_reviewed':True,'review_status':status,'nodes':list(nodes.values()),'nets':list(nets.values()),'wire_paths':paths,'junctions':junctions,'unjoined_crossings':crossings,'printed_labels':[{'column':x,'row':y,'text':s}for x,y,s in labels],'review_notes':review_notes,'validation':checks,'scan_neighbors':neighbor.get('scan_order',neighbor),'source_crops_directory':str(work)}
 if (work/'grid.json').exists():data['native_grid']={k:v for k,v in json.loads((work/'grid.json').read_text(encoding='utf-8')).items()if k!='symbols'}
 base.with_suffix('.txt').write_text(txt,encoding='utf-8');base.with_suffix('.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 note=page+' native source review\n\n'+json.dumps(checks,ensure_ascii=False,indent=2)+'\n\n'+json.dumps(review_notes,ensure_ascii=False,indent=2)+'\n\nScan neighbors\n'+json.dumps(neighbor,ensure_ascii=False,indent=2)+'\n'
 base.with_name(base.name+' review notes.txt').write_text(note,encoding='utf-8')
 cw,ch,fs=(12,18,20) if globals().get('EXACT_GRID',False) else (9,20,15)
 font=ImageFont.truetype(str(ROOT/'tmp/ald-text/JuliaMono-Regular.ttf'),fs);im=Image.new('RGB',(width*cw,height*ch),'white');d=ImageDraw.Draw(im)
 for y,row in enumerate(txt.splitlines()):
  for x,glyph in enumerate(row):
   if glyph!=' ':d.text((x*cw,y*ch),glyph,font=font,fill='black')
 im.save(work/'preview.png');im.save(base.with_name(base.name+' JuliaMono preview.png'))
 progress=Path(__file__).parent/'progress.json'
 if progress.exists():
  pd=json.loads(progress.read_text(encoding='utf-8'))
  for entry in pd['pages']:
   if entry['page']==page:entry.update({'status':status,'validation':checks,'output_base':str(base)})
  pd['completed_pages']=sum(entry['status']=='source reviewed, rendered and validated'for entry in pd['pages'])
  progress.write_text(json.dumps(pd,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(page,checks,flush=True)


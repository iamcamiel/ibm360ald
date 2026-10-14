"""Private renderer for source-reviewed AP pages owned by cas_finish_main."""
from pathlib import Path
from collections import defaultdict
import json
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('D:/Github/IBM360');BASE=Path(__file__).parent;OUT=ROOT/'ALD_Visual_Transcriptions/ALD Diagrams'
class Page:
 def __init__(self,page):
  self.page=page;self.work=BASE/page;self.source=json.loads((self.work/'source.json').read_text())
  self.nodes={};self.nets={};self.paths=[];self.labels=[];self.junctions=[];self.notes=[];self.footer={}
 def node(self,id,x,y,function,unit,card,location,grid):
  self.nodes[id]=dict(id=id,column=x,row=y,function=function,unit=unit,card_type=card[:4],portion=card[4:],printed_card_portion=card,location=location,grid=grid,pins=[],source_reviewed=True)
 def text(self,x,y,s):self.labels.append(dict(column=x,row=y,text=s))
 def wire(self,net,*pts):self.paths.append(dict(net=net,points=[list(p)for p in pts]))
 def j(self,net,x,y):self.junctions.append(dict(net=net,column=x,row=y))
 def pin(self,id,pin,row,side,tri):
  n=self.nodes[id];x=n['column'];p=dict(pin=pin or None,row=row,side=side,triangle=tri,source_reviewed=True)
  if p not in n['pins']:n['pins'].append(p)
  if side=='input':
   self.text(x-len(pin),row,pin+('◺'if tri else''));return x-len(pin)-1,row
  self.text(x+7 if tri else x+8,row,('◺'if tri else'')+pin);return x+8+len(pin),row
 def i(self,id,pin,row,tri=True):return self.pin(id,pin,row,'input',tri)
 def o(self,id,pin,row,tri=True):return self.pin(id,pin,row,'output',tri)
 def net(self,id,driver,targets,external=None):self.nets[id]=dict(id=id,driver=driver,targets=targets,external=external,source_reviewed=True)
 def left(self,row,signal,ref):self.text(3,row,signal);self.text(35,row,ref)
 def right(self,row,page,signal,ref):self.text(217-len(page),row,page);self.text(217,row,' ');self.text(218,row,signal);self.text(242,row,ref)
 def title(self,part,block,date='08-14-69',log='153',machine='7201-02',frame='02',ec='08-08-69 713380'):
  self.footer=dict(part_number=part,block=block,date=date,log=log,machine=machine,frame=frame,engineering_change=ec)
  self.text(230,0,'000 '+self.page);self.text(180,98,ec)
  for k,ch in enumerate(self.page):self.text(2,101+k,ch);self.text(246,99+k,ch)
  self.text(0,107,'000');self.text(245,105,'000')
  self.wire('title',(213,97),(244,97));self.wire('title',(213,97),(213,107));self.wire('title',(244,97),(244,107))
  self.text(217,98,self.source['title'][6:]);self.text(214,100,'DATE '+date+' MACH. '+machine)
  self.text(214,102,'LOG '+log+'      FRAME     '+frame);self.text(226,104,'P.N. '+part);self.text(214,106,'IBM CORP.    BLK.      '+block)
 def validate(self,cells,edges):
  index=json.loads((ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing/ALD references.json').read_text(encoding='utf-8'))['ALD_pages']
  refs=index.get(self.page,[]);cards=[r for r in refs if r['kind']=='card portion'];unmatched=[];fallback=[]
  for n in self.nodes.values():
   for pin in n['pins']:assert n['row']<=pin['row']<=n['row']+n.get('height',6),(n['id'],pin,'port beyond block outline')
   def fits(r):return r['kind']=='card portion'and r['card_type']==n['card_type']and r['portion']==n['portion']and n['location'][4:]in r['sockets']and r['board']=='02'+n['location'][:4]
   matches=[r for r in cards if fits(r)]
   if not matches:
    alternatives=[(page,r)for page,rs in index.items()for r in rs if '�'in page and fits(r)]
    unique={json.dumps(r,sort_keys=True):r for page,r in alternatives}
    if len(unique)==1:
     matches=list(unique.values());n['socket_listing_page_key_uncertain']=sorted(set(page for page,r in alternatives));fallback.append(n['id'])
   if len(matches)==1:n['socket_listing_evidence']=matches[0]
   else:unmatched.append(n['id'])
  if not getattr(self,'allow_unmatched_cards',False):assert not unmatched,unmatched
  owners=defaultdict(list)
  for name,net in self.nets.items():
   for t in net['targets']:owners[t].append(name)
  duplicate={k:v for k,v in owners.items()if len(v)>1};assert not duplicate,duplicate
  shared=[dict(edge=k,nets=list(v))for k,v in edges.items()if len(v)>1];assert not shared,shared
  graphs=defaultdict(lambda:defaultdict(set))
  for(a,b),names in edges.items():
   for name in names:graphs[name][a].add(b);graphs[name][b].add(a)
  for name,net in self.nets.items():
   if net.get('through_port'):
    nodeid,pin=net['through_port'].split('.',1);n=self.nodes[nodeid];ports=[p for p in n['pins']if p['pin']==pin]
    assert len(ports)==2 and {p['side']for p in ports}=={'input','output'}
    pts=[((n['column']-len(pin)-1)if p['side']=='input'else n['column']+8+len(pin),p['row'])for p in ports]
    a,b=pts;graphs[name][a].add(b);graphs[name][b].add(a)
  disconnected=[]
  for name,g in graphs.items():
   seen=set();todo=[next(iter(g))]
   while todo:
    v=todo.pop()
    if v in seen:continue
    seen.add(v);todo.extend(g[v]-seen)
   if len(seen)!=len(g):disconnected.append(name)
  assert not disconnected,disconnected
  for j in self.junctions:assert set(cells[j['column'],j['row']])=={j['net']},j
  inputs=sum(sum(p['side']=='input'for p in n['pins'])for n in self.nodes.values())
  driven=sum(sum(t.split('.')[0]in self.nodes for t in n['targets'])for n in self.nets.values()if n['driver']is not None)
  unused=sum(sum(t.split('.')[0]in self.nodes for t in n['targets'])for n in self.nets.values()if n['driver']is None and n['id'].startswith('UNUSED'))
  jumper=sum(sum(t.split('.')[0]in self.nodes for t in n['targets'])for n in self.nets.values()if n['driver']is None and not n['id'].startswith('UNUSED'))
  assert inputs==driven+jumper+unused,(inputs,driven,jumper,unused)
  return dict(A1_card_portions_matched=len(self.nodes)-len(unmatched),A1_total_card_portions=len(cards),A1_unmatched_card_portions=unmatched,A1_damaged_page_key_matches=fallback,printed_input_terminals=inputs,driven_input_terminals=driven,isolated_jumper_terminals=jumper,unused_source_terminals=unused,multiple_target_owners=duplicate,different_net_shared_segments=shared,disconnected_nets=disconnected,unreadable_locations=sum('�'in q.get('literal','')for q in self.notes))
 def render(self,status='source reviewed'):
  W,H=getattr(self,'canvas_size',(260,111));g=[[' ']*W for _ in range(H)];cells=defaultdict(lambda:defaultdict(set));edges=defaultdict(set)
  for p in self.paths:
   for a,b in zip(p['points'],p['points'][1:]):
    x,y=a;X,Y=b;assert x==X or y==Y,(a,b);dx=(X>x)-(X<x);dy=(Y>y)-(Y<y)
    while(x,y)!=(X,Y):
     xx,yy=x+dx,y+dy;cells[x,y][p['net']].add((dx,dy));cells[xx,yy][p['net']].add((-dx,-dy));edges[tuple(sorted(((x,y),(xx,yy))))].add(p['net']);x,y=xx,yy
  # Pin letters cover the horizontal connection into the block. Retain its
  # direction when a path turns immediately after a printed output label.
  for n in self.nodes.values():
   for pin in n['pins']:
    endpoint=((n['column']+8+len(pin['pin']or''))if pin['side']=='output'else(n['column']-len(pin['pin']or'')-1),pin['row'])
    if endpoint in cells:
     for dirs in cells[endpoint].values():dirs.add((-1,0)if pin['side']=='output'else(1,0))
  corners={frozenset(((1,0),(0,1))):'┌',frozenset(((-1,0),(0,1))):'┐',frozenset(((1,0),(0,-1))):'└',frozenset(((-1,0),(0,-1))):'┘'};crossings=[]
  for(x,y),by in cells.items():
   dirs=set().union(*by.values())
   if len(by)>1:
    crossings.append(dict(column=x,row=y,nets=list(by),joined=False));ch='┼'if any(d[0]for d in dirs)and any(d[1]for d in dirs)else('│'if any(d[1]for d in dirs)else'─')
   else:ch=corners.get(frozenset(dirs),'┼'if len(dirs)>2 else('│'if any(d[1]for d in dirs)else'─'))
   g[y][x]=ch
  for j in self.junctions:g[j['row']][j['column']]='◇'
  for n in self.nodes.values():
   x,y=n['column'],n['row'];g[y][x]='┌';g[y][x+7]='┐'
   for q in range(1,7):g[y][x+q]='─'
   height=n.get('height',6)
   for r in range(1,height+1):g[y+r][x]=g[y+r][x+7]='│'
   for row,s in((y+1,n['function']),(y+3,n['unit']),(y+4,n['printed_card_portion']),(y+5,n['location']),(y+height,n['grid']+'──'+n.get('printed_id',n['id']))):
    for q,ch in enumerate(s):g[row][x+1+q]=ch
  for label in self.labels:
   for q,ch in enumerate(label['text']):
    assert 0<=label['column']+q<W and 0<=label['row']<H,('Label outside canvas',label)
    g[label['row']][label['column']+q]=ch
  overwritten=[j for j in self.junctions if g[j['row']][j['column']]!='◇']
  assert not overwritten,('Printed junction obscured by text',overwritten)
  txt='\n'.join(''.join(r)if getattr(self,'canvas_size',None)==(245,103)else''.join(r).rstrip()for r in g)+'\n';allowed=json.loads((OUT/'Allowed characters.json').read_text(encoding='utf-8'))['allowed_characters'];assert not set(txt)-set(allowed),set(txt)-set(allowed)
  checks=self.validate(cells,edges)
  if getattr(self,'canvas_size',None)==(245,103):
   from exact_grid_check import audit
   checks.update(audit(self,cells,edges,g))
  checks['unreadable_characters']=txt.count('�')
  inventory=json.loads((ROOT/'tmp/ald-text/ald/AP source inventory.json').read_text(encoding='utf-8'))
  entries=inventory if isinstance(inventory,list)else inventory.get('pages',inventory.get('files',[]))
  neighbors=next((e for e in entries if e.get('page')==self.page),{})
  data=dict(page=self.page,title=self.source['title'][6:],source=self.source['source'],source_reviewed=True,review_status=status,nodes=list(self.nodes.values()),nets=list(self.nets.values()),wire_paths=self.paths,junctions=self.junctions,unjoined_crossings=crossings,printed_labels=self.labels,footer=self.footer,review_notes=self.notes,validation=checks,scan_order_evidence=neighbors)
  base=OUT/self.source['title'];base.with_suffix('.txt').write_text(txt,encoding='utf-8');base.with_suffix('.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  notes=self.page+' source review\n\n'+str(len(self.nodes))+' visually reviewed card portions; '+str(len(self.nets))+' nets and '+str(len(self.paths))+' paths.\n'+str(checks['printed_input_terminals'])+' printed input terminals comprise '+str(checks['driven_input_terminals'])+' driven inputs and '+str(checks['isolated_jumper_terminals'])+' isolated jumper terminals and '+str(checks['unused_source_terminals'])+' UNUSED terminals.\nA1 validation: '+json.dumps({k:v for k,v in checks.items()if k.startswith('A1_')})+'. Inputs have one semantic net owner; no different-net shared edges, disconnected nets or multi-net diamonds. A1 validates card portions and connector references, not local gate pins.\nOnly printed ◇ joins wires. Unjoined crossings use ┼ and retain independent net IDs.\nSource lettering, gate portions, external references, pins, footer and wiring inspected in native crops; layout normalized to the printer grid. No handwriting transcribed.\n\nSource review notes\n'+json.dumps(self.notes,ensure_ascii=False,indent=2)+'\n\nOriginal scan order\n'+json.dumps(neighbors,ensure_ascii=False,indent=2)+'\n'
  base.with_name(base.name+' review notes.txt').write_text(notes,encoding='utf-8')
  font=ImageFont.truetype(str(ROOT/'tmp/ald-text/JuliaMono-Regular.ttf'),20);im=Image.new('RGB',(W*12,H*18),'white');d=ImageDraw.Draw(im)
  for y,row in enumerate(txt.splitlines()):
   for x,ch in enumerate(row):
    if ch!=' ':d.text((x*12,y*18),ch,font=font,fill='black')
  im.save(self.work/'preview.png');im.save(base.with_suffix('.png'));im.crop((0,0,W*12,864)).save(self.work/'preview-upper.png');im.crop((0,864,W*12,1728)).save(self.work/'preview-lower.png');im.crop((2000,1728,3120,1998)).save(self.work/'preview-footer.png')
  print(self.page,len(self.nodes),'nodes',len(self.nets),'nets',len(self.paths),'paths',{k:v for k,v in checks.items() if k not in ('physical_terminal_owners','printer_grid')},flush=True)
  return data

"""Independent layout invariants for privately rendered, measured AP pages."""
from collections import defaultdict

def audit(p,cells,edges,g):
 W,H=p.canvas_size
 assert(W,H)==(245,103)
 cols={50,73,96,119,142,165,188};rows={2+7*k for k in range(13)}
 assert all(n['column']in cols and n['row']in rows for n in p.nodes.values()),'Node off source lattice'
 interior=[]
 for n in p.nodes.values():
  for y in range(n['row']+1,n['row']+n.get('height',6)+1):
   for x in range(n['column']+1,n['column']+7):
    if(x,y)in cells:interior.append((n['id'],x,y,list(cells[x,y])))
 assert not interior,('Wire inside block',interior)
 collisions=[];written={}
 for label in p.labels:
  for k,ch in enumerate(label['text']):
   if ch.isspace()or ch in '─│┌┐└┘┼◇◺':continue
   pos=(label['column']+k,label['row'])
   if pos in written and written[pos]!=ch:collisions.append((pos,written[pos],ch))
   written[pos]=ch
 assert not collisions,('Different printed letters collide',collisions)
 def aliases(pin):
  if not pin:return set()
  s=pin.split('✲')[0];a={s}
  if s.startswith('K '):a.add(s[2:])
  if len(s)==4 and s[0]in'BH2':a.add(s[1:])
  return a
 missing=[];terminal_owners=[];used=defaultdict(int)
 for n in p.nodes.values():
  for pin in n['pins']:
   side=pin['side'];printed=pin['pin']or'';row=pin['row']
   x=n['column']-len(printed)-1 if side=='input' else n['column']+8+len(printed)
   direction=(1,0)if side=='input'else(-1,0)
   candidates=[]
   for name,net in p.nets.items():
    endpoints=net['targets']if side=='input'else[net['driver']]+[v['port']for v in net.get('commoned_outputs',[])]+([net['through_port']]if net.get('through_port')else[])
    for endpoint in endpoints:
     if endpoint is None or not endpoint.startswith(n['id']+'.'):continue
     logical=endpoint.split('.',1)[1]
     matched=(logical in aliases(printed)or logical==printed+'@'+str(row)) if printed else logical=='output'or logical.startswith('input')
     if matched and name in cells.get((x,row),{}) and direction in cells[x,row][name]:candidates.append((name,endpoint))
   if len(candidates)!=1:missing.append(dict(node=n['id'],pin=printed,row=row,side=side,point=[x,row],candidates=candidates,geometry=list(cells.get((x,row),{}))))
   else:
    name,endpoint=candidates[0];terminal_owners.append(dict(node=n['id'],pin=printed,row=row,side=side,net=name,semantic_terminal=endpoint))
    if side=='input':used[endpoint]+=1
 assert not missing,('Missing or ambiguous physical terminal owners',missing)
 # Distinct unlabelled ports have distinct input1/input2 targets and rows.
 duplicates={k:v for k,v in used.items()if v>1};assert not duplicates,('Duplicate physical semantic terminal',duplicates)
 expected={t for net in p.nets.values()for t in net['targets']if t.split('.')[0]in p.nodes}
 absent=sorted(expected-set(used));assert not absent,('Semantic input without printed terminal',absent)
 assert all(len(row)==245 for row in g)and len(g)==103
 assert not any('a'<=ch<='z' for row in g for ch in row),'Lowercase diagram glyph'
 assert ''.join(g[100][227:231])=='P.N.','Part-number label must be P.N.'
 for row in (96,100):
  assert g[row][239]!=' ' and g[row][240]==' ' and g[row][241]=='│',('Footer must end value239 blank240 border241',row)
 assert ''.join(g[96][233:240])==p.footer['machine']
 assert ''.join(g[100][233:240])==p.footer['part_number']
 return dict(passed=True,printer_grid={'columns':245,'rows':103,'zero_based':True,'node_left_columns':sorted(cols),'ordinary_top_rows':sorted(rows),'block_width':8,'ordinary_height':7,'title_frame':[210,93,241,102]},physical_terminal_owners=terminal_owners,missing_input_owners=[],ambiguous_port_owners=[],paths_inside_block_interiors=[],text_letter_collisions=[],block_lattice_passed=True,canvas_dimensions_passed=True,uppercase_diagram_passed=True,footer_one_cell_gap_passed=True)

import os
os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import sys,json,re
import numpy as np
from PIL import Image,ImageDraw,ImageFont
O=Path(__file__).parent;sys.path.insert(0,str(O/'cv-runtime'))
import cv2
from glyph_prototype import masks
from cas_local_grid import local_phases
from cas_transcribe import BOX,preview
D=O/'cas';OUT=O.parent.parent/'ALD_Visual_Transcriptions/CAS Diagrams';OUT.mkdir(exist_ok=True)
PLAN=json.loads((O.parent/'ald-renaming/rename-plan.json').read_text());SOURCES={v['page']:v for v in PLAN if v.get('page')}
QZ=json.loads((OUT.parent/'QZ ROS Listing/ROS words.json').read_text())['records'];ROS={v['address']:v for v in QZ}
def normalized(s):return re.sub('[^0-9A-FX]','',s.upper().replace('O','0').replace('I','1').replace('L','1').replace('S','5'))
def render(page):
 spec=json.loads((D/(page+' reviewed.json')).read_text(encoding='utf-8'));source=SOURCES[page];i=source['id']
 g=json.loads((O/f'grid-{i}.json').read_text());im=cv2.imread(str(O/f'grid-{i}.png'),0)
 col,row,center,phase=local_phases(g,im.shape);xp,yp=g['xp'],g['yp'];rows=round(im.shape[0]/yp)+1;cols=round(im.shape[1]/xp)+1
 rows=max(rows,spec.get('canvas_rows',rows));cols=max(cols,spec.get('canvas_columns',cols))
 grid=np.full((rows,cols),' ',dtype='<U1');wires=np.zeros((rows,cols),'uint8')
 if spec.get('source_grid'):
  calibration=spec['source_grid']
  def col(x,y):return round(45+(x-calibration['first_right'])/calibration['column_step']*22)
  def row(x,y):return round(5+(y-calibration['first_header_y'])/calibration['row_step']*11)
 # Derive printed rules from dark ink; pencil strokes do not supply wires.
 dark=np.where(im<190,0,255).astype('uint8');b,hm,vm=masks(dark,xp)
 for mask,axis in [(hm,4),(vm,1)]:
  _,_,st,_=cv2.connectedComponentsWithStats(mask)
  for x,y,w,h,area in st[1:]:
   if y<210 or x<200 or y>4500:continue
   if any(x<r[2] and x+w>r[0] and y<r[3] and y+h>r[1] for r in spec.get('exclude_wiring_rectangles',[])):continue
   if axis==4:
    rr=row(x+w/2,y+h/2);c1=max(0,col(x,y+h/2));c2=min(cols-1,col(x+w,y+h/2))
    if 0<=rr<rows:wires[rr,c1:c2+1]|=4
   else:
    cc=col(x+w/2,y+h/2);r1=max(0,row(x+w/2,y));r2=min(rows-1,row(x+w/2,y+h))
    if 0<=cc<cols:wires[r1:r2+1,cc]|=1
 # Only explicitly reviewed corrections may erase or add projected traces.
 for c1,r1,c2,r2 in spec.get('wire_erase',[]):
  wires[max(0,r1):min(rows,r2+1),max(0,c1):min(cols,c2+1)]=0
 for points in spec.get('wire_paths',[]):
  for (c1,r1),(c2,r2) in zip(points,points[1:]):
   assert c1==c2 or r1==r2,(page,'non-orthogonal wire',points)
   if c1==c2:wires[min(r1,r2):max(r1,r2)+1,c1]|=1
   else:wires[r1,min(c1,c2):max(c1,c2)+1]|=4
 for r,c in zip(*np.nonzero(wires)):
  vertical=bool(wires[r,c]&1);horizontal=bool(wires[r,c]&4)
  key=int(vertical and r>0 and bool(wires[r-1,c]&1))+2*int(vertical and r+1<rows and bool(wires[r+1,c]&1))+4*int(horizontal and c>0 and bool(wires[r,c-1]&4))+8*int(horizontal and c+1<cols and bool(wires[r,c+1]&4))
  grid[r,c]=BOX[key]
 annotations=[];checks=[]
 def put(c,r,text):
  assert 0<=r<rows and 0<=c and c+len(text)<=cols,(page,c,r,text)
  grid[r,c:c+len(text)]=list(text);annotations.append({'row':r+1,'column':c+1,'text':text})
 words=[]
 for s in g['symbols']:
  t=s['word'].strip();x,y,xx,yy=s['box']
  if words and words[-1]['text']==t and abs(words[-1]['box'][1]-y)<40 and x-words[-1]['box'][2]<70:
   a=words[-1]['box'];a[0]=min(a[0],x);a[1]=min(a[1],y);a[2]=max(a[2],xx);a[3]=max(a[3],yy)
  else:words.append({'text':t,'box':[x,y,xx,yy]})
 for node in spec['nodes']:
  label,leg,address=node['box'],node['leg'],node['address'];n=int(label[1:])-1;rank='ACEGJLNQS'.index(label[0])
  nominal_x=1400+n*655;nominal_y=300+rank*495
  candidates=[w for w in words if normalized(w['text'])==address or normalized(w['text'])==address.lstrip('0')]
  candidates=[w for w in candidates if abs(w['box'][0]-nominal_x)<650 and abs(w['box'][1]-nominal_y)<300]
  if candidates:
   best=min(candidates,key=lambda w:abs(w['box'][0]-nominal_x)+abs(w['box'][1]-nominal_y)*2)
   x,y,xx,yy=best['box'];right=col(xx-xp*.5,(y+yy)/2);rr=row((x+xx)/2,(y+yy)/2);cc=right-14
  else:
   x,y=node.get('header_pixel',[nominal_x,nominal_y]);right=col(x,y);rr=row(x,y);cc=right-14
  if spec.get('source_grid'):cc,rr=31+n*22,5+rank*11
  if 'grid' in node:cc,rr=node['grid']
  # Clearing the complete body removes artefacts where characters touch rules.
  # Draw the two borders explicitly around the visually transcribed fields.
  separate_R=node.get('R_line') is not None or bool(node.get('selector'))
  label_row=node.get('label_row',max(7,len(node['fields'])+1+int(separate_R)))
  grid[rr:rr+label_row+1,cc:cc+15]=' '
  for r in range(rr+1,rr+label_row+1):put(cc,r,'│');put(cc+14,r,'│')
  header=leg+' ─── '+address;put(cc+15-len(header),rr,header)
  for k,text in enumerate(node['fields']):put(cc,rr+k+1,text)
  if node.get('selector'):
   put(cc,rr+label_row-1,'R')
   for pos,text in node['selector']:put(cc+pos,rr+label_row-1,text)
  if node.get('R_line') is not None:put(cc,rr+label_row-1,node['R_line'])
  exit=node['exit'];put(cc,rr+label_row,label+'──');put(cc+15-len(exit),rr+label_row,exit)
  for k,text in enumerate(node.get('comments',[])):put(cc-1,rr+label_row+1+k,text)
  if node.get('output_star',True):put(cc+15,rr+node.get('output_port_row',3),node.get('output_symbol','*'))
  for pos,text in node.get('extra',[]):put(cc+pos[0],rr+pos[1],text)
  record=ROS.get(address.zfill(4))
  check={'address':address,'CAS_box':label,'grid':[cc,rr],'QZ_address_present':bool(record)}
  if record:
   fields=record['fields'];controls={f:int(fields[f],2) for f in ['W','A','B','C','D','F','G','L','K','J','M','N','P','Q','R','T','V']}
   controls.update(E=int(fields['EW']+fields['E'],2),H=int(fields['HW']+fields['H'],2),U=int(fields['UA']+fields['U'],2))
   check.update(QZ_page=record['cas_page'],QZ_box=record['cas_box'],QZ_controls=controls,
                QZ_next_base=f"{int(fields['NEXT_HI']+fields['NEXT_MID']+fields['NEXT_LO'],2)<<2:04X}")
   if node.get('codes'):
    expected={f:0 for f in controls}
    for code in node['codes'].split():expected[code[0]]=int(code[1:])
    check['control_field_differences']={f:{'CAS':expected[f],'QZ':v} for f,v in controls.items() if expected[f]!=v}
  checks.append(check)
 for text in spec.get('text',[]):put(text[0],text[1],text[2])
 for coln,rownum,text in spec.get('pixel_text',[]):
  x,y=coln,rownum;put(col(x,y),row(x,y),text)
 for c,r,ch in spec.get('cells',[]):put(c,r,ch)
 # Footer values are visually supplied independently of the ROS listing.
 footer=spec.get('footer',[])
 for c,r,text in footer:put(c,r,text)
 allowed=json.loads((OUT.parent/'Allowed characters.json').read_text(encoding='utf-8'))['allowed_characters']
 assert all(ch in allowed or 0x2500<=ord(ch)<=0x257f for ch in grid.ravel())
 lines=[''.join(a).rstrip() for a in grid];filename=Path(source['newpath']).stem+'.txt'
 (OUT/filename).write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\r\n')
 preview(page+' reviewed',lines,xp,yp)
 (OUT/(page+' verification.json')).write_text(json.dumps({'page':page,'source':source['newpath'],'status':spec.get('status','Visually transcribed; wiring review pending'),
  'nodes':checks,'unresolved':spec.get('unresolved',[]),'annotations':annotations},ensure_ascii=False,indent=2),encoding='utf-8')
 print('Rendered',page,len(checks),'boxes; QZ found',sum(c['QZ_address_present'] for c in checks),flush=True)
 return checks
if __name__=='__main__':
 for page in sys.argv[1:]:render(page)

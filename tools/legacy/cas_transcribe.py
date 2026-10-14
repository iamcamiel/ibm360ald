import os
os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import sys,json,re,time
import numpy as np
from PIL import Image,ImageDraw,ImageFont
O=Path(__file__).parent;sys.path.insert(0,str(O/'cv-runtime'))
import cv2
from glyph_prototype import masks,feature
from cas_local_grid import local_phases
cv2.setNumThreads(1)
D=O/'cas';D.mkdir(exist_ok=True)
z=np.load(O/'cas-font.npz');MODEL=z['features'];LABELS=z['labels'];NORM=(MODEL*MODEL).sum(1)
BOX={0:'─',1:'│',2:'│',3:'│',4:'─',8:'─',12:'─',5:'┘',9:'└',6:'┐',10:'┌',7:'┤',11:'├',13:'┴',14:'┬',15:'┼'}
plan=json.loads((O.parent/'ald-renaming/rename-plan.json').read_text())
records={r['page']:r for r in plan if r.get('page')}
policy=json.loads((O.parent.parent/'ALD_Visual_Transcriptions/Allowed characters.json').read_text(encoding='utf-8'))
allowed=set(policy['allowed_characters'])|{chr(i) for i in range(0x2500,0x2580)}

def transcribe(page):
 record=records[page];i=record['id'];g=json.loads((O/f'grid-{i}.json').read_text());im=cv2.imread(str(O/f'grid-{i}.png'),0)
 xp,yp,x0,y0=[g[k] for k in ['xp','yp','xphase','yphase']]
 col,row,center,phase_metadata=local_phases(g,im.shape)
 rows=round(im.shape[0]/yp)+1;cols=round(im.shape[1]/xp)+1
 b,hm,vm=masks(im,xp);clean=(im<190).astype('uint8')&~(hm|vm)
 grid=np.full((rows,cols),' ',dtype='<U1');wires=np.zeros((rows,cols),'uint8')
 def accepted(x,y):return (500<x<7450 and 100<y<4320) or (4500<x<7450 and 4460<y<4900)
 segments=[]
 for mask,axis in [(hm,4),(vm,1)]:
  _,_,stats,_=cv2.connectedComponentsWithStats(mask)
  for x,y,w,h,area in stats[1:]:
   if not accepted(x+w/2,y+h/2):continue
   if axis==4:
    rr=row(x+w/2,y+h/2);c1=max(0,col(x,y+h/2));c2=min(cols-1,col(x+w,y+h/2))
    if not 0<=rr<rows:continue
    wires[rr,c1:c2+1]|=4
    segments.append({'axis':'horizontal','row':rr,'first':c1,'last':c2,'pixel_box':list(map(int,(x,y,x+w,y+h)))})
   else:
    cc=col(x+w/2,y+h/2);r1=max(0,row(x+w/2,y));r2=min(rows-1,row(x+w/2,y+h))
    if not 0<=cc<cols:continue
    wires[r1:r2+1,cc]|=1
    segments.append({'axis':'vertical','column':cc,'first':r1,'last':r2,'pixel_box':list(map(int,(x,y,x+w,y+h)))})
 for r,c in zip(*np.nonzero(wires)):
  vertical=bool(wires[r,c]&1);horizontal=bool(wires[r,c]&4)
  key=int(vertical and r>0 and bool(wires[r-1,c]&1))+2*int(vertical and r+1<rows and bool(wires[r+1,c]&1))+4*int(horizontal and c>0 and bool(wires[r,c-1]&4))+8*int(horizontal and c+1<cols and bool(wires[r,c+1]&4))
  grid[r,c]=BOX[key]
 features=[];locations=[];bounds=[];props=[]
 _,labs,stats,_=cv2.connectedComponentsWithStats(clean)
 parts={}
 for k,(x,y,w,h,area) in enumerate(stats[1:],1):
  if area<18 or not accepted(x+w/2,y+h/2) or h>yp*1.25 or w>xp*1.65:continue
  if w<7 and h>yp*.8:continue
  rr,cc=row(x+w/2,y+h/2),col(x+w/2,y+h/2)
  if not(0<=rr<rows and 0<=cc<cols):continue
  parts.setdefault((rr,cc),[]).append((int(x),int(y),int(w),int(h),k))
 for (rr,cc),values in parts.items():
  x1=min(v[0] for v in values);y1=min(v[1] for v in values)
  x2=max(v[0]+v[2] for v in values);y2=max(v[1]+v[3] for v in values)
  if x2-x1>xp*1.5 or y2-y1>yp*1.25:continue
  a=np.isin(labs[y1:y2,x1:x2],[v[4] for v in values]).astype('uint8')
  ys,xs=np.nonzero(a);h=y2-y1;w=x2-x1
  if h<4 or w<3:continue
  if h<9 and w>xp*.7:
   if grid[rr,cc]==' ':grid[rr,cc]='-'
   continue
  features.append(feature(a));locations.append((rr,cc));bounds.append([x1,y1,x2,y2]);props.append((w,h,float(ys.mean())))
 cells=[]
 for start in range(0,len(features),128):
  f=np.array(features[start:start+128],dtype='float32')
  distances=(f*f).sum(1)[:,None]+NORM[None,:]-2*f@MODEL.T
  for j,dist in enumerate(distances,start):
   bychar={}
   for char in set(LABELS):bychar[int(char)]=float(dist[LABELS==char].min())
   choices=sorted(bychar,key=bychar.get);ch=chr(choices[0]);d=bychar[choices[0]];margin=bychar[choices[1]]-d
   rr,cc=locations[j];w,h,ymean=props[j]
   if h<yp*.50 and ch.isalnum():ch=' ';d=99
   glyph=ch if d<42 else ' '
   if glyph not in allowed:glyph=' '
   if glyph!=' ':grid[rr,cc]=glyph
   cells.append({'row':rr,'column':cc,'character':glyph,'nearest':ch,'distance':round(d,2),'margin':round(margin,2),
                 'choices':[{ 'character':chr(k),'distance':round(bychar[k],2)} for k in choices[:4]],'box':bounds[j],
                 'uncertain':bool(d>=27 or margin<4),'width':int(w),'height':int(h),'center_y':round(ymean,2)})
 # High-confidence OCR prose is independent corroboration; it never adds glyphs
 # outside the approved set. Operator decisions use the printer templates.
 ocr_agreements=0
 lookup_cells={(v['row'],v['column']):v for v in cells}
 for s in g['symbols']:
  x,y,xx,yy=s['box'];ch=s['text']
  if len(ch)!=1 or not accepted((x+xx)/2,(y+yy)/2) or not(4<yy-y<yp*1.25 and 2<xx-x<xp*1.45):continue
  r,c=row((x+xx)/2,(y+yy)/2),col((x+xx)/2,(y+yy)/2)
  if not(0<=r<rows and 0<=c<cols):continue
  candidates=[]
  for plane in [clean,b]:
   a=plane[y:yy,x:xx];f=feature(a)
   if f.sum()<5:continue
   ds=((MODEL-f)**2).sum(1);k=ds.argmin();candidates.append((float(ds[k]),chr(int(LABELS[k]))))
  if not candidates:continue
  dist,predicted=min(candidates)
  cell=lookup_cells.get((r,c))
  if ch.isalnum() and ch in allowed and s['confidence']>85 and yy-y>yp*.6:
   predicted=ch;dist=min(dist,20)
  if not cell or (cell['uncertain'] and dist<cell['distance']):
   if predicted not in allowed or dist>42:continue
   if cell is None:
    cell={'row':r,'column':c,'box':[x,y,xx,yy],'choices':[]};cells.append(cell);lookup_cells[r,c]=cell
   cell.update(character=predicted,nearest=predicted,distance=round(dist,2),margin=0,
               uncertain=dist>=27,OCR_box_recovered=True)
   grid[r,c]=predicted
 for s in g['symbols']:
  ch=s['text'];x,y,xx,yy=s['box'];word=s['word'].strip()
  if len(ch)!=1 or not ch.isalnum() or ch not in allowed or s['confidence']<93:continue
  if not accepted((x+xx)/2,(y+yy)/2) or yy-y<yp*.65 or yy-y>yp*1.2 or xx-x>xp*1.2:continue
  r=row((x+xx)/2,(y+yy)/2);c=col((x+xx)/2,(y+yy)/2)
  if not(0<=r<rows and 0<=c<cols):continue
  cell=lookup_cells.get((r,c))
  if cell and cell['character']==ch:
   cell['OCR_agrees']=True;cell['uncertain']=False;ocr_agreements+=1
  elif cell and cell['uncertain'] and re.fullmatch('[A-Z]{4,}',word):
   cell['character']=ch;cell['OCR_prose']=True;cell['uncertain']=False;grid[r,c]=ch
 lines=[''.join(row).rstrip() for row in grid]
 meta={'page':page,'source':record['newpath'],'id':i,'rows':rows,'columns':cols,'grid':{k:g[k] for k in ['xp','yp','xphase','yphase','xc','yc']},
       'glyph_cells':cells,'wire_segments':segments,'OCR_agreements':ocr_agreements,'local_phases':phase_metadata,
       'uncertain_cells':sum(v['uncertain'] for v in cells),'blank_unreadable_cells':sum(v['character']==' ' for v in cells)}
 (D/(page+'.json')).write_text(json.dumps(meta,ensure_ascii=False),encoding='utf-8')
 (D/(page+'.txt')).write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\r\n')
 preview(page,lines,xp,yp)
 im=cv2.resize(im,(2040,round(im.shape[0]*2040/im.shape[1])));cv2.imwrite(str(D/(page+' scan.png')),im)
 print(page,len(cells),'glyphs',meta['uncertain_cells'],'uncertain',meta['blank_unreadable_cells'],'blank',flush=True)
 return meta

def preview(page,lines,xp=30,yp=45):
 font=ImageFont.truetype(str(O/'JuliaMono-Regular.ttf'),14)
 cw=font.getlength('M');ch=round(cw*yp/xp)
 canvas=Image.new('RGB',(round(max(map(len,lines))*cw)+20,len(lines)*ch+20),'white');d=ImageDraw.Draw(canvas)
 for r,line in enumerate(lines):
  for c,glyph in enumerate(line):
   if glyph==' ':continue
   d.text((10+c*cw,10+r*ch),glyph,font=font,fill='black')
 canvas.save(D/(page+' preview.png'))

if __name__=='__main__':
 pages=sys.argv[1:] or [r['page'] for r in json.loads((O/'cas-prepared.json').read_text())]
 for page in pages:transcribe(page)

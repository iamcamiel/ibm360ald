from pathlib import Path
import json,sys
import numpy as np
from PIL import Image,ImageDraw,ImageFont
O=Path(__file__).parent;sys.path.insert(0,str(O/'cv-runtime'));import cv2
cv2.setNumThreads(1)

def masks(im,pitch):
 b=(im<210).astype('uint8')
 h=cv2.morphologyEx(cv2.dilate(b,np.ones((5,1),'uint8')),cv2.MORPH_OPEN,np.ones((1,round(pitch*3)),'uint8'))
 vertical=cv2.morphologyEx(b,cv2.MORPH_CLOSE,np.ones((7,1),'uint8'))
 v=cv2.morphologyEx(cv2.dilate(vertical,np.ones((1,3),'uint8')),cv2.MORPH_OPEN,np.ones((round(pitch*4),1),'uint8'))
 return b,h,v

def feature(a):
 if a.size==0 or not np.any(a):return np.zeros(384,dtype='float32')
 ys,xs=np.nonzero(a);a=a[ys.min():ys.max()+1,xs.min():xs.max()+1]
 h,w=a.shape;scale=min(14/w,22/h);small=cv2.resize(a.astype('float32'),(max(1,round(w*scale)),max(1,round(h*scale))),interpolation=cv2.INTER_AREA)
 out=np.zeros((24,16),dtype='float32');h,w=small.shape;y=(24-h)//2;x=(16-w)//2;out[y:y+h,x:x+w]=small
 return out.ravel()

def train(ids):
 features=[];labels=[];patches=[]
 for i in ids:
  g=json.loads((O/f'grid-{i}.json').read_text());im=cv2.imread(str(O/f'grid-{i}.png'),0);b,hm,vm=masks(im,g['xp']);clean=b & ~(hm|vm)
  for s in g['symbols']:
   c=s['text'];x1,y1,x2,y2=s['box']
   if len(c)==1 and c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789=<>+*()/.,:' and s['confidence']>85 and y1>im.shape[0]*.065 and 15<y2-y1<g['yp']*1.3 and x2-x1<g['xp']*1.4:
    patch=clean[y1:y2,x1:x2];f=feature(patch)
    if f.sum()>8:features.append(f);labels.append(ord(c));patches.append((c,patch))
 knn=(np.asarray(features,dtype='float32'),np.asarray(labels,dtype='int32'))
 print('Train chars',len(features),''.join(sorted(set(map(chr,labels)))),flush=True)
 return knn

def prototype(i,knn):
 g=json.loads((O/f'grid-{i}.json').read_text());im=cv2.imread(str(O/f'grid-{i}.png'),0);xp,yp=g['xp'],g['yp'];xphase,yphase=g['xphase'],g['yphase']
 b,hm,vm=masks(im,xp);clean=b & ~(hm|vm)
 cols=int(np.ceil((im.shape[1]-xphase)/xp))+1;rows=int(np.ceil((im.shape[0]-yphase)/yp))+1;grid=np.full((rows,cols),' ',dtype='<U1')
 for mask,axis in [(hm,1),(vm,0)]:
  n,lab,stats,centers=cv2.connectedComponentsWithStats(mask)
  for x,y,w,h,area in stats[1:]:
   if axis==1:
    yy=round((y+h/2-yphase)/yp);xx1=round((x-xphase)/xp);xx2=round((x+w-xphase)/xp)
    if not 0<=yy<rows:continue
    for xx in range(max(0,xx1),min(cols,xx2+1)):grid[yy,xx]='+' if grid[yy,xx]=='|' else '-'
   else:
    xx=round((x+w/2-xphase)/xp);yy1=round((y-yphase)/yp);yy2=round((y+h-yphase)/yp)
    if not 0<=xx<cols:continue
    for yy in range(max(0,yy1),min(rows,yy2+1)):grid[yy,xx]='+' if grid[yy,xx]=='-' else '|'
 n,lab,stats,centers=cv2.connectedComponentsWithStats(clean)
 cells={}
 for k,(x,y,w,h,area) in enumerate(stats[1:],1):
  if area<18 or y<im.shape[0]*.065 or h<8 or h>yp*1.6 or w>xp*1.7:continue
  xx=round((x+w/2-xphase)/xp);yy=round((y+h/2-yphase)/yp)
  if 0<=xx<cols and 0<=yy<rows:
   if h>w*4 and w<7:
    if grid[yy,xx]==' ':grid[yy,xx]='|'
    continue
   cells.setdefault((yy,xx),[]).append((x,y,w,h,k))
 features=[];locations=[];glyphs=[]
 for (yy,xx),parts in cells.items():
  x1=min(t[0] for t in parts);y1=min(t[1] for t in parts);x2=max(t[0]+t[2] for t in parts);y2=max(t[1]+t[3] for t in parts)
  a=clean[y1:y2,x1:x2]
  if y2-y1<25:continue
  if x2-x1>xp*1.4 or y2-y1>yp*1.2:continue
  features.append(feature(a));locations.append((yy,xx));glyphs.append(a)
 if features:
  model,labels=knn;features=np.asarray(features,dtype='float32')
  dists=(features*features).sum(1)[:,None]+(model*model).sum(1)[None,:]-2*features@model.T
  nearest=dists.argmin(1)
  distances=dists[np.arange(len(features)),nearest]
  for loc,k,dist in zip(locations,nearest,distances):grid[loc]=chr(int(labels[k])) if dist<45 else '?'
  ids=np.flatnonzero(distances>40)
  atlas=Image.new('RGB',(1200,((len(ids)+11)//12)*100),'white');ad=ImageDraw.Draw(atlas);af=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',14)
  for n,k in enumerate(ids):
   x=n%12*100;y=n//12*100;patch=Image.fromarray((1-glyphs[k])*255);patch.thumbnail((60,65));atlas.paste(patch,(x+10,y+22));ad.text((x+2,y+2),f'{k}:{chr(labels[nearest[k]])} {distances[k]:.0f}',fill='blue',font=af)
  if len(ids):atlas.save(O/f'unknown-{i}.png')
 # Confident OCR glyphs retain distinctions such as O/0 and S/5.
 for s in g['symbols']:
  x1,y1,x2,y2=s['box'];c=s['text'];yy=round(((y1+y2)/2-yphase)/yp);xx=round(((x1+x2)/2-xphase)/xp)
  if y1>im.shape[0]*.065 and s['confidence']>80 and len(c)==1 and c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789=<>+*()/.,:' and 0<=xx<cols and 0<=yy<rows:grid[yy,xx]=c
 lines=[''.join(row).rstrip() for row in grid]
 (O/f'glyph-{i}.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',14);cw=font.getlength('M');ch=21
 out=Image.new('RGB',(round(cols*cw)+20,rows*ch+20),'white');d=ImageDraw.Draw(out)
 for n,line in enumerate(lines):d.text((10,n*ch+10),line,font=font,fill='black')
 out.save(O/f'glyph-{i}.png');print(i,'glyphs',len(locations),'unknown',sum(line.count('?') for line in lines),flush=True)
if __name__=='__main__':
 ids=list(map(int,sys.argv[1:]));knn=train(ids)
 for i in ids:prototype(i,knn)

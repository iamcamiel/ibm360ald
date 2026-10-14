import os
os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import sys,json,csv
import numpy as np
from PIL import Image,ImageDraw,ImageFont
O=Path(__file__).parent;sys.path.insert(0,str(O/'cv-runtime'))
import cv2
from glyph_prototype import feature
from qz_extract import clusters
cv2.setNumThreads(1)
CACHE=O/'qz'
LENGTHS=[1,1,4,4,2,5,3,1,4,6,5,2,5,4,4,4,2,5,7,5,4,3,1,3,1,1,4,1,4,1,3]
NAMES=['ND','P1','W','A','B','C','D','P2','E','F','G','HW','H','L','NEXT_HI','NEXT_MID','NEXT_LO','K','J','M','N','P','EW','Q','P3','R','T','P4','U','UA','V']

def geometry(g):
 words=g['words']
 def header(name):
  matches=[w for w in words if w['text'].upper()==name]
  if not matches:
   matches=[w for w in words if len(w['text'])==len(name) and sum(a!=b for a,b in zip(w['text'].upper(),name))<=1 and 300<w['box'][0]<3000 and w['box'][1]<max(g['rows'][:1])+40]
  return min(matches,key=lambda w:w['box'][0]) if matches else None
 he=header('HEX');mo=header('MODE');bi=header('BINARY');pa=header('PAGE');bo=header('BOX');lv=header('LEVEL')
 pairs=[(pa,bo,6),(he,bi,9),(bi,pa,20),(he,mo,46),(he,pa,29),(he,bo,35)]
 guesses=[(b['box'][0]-a['box'][0])/n for a,b,n in pairs if a and b]
 guess=float(np.median(guesses)) if guesses else (he or pa)['box'][3]-(he or pa)['box'][1]
 if not guesses:guess=((he or pa)['box'][2]-(he or pa)['box'][0])/(3 if he else 4)
 anchor=he or pa or bi
 ax=anchor['box'][0]-(0 if he else 29 if pa else 9)*guess
 def synthetic(slot,width):return {'box':[ax+slot*guess,anchor['box'][1],ax+(slot+width)*guess,anchor['box'][3]]}
 he=he or synthetic(0,3);bi=bi or synthetic(9,6);pa=pa or synthetic(29,4);bo=bo or synthetic(35,3);mo=mo or synthetic(46,4)
 assert he and mo and bi and pa and bo,(g['source'],he,mo,pa,bo)
 pitch=(mo['box'][0]-he['box'][0])/46
 hex_x=he['box'][0]+pitch*.5
 bit_x=he['box'][0]+guess*60.5
 # Horizontal positions of the printed cells. The two larger gaps bracket NEXT ADDRESS.
 slots=[];k=0
 for i,n in enumerate(LENGTHS):
  slots.extend(range(k,k+n));k+=n+(3 if i in [13,16] else 2 if i in [22,29] else 1)
 rows=[r for r in g['rows'] if r>he['box'][3]+35]
 # The large blank space before EC LEVEL identifies the final V bit.
 ends=[]
 for rr in rows:
  xs=clusters([xx+w/2 for xx,yy,w,h,a in g['components'] if xx>bit_x+105*pitch and abs(yy+h/2-rr)<32 and h>24],12)
  gaps=[(b-a,a) for a,b in zip(xs,xs[1:]) if b-a>100]
  if gaps:ends.append(max(gaps)[1])
 if ends:
  end=float(np.median(ends));pitch=(end-bit_x)/slots[-1]
 # Fit both position and pitch to printed glyph centres. Header spacing alone
 # is distorted by the paper, so it supplies only the initial estimate.
 samples=rows[::max(1,len(rows)//6)]
 centers=[np.array([xx+w/2 for xx,yy,w,h,a in g['components'] if abs(yy+h/2-r)<35 and bit_x-40<xx<bit_x+140*pitch and h>24]) for r in samples]
 best=(1e9,bit_x,pitch)
 for pp in np.arange(pitch*.98,pitch*1.025,.03):
  for xx in np.arange(bit_x-45,bit_x+46,3):
   pred=xx+np.asarray(slots)*pp
   scores=[np.minimum(abs(pred[:,None]-c[None,:]).min(1),pp*.65).mean() for c in centers if len(c)]
   score=np.mean(scores)
   if score<best[0]:best=(score,xx,pp)
 _,bit_x,pitch=best
 return {'pitch':pitch,'hex':hex_x,'bits':bit_x,'binary':bi['box'][0]+pitch*.5,'page':pa['box'][0]+pitch*.5,'box':bo['box'][0]+pitch*.5,'mode':mo['box'][0]+pitch*.5,'level':lv['box'][0]-pitch*1.4 if lv else bit_x+(slots[-1]+10)*pitch,'slots':slots,'rows':rows}

def crop(im,x,y,pitch,yp=90):
 x1=round(x-pitch*.47);x2=round(x+pitch*.47);y1=round(y-36);y2=round(y+36)
 gray=im[y1:y2,x1:x2]
 a=(gray<220).astype('uint8')
 n,l,stats,c=cv2.connectedComponentsWithStats(a)
 good=[(xx,yy,w,h,area) for xx,yy,w,h,area in stats[1:] if area>30 and h>10]
 if not good:return np.zeros((30,20),'uint8'),[x1,y1,x2,y2]
 # Retain the large glyph and its fragments; isolated dirt stays out.
 best=max(good,key=lambda q:q[4]);cy=best[1]+best[3]/2
 mask=np.zeros_like(a)
 for xx,yy,w,h,area in good:
  if abs(yy+h/2-cy)<20:mask[yy:yy+h,xx:xx+w]=a[yy:yy+h,xx:xx+w]
 return mask,[x1,y1,x2,y2]

def templates():
 g=json.loads((O/'grid-1675.json').read_text());im=cv2.imread(str(O/'grid-1675.png'),0)
 model=[];labels=[]
 for s in g['symbols']:
  x1,y1,x2,y2=s['box'];ch=s['text']
  if ch in '01' and len(ch)==1 and s['confidence']>90 and x1>2150 and x2<6400 and y1>600 and 22<y2-y1<45 and x2-x1<34:
   model.append(feature((im[y1:y2,x1:x2]<200).astype('uint8')));labels.append(ch)
 return np.asarray(model),np.asarray(labels)

def decode(g,model,labels,align=False,column_centers=None):
 geo=geometry(g);im=cv2.imread(str(CACHE/(Path(g['source']).stem+'.png')),0)
 residual=[]
 for slot in geo['slots']:
  x=geo['bits']+slot*geo['pitch']
  vals=[xx+w/2-x for xx,yy,w,h,a in g['components'] if abs(xx+w/2-x)<geo['pitch']*.47 and any(abs(yy+h/2-r)<28 for r in geo['rows']) and h>24 and w>geo['pitch']*.6 and a>110]
  residual.append(float(np.median(vals)) if vals else 0)
 feats=[];locs=[]
 for n,y in enumerate(geo['rows']):
  expected=(np.array(column_centers) if column_centers is not None else geo['bits']+np.asarray(geo['slots'])*geo['pitch']+np.asarray(residual))
  if align:
   centers=np.array(sorted(xx+w/2 for xx,yy,w,h,a in g['components'] if abs(yy+h/2-y)<40 and h>23 and geo['pitch']*.55<w<geo['pitch']*1.4 and a>100 and geo['bits']-60<xx<geo['bits']+140*geo['pitch']))
   best=(1e9,expected)
   if len(centers)>50:
    slots=np.array(geo['slots'])
    for pp in np.arange(geo['pitch']*.97,geo['pitch']*1.031,.05):
     for dx in np.arange(-geo['pitch']*.8,geo['pitch']*.81,2):
      pred=geo['bits']+dx+slots*pp
      score=np.minimum(abs(pred[:,None]-centers).min(1),pp*.5).mean()
      if score<best[0]:best=(score,pred)
    expected=best[1]
  anchors=[]
  for xx,yy,w,h,a in g['components']:
   if abs(yy+h/2-y)<28 and h>24 and geo['pitch']*.6<w<geo['pitch']*1.3 and a>110:
    xc=xx+w/2;k=int(np.argmin(abs(expected-xc)));dx=xc-expected[k]
    if abs(dx)<geo['pitch']*.48:anchors.append((xc,dx))
  # Paper distortion is local: use median glyph centres to align each section independently.
  for j,slot in enumerate(geo['slots']):
   x=float(expected[j])
   shifts=[dx for xc,dx in anchors if abs(xc-x)<180]
   if shifts:x+=float(np.median(shifts))
   local=[yy+h/2 for xx,yy,w,h,a in g['components'] if abs(xx+w/2-x)<200 and abs(yy+h/2-y)<25 and h>23]
   cy=float(np.median(local)) if local else y
   nearby=[(xx+w/2,yy+h/2) for xx,yy,w,h,a in g['components'] if abs(xx+w/2-x)<geo['pitch']*.3 and abs(yy+h/2-cy)<23 and h>23 and w>geo['pitch']*.6]
   if nearby:
    closest=min(nearby,key=lambda v:abs(v[0]-x)+abs(v[1]-cy)*.5);x=closest[0]
   patch,box=crop(im,x,cy,geo['pitch']);feats.append(feature(patch));locs.append([n,j,box])
 f=np.asarray(feats);dist=(f*f).sum(1)[:,None]+(model*model).sum(1)-2*f@model.T
 d0=dist[:,labels=='0'].min(1);d1=dist[:,labels=='1'].min(1)
 rows=[{'bits':'','uncertain':[]} for _ in geo['rows']]
 for i,(n,j,box) in enumerate(locs):
  ch='0' if d0[i]<d1[i] else '1';best=min(d0[i],d1[i]);margin=abs(d0[i]-d1[i])
  rows[n]['bits']+=ch
  if best>55 or margin<20:rows[n]['uncertain'].append({'column':j,'box':box,'nearest':ch,'distance':float(best),'margin':float(margin)})
  rows[n].setdefault('cells',[]).append({'column':j,'box':box,'nearest':ch,'distance':float(best),'margin':float(margin)})
 return geo,rows

if __name__=='__main__':
 model,labels=templates()
 print('Templates',len(labels))
 files=sorted(p for p in CACHE.glob('QZ*.json') if p.stem.endswith(tuple(f'{i:04}' for i in range(16))))
 if 'all' not in sys.argv:files=files[:1]
 def run(p):
  try:
   g=json.loads(p.read_text());geo,rows=decode(g,model,labels)
   (CACHE/(p.stem+' decoded.json')).write_text(json.dumps({'geometry':geo,'rows':rows}))
   return p.stem,len(rows),sum(len(r['uncertain']) for r in rows)
  except Exception as e:return p.stem,str(e)
 from concurrent.futures import ThreadPoolExecutor,as_completed
 with ThreadPoolExecutor(max_workers=4) as pool:
  for i,f in enumerate(as_completed([pool.submit(run,p) for p in files]),1):print(i,f.result(),flush=True)

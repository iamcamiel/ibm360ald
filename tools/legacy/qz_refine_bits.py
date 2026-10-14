import os
os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import sys,json
import numpy as np
O=Path(__file__).parent;sys.path.insert(0,str(O))
from qz_decode import *

def parity(s):
 return [sum(map(int,s[1:]))%2,sum(map(int,s[2:43]))%2,(sum(map(int,s[43:69]))+int(s[85]))%2,sum(map(int,s[69:85]+s[86:]))%2]

def run():
 model,labels=templates();models=list(model);ll=list(labels)
 files=sorted(CACHE.glob('* decoded.json'))
 for p in files:
  g=json.loads(p.read_text());im=cv2.imread(str(CACHE/(p.stem[:-8]+'.png')),0);count={'0':0,'1':0}
  for r in g['rows']:
   if parity(r['bits'])!=[1,1,1,1]:continue
   for c in r['cells']:
    ch=c['nearest']
    if count[ch]>=20 or c['distance']>25 or c['margin']<25:continue
    x,y,xx,yy=c['box'];patch,b=crop(im,(x+xx)/2,(y+yy)/2,xx-x)
    models.append(feature(patch));ll.append(ch);count[ch]+=1
 model=np.array(models);labels=np.array(ll);np.savez(CACHE/'bit-model.npz',features=model,labels=labels)
 print('Bit templates',len(labels),flush=True)
 for n,p in enumerate(files,1):
  g=json.loads(p.read_text());im=cv2.imread(str(CACHE/(p.stem[:-8]+'.png')),0)
  cells=[c for r in g['rows'] for c in r['cells']];fs=[];holes=[]
  for c in cells:
   x,y,xx,yy=c['box'];patch,b=crop(im,(x+xx)/2,(y+yy)/2,xx-x);fs.append(feature(patch))
   cnt,hier=cv2.findContours(patch,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
   holes.append(hier is not None and any(v[3]>=0 and cv2.contourArea(cnt[i])>15 for i,v in enumerate(hier[0])))
  fs=np.array(fs);d=(fs*fs).sum(1)[:,None]+(model*model).sum(1)-2*fs@model.T
  a=d[:,labels=='0'].min(1);b=d[:,labels=='1'].min(1)
  for i,c in enumerate(cells):
   ch='0' if a[i]<b[i] else '1';c.update(nearest=ch,distance=float(min(a[i],b[i])),margin=float(abs(a[i]-b[i])),closed_zero=bool(holes[i]))
  k=0
  for r in g['rows']:
   r['bits']=''.join(c['nearest'] for c in r['cells']);r['uncertain']=[c for c in r['cells'] if c['distance']>55 or c['margin']<20]
   r['parity_checks']=parity(r['bits'])
  p.write_text(json.dumps(g))
  print(n,p.name,'unclear',sum(len(r['uncertain']) for r in g['rows']),'parity exceptions',sum(r['parity_checks'] not in [[1,1,1,1],[1,0,0,0]] for r in g['rows']),flush=True)
if __name__=='__main__':run()

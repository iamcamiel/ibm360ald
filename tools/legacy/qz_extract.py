import os
os.environ['OMP_THREAD_LIMIT']='1'
os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import sys,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
O=Path(__file__).parent
sys.path[:0]=[str(O/'cv-runtime'),str(O.parent/'ald-renaming'/'ocr-runtime')]
import cv2,tesserocr
cv2.setNumThreads(1)
ROOT=Path(r'D:\Reference Materials\IBM 360\IBM_360_ALD\QZ ROS Listing')
CACHE=O/'qz';CACHE.mkdir(exist_ok=True)

def clusters(v,gap=15):
 v=sorted(v);groups=[]
 for x in v:
  if not groups or x-groups[-1][-1]>gap:groups.append([x])
  else:groups[-1].append(x)
 return [float(np.median(g)) for g in groups]

def prepare(path):
 stem=path.stem
 target=CACHE/(stem+'.json')
 if target.exists() and json.loads(target.read_text()).get('version')==2:return json.loads(target.read_text())
 im=np.asarray(Image.open(path).convert('L').resize((7650,4950)))
 binary=(im<175).astype('uint8')
 n,lab,stats,centers=cv2.connectedComponentsWithStats(binary)
 useful=[(int(x),int(y),int(w),int(h),int(a)) for x,y,w,h,a in stats[1:] if 300<y<4400 and 16<h<65 and 5<w<50 and a>65]
 hist=np.bincount([round(y+h/2) for x,y,w,h,a in useful],minlength=4950)
 smooth=np.convolve(hist,np.ones(41),mode='same')
 candidates=sorted(np.flatnonzero(smooth>70),key=lambda y:-smooth[y]);rows=[]
 for y in candidates:
  if all(abs(y-r)>60 for r in rows):rows.append(int(y))
 rows=sorted(rows)
 cols=[]
 words=[]
 with tesserocr.PyTessBaseAPI(path=str(O.parent/'ald-renaming'/'best'),lang='eng',psm=6) as api:
  api.SetPageSegMode(11)
  api.SetImage(Image.fromarray(im[:1400]));api.Recognize();it=api.GetIterator()
  if it:
   while True:
    s=it.GetUTF8Text(tesserocr.RIL.WORD)
    if s:
     x1,y1,x2,y2=it.BoundingBox(tesserocr.RIL.WORD)
     words.append({'text':s.strip(),'confidence':it.Confidence(tesserocr.RIL.WORD),'box':[x1,y1,x2,y2]})
    if not it.Next(tesserocr.RIL.WORD):break
 result={'version':2,'source':str(path),'rows':rows,'cols':cols,'words':words,'components':useful}
 target.write_text(json.dumps(result))
 Image.fromarray(im).save(CACHE/(stem+'.png'))
 return result

if __name__=='__main__':
 files=sorted(ROOT.glob('*.tif'))
 selected=files if 'all' in sys.argv else files[:1]
 from concurrent.futures import ThreadPoolExecutor,as_completed
 with ThreadPoolExecutor(max_workers=4) as pool:
  jobs={pool.submit(prepare,p):p for p in selected}
  for i,j in enumerate(as_completed(jobs),1):
   g=j.result();print(i,jobs[j].name,'rows',len(g['rows']),'cols',len(g['cols']),flush=True)

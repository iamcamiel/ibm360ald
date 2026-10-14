from pathlib import Path
import sys,json
import numpy as np
O=Path(__file__).parent;sys.path.insert(0,str(O))
from qz_decode import *
from qz_refine_bits import parity
def run():
 changes=[]
 for p in sorted(CACHE.glob('* decoded.json')):
  g=json.loads(p.read_text());stem=p.stem[:-8];im=cv2.imread(str(CACHE/(stem+'.png')),0)
  ocrp=CACHE/(stem+' OCR bits.json');ocr=json.loads(ocrp.read_text()) if ocrp.exists() else None
  for n,r in enumerate(g['rows']):
   for c in r['cells']:
    x,y,xx,yy=c['box'];patch,box=crop(im,(x+xx)/2,(y+yy)/2,xx-x)
    contours,hier=cv2.findContours(patch,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    closed=hier is not None and any(v[3]>=0 and cv2.contourArea(contours[i])>55 and cv2.boundingRect(contours[v[3]])[2]>(xx-x)*.7 for i,v in enumerate(hier[0]))
    c['large_zero_loop']=bool(closed)
    if closed and c['nearest']=='1':changes.append({'source':stem,'row':n,'column':c['column'],'before':'1','after':'0','box':c['box'],'parity_before':parity(r['bits'])})
    if ocr:
     candidates=[ch for ch in ocr[n]['chars'] if abs((ch['box'][0]+ch['box'][2])/2-(x+xx)/2)<g['geometry']['pitch']*.42 and ch['box'][2]-ch['box'][0]<g['geometry']['pitch']*1.3]
     if candidates:
      oc=max(candidates,key=lambda a:a['confidence']);c['OCR']=oc['text'];c['OCR_confidence']=oc['confidence']
   r['uncertain']=[c for c in r['cells'] if (c['distance']>55 or c['margin']<20) and not ((c.get('large_zero_loop') and c['nearest']=='0') or (c.get('OCR')==c['nearest'] and c.get('OCR_confidence',0)>75))]
  p.write_text(json.dumps(g))
 (CACHE/'zero-loop-proposals.json').write_text(json.dumps(changes))
 print('Large zero loops in predicted ones',len(changes),'remaining cells',sum(len(r['uncertain']) for p in CACHE.glob('* decoded.json') for r in json.loads(p.read_text())['rows']),flush=True)
if __name__=='__main__':run()

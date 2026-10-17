from pathlib import Path
from PIL import Image,ImageDraw,ImageOps,ImageFont
import json,hashlib
BASE=Path(__file__).resolve().parent;HERE=BASE/'Group 3 review';OUT=HERE/'Independent peer review'
d=json.loads((HERE/'Findings.json').read_text('utf-8'));rows=[]
ids={f'pin-{i:04d}'for i in [260,266,267,269,270,272,274,432,433,435,625,626,627,372,373,628,54,400,436,437,565,47,60,61,332,333,334]}
for c in d['cases']:
 if c['case_id']not in ids:continue
 with Image.open(c['source']['path'])as raw:
  image=raw.convert('RGB');a,b,e,f=c['native_crop']['box'];box=[max(0,a-230),max(0,b-80),min(image.width,e+420),min(image.height,f+220)]
  path=OUT/(c['case_id']+' extended.png');image.crop(box).save(path)
  rows.append({'case_id':c['case_id'],'page':c['page'],'original_contact':c['observed_contact'],'proposed_contact':c['proposed_contact'],'source':c['source'],'native_crop':{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'box':box}})
font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',18)
for start in range(0,len(rows),12):
 canvas=Image.new('RGB',(1800,4*360),'#dddddd');draw=ImageDraw.Draw(canvas)
 for i,c in enumerate(rows[start:start+12]):
  x=i%3*600;y=i//3*360;draw.text((x+4,y+2),c['case_id']+' '+c['page']+' '+c['original_contact']+' ->'+str(c['proposed_contact']),font=font,fill='black')
  im=Image.open(c['native_crop']['path']);im=ImageOps.autocontrast(im,.2);im.thumbnail((590,330));canvas.paste(im,(x+4,y+27))
 canvas.save(OUT/f'Extended {start//12+1:02d}.png')
(OUT/'Extended crop bindings.json').write_text(json.dumps({'cases':rows},indent=2)+'\n','utf-8');print(len(rows),'extended private native crops')

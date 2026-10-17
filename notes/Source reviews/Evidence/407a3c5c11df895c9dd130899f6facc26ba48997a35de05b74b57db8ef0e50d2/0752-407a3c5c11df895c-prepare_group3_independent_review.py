from pathlib import Path
from PIL import Image,ImageDraw,ImageOps,ImageFont
import json,hashlib
BASE=Path(__file__).resolve().parent;HERE=BASE/'Group 3 review';OUT=HERE/'Independent peer review';OUT.mkdir(exist_ok=True)
P=HERE/'Findings.json';expected='1f4cd3118b91d42175172773f076b112e6738ac7bb7a61844d7ce7f22f8dc6d4'
assert hashlib.sha256(P.read_bytes()).hexdigest()==expected
d=json.loads(P.read_text('utf-8'));font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',18)
for start in range(0,len(d['cases']),12):
 group=d['cases'][start:start+12];canvas=Image.new('RGB',(1800,4*340),'#dddddd');draw=ImageDraw.Draw(canvas)
 for i,c in enumerate(group):
  x=(i%3)*600;y=(i//3)*340
  label=c['case_id']+' '+c['page']+' '+str(c['node_id'])+' '+c['observed_label']+' ->'+str(c['proposed_contact'])
  draw.text((x+4,y+2),label,font=font,fill='black')
  image=Image.open(c['native_crop']['path']).convert('RGB');image=ImageOps.autocontrast(image,cutoff=.2);image.thumbnail((590,310));canvas.paste(image,(x+4,y+26))
 canvas.save(OUT/f'Review {start//12+1:02d}.png')
print(len(d['cases']),'cases,18 private independent montages')

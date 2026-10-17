"""Private source-bound crop locators; every locator must be visually checked."""
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw,ImageFont
import json,hashlib,math,argparse
BASE=Path(__file__).resolve().parent;OUT=BASE/'Group 2 review';OUT.mkdir(exist_ok=True)
REQUESTS=BASE/'Group 2 requests.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def findfits(value,path=''):
 if isinstance(value,dict):
  for a,b in [('x','y'),('x_coefficients','y_coefficients')]:
   if all(isinstance(value.get(k),list)and len(value[k])==3 and all(isinstance(v,(float,int))for v in value[k])for k in(a,b)):
    yield value[a],value[b],path
  m=value.get('affine_coefficients')
  if isinstance(m,list)and len(m)==3 and all(isinstance(a,list)and len(a)==2 for a in m):yield [a[0]for a in m],[a[1]for a in m],path
  for key,item in value.items():
   if key not in('nodes','nets','wire_paths','printed_labels'):yield from findfits(item,path+'/'+key)
 elif isinstance(value,list):
  for i,item in enumerate(value):
   if isinstance(item,dict):yield from findfits(item,path+'/'+str(i))
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--pages',nargs='*');args=parser.parse_args()
 data=read(REQUESTS);records=[];index=0
 if args.pages and(OUT/'Crop bindings.json').exists():records=[r for r in read(OUT/'Crop bindings.json')['cases']if r['page']not in args.pages]
 for page in data['pages']:
  if args.pages and page['page']not in args.pages:continue
  model=read(page['model']['path']);fits=list(findfits(model));xcoef,ycoef,method=([422.67,39.7867,0],[333.33,0,59.7333],'unverified AP locator')
  if fits:xcoef,ycoef,method=fits[0]
  rowcal=model.get('native_row_calibration',{}).get('fit',{})
  if rowcal:ycoef=[rowcal['origin_y'],0,rowcal['pitch_y']];method+=' + stored row fit'
  overrides=OUT/'Calibration overrides.json'
  if overrides.exists()and page['page']in read(overrides):
   override=read(overrides)[page['page']];xcoef,ycoef,method=override['x'],override['y'],override['evidence']
  source=Path(page['source_TIFF']);source_sha=sha(source)
  with Image.open(source)as raw:
   native=raw.convert('RGB')
   for case in page['cases']:
    node=case['node'];pin=case['pin'];c=node.get('column');r=node.get('row');pr=pin.get('row',r+3)
    if c is None or r is None:raise ValueError('Missing node geometry '+case['case_id'])
    x=xcoef[0]+xcoef[1]*c+xcoef[2]*r;y=ycoef[0]+ycoef[1]*c+ycoef[2]*r
    bottom=max(r+7,pr+1);yb=ycoef[0]+ycoef[1]*c+ycoef[2]*bottom
    box=[max(0,int(x)-230),max(0,int(y)-65),min(native.width,int(x)+540),min(native.height,int(yb)+60)]
    path=OUT/'Native crops'/f"{case['case_id']} {page['page']}.png";path.parent.mkdir(exist_ok=True);native.crop(box).save(path)
    records.append({'case_id':case['case_id'],'page':page['page'],'node_pointer':case['audit_flag']['node_pointer'],'node_id':node.get('id'),
     'old_pin':pin.get('pin'),'pin_index':case['audit_flag']['pin_index'],'pin_row':pr,'side':pin.get('side'),
     'source':{'path':str(source),'sha256':source_sha},'crop':{'path':str(path),'sha256':sha(path),'box':box},
     'calibration':{'x':xcoef,'y':ycoef,'method':method},'model':page['model'],'text':page['text']})
  small=native.resize((1020,660));small.save(OUT/f"{page['page']} source overview.png")
 order={c['case_id']:i for i,c in enumerate(c for p in data['pages']for c in p['cases'])};records.sort(key=lambda r:order[r['case_id']])
 (OUT/'Crop bindings.json').write_text(json.dumps({'request':{'path':str(REQUESTS),'sha256':sha(REQUESTS)},'cases':records},ensure_ascii=False,indent=2)+'\n','utf-8')
 for start in range(0,len(records),12):
  group=records[start:start+12];canvas=Image.new('RGB',(1800,4*340),'#dddddd');draw=ImageDraw.Draw(canvas)
  for i,record in enumerate(group):
   x=(i%3)*600;y=(i//3)*340
   label=f"{record['case_id']} {record['page']} {record['node_id']} {record['old_pin']} row{record['pin_row']} {record['side']}"
   draw.text((x+5,y+4),label,fill='black')
   with Image.open(record['crop']['path'])as image:
    image.thumbnail((590,310));canvas.paste(image,(x+5,y+25))
  canvas.save(OUT/f'Montage {start//12+1:02d}.png')
 print(json.dumps({'pages':len({r['page']for r in records}),'cases':len(records),'montages':math.ceil(len(records)/12)}))
if __name__=='__main__':main()

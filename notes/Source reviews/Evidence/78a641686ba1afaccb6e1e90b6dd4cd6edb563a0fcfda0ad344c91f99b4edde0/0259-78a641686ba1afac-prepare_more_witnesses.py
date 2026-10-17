from pathlib import Path
import json,hashlib,importlib.util
from PIL import Image
ROOT=Path('D:/Github/IBM360');BASE=Path(__file__).resolve().parents[1];HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('crophelper',BASE/'Group 1 review/prepare_native_crops.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def bind(p):return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
out=[]
items=[('RT775','AV','target'),('CT021','BJ','target extended'),('AP741','BR','0141A3 witness'),('AP011','BU2H','target'),('AP011','AG','target'),('AP011','AQ','target'),('KW051','BE','target')]
for page,portion in [('BF051','3330AF')]:
 mp=next((ROOT/'ibm360ald/json').rglob(page+' *.json'));m=read(mp)
 for n in m['nodes']:
  if n.get('printed_card_portion')==portion:items.append((page,n['id'],portion+' witness'));break
for page,nodeid,label in items:
 models=list((ROOT/'ibm360ald/json').rglob(page+' *.json'));assert len(models)==1,(page,models)
 mp=models[0];m=read(mp);nodes=[(i,n)for i,n in enumerate(m.get('nodes',[]))if n.get('id')==nodeid]
 if not nodes:print('MISSING',page,nodeid);continue
 ni,n=nodes[0];sp=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')/mp.relative_to(ROOT/'ibm360ald/json').with_suffix('.tif');assert sp.exists(),sp
 im=Image.open(sp).convert('RGB');xy,pitch,cal=h.locate(im,n,m);x,y=xy
 if page=='KW051':im.resize((2550,1650)).save(HERE/'KW051 overview.png')
 box=[round(x-500),round(y-100),round(x+800),round(y+650)]
 crop=HERE/(page+' '+nodeid+' '+label+'.png');im.crop(box).save(crop)
 out.append({'page':page,'node_id':nodeid,'node_pointer':'/nodes/'+str(ni),'role':label,'model':bind(mp),'source':bind(sp),'crop':dict(bind(crop),box=box),'calibration':cal,'node':n})
(HERE/'Additional native witness bindings.json').write_text(json.dumps({'source_changes_applied':False,'witnesses':out},indent=2,ensure_ascii=False),'utf-8')
print([(x['page'],x['node_id'],x['node'].get('printed_card_portion'))for x in out])

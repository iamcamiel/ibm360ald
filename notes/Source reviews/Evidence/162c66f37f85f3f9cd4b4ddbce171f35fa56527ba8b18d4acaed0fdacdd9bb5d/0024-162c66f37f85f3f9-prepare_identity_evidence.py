"""Private source-bound identity crops and current catalogue/listing inventory."""
from pathlib import Path
import json, hashlib, importlib.util
from PIL import Image
ROOT=Path('D:/Github/IBM360');R=ROOT/'ibm360ald';O=Path(__file__).parent
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def crop(source,box,name,**kw):
 p=O/name;assert not p.exists();im=Image.open(source);box=list(map(int,box));im.crop(box).save(p);return {'source':bind(source),'native_box':box,'crop':bind(p),'dimensions':list(Image.open(p).size),**kw}
cats={c:read(R/'json/Card types current'/f'{c}.json')for c in ['1365','1457','1724']}
uniform=R/'json/Socket listings uniform/Socket listings.json';u=read(uniform)
km=next((R/'json').rglob('KM831*.json'));d=read(km)
h=ROOT/'tmp/ald-text/ald/socket-ald-audit/pin-letter-visual-20261016/Group 1 review/prepare_native_crops.py'
s=importlib.util.spec_from_file_location('private_locator',h);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
rows=[];im=Image.open(d['source'])
for ni in [2,6]:
 n=d['nodes'][ni];xy,pitch,method=m.locate(im,n,d);x,y=xy;xp,yp=pitch;rows.append(crop(d['source'],[x-5*xp,y-yp,x+17*xp,y+8*yp],f'KM831 {n["id"]} native candidate.png',model=bind(km),node_pointer=f'/nodes/{ni}',raw_node=n,locator=method))
ef=R/'json/EF ROS Sense Amplifiers and Latches/EF431 SOCKET LISTING.json';e=read(ef)
for ni,n in enumerate(e['records']):
 if str(n.get('type',n.get('card_type','')))not in ['1457','1724'] and n.get('part_number')not in ['5801457','5801724']:continue
 col=n['source_column'];x=e['native_column_geometry'][col-1];xr=e['native_column_geometry'][col];y=n['source_y'];rows.append(crop(e['source'],[x-20,y-45,xr+10,y+440],f'EF431 {n["sockets"][0]} native.png',model=bind(ef),record_pointer=f'/records/{ni}',record=n))
old=ROOT/'tmp/ald-text/ald/socket-ald-audit/card-portion-visual-20261016/Group 1 source review/A1 historic anchors/A1 crop candidates.json'
for n in read(old)['cases']:
 if n['record_id']in ['21:82:100','21:162:43']:
  rows.append({'historical_crop_entry':n,'historical_register':bind(old)})
out={'schema':'private-prefix1-identity-triage-evidence-v1','canonical_writes':0,'catalogue_inputs':[bind(R/'json/Card types current'/f'{c}.json')for c in cats],'uniform':bind(uniform),'catalogue_counts':{c:{'diagram_occurrences':len(d['diagram_occurrences']),'listing_records':len(d['listing_records'])}for c,d in cats.items()},'crops':rows,'listing_records':[n for n in u['records']if n.get('card_type')in ['1457','1724']or(n.get('board')=='02E-C3'and any(s in ['H2','E5']for s in n.get('sockets',[])))],'locator':bind(h)}
p=O/'Evidence inventory.json';assert not p.exists();p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps({'evidence':bind(p),'crops':len(rows),'counts':out['catalogue_counts']},indent=2))

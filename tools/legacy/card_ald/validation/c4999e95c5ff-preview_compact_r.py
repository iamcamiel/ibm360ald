from pathlib import Path
import json,hashlib
from PIL import Image,ImageDraw,ImageFont

root=Path('D:/Github/IBM360/ibm360ald')
source=root/'json/Card-ALD/definitions/4191.json'
spec=json.loads(source.read_text('utf8'))
r=next(b for b in spec['boxes'] if b['portion']=='01')
gate=next(b for b in spec['boxes'] if b['portion']=='07')
assert r['function']=='R' and len(r['ports'])==1 and r['ports'][0]['pin']=='D12'
assert any(p['pin']=='D12' and p['side']=='input' for p in gate['ports'])
out=root.parent/'tmp/ald-text/ald/card-data/4191-compact-r-study'
out.mkdir(parents=True,exist_ok=True)

def drawing(short):
    rows=[list(' '*66) for _ in range(7 if short else 14)]
    def text(x,y,t):rows[y][x:x+len(t)]=t
    def box(b,top):
        text(44,top,'┌──────┐');text(44,top+6,'└──────┘')
        for y in range(top+1,top+6):text(44,y,'│      │')
        text(45,top+1,b['function']);text(45,top+3,b['circuit_identifier']);text(45,top+4,'4191'+b['portion'])
    box(gate,0)
    for p in gate['ports']:
        y=p['row']-gate['top']
        if p['side']=='input':
            text(0,y,p['pin']);text(3,y,'─'*38);text(41,y,p['pin'])
        else:text(52,y,'─'*14)
    text(12,5,'◇')
    label=' '.join([r['function'],r['circuit_identifier'],r['portion']])
    if short:text(12,6,'└'+label)
    else:
        box(r,7)
        for y in range(6,10):text(12,y,'│')
        text(12,10,'└'+'─'*28);text(41,10,'D12')
    return [''.join(row).rstrip() for row in rows]

before=drawing(False);after=drawing(True)
font=ImageFont.truetype('D:/Github/IBM360/tmp/ald-text/JuliaMono-Regular.ttf',22)
cw=font.getlength('M');lh=29;panel=round(66*cw)+32
im=Image.new('RGB',(panel*2,17*lh+24),'#1e1e1e');draw=ImageDraw.Draw(im)
for col,title,lines in [(0,'CURRENT FULL BOX',before),(1,'PROPOSED COMPACT NOTATION',after)]:
    x=16+col*panel;draw.text((x,12),title,font=font,fill='#ededed')
    for y,line in enumerate(lines):draw.text((x,12+(y+2)*lh),line,font=font,fill='#ededed')
im.save(out/'4191 R notation comparison.png')
(out/'4191 compact R excerpt.txt').write_text('4191 NOTATION STUDY - PORTIONS 07 AND 01\n\n'+'\n'.join(after)+'\n','utf8')
(out/'Study provenance.json').write_text(json.dumps({'status':'PROPOSED STYLE ONLY; NO PUBLISHED DIAGRAM CHANGES','source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'gate_portion':'07','termination_portion':'01','pin':'D12','compact_label':'R U61AC 01','retained_fields':['function','circuit identifier','portion','physical input pin on main net'],'scope':'Excerpt; output continues beyond the crop'},indent=2)+'\n','utf8')
print(out)

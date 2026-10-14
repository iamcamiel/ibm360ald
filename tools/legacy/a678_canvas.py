"""Shared, explicit character-grid exporter for visually reviewed A6/A7/A8 scans.

No OCR is copied automatically. Specs contain reviewed annotations and explicit
wires. All source evidence and uncertain readings remain attached to the export.
"""
from pathlib import Path
import json, sys
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).parent
OUT=ROOT/'ALD_Visual_Transcriptions'
PLAN=json.loads((ROOT/'tmp/ald-renaming/rename-plan.json').read_text())
ALLOWED=set(json.loads((OUT/'Allowed characters.json').read_text(encoding='utf-8'))['allowed_characters'])
GROUPS={'a6':'A6 Indices','a7':'A7 Cabling and Timing','a8':'A8 Adjustment and Configuration'}

def render(path):
    path=Path(path)
    spec=json.loads(path.read_text(encoding='utf-8'))
    source=next(s for s in PLAN if s['id']==spec['id'])
    group=spec.get('group',path.parent.name.lower())
    folder=OUT/GROUPS[group];folder.mkdir(exist_ok=True)
    stem=spec.get('name',Path(source['newpath']).stem)
    width=spec.get('columns',260);height=spec.get('rows',120)
    grid=[[' ']*width for _ in range(height)]
    annotations=[];collisions=[]
    def put(c,r,text,note=''):
        text=text.replace('*','✲')
        if r<0 or r>=height or c<0 or c+len(text)>width:
            raise ValueError((stem,c,r,text,'outside canvas'))
        for k,ch in enumerate(text):
            old=grid[r][c+k]
            if ch!=' ' and old!=' ' and old!=ch:
                collisions.append({'row':r+1,'column':c+k+1,'old':old,'new':ch,'text':text})
            grid[r][c+k]=ch
        annotations.append({'row':r+1,'column':c+1,'text':text,'note':note})
    # Wires first, with explicit crossings/corners. They are never inferred from OCR.
    for wire in spec.get('wires',[]):
        if isinstance(wire,list):
            c,r,t=wire;put(c,r,t,'source-reviewed diagram rule')
        else:
            c=wire['column'];r=wire['row']
            if wire.get('axis')=='vertical':
                for y in range(r,wire['end']+1):put(c,y,'│','source-reviewed vertical rule')
            else:put(c,r,wire['text'],'source-reviewed diagram rule')
    wire_collisions=collisions[:];collisions=[]
    for item in spec.get('annotations',[]):
        if isinstance(item,list):c,r,t=item;note=''
        else:c=item['column'];r=item['row'];t=item['text'];note=item.get('note','')
        put(c,r,t,note)
    lines=[''.join(row).rstrip() for row in grid]
    while lines and not lines[-1]:lines.pop()
    text='\n'.join(lines)+'\n'
    pending=sorted(set(text)-ALLOWED)
    if pending:
        (path.parent/(path.stem+' pending symbols.json')).write_text(json.dumps({'characters':pending,'page':source['page']},ensure_ascii=False,indent=2),encoding='utf-8')
        raise ValueError(f'{stem}: unapproved symbols {pending}')
    # Detect text that later annotations erased, including replacement by spaces.
    overwritten=[]
    for a in annotations:
        if a['note'].startswith('source-reviewed'):continue
        r=a['row']-1;c=a['column']-1
        for k,ch in enumerate(a['text']):
            if ch!=' ' and grid[r][c+k]!=ch:
                overwritten.append({'row':r+1,'column':c+k+1,'expected':ch,'actual':grid[r][c+k]})
    if overwritten:raise ValueError(f'{stem}: overwritten annotations: {overwritten[:10]}')
    target=folder/(stem+'.txt');target.write_text(text,encoding='utf-8',newline='\r\n')
    font=ImageFont.truetype(str(WORK/'JuliaMono-Regular.ttf'),16)
    cw=font.getlength('M');ch=24
    preview=Image.new('RGB',(round(cw*width)+20,ch*len(lines)+20),'white');draw=ImageDraw.Draw(preview)
    for y,line in enumerate(lines):
        for x,glyph in enumerate(line):
            if glyph!=' ':draw.text((10+x*cw,5+y*ch),glyph,font=font,fill='black')
    preview.save(folder/(stem+' preview.png'))
    report={
        'id':source['id'],'page':source['page'],'filename':target.name,
        'source':source['newpath'],'source_spec':str(path.resolve()),
        'rows':len(lines),'columns':width,'utf8':True,'approved_characters_only':True,
        'review_status':spec.get('review_status','visual review pending'),
        'annotations':annotations,'annotation_collisions':collisions,
        'wire_intersections':wire_collisions,'overwritten_annotations':overwritten,
        'unreadable_markers':[{'row':r+1,'column':c+1,'context':line[max(0,c-15):c+16]} for r,line in enumerate(lines) for c,glyph in enumerate(line) if glyph=='�'],
        'source_review':spec.get('source_review',[]),
        'unresolved':spec.get('unresolved',[]),'notes':spec.get('notes',[]),
        'accepted_readings':spec.get('accepted_readings',[]),
        'handwriting':'omitted', 'coordinate_convention':'spec positions are zero based; reports are one based'
    }
    (folder/(stem+' verification.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{source["page"]} scan {source["id"]}: {len(annotations)} reviewed annotations, {len(report["unreadable_markers"])} unreadable characters',flush=True)
    return report

if __name__=='__main__':
    for p in sys.argv[1:]:render(p)

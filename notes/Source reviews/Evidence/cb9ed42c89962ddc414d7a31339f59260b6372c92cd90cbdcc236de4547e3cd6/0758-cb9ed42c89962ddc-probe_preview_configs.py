"""Read-only inventory of accepted preview rendering for the pin-letter stage."""
from pathlib import Path
from hashlib import sha256
from collections import defaultdict
import json,sys
from PIL import Image

ROOT=Path('D:/Github/IBM360');BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'ibm360ald/tools/reviews'))
import source_review as sr

font=sr.binding(ROOT/'tmp/ald-text/JuliaMono-Regular.ttf')
groups=defaultdict(list);missing=[]
for gi in (1,2,3):
    for page in sr.read_json(BASE/f'Group {gi} requests.json')['pages']:
        text=Path(page['working_text']);previews=list(text.parent.glob(text.stem+'*preview.png'))
        if not previews and text.with_suffix('.png').is_file():previews=[text.with_suffix('.png')]
        if not previews:
            missing.append({'page':page['page'],'text':sr.binding(text),'new_preview_target':str(text.with_name(text.stem+' JuliaMono preview.png'))})
            continue
        assert len(previews)==1
        with Image.open(previews[0])as image:size=image.size
        groups[size].append((page,text,previews[0]))
results=[]
for size,entries in groups.items():
    page,text,preview=entries[0]
    origin=[10,10]if size[0]==2960 else[0,0]
    found=None
    for anchor in (None,'lt'):
        config={'font':font,'width':size[0],'height':size[1],'font_size':20,'cell_width':12,'row_height':18,'origin':origin,'anchor':anchor}
        if sr.same_pixels(sr.render_preview(text.read_bytes(),config,BASE),preview.read_bytes()):found=config;break
    results.append({'dimensions':size,'representative':page['page'],'count':len(entries),'configuration':found,
                    'preview':sr.binding(preview),'text':sr.binding(text)})
report={'schema':'pin-letter-predecessor-preview-config-probe-v1','source_changes_applied':False,'configurations':results,'missing_current_preview':missing}
sr.atomic_write(BASE/'Predecessor preview configuration probe.json',sr.encode(report))
print(json.dumps(report,ensure_ascii=False,indent=2))

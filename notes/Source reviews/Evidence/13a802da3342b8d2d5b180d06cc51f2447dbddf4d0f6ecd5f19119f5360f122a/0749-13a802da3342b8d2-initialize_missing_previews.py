"""Create four explicitly new renders of accepted, unchanged working text.

These are newly created derivative assets, not recovered historical previews.
The absent-before state and exact accepted text/font bindings remain explicit.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,sys

ROOT=Path('D:/Github/IBM360');BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'ibm360ald/tools/reviews'))
import source_review as sr

probe=sr.read_json(BASE/'Predecessor preview configuration probe.json')
out=BASE/'New predecessor render initialization receipt.json'
sr.require(not out.exists(),'Initialization already recorded')
config=next(x['configuration']for x in probe['configurations']if x['dimensions']==[2940,1854])
plans=[]
for page in probe['missing_current_preview']:
    text,raw=sr.checked(page['text'],BASE)
    target=Path(page['new_preview_target']).resolve()
    sr.require(target.is_relative_to(ROOT/'ALD_Visual_Transcriptions')and not target.exists(),'New derivative target already exists/escapes')
    plans.append((page,text,raw,target,sr.render_preview(raw,config,BASE)))
created=[]
try:
    for page,text,raw,target,rendered in plans:
        sr.require(text.read_bytes()==raw and not target.exists(),'Accepted source/absence drift')
        with target.open('xb')as stream:
            created.append(target);stream.write(rendered)
        sr.require(sr.same_pixels(target.read_bytes(),sr.render_preview(raw,config,BASE)),'New render verification failed')
    receipt={'schema':'explicit-new-working-preview-initialization-v1','passed':True,
        'created_utc':datetime.now(timezone.utc).isoformat(),
        'source_text_model_notes_or_TIFF_writes':0,'canonical_repository_writes':0,
        'meaning':'New derivative previews rendered now from the accepted unchanged UTF-8 texts. They were absent before this operation; no historical preview existence is asserted.',
        'tool':sr.binding(Path(__file__)),'renderer':sr.binding(ROOT/'ibm360ald/tools/reviews/source_review.py'),
        'configuration':config,'records':[{'page':page['page'],'accepted_text':page['text'],
            'preview_before':None,'new_derivative_preview':sr.binding(target)}for page,text,raw,target,rendered in plans]}
    sr.atomic_write(out,sr.encode(receipt))
except BaseException:
    for target in reversed(created):target.unlink()
    raise
print(json.dumps({'passed':True,'new_derived_previews':len(created),'source_text_changes':0,'receipt':str(out)}))

"""Privately stage the exact C3 card-code correction after the V4 release.

No publication, registry update, uniform rebuild or live source write occurs.
Only active collections at the exact physical site are eligible for JSON edits.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib, importlib.util, json, re, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald'
BASE=ROOT/'tmp/ald-text/ald/socket-ald-audit'
NATIVE=BASE/'reverse-systemic-analysis/native'
V4=ROOT/'tmp/ald-text/ald/uniform-socket-listings/source-review/absent-reference-corrections-v4'
OUT=ROOT/'tmp/ald-text/ald/uniform-socket-listings/source-review/A1241-C3-3388-addendum'
AUDIT=ROOT/'tmp/ald-text/ald/repository-export'
ADAPTER=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json'
REGISTRY=AUDIT/'A1 table application registry.json'
SOURCE=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')
sys.path.insert(0,str(REPO/'tools/reviews'))
import source_review as sr

def need(v,m):
    if not v:raise ValueError(m)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def put(p,v):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(enc(v));return bind(p)
def module(p):
    s=importlib.util.spec_from_file_location('a1241_current_table_registration',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def escape(s):return str(s).replace('~','~0').replace('/','~1')
def physical(s):return re.sub(r'(?<=\d)[BT]$','',str(s))

def active_entries(document):
    """Yield active records only, never historical application/provenance prose."""
    inherited=document.get('board')
    for key in ('records','logical_records','sockets','sections'):
        values=document.get(key)
        if isinstance(values,list):
            for i,item in enumerate(values):
                if isinstance(item,dict):yield '/'+key+'/'+str(i),item,inherited
    buckets=document.get('ALD_pages')
    if isinstance(buckets,dict):
        for key,values in buckets.items():
            if isinstance(values,list):
                for i,item in enumerate(values):
                    if isinstance(item,dict):yield '/ALD_pages/'+escape(key)+'/'+str(i),item,inherited
    elif not any(k in document for k in ('records','logical_records','sockets','sections')):
        # The historical unassigned-page lookup is a root page-key dictionary.
        for key,values in document.items():
            if re.fullmatch(r'[A-Z0-9�]{5}',key) and isinstance(values,list):
                for i,item in enumerate(values):
                    if isinstance(item,dict):yield '/'+escape(key)+'/'+str(i),item,inherited

def fix_json(document):
    after=deepcopy(document);changes=[];seen=set()
    for pointer,item,board in active_entries(after):
        sockets=item.get('sockets') or ([item['socket']] if item.get('socket') else [])
        if isinstance(sockets,str):sockets=[sockets]
        if item.get('board',board)!='02B-D1' or {physical(s) for s in sockets}!={'C3'}:continue
        if not any(k in item for k in ('part_number','card_type')):continue
        need(item.get('card_type') in (None,'3368','3388'),'Unexpected current C3 card type')
        need(item.get('part_number') in (None,'5803368','5803388'),'Unexpected current C3 complete part number')
        for field,old,new in [('part_number','5803368','5803388'),('card_type','3368','3388')]:
            if item.get(field)==old:
                path=pointer+'/'+field;need(path not in seen,'Repeated active pointer');seen.add(path)
                changes.append({'pointer':path,'before':old,'after':new,
                    'proof':'Native A1241-01 C3 complete part number/card type; same exact 02B-D1 socket C3 only'})
                item[field]=new
    return after,changes

def main():
    receipt=V4/'Publication/Publication receipt.json'
    need(receipt.is_file(),'V4 must finish actual publication before addendum preimages are frozen')
    v4=read(receipt);need(v4.get('passed') is True and v4.get('published') is True,'V4 publication did not complete')
    app=module(REPO/'tools/reviews/register_a1_application.py')
    need(app.TABLE_MODEL_SCHEMAS.get('socket-page-records-v1')=='records','Published honest records-table helper is required')
    need(not OUT.exists(),'Private addendum already exists; preserve its frozen epoch')
    plan=read(NATIVE/'A1241-01 C3 exact two-cell plan.json')
    source=Path(plan['native_source']['path']);need(sha(source)==plan['native_source']['sha256'],'Native source changed')
    crop=Path(plan['native_crop']['path']);need(sha(crop)==plan['native_crop']['sha256'],'Native crop changed')
    with Image.open(source) as image,Image.open(crop) as tile:
        need(image.convert('RGB').crop(plan['native_crop']['box']).tobytes()==tile.convert('RGB').tobytes(),'Native crop pixels differ')
    text=Path(plan['current_working_text']['path']);repo_text=Path(plan['current_repository_text']['path'])
    need(sha(text)==plan['current_working_text']['sha256'] and text.read_bytes()==repo_text.read_bytes(),'A1241 source epoch differs')
    model=text.with_suffix('.json');model_data=read(model)
    need(isinstance(model_data.get('records'),list) and model_data['board']=='02B-D1' and 'nodes'not in model_data,'Actual A1241 records-table schema differs')
    OUT.mkdir(parents=True)
    files=[]
    def stage(target,raw,role,changes):
        target=Path(target).resolve();need(target.is_relative_to(ROOT) and target.suffix.lower()not in{'.tif','.tiff'},'Target outside source-data scope')
        old=target.read_bytes();i=f'{len(files):03d}';before=OUT/'before'/i/target.name;candidate=OUT/'candidate'/i/target.name
        before.parent.mkdir(parents=True);candidate.parent.mkdir(parents=True);before.write_bytes(old);candidate.write_bytes(raw)
        files.append({'target':str(target),'role':role,'before':bind(before),'candidate':bind(candidate),'changes':changes})
    raw=text.read_bytes();rows=raw.decode('utf-8-sig').splitlines(keepends=True)
    for change in plan['cell_edits']:
        row,column=change['row'],change['column'];need(rows[row][column]==change['before'],'Exact source digit differs')
        rows[row]=rows[row][:column]+change['after']+rows[row][column+1:]
    corrected=(b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf')else b'')+''.join(rows).encode('utf-8')
    stage(text,corrected,'working accepted TXT',plan['cell_edits']);stage(repo_text,corrected,'repository accepted TXT',plan['cell_edits'])
    paths=[model,REPO/'json/A1 Socket Listing'/model.name]
    for folder in [ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing',REPO/'json/A1 Socket Listing']:
        paths += [folder/name for name in ('Socket reference.json','ALD references.json')]
    paths.append(ROOT/'tmp/ald-text/a1/references without scan filename.json')
    json_changes=[]
    for path in paths:
        data=read(path);after,changes=fix_json(data)
        if changes:
            role='current accepted socket table model' if path in paths[:2] else 'current auxiliary reference mirror'
            stage(path,sr.model_bytes(after,path.read_bytes()),role,changes)
            json_changes.append({'target':str(path),'changes':changes})
    need({p['target']for p in json_changes}>={str(p.resolve())for p in paths[:2]},'Both actual table model copies must change')
    notes=text.with_name(text.stem+' review notes.txt')
    note='A1241-01 C3 NATIVE CARD-CODE REVIEW 2026-10-16\nNative socket 02B-D1 C3 prints 5803388 3388. The former 5803368 3368 transcription misread an 8 as 6 twice. Exactly row 88 columns 68 and 73 are corrected; card portions and all page references remain unchanged. The AP781 A1/B1/H1 native blocks independently read 3388, with F1 already recorded as 3388. Only active JSON complete-part/card-type mirrors for this same physical socket are corrected. Historical notes, application records, accepted predecessor models and original TIFF are preserved. Independent acceptance and publication are separate receipts.'
    stage(notes,sr.append_note(notes.read_bytes(),note),'source review notes',[])
    fontpath=ROOT/'tmp/ald-text/JuliaMono-Regular.ttf';font=ImageFont.truetype(str(fontpath),18);cw=round(font.getlength('M'));lines=corrected.decode('utf-8-sig').splitlines()
    image=Image.new('RGB',(32+max(map(len,lines))*cw,32+len(lines)*25),'white');draw=ImageDraw.Draw(image)
    for y,line in enumerate(lines):draw.text((16,16+y*25),line,font=font,fill='black')
    preview=OUT/'Corrected source preview.png';image.save(preview)
    stage(text.with_name(text.stem+' preview.png'),preview.read_bytes(),'source preview',[])
    baseline=read(AUDIT/'last export manifest.json');entry=next(x for x in baseline['exported']if str(x['source_scan_id'])=='126')
    prior=Path(entry['review_record']);prior=prior if prior.is_absolute()else ROOT/prior
    predecessor=put(OUT/'Predecessor application proof.json',{'schema':'existing-reviewed-export-predecessor-v1',
        'provenance':bind(REPO/'notes/Reviewed export provenance.json'),'export_entry':entry,
        'actual_acceptance_record':bind(prior) if prior.is_file()else None,'literal_acceptance_record':entry['review_record'],
        'current_table_model':bind(model),'v4_completed_publication':bind(receipt),
        'preservation_note':'Actual preexisting records-list table and export acceptance; no nodes model or columns acceptance is invented.'})
    historical=REPO/'notes/A1 Socket Listing/A1241-01 SOCKET LISTING review record.json'
    historycopy=OUT/'Historical repository proof.json';historycopy.write_bytes(historical.read_bytes())
    authority=put(OUT/'Resolution authority.json',{'schema':'socket-card-code-native-resolution-authority-v1','page':'A1241-01',
        'source':bind(source),'native_crop':bind(crop),'native_finding':bind(NATIVE/'A1241-01 C3 finding.json'),
        'exact_cell_plan':bind(NATIVE/'A1241-01 C3 exact two-cell plan.json'),
        'scope':'Coordinator-approved native read 5803388 3388, supported independently by AP781 blocks. Current user request authorizes resolving source discrepancies; no invented direct-human glyph answer.'})
    actual_candidate=next(x['candidate']for x in files if Path(x['target'])==model.resolve())
    stage_doc={'schema':app.STAGE_SCHEMA,'artifact_schema':app.TABLE_QUARTET_SCHEMA,'model_schema':'socket-page-records-v1',
        'page':'A1241-01','board':'02B-D1','source_scan_id':'126','source':bind(source),
        'human_authority':authority,'source_crop':bind(crop),'source_crops':[bind(crop)],
        'predecessor_acceptance':predecessor,'historical_repository_acceptance':bind(historycopy),
        'historical_repository_original':bind(historical),'exact_meaningful_cell_changes':plan['cell_edits'],
        'trailing_space_padding':[],'files':files,'published':False,'independent_acceptance_required':True,
        'model_source_binding':{'mode':'external-stage-binding','model_target':str(model),'model_candidate':actual_candidate,
            'native_source':bind(source),'accepted_predecessor':predecessor,
            'note':'The original table lacks a source field. This exact stage binding preserves the real schema.'},
        'preparation_script':bind(__file__),'font':bind(fontpath),'json_mirror_changes':json_changes,
        'predecessor_adapter':bind(ADAPTER),'registry_predecessor':bind(REGISTRY),
        'registration_helper':bind(REPO/'tools/reviews/register_a1_application.py'),
        'metadata_preimages':[bind(p)for p in (REPO/'notes/Content data manifest.json',REPO/'notes/Reviewed export provenance.json',
            AUDIT/'last export manifest.json',REPO/'notes/A1 Socket Listing/A1241-01 SOCKET LISTING review notes.txt',historical)],
        'post_publication_requirements':['Independent exact-cell/current-record/native review','Guarded publication','Honest records-table registration',
            'Scoped repository content/provenance update','Uniform dataset source-bound rebuild and verification']}
    manifest=OUT/'Stage manifest.json';put(manifest,stage_doc)
    app.validate_table_model(Path(actual_candidate['path']),stage_doc)
    for f in files:need(sha(f['target'])==f['before']['sha256'],'Live preimage changed during private preparation')
    need(sha(source)==stage_doc['source']['sha256'],'Native source changed during private preparation')
    report={'passed':True,'published':False,'manifest':bind(manifest),'source_cells':2,'source_pages':1,
        'actual_schema':'socket-page-records-v1','candidate_files':len(files),'json_fields':sum(len(x['changes'])for x in json_changes),
        'working_and_repository_cell_preimages_equal':True,'no_other_record_transforms':True,'source_scan_writes':0}
    put(OUT/'Preparation assertions.json',report);print(json.dumps(report,indent=2))

if __name__=='__main__':main()

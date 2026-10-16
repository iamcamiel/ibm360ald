"""Privately stage the human-confirmed F5/C1 reference after A1241 publishes."""
from copy import deepcopy
from pathlib import Path
import json,re,sys
from PIL import Image,ImageDraw,ImageFont
from prepare_a1241_addendum import active_entries,bind,enc,module,need,read,sha,put

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald'
BASE=ROOT/'tmp/ald-text/ald/socket-ald-audit';FINDINGS=BASE/'absent-reference-review'
A1241=ROOT/'tmp/ald-text/ald/uniform-socket-listings/source-review/A1241-C3-3388-addendum'
OUT=ROOT/'tmp/ald-text/ald/uniform-socket-listings/source-review/A1151-RF081-addendum'
AUDIT=ROOT/'tmp/ald-text/ald/repository-export';SOURCE=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')
ADAPTER=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json'
REGISTRY=AUDIT/'A1 table application registry.json'
sys.path.insert(0,str(REPO/'tools/reviews'));import source_review as sr

def site(item,board):
    sockets=item.get('sockets')or([item['socket']]if item.get('socket')else[])
    if isinstance(sockets,str):sockets=[sockets]
    return item.get('board',board)=='02A-E1'and sockets==['F5']

def portion(item):
    values=item.get('printed_portions',item.get('portions',[]))
    if isinstance(values,str):values=values.split()
    return item.get('portion')=='C1'or values==['C1']

def fix_rf_json(document):
    """Change only the witnessed F5/0512/C1 reference and its exact cached copies."""
    after=deepcopy(document);changes=[]
    entries=list(active_entries(after))
    # A continuation needs its explicit F5 primary record, not a guessed type.
    primary=any(site(item,board)and item.get('card_type')=='0512' for _,item,board in entries)
    for pointer,item,board in entries:
        if not site(item,board):continue
        typed=item.get('card_type')=='0512'
        continuation=primary and item.get('kind')=='continuation'and item.get('continues_socket')=='F5'
        if not(typed or continuation):continue
        if item.get('card_type')not in(None,'0512'):continue
        for i,ref in enumerate(item.get('references',[])):
            if not isinstance(ref,dict)or not portion(ref):continue
            for field in ('ALD_page','ald_page','page'):
                if ref.get(field)=='RF091':
                    ref[field]='RF081';changes.append({'pointer':pointer+'/references/'+str(i)+'/'+field,'before':'RF091','after':'RF081',
                        'proof':'Exact 02A-E1 F5 0512 C1 source row; explicit primary continuation copy'if continuation else'Exact 02A-E1 F5 0512 C1 source row'})
        for field in ('ALD_page','ald_page','page'):
            if item.get(field)=='RF091'and portion(item):
                item[field]='RF081';changes.append({'pointer':pointer+'/'+field,'before':'RF091','after':'RF081','proof':'Exact F5 0512 C1 entry'})
        for i,line in enumerate(item.get('printed_lines',[])):
            if isinstance(line,str)and re.fullmatch(r'\s*RF091\s+C1\s*',line):
                new=line.replace('RF091','RF081');item['printed_lines'][i]=new
                changes.append({'pointer':pointer+'/printed_lines/'+str(i),'before':line,'after':new,'proof':'Exact source line RF091 C1; no other printed line is edited'})
    # Move only the corroborated card entry; a connector-pin RF091 may remain.
    buckets=after.get('ALD_pages')if isinstance(after.get('ALD_pages'),dict)else after
    if isinstance(buckets.get('RF091'),list):
        moved=[];kept=[]
        for item in buckets['RF091']:
            good=(isinstance(item,dict)and site(item,None)and item.get('card_type')=='0512'and item.get('kind')=='card portion'and portion(item))
            (moved if good else kept).append(item)
        if moved:
            buckets.setdefault('RF081',[]).extend(moved)
            if kept:buckets['RF091']=kept
            else:del buckets['RF091']
            changes.append({'operation':'move_exact_card_portion_bucket','bucket_root':'/ALD_pages'if buckets is not after else'',
                'before_key':'RF091','after_key':'RF081','moved_entries':deepcopy(moved),'count':len(moved),
                'proof':'Move only exact 02A-E1 F5 0512 C1; retain every unrelated connector entry'})
    return after,changes

def main():
    previous=A1241/'Publication/Publication receipt.json'
    need(previous.is_file()and read(previous).get('published')is True and read(previous).get('passed')is True,'A1241 actual publication must finish before shared preimages freeze')
    app=module(REPO/'tools/reviews/register_a1_application.py')
    need(not OUT.exists(),'RF addendum already exists; preserve frozen epoch')
    human_path=FINDINGS/'RF081 Human confirmation.json';human=read(human_path)
    need(human['confirmed_reading']=='RF081'and human['answer']=='RF081 is printed'and human['source_page']=='A1151-01','Direct human authority differs')
    finding=next(x for x in read(FINDINGS/'Current absent reference findings.json')['findings']if x['unavailable_page']=='RF091')
    span=finding['source_reference_spans'][0];need(span['row']==93 and span['token_column']==95,'Expected witnessed source location')
    native=finding['representative_crop'];source=Path(native['source']['path']);crop=Path(native['path'])
    need(sha(source)==native['source']['sha256']and sha(crop)==native['sha256'],'Native evidence changed')
    with Image.open(source)as original,Image.open(crop)as tile:
        need(original.convert('RGB').crop(native['bounds']).tobytes()==tile.convert('RGB').tobytes(),'Native pixels differ')
    text=ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing/A1151-01 SOCKET LISTING.txt';repo_text=REPO/'ALD/A1 Socket Listing'/text.name
    need(text.read_bytes()==repo_text.read_bytes(),'Current working/repo table differs');model=text.with_suffix('.json');data=read(model)
    need(isinstance(data.get('sockets'),list)and data.get('board')=='02A-E1'and'nodes'not in data,'Actual sockets-list schema differs')
    OUT.mkdir(parents=True);files=[]
    def stage(target,raw,role,changes):
        target=Path(target).resolve();need(target.is_relative_to(ROOT)and target.suffix.lower()not in{'.tif','.tiff'},'Write scope escaped')
        i=f'{len(files):03d}';before=OUT/'before'/i/target.name;after=OUT/'candidate'/i/target.name
        old=target.read_bytes()if target.exists()else None
        after.parent.mkdir(parents=True);after.write_bytes(raw)
        if old is not None:before.parent.mkdir(parents=True);before.write_bytes(old)
        files.append({'target':str(target),'role':role,'before':bind(before)if old is not None else None,'candidate':bind(after),'changes':changes})
    raw=text.read_bytes();rows=raw.decode('utf-8-sig').splitlines(keepends=True);need(rows[93][95:100]=='RF091','Source token preimage changed')
    delta=[{'row':93,'column':98,'before':'9','after':'8'}];rows[93]=rows[93][:98]+'8'+rows[93][99:]
    corrected=(b'\xef\xbb\xbf'if raw.startswith(b'\xef\xbb\xbf')else b'')+''.join(rows).encode('utf-8')
    stage(text,corrected,'working accepted TXT',delta);stage(repo_text,corrected,'repository accepted TXT',delta)
    paths=[model,REPO/'json/A1 Socket Listing'/model.name]
    for folder in (ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing',REPO/'json/A1 Socket Listing'):
        paths += [folder/name for name in ('Socket reference.json','ALD references.json')]
    paths += [ROOT/'tmp/ald-text/a1/references without scan filename.json']
    json_changes=[]
    for path in paths:
        before=read(path);after,changes=fix_rf_json(before)
        if changes:
            stage(path,sr.model_bytes(after,path.read_bytes()),'current accepted socket table model'if path in paths[:2]else'current auxiliary reference mirror',changes)
            json_changes.append({'target':str(path),'changes':changes})
    need(all(any(x['target']==str(p.resolve())for x in json_changes)for p in paths[:2]),'Both source table models must change')
    notes=text.with_name(text.stem+' review notes.txt')
    note='A1151-01 F5 C1 DIRECT HUMAN REFERENCE REVIEW 2026-10-16\nThe physical-page reading RF081 is printed was supplied directly by the user. At 02A-E1 socket F5, card type 0512 portion C1, RF091 is corrected to RF081: exactly row 93 column 98, 9 to 8. Active mirrors and explicit primary-record continuation copies for that same card/portion are updated. Only its exact card-portion bucket entry moves to RF081. Unrelated N6 B11 RF091BH4 connector references remain unchanged because this answer establishes the F5 C1 reference only. Historical observations and original TIFF are preserved; independent acceptance and publication have separate immutable receipts.'
    stage(notes,sr.append_note(notes.read_bytes()if notes.exists()else b'',note),'source review notes',[])
    fontpath=ROOT/'tmp/ald-text/JuliaMono-Regular.ttf';font=ImageFont.truetype(str(fontpath),18);cw=round(font.getlength('M'));lines=corrected.decode('utf-8-sig').splitlines()
    image=Image.new('RGB',(32+max(map(len,lines))*cw,32+len(lines)*25),'white');draw=ImageDraw.Draw(image)
    for y,line in enumerate(lines):draw.text((16,16+y*25),line,font=font,fill='black')
    preview=OUT/'Corrected source preview.png';image.save(preview);stage(text.with_name(text.stem+' preview.png'),preview.read_bytes(),'source preview',[])
    baseline=read(AUDIT/'last export manifest.json');entry=next(x for x in baseline['exported']if str(x['source_scan_id'])=='92');prior=Path(entry['review_record']);prior=prior if prior.is_absolute()else ROOT/prior
    predecessor=put(OUT/'Predecessor application proof.json',{'schema':'existing-reviewed-export-predecessor-v1','provenance':bind(REPO/'notes/Reviewed export provenance.json'),
        'export_entry':entry,'actual_acceptance_record':bind(prior)if prior.is_file()else None,'literal_acceptance_record':entry['review_record'],
        'current_table_model':bind(model),'completed_prior_addendum':bind(previous),
        'companion_predecessors':{'notes_existed':notes.exists(),'preview_existed':text.with_name(text.stem+' preview.png').exists()},
        'preservation_note':'Actual sockets-list table and accepted TXT exist. No working notes/preview existed: this stage explicitly creates those new companions, with no invented preimage. No nodes/columns schema is claimed.'})
    historical=REPO/'notes/A1 Socket Listing/A1151-01 SOCKET LISTING review record.json';historycopy=OUT/'Historical repository proof.json';historycopy.write_bytes(historical.read_bytes())
    actual=next(x['candidate']for x in files if Path(x['target'])==model.resolve())
    stage_doc={'schema':app.STAGE_SCHEMA,'artifact_schema':app.TABLE_QUARTET_SCHEMA,'model_schema':'socket-page-sockets-v1','page':'A1151-01','board':'02A-E1','source_scan_id':'92',
        'source':bind(source),'human_authority':bind(human_path),'source_crop':bind(crop),'source_crops':[bind(crop)],'predecessor_acceptance':predecessor,
        'historical_repository_acceptance':bind(historycopy),'historical_repository_original':bind(historical),'exact_meaningful_cell_changes':delta,
        'trailing_space_padding':[],'files':files,'published':False,'independent_acceptance_required':True,'preparation_script':bind(__file__),'font':bind(fontpath),
        'json_mirror_changes':json_changes,'predecessor_adapter':bind(ADAPTER),'registry_predecessor':bind(REGISTRY),'registration_helper':bind(REPO/'tools/reviews/register_a1_application.py'),
        'metadata_preimages':[bind(p)for p in (REPO/'notes/Content data manifest.json',REPO/'notes/Reviewed export provenance.json',AUDIT/'last export manifest.json',
            REPO/'notes/A1 Socket Listing/A1151-01 SOCKET LISTING review notes.txt',historical)],
        'withheld_reference':'N6 B11 RF091BH4 remains unchanged; no exact source-pin reading is supplied by this authority.',
        'post_publication_requirements':['Independent exact-cell/current-record/direct-human review','Guarded publication','Honest sockets-table registration',
            'Scoped content/provenance update','Uniform rebuild only after remaining accepted ALD metadata releases finish']}
    manifest=OUT/'Stage manifest.json';put(manifest,stage_doc);app.validate_table_model(Path(actual['path']),stage_doc)
    for f in files:
        if f['before']:need(sha(f['target'])==f['before']['sha256'],'Live predecessor changed during staging')
        else:need(not Path(f['target']).exists(),'A declared new companion appeared during staging')
    report={'passed':True,'published':False,'manifest':bind(manifest),'source_cells':1,'source_pages':1,'actual_schema':'socket-page-sockets-v1',
        'candidate_files':len(files),'json_operations':sum(len(x['changes'])for x in json_changes),'source_scan_writes':0,'source_changes_applied':False}
    put(OUT/'Preparation assertions.json',report);print(json.dumps(report,indent=2))

if __name__=='__main__':main()

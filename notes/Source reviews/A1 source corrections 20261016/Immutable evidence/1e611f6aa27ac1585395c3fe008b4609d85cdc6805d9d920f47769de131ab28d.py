"""Stage one native-confirmed A1 identity correction; never publish or accept."""
from copy import deepcopy
from datetime import datetime,timezone
import argparse,hashlib,importlib.util,json,re,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';BASE=Path(__file__).resolve().parent
AUDIT=ROOT/'tmp/ald-text/ald/repository-export'
ADAPTER=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json'
REGISTRY=AUDIT/'A1 table application registry.json'
sys.path.insert(0,str(REPO/'tools/reviews'))
import source_review as sr
import register_a1_application as app

def need(ok,message):
    if not ok:raise ValueError(message)
def read(path):return json.loads(Path(path).read_text('utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def bind(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def checked(link):
    path=Path(link['path']);need(sha(path)==link['sha256'],'Stale native evidence');return path
def enc(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def physical(socket):return re.sub(r'(?<=\d)[BT]$','',str(socket))

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--page',required=True);cli.add_argument('--output',required=True,type=Path)
    cli.add_argument('--pin-verification',required=True,type=Path)
    args=cli.parse_args();output=args.output.resolve()
    need(output.is_relative_to(BASE) and not output.exists(),'Use a new private card review stage directory')
    need(read(args.pin_verification).get('passed') is True,'Pin import verification must pass first')
    authority_path=BASE/'Coordinator A1 native literal readings.json';authority=read(authority_path)
    uniform=read(REPO/'json/Socket listings uniform/Socket listings.json')
    byid={r['id']:r for r in uniform['records']}
    selected=[]
    for finding in authority['records']:
        record=byid[finding['record_id']]
        pages={span['page'] for span in record['source_spans']}
        if args.page not in pages:continue
        need(pages=={args.page},'Cross-page identity record needs separate review')
        source=checked(finding['source']);crop=checked(finding['native_crop'])
        with Image.open(source) as original,Image.open(crop) as tile:
            need(original.convert('RGB').crop(finding['native_crop']['box']).tobytes()==tile.convert('RGB').tobytes(),'Native crop differs')
        selected.append((record,finding))
    need(bool(selected),'No coordinator-confirmed native identity corrections for this page')
    sources={finding['source']['path'] for _,finding in selected};need(len(sources)==1,'A1 page binds multiple TIFFs')
    source=Path(next(iter(sources)));name=source.with_suffix('.txt').name
    text=ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing'/name
    repo_text=REPO/'ALD/A1 Socket Listing'/name
    need(text.read_bytes()==repo_text.read_bytes(),'Working and repository A1 text differ')
    model=text.with_suffix('.json');data=read(model)
    kinds={'sockets':'socket-page-sockets-v1','sections':'socket-page-sections-v1','records':'socket-page-records-v1'}
    keys=set(kinds)&set(data);need(len(keys)==1 and 'nodes' not in data,'Unsupported current A1 table schema')
    model_schema=kinds[next(iter(keys))]
    output.mkdir(parents=True);files=[]
    def put(path,value):path.write_bytes(enc(value));return bind(path)
    def stage(target,raw,role,changes):
        target=Path(target).resolve();old=target.read_bytes() if target.exists() else None
        if old==raw:return
        index=f'{len(files):03d}';before=output/'before'/index/target.name;candidate=output/'candidate'/index/target.name
        candidate.parent.mkdir(parents=True)
        if old is not None:before.parent.mkdir(parents=True);before.write_bytes(old)
        candidate.write_bytes(raw)
        files.append({'target':str(target),'role':role,'before':bind(before) if old is not None else None,'candidate':bind(candidate),'changes':changes})
    raw=text.read_bytes();lines=raw.decode('utf-8-sig').splitlines(keepends=True);deltas=[]
    for record,finding in selected:
        old_pair=str(record['part_number'])+' '+str(record['card_type'])
        new_pair=finding['observed_part_number']+' '+finding['observed_card_type']
        need(len(old_pair)==len(new_pair) and old_pair!=new_pair,'Expected exact same-width identity repair')
        spans=[s for s in record['source_spans'] if old_pair in s['literal']]
        need(len(spans)==1,'Identity line is missing or ambiguous')
        span=spans[0];y=span['row'];x=span['column']+span['literal'].index(old_pair)
        need(lines[y][x:x+len(old_pair)]==old_pair,'Current exact source span differs')
        lines[y]=lines[y][:x]+new_pair+lines[y][x+len(old_pair):]
        deltas += [{'row':y,'column':x+i,'before':a,'after':b} for i,(a,b) in enumerate(zip(old_pair,new_pair)) if a!=b]
    deltas.sort(key=lambda change:(change['row'],change['column']))
    newraw=(b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'')+''.join(lines).encode('utf-8')
    stage(text,newraw,'working accepted TXT',deltas);stage(repo_text,newraw,'repository accepted TXT',deltas)
    # Reuse only the old helper's pure active-entry iterator; its historical
    # stage and main routine are never invoked or modified.
    helper=BASE.parent/'prepare_a1241_addendum.py'
    spec=importlib.util.spec_from_file_location('active_socket_entries',helper);active=importlib.util.module_from_spec(spec);spec.loader.exec_module(active)
    paths=[model,REPO/'json/A1 Socket Listing'/model.name]
    for folder in (ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing',REPO/'json/A1 Socket Listing'):
        paths += [folder/'Socket reference.json',folder/'ALD references.json']
    paths.append(ROOT/'tmp/ald-text/a1/references without scan filename.json')
    json_changes=[]
    for path in paths:
        before=read(path);after=deepcopy(before);patches=[]
        for pointer,item,board in active.active_entries(after):
            sockets=item.get('sockets') or ([item['socket']] if item.get('socket') else [])
            if isinstance(sockets,str):sockets=[sockets]
            for record,finding in selected:
                if item.get('board',board)!=record['board'] or {physical(s) for s in sockets}!={physical(s) for s in record['sockets']}:continue
                for key,wanted in [('part_number',finding['observed_part_number']),('card_type',finding['observed_card_type'])]:
                    old=record[key]
                    need(item.get(key) in (None,old,wanted),'Unexpected active identity mirror '+str(path)+pointer)
                    if item.get(key)==old and old!=wanted:
                        item[key]=wanted;patches.append({'pointer':pointer+'/'+key,'before':old,'after':wanted})
                if isinstance(item.get('printed_lines'),list):
                    old_pair=str(record['part_number'])+' '+str(record['card_type']);new_pair=finding['observed_part_number']+' '+finding['observed_card_type']
                    for index,line in enumerate(item['printed_lines']):
                        if old_pair in line:
                            need(line.count(old_pair)==1,'Repeated printed identity mirror')
                            changed=line.replace(old_pair,new_pair)
                            item['printed_lines'][index]=changed;patches.append({'pointer':pointer+'/printed_lines/'+str(index),'before':line,'after':changed})
        if patches:
            stage(path,sr.model_bytes(after,path.read_bytes()),'current accepted socket table model' if path in paths[:2] else 'current auxiliary reference mirror',patches)
            json_changes.append({'target':str(path),'changes':patches})
    need({str(path.resolve()) for path in paths[:2]} <= {row['target'] for row in json_changes},'Both actual page models must change')
    notes=text.with_name(text.stem+' review notes.txt')
    message=args.page+' NATIVE CARD IDENTITY REVIEW\n'+ '\n'.join(record['board']+' '+','.join(record['sockets'])+': '+str(record['part_number'])+' '+str(record['card_type'])+' -> '+finding['observed_part_number']+' '+finding['observed_card_type'] for record,finding in selected)
    message+='\nNative socket headers and part/type lines were inspected independently. Only exact text cells and active identity mirrors for these physical sites change. Historical evidence and original TIFF remain unchanged. Acceptance and publication are separate receipts.'
    stage(notes,sr.append_note(notes.read_bytes() if notes.exists() else b'',message),'source review notes',[])
    fontpath=ROOT/'tmp/ald-text/JuliaMono-Regular.ttf';font=ImageFont.truetype(str(fontpath),18);cw=round(font.getlength('M'))
    visible=newraw.decode('utf-8-sig').splitlines();image=Image.new('RGB',(32+max(map(len,visible))*cw,32+len(visible)*25),'white');draw=ImageDraw.Draw(image)
    for y,line in enumerate(visible):draw.text((16,16+y*25),line,font=font,fill='black')
    preview=output/'Corrected source preview.png';image.save(preview)
    stage(text.with_name(text.stem+' preview.png'),preview.read_bytes(),'source preview',[])
    baseline=read(AUDIT/'last export manifest.json');entries=[r for r in baseline['exported'] if Path(r['transcription_source']).resolve()==text.resolve()]
    need(len(entries)==1,'A1 predecessor export is missing or ambiguous');entry=entries[0]
    prior=Path(entry['review_record']);prior=prior if prior.is_absolute() else ROOT/prior
    predecessor=put(output/'Predecessor application proof.json',{'schema':'existing-reviewed-export-predecessor-v1','provenance':bind(REPO/'notes/Reviewed export provenance.json'),'export_entry':entry,'actual_acceptance_record':bind(prior) if prior.is_file() else None,'literal_acceptance_record':entry['review_record'],'current_table_model':bind(model),'preservation_note':'Exact existing table and accepted export evidence; no acceptance is fabricated.'})
    historical=REPO/'notes/A1 Socket Listing'/(text.stem+' review record.json');saved=output/'Historical repository proof.json';saved.write_bytes(historical.read_bytes())
    authority_link=put(output/'Resolution authority.json',{'schema':'native-a1-identity-resolution-authority-v1','coordinator_native_readings':bind(authority_path),'selected_records':[r['id'] for r,_ in selected],'pin_publication_verification':bind(args.pin_verification),'active_entry_helper':bind(helper),'authority_scope':'User requested visual card/portion discrepancy resolution. Coordinator and separate reviewer inspected these native source readings. No direct human glyph confirmation is invented.'})
    crops=[bind(checked(finding['native_crop'])) for _,finding in selected]
    stage_doc={'schema':app.STAGE_SCHEMA,'artifact_schema':app.TABLE_QUARTET_SCHEMA,'model_schema':model_schema,'page':args.page,'board':data['board'],'source_scan_id':str(entry['source_scan_id']),'source':bind(source),'human_authority':authority_link,'source_crop':crops[0],'source_crops':crops,'predecessor_acceptance':predecessor,'historical_repository_acceptance':bind(saved),'historical_repository_original':bind(historical),'exact_meaningful_cell_changes':deltas,'trailing_space_padding':[],'files':files,'json_mirror_changes':json_changes,'preparation_script':bind(__file__),'font':bind(fontpath),'predecessor_adapter':bind(ADAPTER),'registry_predecessor':bind(REGISTRY),'registration_helper':bind(REPO/'tools/reviews/register_a1_application.py'),'metadata_preimages':[bind(p) for p in (REPO/'notes/Content data manifest.json',REPO/'notes/Reviewed export provenance.json',AUDIT/'last export manifest.json',REPO/'notes/A1 Socket Listing'/(text.stem+' review notes.txt'),historical)],'published':False,'independent_acceptance_required':True}
    app.validate_table_model(Path(next(f['candidate']['path'] for f in files if Path(f['target'])==model.resolve())),stage_doc)
    manifest=output/'Stage manifest.json';put(manifest,stage_doc)
    for file in files:
        need((sha(file['target']) if Path(file['target']).exists() else None)==(file['before']['sha256'] if file['before'] else None),'Live source changed during stage preparation')
    report={'passed':True,'published':False,'manifest':bind(manifest),'source_cells':len(deltas),'sites':len(selected),'candidate_files':len(files),'json_fields':sum(len(row['changes']) for row in json_changes),'source_scan_writes':0}
    put(output/'Preparation assertions.json',report);print(json.dumps(report))

if __name__=='__main__':main()

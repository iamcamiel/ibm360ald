"""Freeze one C3 page-reference correction only after the RF release completes."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import argparse,hashlib,importlib.util,json,re,sys
from PIL import Image,ImageDraw,ImageFont

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';BASE=ROOT/'tmp/ald-text/ald/socket-ald-audit'
OUT=ROOT/'tmp/ald-text/ald/uniform-socket-listings/source-review/A1241-C3-AP781-reference-addendum'
AUDIT=ROOT/'tmp/ald-text/ald/repository-export';SOURCE=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')
ADAPTER=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json';REGISTRY=AUDIT/'A1 table application registry.json'
sys.path.insert(0,str(REPO/'tools/reviews'));import source_review as sr
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def put(p,v):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(sr.encode(v));return bind(p)
def need(v,m):
 if not v:raise ValueError(m)
def physical(s):return re.sub(r'(?<=\d)[BT]$','',str(s))
def escape(s):return str(s).replace('~','~0').replace('/','~1')
def same_site(item,board=None):
 sockets=item.get('sockets')or([item['socket']]if item.get('socket')else[])
 if isinstance(sockets,str):sockets=[sockets]
 return item.get('board',board)=='02B-D1'and{physical(s)for s in sockets}=={'C3'}
def card_guard(item):
 need(item.get('card_type')=='3388'and item.get('part_number')=='5803388','C3 must already have independently accepted3388 type/part')
def fix_json(document):
 after=deepcopy(document);changes=[];inherited=after.get('board')
 for key in['records','logical_records','sections','sockets']:
  values=after.get(key)
  if not isinstance(values,list):continue
  for i,item in enumerate(values):
   if not isinstance(item,dict)or not same_site(item,inherited):continue
   refs=item.get('references',[])
   for j,ref in enumerate(refs):
    field=next((k for k in['ALD_page','ald_page','page']if ref.get(k)=='AP741'),None)
    if field is None:continue
    portions=ref.get('printed_portions',ref.get('portions',[]))
    if not set(portions).intersection({'F1','H1'}):continue
    need(portions==['F1','H1'],'Printed F1/H1 reference group unexpectedly changed');card_guard(item)
    ref[field]='AP781';changes.append({'pointer':f'/{key}/{i}/references/{j}/{field}','before':'AP741','after':'AP781','proof':'Native A1241-01 C3 F1/H1 row92col59; same3388 physical card only'})
 buckets=after.get('ALD_pages')
 if not isinstance(buckets,dict)and all(isinstance(x,list)for x in after.values()):buckets=after;bucket_pointer=''
 else:bucket_pointer='/ALD_pages'
 if isinstance(buckets,dict)and isinstance(buckets.get('AP741'),list):
  moved=[];retained=[]
  for entry in buckets['AP741']:
   if isinstance(entry,dict)and entry.get('kind')=='card portion'and same_site(entry,inherited)and entry.get('portion')in{'F1','H1'}:
    card_guard(entry);moved.append(entry)
   else:retained.append(entry)
  if moved:
   need(sorted(x['portion']for x in moved)==['F1','H1'],'Exactly F1/H1 bucket entries expected')
   if retained:buckets['AP741']=retained
   else:del buckets['AP741']
   buckets.setdefault('AP781',[]).extend(moved)
   changes.append({'operation':'move_bucket_entries','bucket_path':bucket_pointer,'before_key':'AP741','after_key':'AP781','count':2,'moved_entries':moved,'proof':'Same02B-D1 C3 /3388 F1,H1 only; other page entries remain'})
 return after,changes

def main():
 cli=argparse.ArgumentParser();cli.add_argument('--after-publication',required=True,type=Path);args=cli.parse_args()
 prior=read(args.after_publication);need(prior.get('passed')is True and prior.get('published')is True,'RF publication must finish before this stage freezes')
 need('RF'in str(args.after_publication),'Require the explicit RF release receipt, not an earlier source release')
 need(not OUT.exists(),'Do not replace an already frozen reference stage')
 finding_path=BASE/'reverse-systemic-analysis/native/A1241-01 C3 separate AP781 reference finding.json';finding=read(finding_path)
 source=Path(finding['source']['path']);crop=Path(finding['native_crop']['path'])
 need(sha(source)==finding['source']['sha256']and sha(crop)==finding['native_crop']['sha256'],'Native source or crop changed')
 with Image.open(source)as original,Image.open(crop)as tile:need(original.convert('RGB').crop(finding['native_crop']['box']).tobytes()==tile.convert('RGB').tobytes(),'Native crop does not match TIFF pixels')
 text=ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing/A1241-01 SOCKET LISTING.txt';repo_text=REPO/'ALD/A1 Socket Listing'/text.name;model=text.with_suffix('.json')
 raw=text.read_bytes();need(raw==repo_text.read_bytes(),'Working/repository source bytes differ');rows=raw.decode('utf-8-sig').splitlines(keepends=True)
 need('5803388 3388'in rows[88]and rows[92][56:61]=='AP741','Expected already corrected card type and outstanding page reference')
 edit={'row':92,'column':59,'before':'4','after':'8'};need(finding['exact_source_edit']==edit,'Native one-cell plan differs')
 rows[92]=rows[92][:59]+'8'+rows[92][60:];corrected=(b'\xef\xbb\xbf'if raw.startswith(b'\xef\xbb\xbf')else b'')+''.join(rows).encode('utf-8')
 need(sum(x!=y for x,y in zip(raw,corrected))==1 and len(raw)==len(corrected),'Only one source byte may change')
 OUT.mkdir();files=[]
 def stage(target,value,role,changes):
  target=Path(target).resolve();need(target.is_relative_to(ROOT)and target.suffix.lower()not in{'.tif','.tiff'},'Write scope escaped');old=target.read_bytes();i=f'{len(files):03d}'
  a=OUT/'before'/i/target.name;b=OUT/'candidate'/i/target.name;a.parent.mkdir(parents=True);b.parent.mkdir(parents=True);a.write_bytes(old);b.write_bytes(value)
  files.append({'target':str(target),'role':role,'before':bind(a),'candidate':bind(b),'changes':changes})
 stage(text,corrected,'working accepted TXT',[edit]);stage(repo_text,corrected,'repository accepted TXT',[edit])
 paths=[model,REPO/'json/A1 Socket Listing'/model.name]
 for folder in[ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing',REPO/'json/A1 Socket Listing']:paths +=[folder/'Socket reference.json',folder/'ALD references.json']
 paths.append(ROOT/'tmp/ald-text/a1/references without scan filename.json');json_changes=[]
 for p in paths:
  d=read(p);after,changes=fix_json(d)
  if changes:stage(p,sr.model_bytes(after,p.read_bytes()),'current accepted socket table model'if p in paths[:2]else'current auxiliary reference mirror',changes);json_changes.append({'target':str(p),'changes':changes})
 need(len(files)==8,'Expected two TXT and six current JSON targets before notes/preview')
 notes=text.with_name(text.stem+' review notes.txt');note='A1241-01 C3 F1/H1 NATIVE PAGE-REFERENCE REVIEW 2026-10-16\nThe source prints AP781 F1 H1, not AP741 F1 H1. Exactly row92column59 changes4to8. The previously accepted5803388 3388 reading is retained. Only this physical card02B-D1 C3 F1/H1 reference group and its active index memberships move; every other page reference, endpoint, portion, part/type value and historical acceptance is retained. Native reviewers /root and /root/promote_continuation_fix independently agree; this is not a fabricated direct human glyph answer.'
 stage(notes,sr.append_note(notes.read_bytes(),note),'source review notes',[])
 fontpath=ROOT/'tmp/ald-text/JuliaMono-Regular.ttf';font=ImageFont.truetype(str(fontpath),18);lines=corrected.decode('utf-8-sig').splitlines();cw=round(font.getlength('M'));image=Image.new('RGB',(32+max(map(len,lines))*cw,32+len(lines)*25),'white');draw=ImageDraw.Draw(image)
 for y,line in enumerate(lines):draw.text((16,16+y*25),line,font=font,fill='black')
 preview=OUT/'Corrected source preview.png';image.save(preview);stage(text.with_name(text.stem+' preview.png'),preview.read_bytes(),'source preview',[])
 baseline=read(AUDIT/'last export manifest.json');entry=next(x for x in baseline['exported']if str(x['source_scan_id'])=='126');proof=Path(entry['review_record']);proof=proof if proof.is_absolute()else ROOT/proof
 predecessor=put(OUT/'Predecessor application proof.json',{'schema':'existing-reviewed-export-predecessor-v1','provenance':bind(REPO/'notes/Reviewed export provenance.json'),'export_entry':entry,'actual_acceptance_record':bind(proof)if proof.is_file()else None,'literal_acceptance_record':entry['review_record'],'current_table_model':bind(model),'preceding_RF_publication':bind(args.after_publication)})
 historical=REPO/'notes/A1 Socket Listing/A1241-01 SOCKET LISTING review record.json';history=OUT/'Historical repository proof.json';history.write_bytes(historical.read_bytes())
 authority=put(OUT/'Resolution authority.json',{'schema':'socket-page-reference-native-resolution-authority-v1','source':bind(source),'native_crop':bind(crop),'native_finding':bind(finding_path),'scope':'Independent native source readings agree on AP781 F1 H1; direct human glyph answer is not claimed. Current coordinator instruction authorizes resolving this known source error.'})
 model_candidate=next(f['candidate']for f in files if Path(f['target'])==model.resolve())
 app_spec=importlib.util.spec_from_file_location('a1241_reference_registration',REPO/'tools/reviews/register_a1_application.py');app=importlib.util.module_from_spec(app_spec);app_spec.loader.exec_module(app)
 doc={'schema':app.STAGE_SCHEMA,'artifact_schema':app.TABLE_QUARTET_SCHEMA,'model_schema':'socket-page-records-v1','page':'A1241-01','board':'02B-D1','source_scan_id':'126','source':bind(source),'human_authority':authority,'source_crop':bind(crop),'source_crops':[bind(crop)],'predecessor_acceptance':predecessor,'historical_repository_acceptance':bind(history),'historical_repository_original':bind(historical),'exact_meaningful_cell_changes':[edit],'trailing_space_padding':[],'files':files,'published':False,'independent_acceptance_required':True,'model_source_binding':{'mode':'external-stage-binding','model_target':str(model),'model_candidate':model_candidate,'native_source':bind(source),'accepted_predecessor':predecessor},'preparation_script':bind(__file__),'font':bind(fontpath),'json_mirror_changes':json_changes,'predecessor_adapter':bind(ADAPTER),'registry_predecessor':bind(REGISTRY),'registration_helper':bind(REPO/'tools/reviews/register_a1_application.py'),'metadata_preimages':[bind(p)for p in[REPO/'notes/Content data manifest.json',REPO/'notes/Reviewed export provenance.json',AUDIT/'last export manifest.json',REPO/'notes/A1 Socket Listing/A1241-01 SOCKET LISTING review notes.txt',historical]],'preceding_RF_publication':bind(args.after_publication),'native_finding':bind(finding_path),'post_publication_requirements':['Independent one-cell and exact C3 F1/H1 reference review','Use approved generic publish_single_table_addendum.py','Uniform rebuild deferred until ALD11 and source releases finish']}
 app.validate_table_model(Path(model_candidate['path']),doc)
 path=OUT/'Stage manifest.json';put(path,doc)
 for f in files:need(sha(f['target'])==f['before']['sha256'],'Source epoch changed during preparation')
 print(json.dumps({'published':False,'manifest':bind(path),'source_cells':1,'candidate_files':len(files),'json_operations':sum(len(x['changes'])for x in json_changes)}))

if __name__=='__main__':main()

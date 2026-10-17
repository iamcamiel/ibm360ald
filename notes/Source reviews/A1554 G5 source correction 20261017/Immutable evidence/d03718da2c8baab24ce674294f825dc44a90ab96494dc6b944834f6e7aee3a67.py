"""Prepare exact native-bound A1554 G5 identity correction; no publication."""
from copy import deepcopy
from pathlib import Path
import hashlib,importlib.util,json,re,sys
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).parent
OUT=HERE/'A1554 G5 source correction stage v3';AUDIT=ROOT/'tmp/ald-text/ald/repository-export'
ADAPTER=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json'
REGISTRY=AUDIT/'A1 table application registry.json'
sys.path.insert(0,str(REPO/'tools/reviews'))
import source_review as sr
import register_a1_application as app
def need(ok,message):
 if not ok:raise ValueError(message)
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def put(p,v):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(enc(v));return bind(p)
def checked(b):p=Path(b['path']);need(sha(p)==b['sha256'],'Stale input '+str(p));return p
ACTIVE_HELPER=HERE.parent/'prepare_a1241_addendum.py'
spec=importlib.util.spec_from_file_location('exact_active_entries',ACTIVE_HELPER);active=importlib.util.module_from_spec(spec);spec.loader.exec_module(active)
def physical(s):return re.sub(r'(?<=\d)[BT]$','',str(s))
def correct_active(document):
 """Only active same-site identities; history/provenance are not traversed."""
 after=deepcopy(document);patches=[]
 for pointer,item,inherited in active.active_entries(after):
  sockets=item.get('sockets')or([item['socket']]if item.get('socket')else[])
  if isinstance(sockets,str):sockets=[sockets]
  if item.get('board',inherited)!='02E-E4'or{physical(s)for s in sockets}!={'G5'}:continue
  for key,old,new in [('part_number','5800519','5800514'),('card_type','0519','0514')]:
   need(item.get(key)in(None,old,new),'Conflicting exact-site identity '+pointer)
   if item.get(key)==old:item[key]=new;patches.append({'pointer':pointer+'/'+key,'before':old,'after':new})
  if isinstance(item.get('printed_lines'),list):
   for index,line in enumerate(item['printed_lines']):
    old='5800519 0519'
    if old in line:
     need(line.count(old)==1,'Ambiguous printed-line identity');new=line.replace(old,'5800514 0514');item['printed_lines'][index]=new;patches.append({'pointer':pointer+'/printed_lines/'+str(index),'before':line,'after':new})
 return after,patches
def main():
 need(not OUT.exists(),'Stage exists; retain frozen source epoch')
 findings=HERE/'S component review/Findings.json';f=read(findings);finding=f['A1_identity_repair'];proposal=finding['proposal']
 checked(proposal['text']);source=checked(finding['source_evidence']['source']);crop=checked(finding['source_evidence']['native_crop'])
 with Image.open(source)as original,Image.open(crop)as tile:need(original.convert('RGB').crop(finding['source_evidence']['native_crop']['box']).tobytes()==tile.convert('RGB').tobytes(),'Native crop differs')
 uniform=read(REPO/'json/Socket listings uniform/Socket listings.json');record=next(r for r in uniform['records']if r['id']=='35:207:10')
 need((record['board'],record['sockets'],record['part_number'],record['card_type'])==('02E-E4',['G5'],'5800519','0519'),'Uniform exact site differs')
 name='A1554-01 SOCKET LISTING';text=ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing'/(name+'.txt');repo_text=REPO/'ALD/A1 Socket Listing'/(name+'.txt');model=text.with_suffix('.json');data=read(model)
 need(text.read_bytes()==repo_text.read_bytes(),'Working/repository text differs');need(data.get('board')=='02E-E4'and isinstance(data.get('records'),list)and 'nodes'not in data,'True page schema differs')
 OUT.mkdir(parents=True);files=[]
 def stage(target,raw,role,changes):
  target=Path(target).resolve();need(target.is_relative_to(ROOT)and target.suffix.lower()not in{'.tif','.tiff'},'Source write scope escaped');old=target.read_bytes()if target.exists()else None
  if old==raw:return
  i=f'{len(files):03d}';before=OUT/'before'/i/target.name;candidate=OUT/'candidate'/i/target.name;candidate.parent.mkdir(parents=True)
  if old is not None:before.parent.mkdir(parents=True);before.write_bytes(old)
  candidate.write_bytes(raw);files.append({'target':str(target),'role':role,'before':bind(before)if old is not None else None,'candidate':bind(candidate),'changes':changes})
 raw=text.read_bytes();lines=raw.decode('utf-8-sig').splitlines(keepends=True);cells=[{k:e[k]for k in ('row','column','before','after')}for e in proposal['text_edits']];need([(x['row'],x['column'],x['before'],x['after'])for x in cells]==[(11,229,'9','4'),(11,234,'9','4')],'Exact approved cells differ')
 for e in cells:
  r,c=e['row'],e['column'];need(lines[r][c]==e['before'],'Current text cell differs');lines[r]=lines[r][:c]+e['after']+lines[r][c+1:]
 corrected=(b'\xef\xbb\xbf'if raw.startswith(b'\xef\xbb\xbf')else b'')+''.join(lines).encode('utf-8')
 stage(text,corrected,'working accepted TXT',cells);stage(repo_text,corrected,'repository accepted TXT',cells)
 paths=[model,REPO/'json/A1 Socket Listing'/model.name]
 for folder in [ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing',REPO/'json/A1 Socket Listing']:paths +=[folder/'Socket reference.json',folder/'ALD references.json']
 paths.append(ROOT/'tmp/ald-text/a1/references without scan filename.json');json_changes=[]
 for path in paths:
  before=read(path);after,ops=correct_active(before)
  if ops:stage(path,sr.model_bytes(after,path.read_bytes()),'current accepted socket table model'if path in paths[:2]else'current auxiliary reference mirror',ops);json_changes.append({'target':str(path),'changes':ops})
 need({str(p.resolve())for p in paths[:2]}<={x['target']for x in json_changes},'Both real page models must change')
 notes=text.with_name(text.stem+' review notes.txt');message='A1554-01 G5 NATIVE CARD IDENTITY REVIEW 2026-10-17\nThe native 02E-E4 socket G5 header prints 5800514 0514. The former 5800519 0519 transcription misread the final 4 as 9 twice. Native KT752 BJ/BK and KT756 BH/BJ independently read 0514E1/E2/F1/F2 at E-E4G5. Only row11 columns229 and234 and exact active identity mirrors for this socket change. ALD pages, their pins, historical notes and original TIFF are preserved. Independent acceptance and publication are separate receipts.'
 stage(notes,sr.append_note(notes.read_bytes()if notes.exists()else b'',message),'source review notes',[])
 fontpath=ROOT/'tmp/ald-text/JuliaMono-Regular.ttf';font=ImageFont.truetype(str(fontpath),18);cw=round(font.getlength('M'));rows=corrected.decode('utf-8-sig').splitlines();image=Image.new('RGB',(32+max(map(len,rows))*cw,32+len(rows)*25),'white');draw=ImageDraw.Draw(image)
 for y,line in enumerate(rows):draw.text((16,16+y*25),line,font=font,fill='black')
 preview=OUT/'Corrected source preview.png';image.save(preview);stage(text.with_name(text.stem+' preview.png'),preview.read_bytes(),'source preview',[])
 baseline=read(AUDIT/'last export manifest.json');entries=[r for r in baseline['exported']if str(r['source_scan_id'])=='35'];need(len(entries)==1,'Source predecessor ambiguous');entry=entries[0];need(Path(entry['transcription_source']).resolve()==text.resolve(),'Predecessor page differs');prior=Path(entry['review_record']);prior=prior if prior.is_absolute()else ROOT/prior
 predecessor=put(OUT/'Predecessor application proof.json',{'schema':'existing-reviewed-export-predecessor-v1','provenance':bind(REPO/'notes/Reviewed export provenance.json'),'export_entry':entry,'actual_acceptance_record':bind(prior)if prior.is_file()else None,'literal_acceptance_record':entry['review_record'],'current_table_model':bind(model),'preservation_note':'Actual records-table schema and prior acceptance retained. No nodes model/acceptance is invented.'})
 historical=REPO/'notes/A1 Socket Listing'/(name+' review record.json');saved=OUT/'Historical repository proof.json';saved.write_bytes(historical.read_bytes())
 authority=put(OUT/'Resolution authority.json',{'schema':'native-a1-identity-resolution-authority-v1','native_findings':bind(findings),'mechanical_native_binding_verification':bind(HERE/'S component review/Mechanical source binding verification.json'),'record_id':'35:207:10','source':bind(source),'crop':{**bind(crop),'box':finding['source_evidence']['native_crop']['box']},'active_entry_helper':bind(ACTIVE_HELPER),'authority_scope':'Human requested native visual verification and confident source repairs; exact native source reading supported by four ALD blocks. This records source evidence, not a fabricated direct-human glyph answer. No catalogue/module/pseudo-node/CONTINUATION tooling changes are included.'})
 candidate=next(x['candidate']for x in files if Path(x['target'])==model.resolve());stage_doc={'schema':app.STAGE_SCHEMA,'artifact_schema':app.TABLE_QUARTET_SCHEMA,'model_schema':'socket-page-records-v1','page':'A1554-01','board':'02E-E4','source_scan_id':'35','source':bind(source),'human_authority':authority,'source_crop':bind(crop),'source_crops':[bind(crop)],'predecessor_acceptance':predecessor,'historical_repository_acceptance':bind(saved),'historical_repository_original':bind(historical),'exact_meaningful_cell_changes':cells,'trailing_space_padding':[],'files':files,'json_mirror_changes':json_changes,'preparation_script':bind(__file__),'font':bind(fontpath),'predecessor_adapter':bind(ADAPTER),'registry_predecessor':bind(REGISTRY),'registration_helper':bind(REPO/'tools/reviews/register_a1_application.py'),'metadata_preimages':[bind(p)for p in(REPO/'notes/Content data manifest.json',REPO/'notes/Reviewed export provenance.json',AUDIT/'last export manifest.json',REPO/'notes/A1 Socket Listing'/(name+' review notes.txt'),historical)],'published':False,'independent_acceptance_required':True,'model_source_binding':{'mode':'external-stage-binding','model_target':str(model),'model_candidate':candidate,'native_source':bind(source),'accepted_predecessor':predecessor,'note':'True original records table has no source field; retain its schema.'},'post_publication_requirements':['Independent exact scope and native acceptance','Guarded single table publication','Honest records-table successor registration','Scoped current source/repository/provenance verification','Uniform/catalogue derived refresh after all source releases']}
 app.validate_table_model(Path(candidate['path']),stage_doc);manifest=OUT/'Stage manifest.json';put(manifest,stage_doc)
 for f in files:need((sha(f['target'])if Path(f['target']).exists()else None)==(f['before']['sha256']if f['before']else None),'Live source preimage changed')
 report={'passed':True,'published':False,'manifest':bind(manifest),'source_cells':len(cells),'candidate_files':len(files),'active_JSON_fields':sum(len(x['changes'])for x in json_changes),'original_scan_writes':0,'ALD_page_changes':0,'tooling_changes':0};put(OUT/'Preparation assertions.json',report);print(json.dumps(report,indent=2))
if __name__=='__main__':main()

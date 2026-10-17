"""Prepare an honest two-page legacy A1 batch; no canonical writes."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import argparse,hashlib,importlib.util,json,sys
from PIL import Image,ImageDraw,ImageFont
from prepare_A1_BA_proposals import SPECS,entry_patches,need,read,sha,bind
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).resolve().parent;TASK=HERE.parent
AUDIT=ROOT/'tmp/ald-text/ald/repository-export';ADAPTER=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json';REGISTRY=AUDIT/'A1 table application registry.json'
sys.path.insert(0,str(REPO/'tools/reviews'));import source_review as sr

def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(enc(v));return bind(p)
def lookup(root,path):
 parts=path.strip('/').split('/');obj=root
 for key in parts[:-1]:obj=obj[int(key)]if isinstance(obj,list)else obj[key.replace('~1','/').replace('~0','~')]
 return obj,parts[-1]
def apply_patches(d,patches):
 after=deepcopy(d)
 # Array inserts target separate ALD page buckets; no same-bucket ambiguity.
 for p in patches:
  obj,key=lookup(after,p['path']);k=int(key)if isinstance(obj,list)else key
  if p['op']=='replace':need(obj[k]==p['before'],'JSON preimage changed');obj[k]=deepcopy(p['after'])
  else:need(p['op']=='add'and isinstance(obj,list)and obj[k]==p['insert_before_preimage'],'JSON insertion preimage differs');obj.insert(k,deepcopy(p['after']))
 return after

def main():
 cli=argparse.ArgumentParser();cli.add_argument('--output',type=Path,required=True);args=cli.parse_args();out=args.output.resolve();need(out.is_relative_to(ROOT)and not out.exists(),'Fresh private stage required');out.mkdir(parents=True)
 authority=TASK/'Coordinator Group 1 literal review/Coordinator native findings.json';need(authority.exists(),'Coordinator literal review missing');proof=read(HERE/'A1 repeated portion discrepancies/Native source bindings.json');adapter=read(ADAPTER);app_path=REPO/'tools/reviews/register_a1_application.py';files=[];pages=[];stage_docs=[];original_columns=[];fontpath=ROOT/'tmp/ald-text/JuliaMono-Regular.ttf';font=ImageFont.truetype(str(fontpath),18);cw=round(font.getlength('M'))
 def stage(target,raw,role,changes):
  target=Path(target).resolve();need(target.is_relative_to(ROOT)and target.suffix.lower()not in{'.tif','.tiff'},'Target scope escaped');old=target.read_bytes()if target.exists()else None;i=f'{len(files):03d}';before=out/'before'/i/target.name;candidate=out/'candidate'/i/target.name
  if old is not None:before.parent.mkdir(parents=True);before.write_bytes(old)
  candidate.parent.mkdir(parents=True);candidate.write_bytes(raw);item={'target':str(target),'role':role,'before':bind(before)if old is not None else None,'candidate':bind(candidate),'changes':changes};files.append(item);return item
 # Active shared board/reference models; never overwrite historic columns.
 paths=[]
 for spec in SPECS:
  name=spec['page'].split('-')[0]+' BOARD '+spec['board']+'.json'
  for folder in [ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing',REPO/'json/A1 Socket Listing']:paths.extend([folder/name,folder/'Socket reference.json',folder/'ALD references.json'])
 paths.append(ROOT/'tmp/ald-text/a1/references without scan filename.json')
 absent=[]
 for p in dict.fromkeys(paths):
  if not p.exists():absent.append(str(p));continue
  before=read(p);patches=[patch for s in SPECS for patch in entry_patches(before,s)]
  if patches:stage(p,sr.model_bytes(apply_patches(before,patches),p.read_bytes()),'current auxiliary reference mirror',patches)
 for code in ['A1231-01','A1232-01']:
  specs=[s for s in SPECS if s['page']==code];directory=out/'pages'/code;directory.mkdir(parents=True);text=ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing'/(code+' SOCKET LISTING.txt');repo_text=REPO/'ALD/A1 Socket Listing'/text.name;need(not text.with_suffix('.json').exists(),'Do not fabricate or replace a page model');need(text.read_bytes()==repo_text.read_bytes(),'Working/repo source differs');raw=text.read_bytes();rows=raw.decode('utf-8-sig').splitlines(keepends=True);edits=[]
  for s in specs:need(rows[s['row']][s['column']]=='B','TXT token preimage differs');rows[s['row']]=rows[s['row']][:s['column']]+'A'+rows[s['row']][s['column']+1:];edits.append({'row':s['row'],'column':s['column'],'before':'B','after':'A'})
  corrected=(b'\xef\xbb\xbf'if raw.startswith(b'\xef\xbb\xbf')else b'')+''.join(rows).encode('utf-8');need(len(raw)==len(corrected)and sum(a!=b for a,b in zip(raw,corrected))==len(specs),'TXT delta escaped exact source glyphs');own=[stage(text,corrected,'working accepted TXT',edits),stage(repo_text,corrected,'repository accepted TXT',edits)]
  prior=next(x for x in adapter['pages']if x.get('page')==code);need(prior['artifact_schema']=='reviewed-existing-A1-table-and-auxiliary-data-v1','Expected existing legacy table application');put(directory/'Predecessor application item.json',prior)
  columns_link=prior['current_auxiliary_existing_data'][0];columns=Path(columns_link['path']);need(sha(columns)==columns_link['sha256'],'Current accepted column proof stale');d=read(columns);original=deepcopy(d);patches=[]
  for s in specs:
   ci=(s['section_column']-3)//35;starts=[i for i,line in enumerate(d[ci])if line.strip().startswith(s['ALD_page']+' B1 B2')];need(len(starts)==1,'Exact scoped ALD portion group missing');i=starts[0]+1;line=d[ci][i];need(line.strip()==s['line'].strip(),'Current successor row differs');j=line.index('BB');new=line[:j+1]+'A'+line[j+2:];d[ci][i]=new;patches.append({'pointer':f'/{ci}/{i}','before':line,'after':new,'preserve_following_BB':True})
  successor=ROOT/'tmp/ald-text/a1'/(code+' columns card-portion correction 20261016.json');need(not successor.exists(),'Successor proof already exists');own.append(stage(successor,enc(d),'successor columns proof',patches));original_columns.append(bind(columns))
  # Retain both prior successor and original reviewed arrays as immutable inputs.
  original_columns.extend(prior['current_auxiliary_existing_data'][1:]);notes=text.with_name(text.stem+' review notes.txt');note='CARD/PORTION NATIVE REVIEW 2026-10-16\nAt '+', '.join(s['board']+' '+','.join(s['sockets'])+' '+s['ALD_page']for s in specs)+', native source prints BA followed by BB. Only the first misread BB token is corrected to BA. Exact accepted TXT cells, active board/reference mirrors and successor column proof preserve source order; existing BB remains. The older reviewed columns and previous successor columns are preserved unchanged. Acceptance and publication are separately recorded; no native TIFF or historical review is modified.'
  own.append(stage(notes,sr.append_note(notes.read_bytes(),note),'source review notes',[]));lines=corrected.decode('utf-8-sig').splitlines();image=Image.new('RGB',(32+max(map(len,lines))*cw,32+len(lines)*25),'white');draw=ImageDraw.Draw(image)
  for y,line in enumerate(lines):draw.text((16,16+y*25),line,font=font,fill='black')
  preview=directory/'Corrected source preview.png';image.save(preview);own.append(stage(text.with_name(text.stem+' preview.png'),preview.read_bytes(),'source preview',[]))
  native=[next(x for x in proof['cases']if x['record_id']==s['record_id'])for s in specs]
  for n in native:
   need(sha(n['source']['path'])==n['source']['sha256']and sha(n['native_crop']['path'])==n['native_crop']['sha256'],'Native source/crop changed')
   with Image.open(n['source']['path'])as source,Image.open(n['native_crop']['path'])as crop:need(source.convert('RGB').crop(n['native_crop']['box']).tobytes()==crop.convert('RGB').tobytes(),'Native pixels differ')
  crops=[{**n['native_crop'],'source':n['source'],'bounds':n['native_crop']['box']}for n in native];historical=REPO/'notes/A1 Socket Listing'/(code+' SOCKET LISTING review record.json');copy=directory/'Historical repository proof.json';copy.write_bytes(historical.read_bytes())
  page={'page':code,'scan_id':native[0]['record_id'].split(':')[0],'source_relative':str(Path(native[0]['source']['path']).relative_to(Path('D:/Reference Materials/IBM 360/IBM_360_ALD'))),'working_txt':bind(text),'repository_txt':bind(repo_text),'exact_meaningful_cell_changes':edits,'historical_columns':bind(columns)};pages.append(page)
  stage_docs.append((directory/'Stage manifest.json',{'schema':'socket-table-literal-correction-private-stage-v1','artifact_schema':'reviewed-existing-A1-table-and-auxiliary-data-v1','model_schema':'socket-table-columns-v1','page':code,'board':specs[0]['board'],'source_scan_id':page['scan_id'],'source':native[0]['source'],'human_authority':bind(authority),'source_crop':crops[0],'source_crops':crops,'predecessor_acceptance':bind(columns),'predecessor_application_snapshot':bind(directory/'Predecessor application item.json'),'historical_repository_acceptance':bind(copy),'historical_repository_original':bind(historical),'exact_meaningful_cell_changes':edits,'trailing_space_padding':[],'files':own,'published':False,'independent_acceptance_required':True}))
 metadata={REPO/'notes/Content data manifest.json',REPO/'notes/Reviewed export provenance.json',AUDIT/'last export manifest.json'}
 for p in pages:metadata|={REPO/'notes/A1 Socket Listing'/(Path(p['repository_txt']['path']).stem+' review notes.txt'),REPO/'notes/A1 Socket Listing'/(Path(p['repository_txt']['path']).stem+' review record.json')}
 batch={'schema':'socket-reference-batch-application-stage-v1','created_utc':datetime.now(timezone.utc).isoformat(),'preparation_script':bind(Path(__file__)),'publication_script':bind(TASK.parent/'publish_a1_literal_batch.py'),'authority':bind(authority),'registration_helper':bind(app_path),'font':bind(fontpath),'source_bindings':[{'path':app_path.relative_to(REPO).as_posix(),'sha256':sha(app_path)}],'predecessor_adapter':bind(ADAPTER),'registry_predecessor':bind(REGISTRY),'metadata_preimages':[bind(p)for p in sorted(metadata)],'uniform_preimages':[],'uniform_rebuild_deferred':True,'preserved_column_proofs':original_columns,'absent_legacy_paths_no_initialization_proposed':absent,'files':files,'tool_candidates':[],'pages':pages,'counts':{'source_pages':2,'source_tokens':3,'source_cells':3,'candidate_files':len(files)},'source_changes_applied':False,'historical_proof_policy':'No original reviewed array, prior successor array, original TIFF or historical notes/review is overwritten.'}
 manifest=put(out/'Batch manifest.json',batch);stages=[]
 for p,s in stage_docs:s['batch_manifest']=manifest;stages.append(put(p,s))
 put(out/'Prepared page stages.json',{'batch_manifest':manifest,'page_stages':stages,'published':False,'required_independent_acceptance_schema':'socket-reference-batch-independent-acceptance-v1'});print(json.dumps({'manifest':manifest,'page_stages':stages,'targets':len(files),'source_pages':2,'source_cells':3,'canonical_writes':0},indent=2))
if __name__=='__main__':main()

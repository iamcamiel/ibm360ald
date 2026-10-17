"""Read-only release guard and exact one-record uniform semantic comparison."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,sys
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';H=Path(__file__).parent
def need(ok,message):
 if not ok:raise ValueError(message)
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def checked(b):p=Path(b['path']);need(bind(p)['sha256']==b['sha256'],'Stale source release evidence: '+str(p));return p
def verify_semantic_delta(before_path,after_path):
 before=read(before_path);after=read(after_path);need(before.keys()==after.keys(),'Uniform root schema changed')
 expected=deepcopy(before);records=[r for r in expected['records']if r['id']=='35:207:10'];need(len(records)==1,'Exact target record ambiguous');r=records[0]
 need((r['board'],r['sockets'],r['physical_sockets'],r['part_number'],r['card_type'])==('02E-E4',['G5'],['G5'],'5800519','0519'),'Unexpected target record identity')
 r['part_number']='5800514';r['card_type']='0514';literal_changes=[]
 for field in ['source_spans','raw_lines']:
  selected=[(i,s)for i,s in enumerate(r[field])if '5800519 0519'in s.get('literal','')]
  need(len(selected)==1,'Missing or duplicate identity literal in '+field)
  i,s=selected[0];need(s['page']=='A1554-01'and s['scan_id']=='35'and s['row']==11 and s['column']==207,'Identity source span differs');s['literal']=s['literal'].replace('5800519 0519','5800514 0514');literal_changes.append('/records/'+str(expected['records'].index(r))+'/'+field+'/'+str(i)+'/literal')
 need(expected==after,'Other uniform semantic records/fields changed')
 return {'passed':True,'record_id':'35:207:10','exact_physical_site':'02E-E4G5','part_number':{'before':'5800519','after':'5800514'},'card_type':{'before':'0519','after':'0514'},'changed_literals':literal_changes,'other_record_changes':0,'counts_unchanged':before['counts']==after['counts'],'before':bind(before_path),'after':bind(after_path)}
def check_release(receipt_path):
 receipt_path=Path(receipt_path).resolve();need(receipt_path.is_relative_to(ROOT),'Release receipt outside workspace');receipt=read(receipt_path)
 need(receipt.get('schema')=='single-socket-table-addendum-publication-v1'and receipt.get('passed')is True and receipt.get('published')is True and not receipt.get('rolled_back'),'Actual source publication required')
 stage_path=checked(receipt['manifest']);stage=read(stage_path);need(stage.get('page')=='A1554-01'and stage.get('board')=='02E-E4'and stage.get('source_scan_id')=='35','Wrong release page');acceptance_path=checked(receipt['independent_acceptance']);acceptance=read(acceptance_path)
 need(acceptance.get('schema')=='socket-table-literal-correction-independent-acceptance-v1'and acceptance.get('independent_review')is True and acceptance.get('passed')is True and not acceptance.get('failures')and acceptance.get('manifest_sha256')==bind(stage_path)['sha256'],'Exact stage independent acceptance required')
 need([(x['row'],x['column'],x['before'],x['after'])for x in stage['exact_meaningful_cell_changes']]==[(11,229,'9','4'),(11,234,'9','4')],'Source release scope differs');postimages=[]
 for f in stage['files']:
  target=Path(f['target']).resolve();need(target.is_relative_to(ROOT),'Stage target escaped');candidate=checked(f['candidate']);need(target.read_bytes()==candidate.read_bytes(),'Current source release postimage changed');postimages.append(bind(target))
 need(len(postimages)==10,'Source release target scope differs')
 sys.path.insert(0,str(REPO/'tools/reviews'));import register_a1_application as app
 registration=REPO/'tools/reviews/register_a1_application.py';checked(stage['registration_helper'])
 registry=ROOT/'tmp/ald-text/ald/repository-export/A1 table application registry.json';adapter=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json'
 app.validate_registered_applications(registry,adapter,ROOT,ROOT/'ALD_Visual_Transcriptions',Path('D:/Reference Materials/IBM 360/IBM_360_ALD'))
 entries=[x for x in read(registry)['entries']if Path(x['target']).name=='A1554-01 SOCKET LISTING.txt'];need(len(entries)==1,'Registered source release missing/ambiguous')
 # Current matching application is independently checked by the existing
 # registry validator; avoid inferring a legacy publication-field spelling.
 provenance=REPO/'notes/Reviewed export provenance.json';baseline=ROOT/'tmp/ald-text/ald/repository-export/last export manifest.json';need(provenance.read_bytes()==baseline.read_bytes(),'Published/export provenance differs');e=[x for x in read(provenance)['exported']if str(x['source_scan_id'])=='35'];need(len(e)==1,'Source export missing');need(bind(e[0]['transcription_source'])['sha256']==e[0]['text_sha256']==bind(e[0]['destination'])['sha256'],'Accepted source export differs')
 return {'passed':True,'actual_publication':bind(receipt_path),'manifest':bind(stage_path),'independent_acceptance':bind(acceptance_path),'current_postimages':postimages,'current_registry':bind(registry),'current_adapter':bind(adapter),'current_provenance':bind(provenance),'inputs':[bind(receipt_path),bind(stage_path),bind(acceptance_path),bind(__file__),bind(registration)],'portable_evidence_scope':'Compact release receipts, manifests and tool hashes. Full stage before/candidate/current-source objects remain at their bound original paths; published uniform build independently binds accepted TXT inputs.'}

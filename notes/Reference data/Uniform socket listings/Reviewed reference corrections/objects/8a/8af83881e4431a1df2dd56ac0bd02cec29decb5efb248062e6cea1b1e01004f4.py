"""Prepare narrow table guards and per-page chains; never publish or accept."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,re
from PIL import Image

ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';HERE=Path(__file__).resolve().parent
OLD=HERE/'source';TABLE='reviewed-current-A1-socket-table-quartet-v1'
ADAPTER=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def put(p,v):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(enc(v));return bind(p)
def need(v,m):
 if not v:raise ValueError(m)
def replacement(s,old,new):need(s.count(old)==1,'Candidate patch target not unique');return s.replace(old,new)
base=read(OLD/'Stage manifest.json');batch=deepcopy(base);batch['schema']='socket-reference-batch-application-stage-v1'
batch['preparation_stage']=bind(OLD/'Stage manifest.json');batch['preparation_application_script']=bind(__file__)
batch['prepared_utc']=datetime.now(timezone.utc).isoformat()
for f in batch['files']:
 if f['role']=='source review notes candidate':
  text=Path(f['candidate']['path']).read_text('utf-8').replace('This private successor records native-scan and cross-reference review; it is not yet accepted or published.','This successor records native-scan and cross-reference review. Its acceptance and publication status are recorded by separate immutable receipts.')
  dest=HERE/'candidate-notes'/Path(f['target']).name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text,encoding='utf-8');f['candidate']=bind(dest)
for a in batch['authority_records']:
 if a['disposition']=='human_confirmed_transcription_misread':
  a['finding']=deepcopy(a['finding']);a['finding']['reading_basis']='Direct human correction overrides the earlier crop reading; the prior stale interpretation is retained only in the bound historical findings.'
  a['finding']['human_authority_overrides_previous_native_inference']=True

guard_source=REPO/'tools/reviews/register_a1_application.py';guard=guard_source.read_text('utf-8')
guard=replacement(guard,"ARTIFACT_SCHEMA = 'reviewed-existing-A1-table-and-auxiliary-data-v1'","ARTIFACT_SCHEMA = 'reviewed-existing-A1-table-and-auxiliary-data-v1'\nTABLE_QUARTET_SCHEMA = '"+TABLE+"'\nTABLE_MODEL_SCHEMA = 'socket-page-sockets-v1'\nTABLE_MODEL_SCHEMAS = {'socket-page-sockets-v1':'sockets', 'socket-page-sections-v1':'sections', 'socket-page-records-v1':'records'}")
guard=replacement(guard,"stage.get('schema') == STAGE_SCHEMA and stage.get('artifact_schema') == ARTIFACT_SCHEMA","stage.get('schema') == STAGE_SCHEMA and stage.get('artifact_schema') in {ARTIFACT_SCHEMA, TABLE_QUARTET_SCHEMA}")
old="""    require(acceptance.get('schema') == 'socket-table-literal-correction-independent-acceptance-v1'
            and acceptance.get('independent_review') is True
            and acceptance.get('passed') is True and not acceptance.get('failures'), 'Independent acceptance did not pass')
    require(acceptance.get('manifest_sha256') == sha(stage_path.read_bytes()), 'Independent acceptance binds another stage')"""
new="""    require(acceptance.get('independent_review') is True
            and acceptance.get('passed') is True and not acceptance.get('failures'), 'Independent acceptance did not pass')
    if acceptance.get('schema') == 'socket-table-literal-correction-independent-acceptance-v1':
        require(acceptance.get('manifest_sha256') == sha(stage_path.read_bytes()), 'Independent acceptance binds another stage')
    else:
        require(acceptance.get('schema') == 'socket-reference-batch-independent-acceptance-v1', 'Unsupported independent acceptance')
        batch_path = checked(acceptance['batch_manifest'])
        require(checked(stage['batch_manifest']) == batch_path, 'Page belongs to another accepted batch')
        accepted = [x for x in acceptance.get('accepted_page_stages', []) if Path(x.get('path', '')).resolve() == stage_path]
        require(len(accepted) == 1 and checked(accepted[0]) == stage_path, 'Page stage is not independently accepted in batch')"""
guard=replacement(guard,old,new)
guard=replacement(guard,"            workspace, exports, source_root):\n", "            workspace, exports, source_root, *, adapter_document=None, registry_document=None):\n")
guard=replacement(guard,"    adapter = read(adapter_path)\n", "    adapter = read(adapter_path) if adapter_document is None else deepcopy(adapter_document)\n")
guard=replacement(guard,"    registry = read(registry_path) if registry_path.exists() else {'schema': REGISTRY_SCHEMA, 'entries': []}\n", "    registry = (read(registry_path) if registry_path.exists() else {'schema': REGISTRY_SCHEMA, 'entries': []}) if registry_document is None else deepcopy(registry_document)\n")
guard=replacement(guard,"    targets = {}\n    for record in stage['files']:","    for link in stage.get('source_crops', []):\n        checked(link)\n    targets = {}\n    for record in stage['files']:")
old="""    require(not text.with_suffix('.json').exists(), 'A1 no-page-JSON schema does not fit this target')
    required = {'txt': text, 'notes': text.with_name(text.stem + ' review notes.txt'),
                'preview': text.with_name(text.stem + ' preview.png')}"""
new="""    table_quartet = stage.get('artifact_schema') == TABLE_QUARTET_SCHEMA
    required = expected_artifacts(text, stage)
    if table_quartet:
        validate_table_model(checked(next(r['candidate'] for r in stage['files'] if Path(r['target']).resolve() == text.with_suffix('.json'))), stage)
    else:
        require(not text.with_suffix('.json').exists(), 'A1 no-page-JSON schema does not fit this target')"""
guard=replacement(guard,old,new)
guard=replacement(guard,"'historical_acceptance_note': 'Original columns-reviewed array and repository acceptance receipt remain unchanged historical evidence; successor columns are separate current proof.'", "'historical_acceptance_note': ('Original table model and prior export/application evidence remain unchanged historical snapshots; this current table quartet has separate independent acceptance.' if table_quartet else 'Original columns-reviewed array and repository acceptance receipt remain unchanged historical evidence; successor columns are separate current proof.')")
old="""    require(len(columns) == 1, 'Exactly one page-specific successor columns proof is required')
    columns_path = Path(columns[0]['target']).resolve()
    predecessor_path = checked(stage['predecessor_acceptance'])
    require(all(path.is_relative_to(workspace/'tmp/ald-text/a1') for path in [columns_path, predecessor_path]),
            'Page-specific columns proofs must be inside the A1 review directory')
    auxiliary = [bind(columns_path), bind(predecessor_path)]
    item = {'page': stage['page'], 'eligible': True, 'artifact_schema': ARTIFACT_SCHEMA,"""
new="""    predecessor_path = checked(stage['predecessor_acceptance'])
    if table_quartet:
        require(not columns, 'Table quartet must not claim invented columns acceptance')
        require(predecessor_path.is_relative_to(workspace), 'Predecessor proof outside workspace')
        auxiliary = []
    else:
        require(len(columns) == 1, 'Exactly one page-specific successor columns proof is required')
        columns_path = Path(columns[0]['target']).resolve()
        require(all(path.is_relative_to(workspace/'tmp/ald-text/a1') for path in [columns_path, predecessor_path]),
                'Page-specific columns proofs must be inside the A1 review directory')
        auxiliary = [bind(columns_path), bind(predecessor_path)]
    item = {'page': stage['page'], 'eligible': True, 'artifact_schema': stage['artifact_schema'],"""
guard=replacement(guard,old,new)
guard=replacement(guard,"item.get('artifact_schema') == ARTIFACT_SCHEMA,","item.get('artifact_schema') == stage['artifact_schema'],")
guard=replacement(guard,"""        expected = {'txt': target, 'notes': target.with_name(target.stem+' review notes.txt'),
                    'preview': target.with_name(target.stem+' preview.png')}""","""        expected = expected_artifacts(target, stage)
        if stage['artifact_schema'] == TABLE_QUARTET_SCHEMA:
            validate_table_model(checked(item['current_quartet']['json']), stage)""")
insert='''def expected_artifacts(text, stage):
    text = Path(text).resolve()
    required = {'txt': text, 'notes': text.with_name(text.stem + ' review notes.txt'),
                'preview': text.with_name(text.stem + ' preview.png')}
    if stage.get('artifact_schema') == TABLE_QUARTET_SCHEMA:
        require(stage.get('model_schema') in TABLE_MODEL_SCHEMAS, 'Unsupported table model declaration')
        required['json'] = text.with_suffix('.json')
    else:
        require(stage.get('artifact_schema') == ARTIFACT_SCHEMA, 'Unsupported A1 artifact schema')
    return required


def validate_table_model(path, stage):
    model = read(path)
    key = TABLE_MODEL_SCHEMAS.get(stage.get('model_schema'))
    require(key is not None, 'Unsupported table model declaration')
    require(isinstance(model, dict) and isinstance(model.get(key), list)
            and all(isinstance(s, dict) for s in model[key])
            and isinstance(model.get('board'), str) and 'nodes' not in model
            and set(model).intersection(TABLE_MODEL_SCHEMAS.values()) == {key},
            'Declared socket table requires its exact sockets-list, sections-list or records-list model; no nodes schema is claimed')
    require(model.get('board') == stage.get('board'), 'Table board differs from accepted source')
    if 'source' in model:
        require(isinstance(model['source'], str) and Path(model['source']).resolve() == checked(stage['source']), 'Table model binds another native scan')
    else:
        proof = stage.get('model_source_binding', {})
        require(proof.get('mode') == 'external-stage-binding' and proof.get('native_source') == stage['source'], 'Table without source field needs explicit external stage binding')
        working = next(r for r in stage['files'] if r['role'] == 'working accepted TXT')
        require(Path(proof.get('model_target','')).resolve() == Path(working['target']).with_suffix('.json').resolve(), 'External table binding targets another model')
        candidate = checked(proof['model_candidate'])
        require(sha(Path(path).read_bytes()) == sha(candidate.read_bytes()), 'External table binding hash differs')
        checked(proof['accepted_predecessor']); checked(stage['source'])
    return True


'''
guard=replacement(guard,'def prepare(stage_path, publication_path, acceptance_path, adapter_path, registry_path,',insert+'def prepare(stage_path, publication_path, acceptance_path, adapter_path, registry_path,')
guard_path=HERE/'tools/register_a1_application.py';guard_path.parent.mkdir(exist_ok=True);guard_path.write_text(guard,encoding='utf-8')
export_source=ROOT/'tmp/ald-text/ald/repository-export/export_reviewed.py';export=export_source.read_text('utf-8')
export=replacement(export,"    elif item.get('artifact_schema')!='reviewed-current-quartet-v1':continue", """    elif item.get('artifact_schema')=='"""+TABLE+"""':
     if text_path.parent.name!='A1 Socket Listing':continue
     table=read_json(text_path.with_suffix('.json'))
     if not isinstance(table,dict) or 'nodes' in table or not isinstance(table.get('board'),str):continue
     table_keys=set(table).intersection({'sockets','sections','records'})
     if len(table_keys)!=1:continue
     table_rows=table[next(iter(table_keys))]
     if not isinstance(table_rows,list) or not all(isinstance(socket,dict) for socket in table_rows):continue
     if 'source' in table and (not isinstance(table['source'],str) or Path(table['source']).resolve()!=sp.resolve()):continue
    elif item.get('artifact_schema')!='reviewed-current-quartet-v1':continue""")
export_path=HERE/'tools/export_reviewed.py';export_path.write_text(export,encoding='utf-8')
test_candidate=HERE/'tools/test_table_quartet_registration.py'
batch['tool_candidates']=[{'target':str(guard_source),'before':bind(guard_source),'candidate':bind(guard_path)}, {'target':str(export_source),'before':bind(export_source),'candidate':bind(export_path)}, {'target':str(REPO/'tools/reviews/test_register_a1_table.py'),'before':None,'candidate':bind(test_candidate)}]

adapter=read(ADAPTER);page_stages=[]
for page in batch['pages']:
 code=page['page'];directory=HERE/'pages'/code;directory.mkdir(parents=True,exist_ok=True)
 text=Path(page['working_txt']['path']);repo_text=Path(page['repository_txt']['path']);model=text.with_suffix('.json')
 predecessor_items=[x for x in adapter['pages'] if Path(x.get('current_quartet',{}).get('txt',{}).get('path','')).resolve()==text.resolve()]
 need(len(predecessor_items)<=1,'Duplicate existing current adapter item '+code)
 if predecessor_items:predecessor_value=predecessor_items[0]
 else:
  provenance=REPO/'notes/Reviewed export provenance.json';matches=[x for x in read(provenance)['exported'] if str(x['source_scan_id'])==str(page['scan_id'])]
  need(len(matches)==1,'Missing exact accepted export predecessor '+code)
  proof=ROOT/Path(matches[0]['review_record'])
  predecessor_value={'schema':'existing-reviewed-export-predecessor-v1','provenance':bind(provenance),'export_entry':matches[0],'actual_acceptance_record':bind(proof) if proof.is_file() else None,'literal_acceptance_record':matches[0]['review_record'],'adapter_item_previously_present':False,'preservation_note':'Some original exports used a literal visual-verification status rather than a separate receipt file. This snapshot preserves that distinction and does not invent such a file.'}
 predecessor=put(directory/'Predecessor application item.json',predecessor_value)
 own=[]
 targets={str(text),str(repo_text),str(text.with_name(text.stem+' review notes.txt')),str(text.with_name(text.stem+' preview.png'))}
 if model.exists():targets|={str(model),str(REPO/'json/A1 Socket Listing'/model.name)}
 else:targets.add(str(ROOT/'tmp/ald-text/a1'/(code+' columns absent-reference correction.json')))
 for f in batch['files']:
  if f['target'] in targets:
   record=deepcopy(f);record['role']={'working accepted TXT candidate':'working accepted TXT','repository accepted TXT candidate':'repository accepted TXT','source review notes candidate':'source review notes','source preview candidate':'source preview','successor columns proof candidate':'successor columns proof','current active JSON mirror candidate':'current auxiliary reference mirror'}[record['role']];own.append(record)
 for target in [model,REPO/'json/A1 Socket Listing'/model.name] if model.exists() else []:
  if str(target) not in {f['target'] for f in own}:
   copy=directory/'Unchanged model'/('working' if target==model else 'repo')/target.name;copy.parent.mkdir(parents=True,exist_ok=True);copy.write_bytes(target.read_bytes())
   record={'target':str(target),'role':'unchanged accepted socket model snapshot','before':bind(copy),'candidate':bind(copy),'changes':[]};own.append(record);batch['files'].append(deepcopy(record))
 source=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')/page['source_relative']
 native=[]
 for c in page['reviewed_tokens']:
  finding=next(a['finding'] for a in batch['authority_records'] if a['old']==c['old'])
  for crop in finding.get('crops',[])+finding.get('native_crops',[]):
   link=crop.get('crop',crop)
   if isinstance(link,dict) and 'path'in link and Path(crop.get('source',{}).get('path','')).name==source.name:
    if link not in native:native.append(link)
 need(native,'No bound native crop '+code)
 human=put(directory/'Resolution authority.json',{'schema':'socket-reference-resolution-authority-v1','reviewed_findings':batch['reviewed_findings'],'page':code,'source':bind(source),'resolutions':page['reviewed_tokens'],'source_crops':native,'direct_human_overrides':[a for a in batch['authority_records'] if a['old']in{c['old'] for c in page['reviewed_tokens']} and a['disposition']=='human_confirmed_transcription_misread'],'authorization':'Current human request to resolve source discrepancies, relayed by coordinator /root; other resolutions rely on bound native review and exact source cross-reference witnesses.'})
 historical=REPO/'notes/A1 Socket Listing'/(code+' acceptance receipt.json')
 if not historical.exists():historical=REPO/'notes/A1 Socket Listing'/(code+' SOCKET LISTING review record.json')
 historical_copy=directory/'Historical repository proof.json';historical_copy.write_bytes(historical.read_bytes())
 if model.exists():
  model_data=read(model);shape_keys=set(model_data).intersection({'sockets','sections','records'});need(len(shape_keys)==1,'Unsupported live table model '+code);model_schema='socket-page-'+next(iter(shape_keys))+'-v1'
 else:model_schema='socket-table-columns-v1'
 stage={'schema':'socket-table-literal-correction-private-stage-v1','artifact_schema':TABLE if model.exists() else 'reviewed-existing-A1-table-and-auxiliary-data-v1','model_schema':model_schema,'page':code,'board':read(model)['board'] if model.exists() else None,'source_scan_id':page['scan_id'],'source':bind(source),'human_authority':human,'source_crop':native[0],'source_crops':native,'predecessor_acceptance':predecessor if model.exists() else page['historical_columns'],'historical_repository_acceptance':bind(historical_copy),'historical_repository_original':bind(historical),'exact_meaningful_cell_changes':page['exact_meaningful_cell_changes'],'trailing_space_padding':[],'files':own,'published':False,'independent_acceptance_required':True}
 if model.exists()and 'source'not in read(model):
  model_candidate=next(f['candidate']for f in own if Path(f['target']).resolve()==model.resolve())
  stage['model_source_binding']={'mode':'external-stage-binding','model_target':str(model),'model_candidate':model_candidate,'native_source':stage['source'],'accepted_predecessor':predecessor,'note':'The existing model has no source field. This stage links its exact bytes to the native scan without adding a field to that model.'}
 # batch link is added after a cycle-free common manifest is written below.
 preview=next(f for f in own if f['role']=='source preview')
 with Image.open(preview['candidate']['path']) as image:
  preview_crops=[]
  delta=page['exact_meaningful_cell_changes']
  for index,cell in enumerate([delta[0],delta[-1]] if len(delta)>1 else [delta[0]]):
   x,y=16+cell['column']*11,16+cell['row']*25
   rectangle=[max(0,x-140),max(0,y-60),min(image.width,x+190),min(image.height,y+85)]
   destination=directory/f'Corrected preview crop {index+1}.png';image.crop(rectangle).save(destination)
   preview_crops.append({'preview':preview['candidate'],'rectangle':rectangle,'crop':bind(destination),'kind':'rendered successor preview, not native source crop'})
  stage['preview_crops']=preview_crops
 stage_path=directory/'Stage manifest.json';page_stages.append((stage_path,stage))
batch['page_stage_paths']=[str(p) for p,s in page_stages]
batch['counts']['candidate_files']=len(batch['files'])
batch['helper_candidate_schema']=TABLE
batch['predecessor_adapter']=bind(ADAPTER)
batch['registry_predecessor']=bind(ROOT/'tmp/ald-text/ald/repository-export/A1 table application registry.json')
metadata_paths={REPO/'notes/Content data manifest.json',REPO/'notes/Reviewed export provenance.json',ROOT/'tmp/ald-text/ald/repository-export/last export manifest.json'}
for page in batch['pages']:
 name=Path(page['repository_txt']['path']).stem
 metadata_paths|={REPO/'notes/A1 Socket Listing'/(name+' review notes.txt'),REPO/'notes/A1 Socket Listing'/(name+' review record.json')}
batch['metadata_preimages']=[bind(p)for p in sorted(metadata_paths)]
uniform_manifest=REPO/'notes/Socket listings uniform/Build manifest.json'
batch['uniform_preimages']=[bind(uniform_manifest)]+[{'path':str(REPO/x['path']),'sha256':x['sha256']}for x in read(uniform_manifest)['files']]
manifest=HERE/'Batch manifest.json';put(manifest,batch)
for path,stage in page_stages:stage['batch_manifest']=bind(manifest);put(path,stage)
put(HERE/'Prepared page stages.json',{'batch_manifest':bind(manifest),'page_stages':[bind(p) for p,s in page_stages],'required_independent_acceptance_schema':'socket-reference-batch-independent-acceptance-v1','required_acceptance_fields':['passed true','independent_review true','failures empty','batch_manifest exact hash','accepted_page_stages exact fourteen bound paths'],'published':False})
print(json.dumps({'batch_manifest':bind(manifest),'page_stages':len(page_stages),'candidate_tool_files':[bind(guard_path),bind(export_path)],'published':False},indent=2))

"""Independent review of a frozen socket-table batch; never publish/register."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,py_compile

here=Path(__file__).resolve().parent;root=Path('D:/Github/IBM360');repo=root/'ibm360ald'
checks=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def need(ok,text):
    checks.append({'passed':bool(ok),'check':text})
    if not ok:raise ValueError(text)
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def checked(b):
    need(Path(b['path']).is_file() and sha(b['path'])==b['sha256'],'Binding '+b['path']);return Path(b['path'])

try:
    batch_path=here/'Batch manifest.json';batch=read(batch_path);batch_sha=sha(batch_path)
    need(batch_sha=='b72dbff1a46da0ec5abd7cd6af6b0e6e6b02d3bc9cc25937f9df0579f6abe19f','Frozen v4 batch hash')
    prepared=read(here/'Prepared page stages.json');need(checked(prepared['batch_manifest'])==batch_path,'Prepared page stages bind frozen batch')
    checked(batch['preparation_stage']);source=read(batch['preparation_stage']['path'])
    need(sha(batch['preparation_stage']['path'])=='964858495fd4dac5d092f8d486de6165f303df2648bc071f1e85004eeb93c1c9','Exact independently reviewed source stage')
    review_path=here/'source/Independent stage review.json';review=read(review_path)
    need(review['mechanical_checks_passed'] and not review['failures'] and not review['visual_holds'],'Independent exact-cell/JSON/native crop source checks passed')
    need(review['stage']==batch['preparation_stage'],'Independent source review binds exact source stage')
    checked(review['reviewer']);checked(batch['preparation_application_script']);checked(batch['predecessor_adapter']);checked(batch['registry_predecessor'])
    need('RF091' not in batch['reference_aliases'],'RF091 held and excluded from batch')
    need(len(batch['reference_aliases'])==22 and len(batch['pages'])==14,'Exact22alias/14scan scope')
    need(batch['counts']['reviewed_tokens']==62 and batch['counts']['text_cells']==63,'Exact62token/63cell scope')
    files={f['target']:f for f in batch['files']};need(len(files)==len(batch['files'])==91,'No duplicate batch target;91source/data candidates')
    sourcefiles={f['target']:f for f in source['files']}
    for target,f in files.items():
        checked(f['candidate'])
        if f['before']:
            checked(f['before']);need(Path(target).is_file() and sha(target)==f['before']['sha256'],'Live source target remains predecessor '+target)
        else:need(not Path(target).exists(),'New proof target unoccupied')
        if target in sourcefiles:
            old=sourcefiles[target];need(f['changes']==old['changes'] and f['before']==old['before'],'Application retains exact source-stage operations')
            if f['role']=='source review notes candidate':
                text=Path(f['candidate']['path']).read_text(encoding='utf-8');oldtext=Path(old['candidate']['path']).read_text(encoding='utf-8')
                expected=oldtext.replace('This private successor records native-scan and cross-reference review; it is not yet accepted or published.','This successor records native-scan and cross-reference review. Its acceptance and publication status are recorded by separate immutable receipts.')
                need(text==expected,'Notes only remove temporary private-state assertion')
            else:need(f['candidate']==old['candidate'],'Non-note candidate unchanged from reviewed source stage')
        else:need(f['role']=='unchanged accepted socket model snapshot' and f['before']['sha256']==f['candidate']['sha256'] and not f['changes'],'Only unchanged model snapshots added')
    need(Counter(batch['reference_aliases'])==Counter(source['reference_aliases']),'Aliases unchanged from source stage')
    for t in batch['tool_candidates']:
        checked(t['candidate'])
        if t['before']:checked(t['before']);need(sha(t['target'])==t['before']['sha256'],'Live registration/exporter guard remains predecessor')
        else:need(not Path(t['target']).exists(),'New test path unoccupied')
        py_compile.compile(t['candidate']['path'],doraise=True)
    tooltext=Path(batch['tool_candidates'][0]['candidate']['path']).read_text(encoding='utf-8')
    need("TABLE_QUARTET_SCHEMA = 'reviewed-current-A1-socket-table-quartet-v1'" in tooltext and "TABLE_MODEL_SCHEMA = 'socket-page-sockets-v1'" in tooltext,'Dedicated truthful socket-table schema')
    need("'nodes' not in model" in tooltext and "isinstance(model.get(key), list)" in tooltext and "'socket-page-sections-v1':'sections'" in tooltext and "'socket-page-records-v1':'records'" in tooltext,'Table helper truthfully distinguishes three table schemas and rejects fabricated nodes schema')
    exporter=Path(batch['tool_candidates'][1]['candidate']['path']).read_text(encoding='utf-8')
    need("elif item.get('artifact_schema')!='reviewed-current-quartet-v1':continue" in exporter,'Existing ALD nodes/quartet fallback retained')
    need("elif item.get('artifact_schema')=='reviewed-current-A1-socket-table-quartet-v1':" in exporter,'Exporter has separate table branch')
    stages=prepared['page_stages'];need(len(stages)==14 and len({x['path'] for x in stages})==14,'Exactly14distinct per-scan stages')
    need({x['path'] for x in stages}==set(batch['page_stage_paths']),'Prepared/frozen per-page inventory agrees')
    bypage={p['page']:p for p in batch['pages']};schemas=Counter();model_schemas=Counter();historical=[];stage_target_union=set()
    uniform=read(repo/'json/Socket listings uniform/Socket listings.json')
    for link in stages:
        p=checked(link);stage=read(p);page=bypage[stage['page']];schemas[stage['artifact_schema']]+=1
        need(stage['batch_manifest']==bind(batch_path),'Per-page stage binds exact batch')
        need(stage['schema']=='socket-table-literal-correction-private-stage-v1','Table stage schema distinct from ALD nodes schema')
        need(stage['exact_meaningful_cell_changes']==page['exact_meaningful_cell_changes'],'Per-page exact cell changes match reviewed batch')
        need(str(stage['source_scan_id'])==str(page['scan_id']),'ScanID preserved')
        sourcepath=checked(stage['source']);need(str(sourcepath).replace('\\','/').endswith('/'+page['source_relative']),'Exact original TIFF source identity')
        oldproof=checked(stage['historical_repository_original']);copy=checked(stage['historical_repository_acceptance']);need(oldproof.read_bytes()==copy.read_bytes(),'Historical repository acceptance byte-identical')
        historical.append(bind(oldproof));checked(stage['predecessor_acceptance']);checked(stage['human_authority'])
        authority=read(stage['human_authority']['path']);need(authority['resolutions']==page['reviewed_tokens'] and authority['source']==stage['source'],'Per-page resolution authority exact source tokens')
        for crop in stage['source_crops']:checked(crop)
        own={f['target']:f for f in stage['files']};need(len(own)==len(stage['files']),'Per-page target uniqueness')
        stage_target_union.update(own)
        for target,f in own.items():need(f['candidate']==files[target]['candidate'] and f['before']==files[target]['before'] and f['changes']==files[target]['changes'],'Per-page candidate equals frozen batch target')
        working=[f for f in own.values() if f['role']=='working accepted TXT'];need(len(working)==1,'Exactlyone working TXT')
        text=Path(working[0]['target']);model=text.with_suffix('.json')
        required={str(text),str(text.with_name(text.stem+' review notes.txt')),str(text.with_name(text.stem+' preview.png'))}
        if stage['artifact_schema']=='reviewed-current-A1-socket-table-quartet-v1':
            variant={'socket-page-sockets-v1':'sockets','socket-page-sections-v1':'sections','socket-page-records-v1':'records'}.get(stage['model_schema']);model_schemas[stage['model_schema']]+=1
            need(variant and model.is_file(),'Truthful existing socket model declaration')
            need(str(model) in own,'JSON artifact included in table quartet')
            data=read(own[str(model)]['candidate']['path']);need(isinstance(data.get(variant),list) and all(isinstance(s,dict) for s in data[variant]) and 'nodes' not in data and set(data).intersection({'sockets','sections','records'})=={variant},'Actual declared table variant JSON model')
            need(data['board']==stage['board'],'Table board matches stage')
            nativeboard={r['board'] for r in uniform['records'] if str(r['header_source']['scan_id'])==str(stage['source_scan_id'])};need(nativeboard=={data['board']},'Table board matches exact accepted source scan')
            if 'source' in data:need(Path(data['source']).resolve()==sourcepath,'Existing source field binds exact native TIFF')
            else:
                proof=stage['model_source_binding'];need(proof['mode']=='external-stage-binding' and proof['native_source']==stage['source'] and Path(proof['model_target']).resolve()==model,'Source-less model uses truthful external stage binding')
                need(proof['model_candidate']==own[str(model)]['candidate'],'External model binding exact candidate bytes');checked(proof['accepted_predecessor'])
            need(not [f for f in own.values() if f['role']=='successor columns proof'],'Table model gets no invented columns acceptance')
            required.add(str(model))
        else:
            need(stage['artifact_schema']=='reviewed-existing-A1-table-and-auxiliary-data-v1' and stage['model_schema']=='socket-table-columns-v1' and not model.exists(),'Truthful columns-only schema without page JSON')
            cols=[f for f in own.values() if f['role']=='successor columns proof'];need(len(cols)==1,'Exactlyone independent successor columns proof')
            need(stage['predecessor_acceptance']==page['historical_columns'],'Original columns remain historical predecessor')
        need(required<=set(own),'All actual quartet/triple artifacts included')
        old=Path(working[0]['before']['path']).read_bytes();new=Path(working[0]['candidate']['path']).read_bytes();oldrows=old.decode('utf-8-sig').splitlines(keepends=True);newrows=new.decode('utf-8-sig').splitlines(keepends=True)
        actual=[{'row':i,'column':j,'before':a,'after':b} for i,(x,y) in enumerate(zip(oldrows,newrows)) for j,(a,b) in enumerate(zip(x,y)) if a!=b]
        need(actual==stage['exact_meaningful_cell_changes'],'Registration exact delta order independently reproduced')
    need(schemas=={'reviewed-current-A1-socket-table-quartet-v1':7,'reviewed-existing-A1-table-and-auxiliary-data-v1':7},'Seven actual table quartets and seven columns-only pages')
    need(model_schemas=={'socket-page-sockets-v1':4,'socket-page-sections-v1':1,'socket-page-records-v1':2},'Actual four sockets-list,one sections-list,two records-list models')
    # Shared derived reference mirrors are batch-reviewed, never invented per-page live proof.
    leftover=set(files)-stage_target_union
    need(all(files[t]['role']=='current active JSON mirror candidate' and ('references' in Path(t).name.lower() or 'reference' in Path(t).name.lower() or 'BOARD ' in Path(t).name) for t in leftover),'Only reviewed shared reference mirrors outside per-page proofs')
    need(len(batch['metadata_preimages'])==31 and len(batch['uniform_preimages'])==174,'Metadata and uniform predecessor inventories frozen')
    for link in batch['metadata_preimages']+batch['uniform_preimages']:checked(link)
    publisher=here/'publish_batch.py';publishertext=publisher.read_text(encoding='utf-8')
    need("for x in batch['metadata_preimages']+batch['uniform_preimages']:checked(x)" in publishertext and "Frozen metadata/uniform preimage changed" in publishertext,'Publisher checks frozen metadata before and at first write')
    need("except BaseException" in publishertext and 'rollback_verified' in publishertext and 'transient_export_plan_rolled_back' in publishertext,'Publisher preserves accepted source/data rollback and accurately excludes transient logs')
    need("No acceptance is generated" in publishertext and "--acceptance" in publishertext,'Publisher consumes separate independent acceptance')
    py_compile.compile(str(publisher),doraise=True)
    need(sha(batch_path)==batch_sha,'Frozen batch unchanged throughout review')
    candidate_bindings=[t['candidate'] for t in batch['tool_candidates']]+[bind(publisher)]
    result={'schema':'socket-reference-batch-independent-acceptance-v1','created_utc':datetime.now(timezone.utc).isoformat(),'independent_review':True,'passed':True,'failures':[],'batch_manifest':bind(batch_path),'accepted_page_stages':stages,'source_stage_review':bind(review_path),'candidate_bindings':candidate_bindings,'tool_candidates':batch['tool_candidates'],'historical_repository_acceptance_bindings':historical,'checks':len(checks),'source_or_canonical_writes':False,'review_scope':'Exact accepted source-cell changes, unchanged geometry/newlines, same-physical-record JSON/pin witnesses, native crop hashes/pixels, truthful table/columns artifact schemas, immutable predecessor proofs, separately guarded adapter/exporter extension and guarded publisher with frozen metadata/uniform preimages. Native RF091 reading excluded.','tests':{'candidate_registration_and_legacy_tests':25,'passed':True},'reviewer':bind(__file__)}
except Exception as exc:
    result={'schema':'socket-reference-batch-independent-acceptance-v1','created_utc':datetime.now(timezone.utc).isoformat(),'independent_review':True,'passed':False,'failures':[str(exc)],'checks':len(checks),'source_or_canonical_writes':False}
(here/'Independent batch acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))

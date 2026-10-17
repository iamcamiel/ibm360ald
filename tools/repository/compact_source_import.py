"""Mirror one newly published reviewed stage into a compact current repository.

No successor registry, old export plan, prior receipt tree, preview copy or
permanent predecessor archive is used. Dry-run preparation is read-only.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reviews'))
import source_review as sr
import current_checkpoint as checkpoint_api
import compact_metadata
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'normalization'))
import read_page as page_reader
from pages import renormalize_page

CONTENT='notes/Content data manifest.json'
PROVENANCE='notes/Reviewed export provenance.json'
INVENTORY='notes/Repository records manifest.json'


def safe_target(repo,relative):
    candidate=repo/checkpoint_api.relative(relative)
    resolved=candidate.resolve()
    sr.require(resolved.is_relative_to(repo) and resolved==candidate.absolute(),'Compact import target aliases another path: '+relative)
    return resolved


def _index(items):
    sr.require(isinstance(items,list),'Current manifest file list missing')
    result={}
    for item in items:
        sr.require(isinstance(item,dict),'Invalid current manifest entry')
        key=checkpoint_api.relative(item.get('path'))
        sr.require(key not in result,'Duplicate current manifest entry');result[key]=item
    return result


def _notes_after(after_model,existing,patches,new_note=None):
    if isinstance(new_note,str) and new_note.strip():existing=existing+'\n'+new_note
    clean,notes=compact_metadata.prune_history(after_model,existing_notes=existing)
    # Pointer questions describe current fields, not a permanent question log.
    # Keep free-form uncertainty conservatively, but drop answered/removed fields.
    def current_unresolved(value,key=''):
        if isinstance(value,str):return '\ufffd' in value
        if value is True:return key=='unresolved' or key.endswith('_unresolved') or key in ('source_unknown_pin',)
        if isinstance(value,dict):return any(current_unresolved(v,k)for k,v in value.items())
        if isinstance(value,list):return any(current_unresolved(v)for v in value)
        return False
    def keep_question(item):
        pointer=item.get('field')if isinstance(item,dict)else None
        if not isinstance(pointer,str)or not pointer.startswith('/'):return True
        try:
            parts=sr.pointer_parts(pointer);value=clean
            for part in parts:
                if isinstance(value,list):
                    if not part.isdigit()or str(int(part))!=part:return False
                    value=value[int(part)]
                else:value=value[part]
            return current_unresolved(value,parts[-1])
        except (ValueError,KeyError,IndexError,TypeError):return False
    notes['unresolved']=[item for item in notes['unresolved']if keep_question(item)]
    for line in existing.splitlines():
        prefix,sep,body=line.partition(':')
        key={'Correction':'significant_literal_corrections','Exception':'exceptions','Unresolved':'unresolved'}.get(prefix)
        if key and sep:
            try:item=json.loads(body)
            except json.JSONDecodeError:item={'note':body.strip()}
            if key=='unresolved'and not keep_question(item):continue
            if item not in notes[key]:notes[key].append(item)
    def unreadable_fields(value,pointer=''):
        if isinstance(value,str)and '\ufffd'in value:
            if not any(isinstance(item,dict)and item.get('field')==pointer for item in notes['unresolved']):
                notes['unresolved'].append({'field':pointer,'status':'unreadable current literal retained'})
        elif isinstance(value,dict):
            for key,child in value.items():unreadable_fields(child,pointer+'/'+key.replace('~','~0').replace('/','~1'))
        elif isinstance(value,list):
            for index,child in enumerate(value):unreadable_fields(child,pointer+'/'+str(index))
    unreadable_fields(clean)
    for patch in patches:
        before,after=patch.get('before'),patch.get('after')
        if all(v is None or type(v)in(bool,int,float,str)for v in (before,after)) and sr.json_equal(before,after) is False:
            if any(isinstance(v,str)and len(v)>320 for v in (before,after)):continue
            item={'field':patch['pointer'],'before':deepcopy(before),'after':deepcopy(after)}
            if item not in notes['significant_literal_corrections']:notes['significant_literal_corrections'].append(item)
    return clean,compact_metadata.render_compact_notes(notes).encode('utf-8')


def _publication(manifest_path,acceptance_path):
    manifest=sr.read_json(manifest_path)
    sr.require(manifest.get('schema')==sr.STAGE,'Compact import requires a new declarative generic stage')
    accepted=sr.acceptance_document(acceptance_path,manifest_path,[r['page']for r in manifest['records']])
    sr.require(accepted.get('schema')=='source-review-independent-acceptance-v1','Generic independent acceptance required')
    sr.verify_stage(manifest_path,'published',acceptance_path)
    pubpath=manifest_path.parent/'publication.json';pub=sr.read_json(pubpath)
    sr.require(pub.get('schema')=='source-review-publication-v1' and pub.get('passed')is True and pub.get('original_scan_writes')==0,'Successful published current stage required')
    sr.require(pub.get('review_id')==manifest['review_id'] and pub.get('published_pages')==[r['page']for r in manifest['records']],'Publication page/review identity differs')
    mp,_=sr.checked(pub['manifest'],pubpath.parent)
    ap,_=sr.checked(pub['independent_acceptance'],pubpath.parent)
    sr.require(mp==manifest_path and sr.digest(ap.read_bytes())==sr.digest(acceptance_path.read_bytes()),'Publication binds different stage/acceptance')
    expected=[]
    for record in manifest['records']:
        expected.append({'page':record['page'],'eligible':True,'artifact_schema':'reviewed-current-quartet-v1',
            'source':deepcopy(record['source']),'current_quartet':{kind:{'path':str(sr.resolve(record['prior_quartet'][kind]['path'],manifest_path.parent)),
                'sha256':record['staged_quartet'][kind]['sha256']}for kind in sorted(sr.KINDS)},
            'checks':{'source_binding':True,'exact_declarative_replay':True,'independent_acceptance':True,'current_quartet':True}})
    sr.require(sr.json_equal(pub.get('pages'),expected),'Publication current artifact claims differ')
    return manifest,pubpath


def prepare(repo,manifest_path,acceptance_path,source_root):
    repo,manifest_path,acceptance_path,source_root=map(lambda p:Path(p).resolve(),(repo,manifest_path,acceptance_path,source_root))
    sr.require(not manifest_path.is_relative_to(repo),'Review stage must be outside the repository')
    guards={};changes={};roles={}
    def capture(path,expected=None):
        path=Path(path);raw=path.read_bytes()if path.is_file()else None
        actual=None if raw is None else sr.digest(raw)
        if expected is not None:sr.require(actual==expected,'Compact import input binding changed: '+str(path))
        sr.require(path not in guards or guards[path]==actual,'Input changed while preparing compact import')
        guards[path]=actual;return raw
    def put(relative,raw,role):
        path=safe_target(repo,relative);capture(path)
        sr.require(path not in changes or changes[path]==raw,'Conflicting compact import target')
        changes[path]=raw;roles[path]=role
    inventory_path=safe_target(repo,INVENTORY);inventory=checkpoint_api.read_json(capture(inventory_path))
    inventory_entries=_index(inventory['files'])
    checkpoint=checkpoint_api.load_checkpoint(repo,inventory=inventory)
    for relative,expected,resolved in checkpoint._guards:capture(safe_target(repo,relative),expected)
    doc=deepcopy(checkpoint.document)
    globals={}
    for relative in (CONTENT,PROVENANCE):
        sr.require(relative in inventory_entries,'Current compatibility manifest is not inventoried')
        globals[relative]=checkpoint_api.read_json(capture(safe_target(repo,relative),inventory_entries[relative]['sha256']))
    content=globals[CONTENT];provenance=globals[PROVENANCE];content_entries=_index(content['files'])
    old_content,old_provenance=deepcopy(content),deepcopy(provenance)
    manifest,pubpath=_publication(manifest_path,acceptance_path)
    for path in (manifest_path,acceptance_path,pubpath,Path(compact_metadata.__file__).resolve()):capture(path)
    selected=set();summaries=[]
    for record in manifest['records']:
        source=sr.resolve(record['source']['path'],manifest_path.parent)
        sr.require(source.is_relative_to(source_root),'New reviewed source is outside declared scan root')
        source_relative=source.relative_to(source_root).as_posix()
        matches=[r for r in doc['records']if r['page']==record['page'] and r['scan_reference']['relative_path']==source_relative]
        sr.require(len(matches)==1,'New stage does not identify exactly one current page/scan')
        current=matches[0];sid=str(current['scan_reference']['id'])
        sr.require(sid not in selected,'Stage repeats a current source');selected.add(sid)
        if 'sha256'in current['scan_reference']:sr.require(current['scan_reference']['sha256']==record['source']['sha256'],'Original scan checksum changed')
        links=current['repository'];sr.require('json'in links,'Compact generic import requires an existing current JSON model; TXT-only updates need their own reviewed model workflow')
        before={k:sr.checked(v,manifest_path.parent)[1]for k,v in record['before_saved'].items()}
        after={k:sr.checked(v,manifest_path.parent)[1]for k,v in record['staged_quartet'].items()}
        text_path=safe_target(repo,links['txt']['path']);model_path=safe_target(repo,links['json']['path'])
        current_txt=capture(text_path,links['txt']['sha256']);current_json=capture(model_path,links['json']['sha256'])
        before_clean,_=compact_metadata.prune_history(checkpoint_api.read_json(before['json']))
        after_model=checkpoint_api.read_json(after['json']);after_clean,_=compact_metadata.prune_history(after_model)
        current_document=checkpoint_api.read_json(current_json)
        current_model=page_reader.source_view(current_document)
        sr.require(current_txt in (before['txt'],after['txt']),'Current repository TXT is not the new stage predecessor or successor')
        is_before=before['txt']==current_txt and sr.json_equal(before_clean,current_model)
        is_after=after['txt']==current_txt and sr.json_equal(after_clean,current_model)
        sr.require(is_before or is_after,'Stage predecessor JSON has different current semantics or a mixed epoch')
        notes_relative=links.get('notes',{}).get('path','notes/'+links['txt']['path'][4:-4]+' review notes.txt')
        notes_path=safe_target(repo,notes_relative);old_notes=capture(notes_path)
        if old_notes is not None:
            sr.require(notes_relative in inventory_entries and inventory_entries[notes_relative]['sha256']==sr.digest(old_notes),'Current notes are not owned')
        clean,compact_notes=_notes_after(after_model,(old_notes or b'').decode('utf-8-sig'),record.get('json_patches',[]),record.get('notes_append'))
        if page_reader.is_uniform(current_document):
            clean=renormalize_page(clean,current_document)
            model_raw=(json.dumps(clean,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
        else:model_raw=sr.model_bytes(clean,current_json)
        put(links['txt']['path'],after['txt'],'Current reviewed source TXT')
        put(links['json']['path'],model_raw,'Current compact page model')
        put(notes_relative,compact_notes,'Current significant corrections and unresolved source notes')
        new_hashes={'txt':sr.digest(after['txt']),'json':sr.digest(model_raw),'notes':sr.digest(compact_notes)}
        for kind,relative in (('txt',links['txt']['path']),('json',links['json']['path']),('notes',notes_relative)):
            links[kind]={'path':relative,'sha256':new_hashes[kind]}
        current['status']='reviewed'
        # Do not copy a new private-stage bundle or claim its raw JSON is the
        # cleaned repository byte stream. The current checkpoint owns the result.
        current.pop('working_quartet',None)
        ce=content_entries.get(links['json']['path']);sr.require(ce is not None,'Current model missing from content manifest')
        ce['sha256']=new_hashes['json']
        if isinstance(content.get('managed_files'),dict):content['managed_files'][links['json']['path']]=new_hashes['json']
        exports=[]
        for entry in provenance.get('exported',[]):
            stored=str(entry.get('destination','')).replace('\\','/')
            relative='ALD/'+stored.split('/ALD/',1)[1]if'/ALD/'in stored else stored
            if relative==links['txt']['path'] and str(entry.get('source_scan_id'))==sid:exports.append(entry)
        sr.require(len(exports)==1,'Current reviewed export membership differs')
        entry=exports[0]
        sr.require(entry.get('page')==record['page'] and str(entry.get('source_relative','')).replace('\\','/')==source_relative,'Current export scan/page reference differs')
        prior_destinations={'txt':entry.get('destination'),'notes':entry.get('notes_destination')}
        entry.update(destination=str(text_path),text_sha256=new_hashes['txt'],notes_sha256=new_hashes['notes'],
            notes_destination=str(notes_path),review_record=checkpoint_api.DEFAULT_PATH)
        if isinstance(provenance.get('managed_files'),dict):
            for kind,path in (('txt',text_path),('notes',notes_path)):
                old_key=prior_destinations[kind]
                if old_key!=str(path):provenance['managed_files'].pop(old_key,None)
                provenance['managed_files'][str(path)]=new_hashes[kind]
        summaries.append({'page':record['page'],'scan_id':sid,'after':new_hashes,'targets':{k:v['path']for k,v in links.items()}})
    if 'original_model_bytes_preserved'in content:content['original_model_bytes_preserved']=False
    dirty=(any(guards[path]!=sr.digest(raw)for path,raw in changes.items())or not sr.json_equal(doc,checkpoint.document)
           or not sr.json_equal(content,old_content)or not sr.json_equal(provenance,old_provenance))
    if dirty:
        stamp=sr.now();doc['updated_utc']=stamp;content['updated_utc']=stamp;provenance['updated_utc']=stamp
        for relative,value in ((checkpoint_api.DEFAULT_PATH,doc),(CONTENT,content),(PROVENANCE,provenance)):
            put(relative,sr.encode(value),'Current compact source bindings')
        for path,raw in changes.items():
            relative=path.relative_to(repo).as_posix();entry=inventory_entries.get(relative)
            if entry is None:entry={'path':relative};inventory['files'].append(entry);inventory_entries[relative]=entry
            entry.update(sha256=sr.digest(raw),role=roles[path])
        inventory['updated_utc']=stamp
        inventory.pop('scoped_inventory_reviews',None)
        inventory['current_inventory_review']={'mode':'accepted-compact-source-import','review_id':manifest['review_id']}
        put(INVENTORY,sr.encode(inventory),'Current repository integrity inventory')
    checkpoint.recheck()
    changes={path:raw for path,raw in changes.items()if guards[path]!=sr.digest(raw)}
    report={'schema':'compact-source-import-plan-v1','passed':True,'write':False,'review_id':manifest['review_id'],
        'manifest':sr.binding(manifest_path),'acceptance':sr.binding(acceptance_path),'pages':summaries,
        'planned_writes':len(changes),'history_replayed':False,'archives_written':0,'repository_previews_written':0,
        'idempotent_retry':not dirty,
        'requires_refresh':['Socket listings uniform','Card types current'],
        'mutations':[{'path':str(path),'before_sha256':guards[path],'after_sha256':sr.digest(raw)}for path,raw in changes.items()]}
    return {'report':report,'changes':changes,'guards':guards,'checkpoint':checkpoint,'repo':repo,
            'manifest':manifest_path,'acceptance':acceptance_path}


def apply(prepared):
    prepared['checkpoint'].recheck()
    _publication(prepared['manifest'],prepared['acceptance'])
    for path,expected in prepared['guards'].items():
        actual=sr.digest(path.read_bytes())if path.is_file()else None
        sr.require(actual==expected,'Compact import input changed before write: '+str(path))
        if path.is_relative_to(prepared['repo']):safe_target(prepared['repo'],path.relative_to(prepared['repo']).as_posix())
    changes=prepared['changes'];originals={p:p.read_bytes()if p.is_file()else None for p in changes};installed=[]
    try:
        for path,raw in changes.items():
            installed.append(path);sr.atomic_write(path,raw)
        for path,raw in changes.items():sr.require(path.read_bytes()==raw,'Compact import write verification failed')
        inventory=sr.read_json(prepared['repo']/INVENTORY)
        checkpoint_api.load_checkpoint(prepared['repo'],inventory=inventory)
    except BaseException as failure:
        rollback_errors=[]
        for path in reversed(installed):
            current=path.read_bytes()if path.is_file()else None;old=originals[path]
            if current==old:continue
            if current!=changes[path]:
                rollback_errors.append('Concurrent target preserved: '+str(path));continue
            try:
                if old is None:path.unlink()
                else:sr.atomic_write(path,old)
            except BaseException as exc:rollback_errors.append(str(path)+': '+str(exc))
        if rollback_errors:raise RuntimeError('Compact rollback needs attention: '+'; '.join(rollback_errors))from failure
        raise
    return {**prepared['report'],'schema':'compact-source-import-result-v1','write':True,'written_files':len(changes)}

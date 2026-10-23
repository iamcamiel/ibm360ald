"""Current canonical ALD page API. Historical v2 is import-only."""
from copy import deepcopy
from pathlib import Path
import hashlib,json
import legacy_v2 as legacy
import review

SCHEMA='ibm360-ald-page-v3'
LEGACY_SCHEMA='ibm360-ald-page-v2'
ENVELOPE={'schema','document_id','page','source_status_ref','objects','nets','junctions','source_containers','current_extensions','review'}
VOCABULARY='Canonical vocabulary.json'
RELEASE='Format release.json'
_vocabulary=None
_schema=None

def vocabulary():
    global _vocabulary
    if _vocabulary is None:
        base=Path(__file__).parent;data=(base/VOCABULARY).read_bytes();release=json.loads((base/RELEASE).read_bytes())
        if release['page_schema']!=SCHEMA or release['format_version']!=3 or release['vocabulary_sha256']!=hashlib.sha256(data).hexdigest() or release['schema_sha256']!=hashlib.sha256((base/'ALD page schema.json').read_bytes()).hexdigest():raise ValueError('Schema vocabulary changed without a coordinated format release')
        _vocabulary=json.loads(data)
    return _vocabulary

def _type(v):return'null'if v is None else'boolean'if type(v)is bool else'integer'if type(v)is int else'number'if type(v)is float else'string'if isinstance(v,str)else'array'if isinstance(v,list)else'object'

def validate_notation(raw, *, allow_split_prefix=False):
    from notation import PIN_KEYS,COLLECTIONS,HEIGHTS
    spec=vocabulary()
    def record(section,value):
        if not isinstance(value,dict):return
        allowed=spec['fields'][section]
        for key,v in value.items():
            if key not in allowed:raise ValueError('Unregistered '+section+' field: '+key)
            if _type(v)not in allowed[key]and not(type(v)is int and'number'in allowed[key]):raise ValueError('Invalid '+section+' field type: '+key)
        observations=value.get('source_observations',[])
        if not isinstance(observations,list):raise ValueError('Source observations must be an array')
        names=spec['observation_names'].get('terminal'if section=='pin'else section,[])
        for observation in observations:
            if not isinstance(observation,dict)or set(observation)!={'field','value'}or observation['field']not in names:raise ValueError('Unregistered '+section+' source observation: '+str(observation.get('field')))
        if section=='pin':
            if set(value)!=PIN_KEYS:raise ValueError('Every terminal must use the complete canonical pin record')
            if value['pin']is not None and not isinstance(value['pin'],str):raise ValueError('Physical pin must be text or null')
            if value['pin_status']not in spec['enums']['pin_status']:raise ValueError('Unknown physical pin status')
            if value['side']not in('input','output',None):raise ValueError('Unknown terminal side')
            if value['occurrence_kind']not in('primary','alternate-unresolved-observation'):raise ValueError('Unknown terminal occurrence kind')
            for key in('row','column','label_column'):
                if value[key]is not None and type(value[key])is not int:raise ValueError('Grid coordinates must be integer or null')
            for key in('point','border_point'):
                if value[key]is not None and not(isinstance(value[key],list)and len(value[key])==2 and all(type(n)is int for n in value[key])):raise ValueError('Grid points must be integer [column,row] or null')
            if value['triangle']is not None and type(value['triangle'])is not bool:raise ValueError('Triangle must be boolean or null')
            if not isinstance(value['references'],list)or any(not isinstance(v,str)for v in value['references']):raise ValueError('Terminal references must be a text array')
    record('page',raw)
    for container in('nodes','boxes','groups','CAS_boxes'):
        if not isinstance(raw.get(container),list):continue
        for node in raw[container]:
            record('node',node)
            if not isinstance(node,dict):continue
            if any(key in node for key in COLLECTIONS if key!='pins')or any(key in node for key in HEIGHTS if key!='height'):raise ValueError('Legacy terminal or height notation is import-only')
            for pin in node.get('pins',[])if isinstance(node.get('pins'),list)else[]:record('pin',pin)
    for section,key in(('net','nets'),('junction','junctions'),('label','printed_labels'),('path','wire_paths'),('crossing','unjoined_crossings')):
        if not isinstance(raw.get(key),list):continue
        for value in raw[key]:
            if section=='label'and not isinstance(value,dict):raise ValueError('Printed labels must use canonical records')
            record(section,value)
    if not allow_split_prefix:
        from printed_literals import validate as validate_printed_literals
        validate_printed_literals(raw)
    return raw

def _v2(data):
    result={k:deepcopy(v)for k,v in data.items()if k!='review'};result['schema']=LEGACY_SCHEMA;return result

def _restore_page(data):
    return legacy._restore_page(_v2(data))if data.get('schema')==SCHEMA else legacy._restore_page(data)

def _checked_raw(data, *, allow_split_prefix=False):
    """Closed structural/digest checks for read-only projections.

    Writes and publication additionally replay the full semantic projection in
    validate_current_page. Readers never normalize or guess an alternate form.
    """
    global _schema
    if not isinstance(data,dict)or data.get('schema')!=SCHEMA or set(data)!=ENVELOPE:raise ValueError('Canonical v3 page required; use the explicit legacy importer')
    vocabulary()  # Verify the coordinated schema/vocabulary release first.
    from check_format import schema_check
    if _schema is None:_schema=json.loads((Path(__file__).parent/'ALD page schema.json').read_bytes())
    schema_check(data,_schema)
    review.validate(data);raw=legacy._restore_page(_v2(data));validate_notation(raw,allow_split_prefix=allow_split_prefix)
    return raw

def validate_current_page(data):
    _checked_raw(data)
    legacy.validate_current_page(_v2(data))
    return data

def restore_page(data):
    if data.get('schema')==LEGACY_SCHEMA:return legacy.restore_page(data)
    return _checked_raw(data)

def normalize_page(raw,model_relative,source_scan_id,source_status_ref='notes/Source status.json',context=None):
    validate_notation(raw)
    projected=legacy.normalize_page(raw,model_relative,source_scan_id,source_status_ref,context)
    projected['data']['schema']=SCHEMA;projected['data']['review']=review.make(projected['data'])
    return projected

def import_legacy_page(document):
    """Explicit in-memory migration; source and saved draft files stay intact."""
    if document.get('schema')==SCHEMA:return deepcopy(validate_current_page(document))
    if document.get('schema')!=LEGACY_SCHEMA:raise ValueError('Only an explicitly identified v2 page can be imported')
    import notation,sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'page_text'))
    import layout
    raw=legacy.restore_page(document);text=layout.render(raw);current,_=notation.convert(raw,text)
    from printed_literals import repair_raw
    current,_=repair_raw(current,text)
    scan=document['page']['scan_id'];relative=document['document_id'][len(scan)+1:]
    return normalize_page(current,relative,scan,document['source_status_ref']['path'])['data']

def renormalize_page(raw,template,context=None):
    if template.get('schema')==LEGACY_SCHEMA:
        import notation,layout
        current,_=notation.convert(raw,layout.render(raw));template=import_legacy_page(template);raw=current
    validate_current_page(template)
    scan=template['page']['scan_id'];relative=template['document_id'][len(scan)+1:]
    result=normalize_page(raw,relative,scan,template['source_status_ref']['path'],context)['data']
    result['review']=review.refresh(result,template['review'])
    return validate_current_page(result)



def import_review_page(document):
    """Explicit, pure import of saved v2 or historical split-literal v3 copies.

    Source files stay intact. The editor records a new copy; current published
    v3 files must already satisfy the full-literal contract without this import.
    """
    if document.get('schema')==LEGACY_SCHEMA:return import_legacy_page(document)
    raw=_checked_raw(document,allow_split_prefix=True)
    legacy.validate_current_page(_v2(document))
    from printed_literals import repair_raw
    fixed,changes=repair_raw(raw)
    if not changes:return validate_current_page(deepcopy(document))
    scan=document['page']['scan_id'];relative=document['document_id'][len(scan)+1:]
    result=normalize_page(fixed,relative,scan,document['source_status_ref']['path'])['data']
    result['review']=review.refresh(result,document['review'])
    return validate_current_page(result)

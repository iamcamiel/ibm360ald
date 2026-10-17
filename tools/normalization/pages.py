"""Pure current-page normalization. No archive, history or persisted mapping.

Reviewed identity/terminal projections provide the common semantic interface.
Small source forms retain current alias spellings and collection membership so
the transitional reader can reconstruct the exact current source representation.
"""
from copy import deepcopy
import json
import re
from pathlib import PurePosixPath

from identity import normalize_identity
from terminals import collect_terminals, normalize_net, ARRAY_TERMINAL_FIELDS, SCALAR_TERMINAL_FIELDS

SCHEMA = 'ibm360-ald-page-v2'
OBJECT_CONTAINERS = ('nodes', 'boxes', 'groups', 'CAS_boxes')
NETWORK_CONTAINERS = ('nets', 'junctions')
GEOMETRY_FIELDS = frozenset(('column','row','width','height','height_rows',
    'height_including_edges','top_row','bottom_row','total_rows','box_height',
    'function_offset','function_column_offset','function_column','function_indent',
    'body_bottom_offset','id_offset','grid_row_offset','field_offsets','native_xy',
    'native_box_xy','calibrated_grid_position'))
PAGE_FIELDS = ('page','page_identifier','printed_page','printed_page_identity','title','printed_title')


def pointer(parent, key):
    return parent + '/' + str(key).replace('~', '~0').replace('/', '~1')


def value_type(value):
    if value is None: return 'null'
    if type(value) is bool: return 'boolean'
    if type(value) is int: return 'integer'
    if type(value) is float: return 'number'
    if isinstance(value, str): return 'string'
    if isinstance(value, list): return 'array'
    if isinstance(value, dict): return 'object'
    raise TypeError('Only JSON values are supported')


def _portable(path):
    if not isinstance(path,str) or not path or '\\' in path or ':' in path:
        raise ValueError('Expected a portable repository-relative path')
    p=PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts or p.as_posix()!=path:
        raise ValueError('Unsafe repository-relative path')
    return path


def page_kind(raw, model_relative):
    family=model_relative.split('/')[1] if '/' in model_relative else ''
    if family.startswith(('A1 ', 'EF ')) and 'nodes' not in raw: return 'socket-listing'
    if isinstance(raw.get('boxes'),list) and 'nodes' not in raw: return 'programmed-ground'
    if isinstance(raw.get('groups'),list) and 'nodes' not in raw: return 'connector-routing'
    if isinstance(raw.get('nodes'),list):
        return 'cas-control-diagram' if any(isinstance(n,dict) and 'CAS_box' in n for n in raw['nodes']) else 'ald-diagram'
    if 'CAS_boxes' in raw: return 'cas-layout'
    return 'annotation-table-or-layout'


def object_kind(raw, container):
    if not isinstance(raw,dict): return 'uninterpreted-object'
    if container=='boxes': return 'programmed-ground-box'
    if container=='groups': return 'connector-group'
    if container=='CAS_boxes' or 'CAS_box' in raw: return 'cas-control-box'
    if any(k in raw for k in ('card_type','card','part','printed_card_portion')): return 'card-or-special-block'
    return 'diagram-object'


def _current_terminal(record):
    """Reconstruct one mapper occurrence from its transient source observations."""
    typ=record['raw_type']
    if typ!='object':
        for observation in record.get('raw_observations',[]):
            if observation.get('field')=='$scalar': return deepcopy(observation['value'])
        for observation in record.get('raw_extensions',[]):
            if 'field' not in observation and 'value' in observation: return deepcopy(observation['value'])
        raise ValueError('Unsupported terminal value has no literal observation')
    observed={}
    collections=[record.get('raw_observations',[]),record['symbols']['observations'],
        record.get('border_decorations',[]),record['geometry']['observations'],
        record['geometry'].get('edge_observations',[]),record.get('role_observations',[]),
        record.get('endpoint_aliases',[]),record.get('raw_extensions',[])]
    def visit(value):
        if isinstance(value,dict):
            field=value.get('field')
            if field in record.get('source_field_presence',{}) and 'value' in value:
                if field in observed and observed[field]!=value['value']: raise ValueError('Conflicting mapper observations')
                observed[field]=deepcopy(value['value'])
            for child in value.values(): visit(child)
        elif isinstance(value,list):
            for child in value: visit(child)
    for entries in collections: visit(entries)
    # side is intentionally represented directly by the reviewed mapper.
    if 'side' in record.get('source_field_presence',{}): observed['side']=deepcopy(record['side'])
    expected=set(record.get('source_field_presence',{}))
    if set(observed)!=expected: raise ValueError('Terminal mapping did not retain every current field: '+str(expected-set(observed)))
    return observed


def _namespace(data, object_id):
    result=deepcopy(data)
    for terminal in result['terminals']: terminal['terminal_id']=object_id+'/'+terminal['terminal_id']
    for alias in result['alias_relationships']: alias['terminal_id']=object_id+'/'+alias['terminal_id']
    for key in ('terminal_pairs','group_memberships'):
        for group in result[key]: group['terminal_ids']=[object_id+'/'+v for v in group['terminal_ids']]
    return result


def _object(obj, container, ordinal, sp, context):
    oid=container+':'+str(ordinal)
    record={'object_id':oid,'kind':object_kind(obj,container),
        'source_form':{'container':container,'ordinal':ordinal,'value_type':value_type(obj)}}
    if not isinstance(obj,dict):
        record['current_value']=deepcopy(obj)
        return record, {'source_pointer':sp}
    identity=normalize_identity(obj,sp,context)
    terminals=collect_terminals(obj,sp,{'owner_id':oid})
    record.update(deepcopy(identity['data']))
    record.update(_namespace(terminals['data'],oid))
    # Identity aliases are current literal observations. They are not a history
    # ledger, and are needed to distinguish absent/null or conflicting mirrors.
    identity_keys={p[len(sp)+1:] for p in identity['provenance']['source_fields_consumed'] if p.startswith(sp+'/') and '/' not in p[len(sp)+1:]}
    record['source_literals']={k:deepcopy(v) for k,v in obj.items() if k in identity_keys}
    record['geometry']={k:deepcopy(v) for k,v in obj.items() if k in GEOMETRY_FIELDS and k not in identity_keys}
    term_proof=terminals['provenance']
    terminal_by_ptr={}
    for terminal, proof in zip(record['terminals'],term_proof['terminals']):
        terminal['source_literals']=_current_terminal(proof)
        terminal['source_form']={'value_type':proof['raw_type']}
        terminal_by_ptr[proof['source_pointer']]={'terminal_id':terminal['terminal_id']}
    for i,(alias,proof) in enumerate(zip(record['alias_relationships'],term_proof['alias_claims'])):
        alias['source_literals']=_current_terminal(proof['observation'])
        alias['source_form']={'value_type':proof['observation']['raw_type']}
        terminal_by_ptr[proof['source_pointer']]={'alias_index':i}
    source_collections=[]
    consumed=set(identity_keys)|set(record['geometry'])
    terminal_fields=set(ARRAY_TERMINAL_FIELDS)|set(SCALAR_TERMINAL_FIELDS)
    for field,value in obj.items():
        if field not in terminal_fields: continue
        base=pointer(sp,field)
        is_array=field in ARRAY_TERMINAL_FIELDS and isinstance(value,list)
        paths=[pointer(base,i) for i in range(len(value))] if is_array else [base]
        if not all(p in terminal_by_ptr for p in paths):
            raise ValueError('Unowned current terminal collection '+base)
        source_collections.append({'field':field,'representation':'array' if is_array else 'scalar',
            'members':[deepcopy(terminal_by_ptr[p]) for p in paths]})
        consumed.add(field)
    record['source_form']['terminal_collections']=source_collections
    # These nonstandard structures combine pair/group geometry and terminal
    # ownership. Keep their current literals once; never infer a logical union.
    group_keys={p[len(sp)+1:] for p in term_proof['source_fields_consumed'] if p.startswith(sp+'/') and '/' not in p[len(sp)+1:] and p[len(sp)+1:] not in terminal_fields}
    record['source_group_fields']={k:deepcopy(obj[k]) for k in group_keys}
    consumed.update(group_keys)
    record['current_extensions']={k:deepcopy(v) for k,v in obj.items() if k not in consumed}
    context_only={'accepted_page_inheritance_not_established','page_review_presence_value_missing'}
    record['current_issues']={'identity':[deepcopy(v) for v in identity['provenance'].get('issues',[]) if v.get('code') not in context_only],
        'terminals':deepcopy(term_proof.get('issues',[]))}
    return record, {'source_pointer':sp,'identity':identity['provenance'],'terminals':term_proof}


def _network(raw, container, ordinal, sp):
    projected=normalize_net(raw,sp,{'source_container':container,'source_ordinal':ordinal})
    record={'network_id':container+':'+str(ordinal),'kind':'source-net' if container=='nets' else 'source-junction',
        **deepcopy(projected['data']),
        'source_form':{'container':container,'ordinal':ordinal,'value_type':value_type(raw)}}
    # Crossings are a rendering consequence of paths, not a second maintained
    # connectivity list. Preserve any existing literal claims for the adapter.
    record.pop('crossings',None)
    proof=projected['provenance']
    if not isinstance(raw,dict):
        record['current_value']=deepcopy(raw)
        return record,proof
    consumed={}
    for entry in proof.get('endpoint_field_observations',[]): consumed[entry['field']]=deepcopy(entry['value'])
    if 'id' in raw: consumed['id']=deepcopy(raw['id'])
    for entry in proof.get('crossing_claims',[]): consumed[entry['field']]=deepcopy(entry['value'])
    record['source_literals']=consumed
    # The reviewed mapper intentionally removes some explanatory fields. The
    # source has already been compacted; retain all its remaining current facts.
    for destination,source in [('routes','route_geometry'),('junctions','junction_claims'),('unresolved_current_claims','uncertainty_claims')]:
        record[destination]=[{'kind':o['field'],'value':deepcopy(o['value'])} for o in proof[source]]
    has_route=any(o['value'] not in (None,[],{},False,'') for o in proof['route_geometry'])
    has_path=any(o['field'] in ('edges','paths','cells','wire_cells') and o['value'] not in (None,[],{},False,'') for o in proof['route_geometry'])
    damaged_route=any(o['value'] not in (None,[],{},False,'') for o in proof['uncertainty_claims'])
    record['routing_status']='partial' if has_route and (not has_path or damaged_route) else 'recorded' if has_route else 'not-recorded'
    record['extensions']={o['field']:deepcopy(o['value']) for o in proof['raw_extensions'] if 'field' in o}
    record['current_issues']=deepcopy(proof.get('issues',[]))
    return record,proof


def normalize_page(raw, model_relative, source_scan_id, source_status_ref='notes/Source status.json', context=None):
    """Return current data plus a transient comparison mapping, never a sidecar."""
    if not isinstance(raw,dict): raise TypeError('Source page must be a JSON object')
    if raw.get('schema')==SCHEMA: raise ValueError('Page is already uniform; restore_page before rebuilding current data')
    _portable(model_relative);_portable(source_status_ref)
    data={'schema':SCHEMA,'document_id':str(source_scan_id)+':'+model_relative,
        'page':{'scan_id':str(source_scan_id),'kind':page_kind(raw,model_relative)},
        'source_status_ref':{'path':source_status_ref,'scan_id':str(source_scan_id)},
        'objects':[],'nets':[],'junctions':[],'source_containers':{},'current_extensions':{}}
    mapping={'objects':[],'nets':[],'junctions':[]}
    consumed=set()
    for key in PAGE_FIELDS:
        if key in raw:data['page'][key]=deepcopy(raw[key]);consumed.add(key)
    for container in OBJECT_CONTAINERS+NETWORK_CONTAINERS:
        if container not in raw:continue
        values=raw[container]
        data['source_containers'][container]={'value_type':value_type(values),'projected':isinstance(values,list)}
        if not isinstance(values,list):continue
        consumed.add(container)
        for ordinal,value in enumerate(values):
            sp=pointer(pointer('',container),ordinal)
            if container in OBJECT_CONTAINERS:
                obj,proof=_object(value,container,ordinal,sp,context)
                data['objects'].append(obj);mapping['objects'].append(proof)
            else:
                net,proof=_network(value,container,ordinal,sp)
                data[container].append(net);mapping[container].append(proof)
    data['current_extensions']={k:deepcopy(v) for k,v in raw.items() if k not in consumed}
    if _typed_literal(_restore_page(data))!=_typed_literal(raw):raise ValueError('Current page cannot be reconstructed exactly')
    return {'data':data,'mapping':mapping}


def _merge(target,fields):
    if not isinstance(fields,dict): raise ValueError('Current field collection is not an object')
    for key,value in fields.items():
        if key in target:raise ValueError('Duplicate current field '+key)
        target[key]=deepcopy(value)


def _restore_object(record):
    form=record['source_form']
    if form['value_type']!='object':return deepcopy(record['current_value'])
    result={}
    for key in ('source_literals','geometry','source_group_fields','current_extensions'):_merge(result,record[key])
    terminals={t['terminal_id']:t for t in record['terminals']}
    if len(terminals)!=len(record['terminals']):raise ValueError('Duplicate terminal identity')
    seen_collections=set();seen_members=set()
    for collection in form['terminal_collections']:
        field=collection['field']
        if field in seen_collections or field in result:raise ValueError('Duplicate terminal collection')
        seen_collections.add(field);members=[]
        for member in collection['members']:
            if set(member)=={'terminal_id'}:
                identity=('terminal',member['terminal_id'])
                if member['terminal_id'] not in terminals:raise ValueError('Unknown terminal reference')
                source=terminals[member['terminal_id']]
            elif set(member)=={'alias_index'}:
                index=member['alias_index']
                if type(index)is not int or not 0<=index<len(record['alias_relationships']):raise ValueError('Unknown terminal alias')
                identity=('alias',index);source=record['alias_relationships'][index]
            else:raise ValueError('Invalid terminal member')
            if identity in seen_members:raise ValueError('Duplicate source terminal membership')
            seen_members.add(identity);members.append(deepcopy(source['source_literals']))
        if collection['representation']=='array':result[field]=members
        elif collection['representation']=='scalar' and len(members)==1:result[field]=members[0]
        else:raise ValueError('Invalid terminal collection shape')
    return result


def _restore_network(record):
    if record['source_form']['value_type']!='object':return deepcopy(record['current_value'])
    result={};_merge(result,record['source_literals'])
    # Some source fields intentionally appear in two semantic categories.
    # Their current literals must agree exactly; disagreement fails closed.
    for key in ('routes','junctions','unresolved_current_claims'):
        for observation in record[key]:
            field,value=observation['kind'],observation['value']
            if field in result and (type(result[field])is not type(value) or result[field]!=value):raise ValueError('Conflicting current net claims')
            result[field]=deepcopy(value)
    _merge(result,record['extensions'])
    return result


def _restore_page(data):
    """Reconstruct a detached current legacy view without reading any archive."""
    if not isinstance(data,dict) or data.get('schema')!=SCHEMA:raise ValueError('Unknown uniform page schema')
    result={};_merge(result,data['current_extensions'])
    for key in PAGE_FIELDS:
        if key in data['page']:_merge(result,{key:data['page'][key]})
    by_container={}
    for section,collection in (('objects',data['objects']),('nets',data['nets']),('junctions',data['junctions'])):
        for record in collection:
            form=record['source_form'];container=form['container'];ordinal=form['ordinal']
            if container not in OBJECT_CONTAINERS+NETWORK_CONTAINERS or type(ordinal)is not int or ordinal<0:raise ValueError('Invalid source occurrence')
            if section=='objects' and container not in OBJECT_CONTAINERS or section!='objects' and container!=section:raise ValueError('Source occurrence is in the wrong semantic collection')
            identifier_key='object_id' if section=='objects' else 'network_id'
            if record.get(identifier_key)!=container+':'+str(ordinal):raise ValueError('Source occurrence identity disagrees with its form')
            if container not in data['source_containers'] or data['source_containers'][container].get('projected')is not True:raise ValueError('Unowned source occurrence')
            entries=by_container.setdefault(container,{})
            if ordinal in entries:raise ValueError('Duplicate source occurrence')
            entries[ordinal]=_restore_object(record) if container in OBJECT_CONTAINERS else _restore_network(record)
    for container,shape in data['source_containers'].items():
        if container not in OBJECT_CONTAINERS+NETWORK_CONTAINERS:raise ValueError('Unknown source container')
        if shape['projected']:
            if shape['value_type']!='array' or container in result:raise ValueError('Conflicting source container')
            entries=by_container.get(container,{})
            if set(entries)!=set(range(len(entries))):raise ValueError('Missing source occurrence')
            result[container]=[entries[i] for i in range(len(entries))]
        elif container not in result or value_type(result[container])!=shape['value_type']:raise ValueError('Missing unprojected source container')
    return result


def _typed_literal(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def validate_current_page(data):
    """Reject semantic/literal disagreement instead of silently choosing a view.

    This is representational consistency, not new source or electrical approval.
    Authoritative geometry stored once may be changed by reviewed workflows;
    immutable current file/checkpoint hashes remain the acceptance guard.
    """
    restored=_restore_page(data)
    scan_id=data['page']['scan_id'];prefix=str(scan_id)+':'
    if not isinstance(scan_id,str) or not data['document_id'].startswith(prefix):raise ValueError('Document identity disagrees with page')
    ref=data['source_status_ref']
    if not isinstance(ref,dict) or set(ref)!={'path','scan_id'} or ref.get('scan_id')!=scan_id or ref.get('path')!='notes/Source status.json':raise ValueError('Invalid current Source status reference')
    projected=normalize_page(restored,data['document_id'][len(prefix):],scan_id,ref['path'])['data']
    if _typed_literal(projected)!=_typed_literal(data):raise ValueError('Uniform structured facts disagree with current source literals/forms')
    return data


def restore_page(data):
    """Return an exact detached current view after semantic consistency checks."""
    validate_current_page(data)
    return _restore_page(data)


def renormalize_page(raw, template, context=None):
    """Replace current contents while keeping stable page/checkpoint identity."""
    if template.get('schema')!=SCHEMA:raise ValueError('Unknown template schema')
    validate_current_page(template)
    scan_id=template['page']['scan_id'];prefix=str(scan_id)+':'
    if not template['document_id'].startswith(prefix):raise ValueError('Document identity disagrees with page')
    return normalize_page(raw,template['document_id'][len(prefix):],scan_id,template['source_status_ref']['path'],context)['data']

"""Private read-only source restoration adapted from ibm360ald/tools/normalization.

Only lossless source reconstruction is vendored. The caller is responsible for
schema, digest, review and publication validation before passing models here.
No semantic normalization or source mutation takes place.
"""
from copy import deepcopy

READ_SCHEMAS = ('ibm360-ald-page-v2', 'ibm360-ald-page-v3')
OBJECT_CONTAINERS = ('nodes', 'boxes', 'groups', 'CAS_boxes')
NETWORK_CONTAINERS = ('nets', 'junctions')
PAGE_FIELDS = ('page','page_identifier','printed_page','printed_page_identity','title','printed_title')

def value_type(value):
    if value is None: return 'null'
    if type(value) is bool: return 'boolean'
    if type(value) is int: return 'integer'
    if type(value) is float: return 'number'
    if isinstance(value, str): return 'string'
    if isinstance(value, list): return 'array'
    if isinstance(value, dict): return 'object'
    raise TypeError('Only JSON values are supported')

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
    if not isinstance(data,dict) or data.get('schema') not in READ_SCHEMAS:raise ValueError('Unknown uniform page schema')
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



def source_view(model):
    if not isinstance(model, dict):
        raise ValueError('Page model must be an object')
    if model.get('schema') in READ_SCHEMAS:
        return _restore_page(model)
    schema = model.get('schema')
    if isinstance(schema, str) and schema.startswith('ibm360-ald-page-'):
        raise ValueError('Unsupported legacy ALD schema: ' + schema)
    return deepcopy(model)
"""Lossless, IO-free identity/literal projection of one accepted raw ALD object.

Derived values never replace observations. Source membership, geometry, pins and
electrical semantics are deliberately outside this mapper.
"""
from copy import deepcopy
import re

COMBINED = re.compile(r'([0-9]{4})([A-Z0-9]{2})\Z')
CARD = re.compile(r'[0-9]{4}\Z')
PORTION = re.compile(r'[A-Z0-9]{2}\Z')
CIRCUIT = re.compile(r'[A-Z][0-9]{2}[A-Z]{2}\Z')
SITE = re.compile(r'(?:[0-9]{2})?[A-Z]-[A-Z][0-9][A-Z][0-9](?:[BT])?\Z')
GRID_ID = re.compile(r'[0-9]+[A-Z]-[A-Z0-9]+\Z')
SHA256 = re.compile(r'[0-9a-fA-F]{64}\Z')
# Scoped metadata split for display-label subobjects. Unknown current fields,
# including geometry, electrical labels and semantic owner/reference names,
# are retained. Do not use a source_* wildcard or import pages.py (cycle).
DISPLAY_HISTORY = re.compile(r'(?:^|_)(?:history|historical|previous|prior|superseded|review|reviewed|'
    r'acceptance|accepted|audit|evidence|proof|provenance|sha256|hash|hashes|timestamp|mtime|'
    r'author|worker|coordinator|human|manual|workbook)(?:_|$)', re.I)
DISPLAY_HISTORY_EXACT = frozenset(('notes','note','uncertainties','pending_manual_checks',
    'source_crop','source_crops','native_crop','source_crops_directory','native_evidence_directory'))


def _type(value):
    if value is None: return 'null'
    if type(value) is bool: return 'boolean'
    if isinstance(value, str): return 'string'
    if type(value) is int: return 'integer'
    if type(value) is float: return 'number'
    if isinstance(value, list): return 'array'
    if isinstance(value, dict): return 'object'
    raise TypeError('Input must contain JSON values only')


def _pointer(parent, key):
    return parent + '/' + str(key).replace('~', '~0').replace('/', '~1')


def _matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _nonempty(value):
    # False and 0 are explicit values, not missing or empty strings.
    return value is not None and not (isinstance(value, str) and value == '')


def _accepted_context(context):
    """Validate the caller's hash-bound acceptance assertion, without IO.

    The driver must independently validate these bindings against the accepted
    manifest and rehash actual bytes. This pure module cannot establish acceptance.
    """
    if not isinstance(context, dict): return None
    source = context.get('source_model')
    text = context.get('text')
    page = context.get('accepted_page')
    if not all(isinstance(v, dict) for v in (source, text, page)): return None
    if page.get('exact_current_accepted') is not True: return None
    if type(page.get('source_reviewed_present')) is not bool: return None
    if page['source_reviewed_present'] != ('source_reviewed' in page): return None
    if not all(isinstance(v.get('path'), str) and bool(v['path']) for v in (source, text)): return None
    hashes = [source.get('sha256'), text.get('sha256'), page.get('model_sha256'), page.get('text_sha256')]
    if not all(_matches(SHA256, h) for h in hashes): return None
    if source['sha256'] != page['model_sha256'] or text['sha256'] != page['text_sha256']: return None
    provenance = page.get('provenance_binding')
    if not isinstance(provenance, dict) or not isinstance(provenance.get('path'), str) or not provenance['path']: return None
    if not _matches(SHA256, provenance.get('sha256')): return None
    return {'basis': 'exact-current-accepted-context',
            'source_model': deepcopy(source), 'text': deepcopy(text),
            'acceptance': deepcopy(page),
            'verification_responsibility': 'Caller verifies current accepted manifests and actual bytes before/after normalization.'}


def _project_identity(node, source_pointer, context=None):
    """Return detached normalized identity/literals and exact raw observations.

    source_pointer is the original JSON pointer, e.g. /nodes/7 or /boxes/2.
    context is optional; only its explicit accepted_page contract can support a
    derived review claim. Explicit raw source_reviewed False/null is never inherited.
    """
    if not isinstance(node, dict): raise TypeError('node must be a JSON object')
    if not isinstance(source_pointer, str) or not source_pointer.startswith('/'):
        raise ValueError('source_pointer must be a non-root JSON pointer')
    if re.search(r'~(?![01])', source_pointer): raise ValueError('invalid JSON pointer escape')
    context = {} if context is None else context
    if not isinstance(context, dict): raise TypeError('context must be an object')
    consumed = set()
    issues = []

    def obs(key):
        pointer = _pointer(source_pointer, key)
        if key not in node: return {'presence': 'absent', 'source_pointer': pointer}
        consumed.add(pointer)
        return {'presence': 'present', 'value_type': _type(node[key]),
                'value': deepcopy(node[key]), 'source_pointer': pointer}

    def issue(code, keys, detail):
        issues.append({'code': code, 'source_pointers': [_pointer(source_pointer, k) for k in keys], 'detail': detail})

    identifiers = {'source_pointer': source_pointer,
                   'observations': {k: obs(k) for k in ('id', 'printed_id', 'printed_identifier', 'grid', 'printed_grid', 'CAS_box', 'address')}}
    if 'id' not in node: identifiers['status'] = 'source-id-absent'
    elif not isinstance(node['id'], str) or not node['id']: identifiers['status'] = 'source-id-unusable'
    else: identifiers['status'] = 'source-id-present'

    identity_keys = ('card_type', 'portion', 'printed_card_portion', 'card', 'part')
    card_identity = {'observations': {k: obs(k) for k in identity_keys}, 'rule': 'strict-combined-and-split-agreement-v1',
                     'status': 'absent', 'derived': None}
    evidence = []
    for k in ('card', 'part', 'printed_card_portion'):
        m = COMBINED.fullmatch(node[k]) if isinstance(node.get(k), str) else None
        if m: evidence.append((k, m.group(1), m.group(2)))
    candidates = {(a, b) for _, a, b in evidence}
    conflict = len(candidates) > 1
    for key, index in (('card_type', 0), ('portion', 1)):
        if key in node and _nonempty(node[key]) and any(node[key] != pair[index] for pair in candidates): conflict = True
    printed = node.get('printed_card_portion')
    if _nonempty(printed) and any(printed != a+b for a,b in candidates): conflict = True
    if conflict:
        card_identity['status'] = 'conflict'
        issue('card_identity_alias_conflict', identity_keys, 'Explicit identity representations disagree; no identity selected.')
    elif len(candidates) == 1:
        card, portion = next(iter(candidates))
        card_identity.update(status='resolved', derived={'card_type': card, 'portion': portion, 'combined': card+portion,
            'source_pointers': [_pointer(source_pointer,k) for k,_,_ in evidence]})
    elif _matches(CARD,node.get('card_type')) and _matches(PORTION,node.get('portion')):
        # Unreadable printed evidence is not a contradictory *exact* alias.
        # Preserve accepted explicit split fields; never claim the damaged
        # printed observation independently confirms them.
        card_identity.update(status='resolved',derived={'card_type':node['card_type'],'portion':node['portion'],
            'combined':node['card_type']+node['portion'],'source_pointers':[_pointer(source_pointer,'card_type'),_pointer(source_pointer,'portion')]})
        if _nonempty(printed):
            issue('damaged_printed_identity_with_explicit_splits', ('card_type','portion','printed_card_portion'), 'Current split fields retained; damaged printed literal is provenance, not an exact corroborating alias.')
    elif any(k in node for k in identity_keys):
        card_identity['status']='unresolved'
        issue('card_identity_incomplete_or_noncard',identity_keys,'No exact complete card identity; original observations retained without guessing.')

    # Explicit legacy schema: ZA-style card means physical site; location is grid.
    legacy_site_roles = (isinstance(node.get('technology'),str) and isinstance(node.get('part'),str)
                         and _matches(SITE,node.get('card')) and _matches(GRID_ID,node.get('location')))
    legacy_roles = (legacy_site_roles and _matches(CIRCUIT,node.get('technology'))
                    and _matches(COMBINED,node.get('part')))
    function = {'observations':{k:obs(k) for k in ('function','printed_function','primary_function','secondary_function')},
                'literal':obs('function'), 'clean_label':None, 'primary':None, 'secondary':None}
    if isinstance(node.get('function'),str): function['clean_label']=node['function'].lstrip(' ')
    for key, output in (('primary_function','primary'),('secondary_function','secondary')):
        if isinstance(node.get(key),str): function[output]={'value':node[key],'basis':'explicit-source-field','source_pointer':_pointer(source_pointer,key)}
    if 'function' in node and 'printed_function' in node and (type(node['function']) is not type(node['printed_function']) or node['function'] != node['printed_function']):
        issue('function_literal_disagreement',('function','printed_function'),'Both source literals retained; no precedence selected.')

    circuit = {'observations':{k:obs(k) for k in ('unit','technology','printed_unit','possible_unit')},
               'status':'absent','literal':None,'rule':None}
    if 'unit' in node:
        circuit.update(status='resolved' if _matches(CIRCUIT,node['unit']) else 'unparsed',literal=obs('unit'),rule='explicit-unit-literal')
        if legacy_roles and node['unit'] != node['technology']:
            circuit.update(status='conflict',literal=None)
            issue('circuit_literal_disagreement',('unit','technology'),'Legacy technology and unit disagree; neither selected.')
    elif legacy_roles:
        circuit.update(status='resolved',literal=obs('technology'),rule='declared-legacy-technology-cardsite-grid-shape')
    elif 'technology' in node:
        circuit['status']='unparsed'
        issue('technology_role_unresolved',('technology',),'Technology retained, but full legacy schema is not established.')

    site_keys=('location','physical_location','printed_location','card_location','socket_location','connector_location','board_location','socket','position','board')
    site={'observations':{k:obs(k) for k in site_keys},'literal':None,'role':None,'derived_physical_site':None,
          'evidence_observations':{k:obs(k) for k in ('socket_listing_location','location_candidate_from_A1','A1_supported_location','a1_corresponding_location','contextual_socket_location_proposal','historical_physical_location_candidate','workbook_confirmed_location')}}
    if legacy_site_roles:
        site.update(literal=obs('card'),role='physical-site',grid_literal=obs('location'),rule='declared-legacy-technology-cardsite-grid-shape')
    elif 'board_location' in node:
        site.update(literal=obs('board_location'),role='programmed-ground-board-location',rule='explicit-board-location')
    elif 'location' in node:
        site.update(literal=obs('location'),role='source-location-uninterpreted',rule='explicit-location-literal')
    # No board expansion or site spelling canonicalization occurs here.

    display_keys=('printed_unit','top_border_text','auxiliary_field','control','printed_control','above_block_caption',
                  'block_caption','caption','body_fields','printed_labels','printed_ground','lamp_label','printed_device_code')
    display_labels=[{'role':'auxiliary-source-label' if k=='printed_unit' else k,'observation':obs(k)} for k in display_keys if k in node]

    raw_review=obs('source_reviewed')
    page_review={'presence':'absent'}
    page_context=context.get('accepted_page')
    if isinstance(page_context,dict) and page_context.get('source_reviewed_present') is True:
        if 'source_reviewed' not in page_context:
            issue('page_review_presence_value_missing',(), 'Page review presence was asserted without its raw value.')
        else:
            page_review={'presence':'present','value_type':_type(page_context['source_reviewed']),'value':deepcopy(page_context['source_reviewed'])}
    binding=_accepted_context(context)
    review={'explicit_node':raw_review,'explicit_page':page_review,'effective':None,'derived_inheritance':None,
            'effective_approved':False,'acceptance_binding':binding}
    if 'source_reviewed' in node:
        review['effective']={'basis':'explicit-node','observation':raw_review}
        review['effective_approved']=node['source_reviewed'] is True and binding is not None
    else:
        if binding and isinstance(page_context,dict) and page_context.get('source_reviewed_present') is True and page_context.get('source_reviewed') is True:
            claim=dict(binding,value=True,basis='exact-current-accepted-page')
            review['derived_inheritance']=claim
            review['effective']={'basis':'derived-exact-accepted-page','value':True}
            review['effective_approved']=True
        elif context.get('accepted_page') is not None:
            issue('accepted_page_inheritance_not_established',(), 'Incomplete or mismatched acceptance context cannot establish review inheritance.')

    return {'identifiers':identifiers,'card_identity':card_identity,'function':function,'circuit':circuit,
            'site':site,'display_labels':display_labels,'review':review,
            'source_fields_consumed':sorted(consumed),'issues':issues}


def normalize_identity(node, source_pointer, context=None):
    """Return clean current diagram data plus separately owned provenance.

    No source pointers, acceptance history or hash metadata are put into data.
    The enclosing driver stores provenance under the separate provenance tree.
    """
    projected=_project_identity(node,source_pointer,context)
    observed={}
    def gather(value):
        if isinstance(value,dict):
            if value.get('presence') in ('present','absent') and isinstance(value.get('source_pointer'),str):
                observed[value['source_pointer']]=deepcopy(value)
            for child in value.values():gather(child)
        elif isinstance(value,list):
            for child in value:gather(child)
    gather(projected)
    derived=projected['card_identity']['derived']
    card_data={'parse_status':projected['card_identity']['status']}
    if derived:
        card_data.update(card_type=derived['card_type'],portion=derived['portion'])
    else:
        for key in ('card_type','portion'):
            if key in node:card_data[key]=deepcopy(node[key])
        # Current unreadable active labels stay visible to data consumers.
        # Valid combined labels and historical printed observations stay in
        # provenance; they are not copied into clean structured identity.
        unresolved={key:deepcopy(node[key]) for key in ('card','part','printed_card_portion')
                    if key in node and not _matches(COMBINED,node[key]) and not _matches(SITE,node[key]) and _nonempty(node[key])}
        if unresolved:card_data['unparsed_identity_labels']=unresolved
    function_data={'parse_status':'absent'}
    if 'function' in node:
        value=node['function']
        function_data={'label':value.lstrip(' ') if isinstance(value,str) else deepcopy(value),
                       'parse_status':'unreadable' if isinstance(value,str) and '�' in value else 'literal'}
    for key in ('primary','secondary'):
        if projected['function'][key] is not None:function_data[key]=deepcopy(projected['function'][key]['value'])
    circuit_data={'parse_status':projected['circuit']['status']}
    if projected['circuit']['literal'] is not None:
        circuit_data['identifier']=deepcopy(projected['circuit']['literal']['value'])
    elif 'unit' in node:circuit_data['unparsed_identifier']=deepcopy(node['unit'])
    elif 'technology' in node:circuit_data['unparsed_technology']=deepcopy(node['technology'])
    site_data={'parse_status':'absent'}
    if projected['site']['literal'] is not None:
        site_data.update(label=deepcopy(projected['site']['literal']['value']),role=projected['site']['role'],parse_status='literal')
    if 'grid_literal' in projected['site']:site_data['grid_label']=deepcopy(projected['site']['grid_literal']['value'])
    # These explicitly named current roles must not disappear when location is
    # merely a display/grid slot or empty. No candidate/history field is active.
    for key in ('physical_location','card_location','socket_location','connector_location','board_location','socket','position','board'):
        if key in node:site_data[key]=deepcopy(node[key])
    display_history=[]
    display_projection=[]
    def current_display_value(value,sp,dp):
        # Every unknown current attribute is retained recursively. Only explicit
        # metadata names move out, preserving empty objects/array positions.
        if isinstance(value,dict):
            result={}
            if not value:display_projection.append({'source_pointer':sp,'data_pointer':dp})
            for k,child in value.items():
                child_sp=_pointer(sp,k)
                if k in DISPLAY_HISTORY_EXACT or DISPLAY_HISTORY.search(k):
                    display_history.append({'source_pointer':child_sp,'value_type':_type(child),'value':deepcopy(child)})
                else:result[k]=current_display_value(child,child_sp,_pointer(dp,k))
            return result
        if isinstance(value,list):
            if not value:display_projection.append({'source_pointer':sp,'data_pointer':dp})
            return [current_display_value(v,_pointer(sp,i),_pointer(dp,i)) for i,v in enumerate(value)]
        display_projection.append({'source_pointer':sp,'data_pointer':dp})
        return deepcopy(value)
    data={'identifiers':{k:deepcopy(node[k]) for k in ('id','printed_id','printed_identifier','grid','printed_grid','CAS_box','address') if k in node},
          'card_identity':card_data,'function':function_data,'circuit':circuit_data,'site':site_data,
          'display_labels':[{'role':label['role'],'value':current_display_value(label['observation']['value'],
              label['observation']['source_pointer'],f'/display_labels/{i}/value')} for i,label in enumerate(projected['display_labels'])]}
    provenance={'raw_observations':observed,
        'alias_claims':{
            'card_identity':{k:deepcopy(v) for k,v in projected['card_identity'].items() if k!='observations'},
            'function':{k:deepcopy(v) for k,v in projected['function'].items() if k not in ('observations','literal')},
            'circuit':{k:deepcopy(v) for k,v in projected['circuit'].items() if k!='observations'},
            'site':{k:deepcopy(v) for k,v in projected['site'].items() if k not in ('observations','evidence_observations')}},
        'review':deepcopy(projected['review']),
        'display_label_history':display_history,'display_label_projection':display_projection,
        'source_fields_consumed':projected['source_fields_consumed'],'issues':projected['issues']}
    return {'data':data,'provenance':provenance}

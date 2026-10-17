"""Pure source-field terminal and net projections; no electrical inference or IO.

Pin numbers, literal label marks, and physical-border decorations are independent.
All claims retain exact source pointers/values; unknown fields remain extensions.
No contact alphabet, numeric range, power role, driver, junction or alias is invented.
"""
from copy import deepcopy
import re

LABEL_FIELDS=('printed_combined_label','raw_printed_pin_field','printed_pin_label','printed_label','printed_pin','pin','label','display_pin')
PHYSICAL_FIELDS=('physical_pin','physical_terminal','physical_pin_label','terminal_pin','physical_pin_candidate')
PREFIX_FIELDS=('printed_prefix','printed_control_prefix','control_prefix','numeric_control_prefix','printed_numeric_prefix')
SUFFIX_FIELDS=('printed_suffix','control_suffix','printed_control_suffix','printed_output_suffix','printed_terminal_suffix','printed_numeric_suffix')
MARK_FIELDS=('printed_control','control_marker','printed_qualifier','qualifier','source_control_annotation','printed_output_marker','printed_output_qualifier','marker','printed_open_star','printed_annotation','control_qualifier','printed_wire_qualifier','printed_terminal_annotation','printed_fanout_count','fanout_count','numeric_qualifier','wire_qualifier','printed_input_qualifier','printed_local_qualifier','printed_control_qualifier','printed_numeric_qualifier','printed_terminal_asterisk','printed_asterisk','asterisk','star_qualifier','printed_numeric_control_qualifier','printed_terminal_mark','floating_wire_qualifier','inline_marker','inline_numeric_controls','printed_trailing_annotation','printed_operator','control','border_annotation','pin_qualifier','printed_connection_marker','native_printed_qualifiers','source_terminal_marker','printed_terminal_suffix')
BORDER_FIELDS=('triangle','open_wedge','triangle_in_border','triangle_on_border','source_unknown_border_wedge','native_wedge_shape','wedge_status','printed_border_marker','border_marker','border_control','border_qualifier','border_glyph','border_literal','source_border_symbol','printed_border_glyph','border_operator','printed_operator_replaces_border','native_border_qualifier','printed_border_override','border_glyph_candidates','printed_K_border_contact')
EDGE_FIELDS=('physical_border','border_side','edge','physical_side','native_physical_side','native_side','layout_side','diagram_side','source_side','geometric_side','border_corner')
GEOMETRY_FIELDS=('row','absolute_row','column','point','absolute_point','border_point','box_border_point','triangle_border_point','source_position','row_offset','text_column','label_column','label_position','wire_anchor','border_position','printed_marker_position','triangle_placement','printed_marker_placement','source_top_border','source_right_border','source_top_corner','control_column','star_column','asterisk_column','marker_column','qualifier_column','printed_control_column','printed_label_column','printed_reference_column','printed_pin_column','prefix_column','physical_border_column','printed_operator_column','operator_position','floating_wire_qualifier_column','printed_output_marker_position')
ROLE_FIELDS=('role','physical_role','electrical_role','logical_role','logical_direction','source_terminal_role','physical_port_kind','label_role','native_role','electrical_direction','source_printed_role','semantic_role','semantic_direction','printed_direction','semantic_direction_status','source_label_kind','classification','connection_kind','electrical_status','physical_pin_status','native_control_role_unresolved','unlabeled','source_unlabelled','source_unknown_pin','pin_inferred','source_unused','source_supported_unused','passive_terminal','passive_termination','native_commoned_contact','source_right_hand_sink')
ALIAS_FIELDS=('reference','printed_reference','terminal_id','internal_key','key','terminal_identity','owner','semantic_owner','net','nets')
# Do not accept bare Knn as a physical contact merely because it resembles a pin.
# Other alphabets/ranges remain legal observations for connectors/special modules.
CONTACT=re.compile(r'(?P<prefix>[0-9KLX✲*]*)(?P<contact>[A-JL-Za-jl-z][0-9]+)(?P<suffix>[XTKLxtkl0-9✲*†‡?!+\-]*)\Z')
EXPLICIT_CONTACT=re.compile(r'[A-Za-z][0-9]+\Z|[0-9]+\Z')
CONTROL_ONLY=re.compile(r'[0-9KLX✲*†‡?!+\-]+\Z')


def _type(v):
    if v is None:return 'null'
    if type(v)is bool:return 'boolean'
    if isinstance(v,str):return 'string'
    if type(v)is int:return 'integer'
    if type(v)is float:return 'number'
    if isinstance(v,list):return 'array'
    if isinstance(v,dict):return 'object'
    raise TypeError('Only JSON values are supported')

def _ptr(parent,key):return parent+'/'+str(key).replace('~','~0').replace('/','~1')
def _obs(raw,key,pointer):return {'field':key,'source_pointer':_ptr(pointer,key),'presence':'present','raw_type':_type(raw[key]),'value':deepcopy(raw[key])}
def _observations(raw,fields,pointer):return [_obs(raw,k,pointer)for k in dict.fromkeys(fields)if k in raw]
def _presence(raw,fields):return {k:'present'for k in raw}  # Complete map: an omitted key is absent, never null.
def _ord(pointer,context):
    if 'source_ordinal'in context:return deepcopy(context['source_ordinal'])
    end=pointer.rsplit('/',1)[-1]
    return int(end)if end.isascii()and end.isdigit()else None

def _label_parse(value,explicit=False):
    if not isinstance(value,str):return {'status':'explicit-null'if value is None else'non-string','pin_number':None,'prefix':'','suffix':''}
    if value=='':return {'status':'empty-label','pin_number':None,'prefix':'','suffix':''}
    if '�'in value:
        damaged=re.fullmatch(r'(?P<prefix>[0-9KLX✲*]*)(?P<contact>[A-JL-Za-jl-z�][0-9�]*)(?P<suffix>[XTKLxtkl✲*†‡?!+\-]*)',value)
        return {'status':'unreadable','pin_number':damaged['contact']if damaged else value,'prefix':damaged['prefix']if damaged else'','suffix':damaged['suffix']if damaged else''}
    # Do not strip whitespace or reinterpret a replacement glyph.
    if explicit and EXPLICIT_CONTACT.fullmatch(value):return {'status':'explicit-physical-field','pin_number':value,'prefix':'','suffix':''}
    match=CONTACT.fullmatch(value)
    if match:return {'status':'lexically-observed','pin_number':match['contact'],'prefix':match['prefix'],'suffix':match['suffix']}
    return {'status':'control-only'if CONTROL_ONLY.fullmatch(value)else'unparsed','pin_number':None,'prefix':'','suffix':''}

def _literal_marks(text,pointer,location,offset=0):
    return [{'literal':c,'source_pointer':pointer,'location':location,'literal_order':i,'label_character_offset':offset+i,'meaning':'unresolved'}for i,c in enumerate(text)]

def _terminal_record(raw_port,source_pointer,context=None):
    """Normalize exactly one raw pin occurrence without deduplicating contacts.

    context may carry source_ordinal, container_role, coordinate_frame and an
    owner/source key. Context is retained separately, never written into raw fields.
    """
    context=deepcopy(context or {});rawtype=_type(raw_port)
    result={'source_pointer':source_pointer,'source_ordinal':_ord(source_pointer,context),'raw_type':rawtype,
            'pin_number':None,'pin_number_status':'unresolved','pin_number_candidates':[],
            'printed_label':None,'printed_label_source':None,'printed_label_status':'missing',
            'symbols':{'prefix':[],'suffix':[],'other':[],'observations':[]},'border_decorations':[],
            'side':None,'role':None,'geometry':{'coordinate_frame':deepcopy(context.get('coordinate_frame')),'observations':[]},
            'endpoint_aliases':[],'raw_observations':[],'source_field_presence':{},'source_fields_consumed':[],
            'raw_extensions':[],'context':context,'issues':[]}
    if isinstance(raw_port,str):
        raw={'pin':raw_port};pointer=source_pointer
        labels=[{'field':'$scalar','source_pointer':source_pointer,'presence':'present','raw_type':'string','value':raw_port}]
    elif isinstance(raw_port,dict):
        raw=raw_port;pointer=source_pointer;labels=_observations(raw,LABEL_FIELDS,pointer)
    else:
        result['raw_extensions']=[dict(source_pointer=source_pointer,raw_type=rawtype,value=deepcopy(raw_port))]
        result['pin_number_status']='unsupported-scalar';result['issues'].append({'kind':'unsupported-terminal-shape','source_pointer':source_pointer});return result
    scalar=isinstance(raw_port,str)
    consumed=set()
    if not scalar:consumed.update(k for k in LABEL_FIELDS if k in raw)
    parsed=[]
    for observation in labels:
        parse=_label_parse(observation['value']);parsed.append({**observation,'parse':parse})
        if parse['pin_number']is not None:result['pin_number_candidates'].append(dict(value=parse['pin_number'],source_pointer=observation['source_pointer'],field=observation['field'],basis=parse['status']))
    physical=_observations(raw,PHYSICAL_FIELDS,pointer)if not scalar else[]
    for observation in physical:
        parse=_label_parse(observation['value'],explicit=observation['field']=='physical_pin')
        parsed.append({**observation,'parse':parse});consumed.add(observation['field'])
        if parse['pin_number']is not None:result['pin_number_candidates'].append(dict(value=parse['pin_number'],source_pointer=observation['source_pointer'],field=observation['field'],basis=parse['status']))
    if labels:
        # Priority is a presentation choice only; other labels and conflicts remain.
        selected=next((o for o in labels if isinstance(o['value'],str)),labels[0])
        result.update(printed_label=deepcopy(selected['value']),printed_label_source=selected['source_pointer'],printed_label_status='present-'+selected['raw_type'])
        parse=_label_parse(selected['value'])
        if parse['pin_number']is not None:
            prefix=parse['prefix'];suffix=parse['suffix'];contact=parse['pin_number']
            result['symbols']['prefix']=_literal_marks(prefix,selected['source_pointer'],'prefix')
            result['symbols']['suffix']=_literal_marks(suffix,selected['source_pointer'],'suffix',len(prefix)+len(contact))
        elif isinstance(selected['value'],str)and CONTROL_ONLY.fullmatch(selected['value']):
            result['symbols']['other']=_literal_marks(selected['value'],selected['source_pointer'],'position-unresolved')
    candidates={o['value']for o in result['pin_number_candidates']}
    explicit_none='physical_pin'in raw and raw['physical_pin']is None
    unknown=any(raw.get(k)is True for k in ('source_unknown_pin','pin_inferred'))
    damaged=any(o['parse']['status']=='unreadable'for o in parsed)
    if len(candidates)>1:
        result['pin_number_status']='conflicting-observations';result['issues'].append({'kind':'physical-contact-mirror-conflict','candidates':sorted(candidates)})
    elif unknown or (explicit_none and candidates):
        result['pin_number_status']='explicitly-unresolved';result['issues'].append({'kind':'readable-label-not-established-physical-contact','explicit_physical_null':explicit_none,'unknown_or_inferred_source_flag':unknown})
    elif damaged and candidates:
        result['pin_number']=next(iter(candidates));result['pin_number_status']='unreadable';result['issues'].append({'kind':'damaged-label-mirror-retained'})
    elif candidates:
        result['pin_number']=next(iter(candidates));result['pin_number_status']='observed'
    elif damaged:result['pin_number_status']='unreadable'
    elif explicit_none:result['pin_number_status']='explicit-none'
    elif not labels and not physical:result['pin_number_status']='missing'
    elif all(o['value']in(None,'')for o in labels+physical):result['pin_number_status']='unlabeled'
    else:result['pin_number_status']='unparsed-or-control'
    result['raw_observations']=parsed
    for field,position in [(k,'prefix')for k in PREFIX_FIELDS]+[(k,'suffix')for k in SUFFIX_FIELDS]+[(k,'position-unresolved')for k in MARK_FIELDS]:
        if field in raw and field not in consumed:
            o=_obs(raw,field,pointer);o['declared_position']=position;result['symbols']['observations'].append(o);consumed.add(field)
            if isinstance(raw[field],str):result['symbols']['other'].extend(_literal_marks(raw[field],o['source_pointer'],position))
    edges=_observations(raw,EDGE_FIELDS,pointer);positions=_observations(raw,('border_point','box_border_point','triangle_border_point','printed_marker_position','triangle_placement','printed_marker_placement'),pointer)
    for field in BORDER_FIELDS:
        if field in raw:
            o=_obs(raw,field,pointer);o.update(kind='triangle'if 'triangle'in field or field in ('open_wedge','native_wedge_shape','wedge_status')else'literal-border-mark',glyph=raw[field]if isinstance(raw[field],str)else None,edge_observations=deepcopy(edges),position_observations=deepcopy(positions))
            result['border_decorations'].append(o);consumed.add(field)
    result['geometry']['observations']=_observations(raw,GEOMETRY_FIELDS,pointer)
    result['geometry']['edge_observations']=edges
    consumed.update(k for k in GEOMETRY_FIELDS+EDGE_FIELDS if k in raw)
    if 'side'in raw:result['side']=deepcopy(raw['side']);consumed.add('side')
    result['role_observations']=_observations(raw,ROLE_FIELDS,pointer);consumed.update(k for k in ROLE_FIELDS if k in raw)
    if 'role'in raw:result['role']=deepcopy(raw['role'])
    result['endpoint_aliases']=_observations(raw,ALIAS_FIELDS,pointer);consumed.update(k for k in ALIAS_FIELDS if k in raw)
    recognized=LABEL_FIELDS+PHYSICAL_FIELDS+PREFIX_FIELDS+SUFFIX_FIELDS+MARK_FIELDS+BORDER_FIELDS+EDGE_FIELDS+GEOMETRY_FIELDS+ROLE_FIELDS+ALIAS_FIELDS+('side',)
    result['source_field_presence']={}if scalar else _presence(raw,recognized)
    result['source_field_presence_is_complete']=not scalar
    result['source_fields_consumed']=[source_pointer]if scalar else[_ptr(pointer,k)for k in raw if k in consumed]
    result['raw_extensions']=[]if scalar else[_obs(raw,k,pointer)for k in raw if k not in consumed]
    if 'row'in raw and'absolute_row'in raw and raw['row']!=raw['absolute_row']:
        result['issues'].append({'kind':'distinct-source-coordinate-frames','fields':[_ptr(pointer,'row'),_ptr(pointer,'absolute_row')],'action':'both values retained; no coordinate conversion'})
    return result


ARRAY_TERMINAL_FIELDS={'pins':None,'input_pins':'input','output_pins':'output','printed_inputs':'input','printed_outputs':'output','inputs':'input','outputs':'output','terminals':None,'ports':None}
SCALAR_TERMINAL_FIELDS={'input_pin':'input','output_pin':'output','input':'input','output':'output','upper_input':'input','lower_input':'input','input_upper':'input','input_lower':'input','output_upper':'output','output_lower':'output','upper_output':'output','lower_output':'output'}

def _collect_records(raw_object,source_pointer='',context=None):
    """Collect source occurrences and uniquely proved scalar/array mirrors.

    Primary pins[] multiplicity is always preserved. Other declarations have an
    alias link only on one exact contact, compatible declared side, and (if both
    supply it) identical row. Ambiguous mirrors remain observations, not a new
    asserted physical terminal. No union of duplicate contacts is performed.
    """
    context=deepcopy(context or {});terminals=[];aliases=[];issues=[];consumed=[]
    if not isinstance(raw_object,dict):return {'terminals':[],'alias_claims':[],'issues':[{'kind':'object-not-dictionary','source_pointer':source_pointer}],'source_fields_consumed':[]}
    for field,declared in list(ARRAY_TERMINAL_FIELDS.items())+list(SCALAR_TERMINAL_FIELDS.items()):
        if field not in raw_object:continue
        value=raw_object[field];base=_ptr(source_pointer,field)
        entries=list(enumerate(value))if field in ARRAY_TERMINAL_FIELDS and isinstance(value,list)else[(None,value)]
        for ordinal,entry in entries:
            ptr=_ptr(base,ordinal)if ordinal is not None else base
            local={**context,'container_field':field,'container_role':declared,'source_ordinal':ordinal}
            t=_terminal_record(entry,ptr,local);t['source_collection_field']=field;t['primary_occurrence']=field=='pins'or not isinstance(raw_object.get('pins'),list)
            choices=[]
            if field!='pins'and t['pin_number']is not None:
                for prior in terminals:
                    if prior.get('source_collection_field')!='pins'or prior['pin_number']!=t['pin_number']:continue
                    pside=prior.get('side');nside=t.get('side')or declared
                    if nside is not None and pside is not None and nside!=pside:continue
                    pgeom={o['field']:o['value']for o in prior['geometry']['observations']};ngeom={o['field']:o['value']for o in t['geometry']['observations']}
                    if 'row'in pgeom and'row'in ngeom and pgeom['row']!=ngeom['row']:continue
                    choices.append(prior)
            if len(choices)==1:
                aliases.append({'source_pointer':ptr,'target_source_pointer':choices[0]['source_pointer'],'basis':'unique exact contact/compatible declared side/row','observation':t})
            else:
                if field!='pins'and choices:
                    t['issues'].append({'kind':'ambiguous-terminal-alias','candidates':[x['source_pointer']for x in choices]})
                if field!='pins'and isinstance(raw_object.get('pins'),list):t['physical_identity_status']='unresolved-alternate-observation'
                terminals.append(t)
        consumed.append(base)
    # Programmed-ground boxes use explicit paired printed_pins with undetermined
    # directions. Each occurrence is retained; the U route is not interpreted.
    if isinstance(raw_object.get('stub_pairs'),list):
        for i,pair in enumerate(raw_object['stub_pairs']):
            if not isinstance(pair,dict)or not isinstance(pair.get('printed_pins'),list):continue
            for j,entry in enumerate(pair['printed_pins']):
                ptr=_ptr(_ptr(_ptr(source_pointer,'stub_pairs'),i),'printed_pins');ptr=_ptr(ptr,j)
                local={**context,'container_field':'stub_pairs.printed_pins','source_ordinal':j,'declared_direction':deepcopy(pair.get('direction')),'paired_rows_observation':{'source_pointer':_ptr(_ptr(_ptr(source_pointer,'stub_pairs'),i),'rows'),'value':deepcopy(pair.get('rows'))}}
                t=_terminal_record(entry,ptr,local);t['source_collection_field']='stub_pairs.printed_pins';t['primary_occurrence']=True;terminals.append(t)
        if all(isinstance(p,dict)and isinstance(p.get('printed_pins'),list)for p in raw_object['stub_pairs']):consumed.append(_ptr(source_pointer,'stub_pairs'))
        else:issues.append({'kind':'unsupported-stub-pair-shape','source_pointer':_ptr(source_pointer,'stub_pairs'),'action':'not marked consumed'})
    return {'terminals':terminals,'alias_claims':aliases,'issues':issues,'source_fields_consumed':consumed}

ENDPOINT_FIELDS=('pin','literal_forward_pin','driver','drivers','semantic_driver','source_driver','targets','ports','terminals','connected','source','destination','destinations','connector','connectors','connector_pin','destination_pin','source_pin','input_pin','output_pin','entry_pin','through_port','external','external_input','external_outputs','external_destinations','external_references','external_aliases','source_reference','destination_reference','output_reference','printed_external_reference','additional_same_block_drivers','additional_drivers','driver_aliases','commoned_outputs','same_block_output_drivers','external_source_drivers','candidate_origins','physical_output_ports','additional_driver_outputs','passive_outputs','same_block_drivers','additional_driver_ports','additional_driver_pins','same_block_output_ports','co_drivers','grounded_pins','declared_physical_output_drivers','physical_drivers','physical_driver_contacts','native_external_drivers','commoned_output_drivers','commoned_output_ports','same_block_commoned_outputs','additional_physical_driver_ports','additional_source_drivers','additional_printed_origins','additional_external_sources','additional_external_origins','candidate_driver','external_origin_references','passive_terminals','jumper_terminals','physical_commoning_evidence','native_commoned_output_drivers','additional_driver_sources','additional_source_labels','additional_printed_outputs','additional_printed_output_coordinates','passive_entry_feeds','commoned_nonlogical_ports','connected_role_unresolved_ports')
ROUTE_FIELDS=('edges','paths','cells','wire_cells','bounds','drawn','driver_coordinate','target_coordinates','external_points','geometric_connectivity','geometric_label_bridges','external_origin_point','isolated_native_segment','zero_length_source_stub','native_geometric_origin','physical_driver_fragment','output_rows','vertical_column','trunk_column','bus_column','join_column','transfer_column','fanout_column','diagram_row','row','input_row','output_row','top_row','bottom_row','upper_row','lower_row','primary_reference_row','secondary_reference_row','route_owners')
JUNCTION_FIELDS=('joined_diamonds','source_diamond_at','source_join_evidence','same_block_output_join','same_block_output_connection','same_block_physical_outputs_joined','native_wired_OR','electrical_continuity_verified','connection_kind','passive_connection','geometric_connectivity')
CROSSING_FIELDS=('unjoined_crosses','unjoined_endpoint_crossing','separate_from','printed_gap','source_gap_exception')
UNCERTAINTY_FIELDS=('candidate_edges','uncertain_edges','candidate_edges_including_uncertainties','rendered_edges_including_uncertain_fragments','uncertain_rendered_edges','candidate_fragment_association','candidate_fragment_associations','uncertain_corresponding_fragments','uncertain_external_correspondence','fragment_ownership','unresolved_source_association','scan_gap_uncertainties','electrical_driver_unresolved','source_driver_unresolved','electrical_driver_status','undriven_kind','source_undriven','driver_condition','source_damage','source_wire_status','source_label_status')

def _net_record(raw_net,source_pointer,context=None):
    """Preserve literal endpoint, route, join and crossing claims independently.

    A field named driver is a raw claim, not evidence that the normalizer has
    resolved a driver. Geometry/crossings never create additional incidences.
    """
    context=deepcopy(context or {});result={'source_pointer':source_pointer,'source_ordinal':_ord(source_pointer,context),'raw_type':_type(raw_net),'literal_id':None,'endpoint_field_observations':[],'endpoint_claims':[],'route_geometry':[],'junction_claims':[],'crossing_claims':[],'uncertainty_claims':[],'source_field_presence':{},'source_fields_consumed':[],'raw_extensions':[],'context':context,'issues':[],'connectivity_inference_applied':False}
    if not isinstance(raw_net,dict):
        result['raw_extensions']=[dict(source_pointer=source_pointer,raw_type=_type(raw_net),value=deepcopy(raw_net))];result['issues'].append({'kind':'unsupported-net-shape'});return result
    consumed=set()
    if'id'in raw_net:result['literal_id']=deepcopy(raw_net['id']);result['literal_id_observation']=_obs(raw_net,'id',source_pointer);consumed.add('id')
    result['endpoint_field_observations']=_observations(raw_net,ENDPOINT_FIELDS,source_pointer)
    for field in ENDPOINT_FIELDS:
        if field not in raw_net:continue
        raw=raw_net[field];values=list(enumerate(raw))if isinstance(raw,list)else[(None,raw)]
        for i,value in values:
            pointer=_ptr(_ptr(source_pointer,field),i)if i is not None else _ptr(source_pointer,field)
            result['endpoint_claims'].append(dict(source_pointer=pointer,source_field=field,source_ordinal=i,value=deepcopy(value),raw_type=_type(value),role_claim=field,resolution_status='literal-unresolved',terminal_bindings=[]))
        consumed.add(field)
    for key,fields in [('route_geometry',ROUTE_FIELDS),('junction_claims',JUNCTION_FIELDS),('crossing_claims',CROSSING_FIELDS),('uncertainty_claims',UNCERTAINTY_FIELDS)]:
        result[key]=_observations(raw_net,fields,source_pointer);consumed.update(k for k in fields if k in raw_net)
    result['source_field_presence']=_presence(raw_net,('id',)+ENDPOINT_FIELDS+ROUTE_FIELDS+JUNCTION_FIELDS+CROSSING_FIELDS+UNCERTAINTY_FIELDS)
    result['source_field_presence_is_complete']=True
    result['source_fields_consumed']=[_ptr(source_pointer,k)for k in raw_net if k in consumed]
    result['raw_extensions']=[_obs(raw_net,k,source_pointer)for k in raw_net if k not in consumed]
    return result

# Presentation/provenance split. These keys describe review history/evidence,
# never additional observed terminal incidence or geometry.
_HISTORY_TOKEN=re.compile(r'(?:^|_)(?:notes?|evidence|review(?:ed)?|provenance|history|proof|certification|verification|interpretation|explanation|reason|crop|recovery|acceptance|approval|timestamp|sha256|hash|binding)(?:_|$)|(?:_verified|_certified)$')

def _history_field(field):return bool(_HISTORY_TOKEN.search(str(field)))
def _facts(value):
    """Keep current unknown facts, place explanatory/history fields in provenance."""
    if isinstance(value,dict):return {k:_facts(v)for k,v in value.items()if not _history_field(k)and k not in ('source_pointer','source_fields_consumed')}
    if isinstance(value,list):return [_facts(v)for v in value]
    return deepcopy(value)

def _field_facts(observations):
    return [{'kind':o['field'],'value':_facts(o['value'])}for o in observations if not _history_field(o['field'])]

def _mark_facts(record):
    # A mark pattern has one identity. Different raw mirror observations point
    # at it; selected presentation is a reference, not a second mark occurrence.
    result={'prefix':[],'suffix':[],'unplaced':[],'observations':[],
            'selected_presentation':None,
            'sequence_status':'ordered within each literal observation; cross-observation placement is not inferred'}
    next_id=0
    def group(text,position):
        nonlocal next_id
        if not isinstance(text,str)or not text:return []
        seq=[{'literal':c,'order':i,'meaning_status':'uninterpreted'}for i,c in enumerate(text)]
        target=result[position]
        existing=next((g for g in target if g['marks']==seq),None)
        if existing is None:
            existing={'mark_id':'m:'+str(next_id),'marks':seq};next_id+=1;target.append(existing)
        return [existing['mark_id']]
    for i,o in enumerate(record['raw_observations']):
        # All literal label mirrors participate, not just the chosen display.
        parse=o['parse'];selected=o['source_pointer']==record['printed_label_source']
        claim={'observation_id':'label:'+str(i),'prefix_mark_ids':group(parse.get('prefix',''),'prefix'),
               'suffix_mark_ids':group(parse.get('suffix',''),'suffix'),'unplaced_mark_ids':[],
               'selected_presentation':selected}
        if parse['status']=='control-only'and isinstance(o['value'],str):claim['unplaced_mark_ids']=group(o['value'],'unplaced')
        result['observations'].append(claim)
        if selected:result['selected_presentation']={k:deepcopy(v)for k,v in claim.items()if k!='selected_presentation'}
    for i,o in enumerate(record['symbols']['observations']):
        position=o['declared_position'];position=position if position in ('prefix','suffix')else'unplaced'
        claim={'observation_id':'mark-field:'+str(i),'prefix_mark_ids':[],'suffix_mark_ids':[],'unplaced_mark_ids':[],
               'selected_presentation':False}
        claim[position+'_mark_ids']=group(o['value'],position)
        if o['value']is not None and not isinstance(o['value'],str):claim['current_value']=_facts(o['value']);claim['value_type']=o['raw_type'];claim['declared_position']=position
        result['observations'].append(claim)
    return result

def _terminal_split(record):
    geometry={o['field']:deepcopy(o['value'])for o in record['geometry']['observations']}
    if record['geometry'].get('coordinate_frame')is not None:geometry['declared_coordinate_frame']=deepcopy(record['geometry']['coordinate_frame'])
    geometry['edge_observations']=_field_facts(record['geometry'].get('edge_observations',[]))
    decorations=[]
    for o in record['border_decorations']:
        edges=[e['value']for e in o['edge_observations']if e['value']is not None]
        same_edges=all(e==edges[0]for e in edges)if edges else False
        decorations.append({'kind':o['kind'],'glyph':o['glyph'],'observed_value':deepcopy(o['value']),
                            'edge':deepcopy(edges[0])if same_edges else None,
                            'edge_status':'observed'if same_edges else'conflicting-observations'if edges else'unspecified',
                            'position_observations':_field_facts(o['position_observations'])})
    extensions={o['field']:_facts(o['value'])for o in record['raw_extensions']if 'field'in o and not _history_field(o['field'])}
    data={'pin_number':record['pin_number'],'pin_number_status':record['pin_number_status'],
          'symbols':_mark_facts(record),'border_decorations':decorations,'side':deepcopy(record['side']),'declared_container_role':deepcopy(record['context'].get('container_role')),
          'role':deepcopy(record['role']),'role_observations':_field_facts(record.get('role_observations',[])),
          'geometry':geometry,'endpoint_aliases':[{'kind':o['field'],'claim':_endpoint_facts(o['value'])}for o in record['endpoint_aliases']],'extensions':extensions}
    if record['pin_number_status']=='conflicting-observations':data['pin_number_alternatives']=list(dict.fromkeys(c['value']for c in record['pin_number_candidates']))
    # Unknown current semantic labels stay usable in the clean view, while
    # complete successfully parsed printed labels remain only in provenance.
    unresolved=[]
    for i,o in enumerate(record['raw_observations']):
        if o['parse']['status']in ('unparsed','non-string'):
            unresolved.append({'observation_id':'label:'+str(i),'current_value':_facts(o['value']),
                               'raw_type':o['raw_type'],'parse_status':o['parse']['status']})
    if unresolved:data['current_unparsed_label_observations']=unresolved
    if record['pin_number_status']=='unsupported-scalar':data['uninterpreted_value']=_facts(record['raw_extensions'][0]['value'])
    provenance=deepcopy(record)
    provenance['symbol_observation_sources']=[{'observation_id':'label:'+str(i),'source_pointer':o['source_pointer'],'field':o['field']}
        for i,o in enumerate(record['raw_observations'])]+[{'observation_id':'mark-field:'+str(i),'source_pointer':o['source_pointer'],'field':o['field']}
        for i,o in enumerate(record['symbols']['observations'])]
    return {'data':data,'provenance':provenance}

def normalize_terminal(raw_port,source_pointer,context=None):
    """Return {data,provenance}; printed_label and mapping/history are provenance."""
    return _terminal_split(_terminal_record(raw_port,source_pointer,context))

def collect_terminals(raw_object,source_pointer='',context=None):
    """Return clean terminal facts and separate source mapping/provenance.

    IDs t:0,t:1,... are deterministic local identities, not printed source IDs.
    The caller namespaces them with its normalized containing-object identity.
    """
    records=_collect_records(raw_object,source_pointer,context);split=[_terminal_split(t)for t in records['terminals']]
    pointer_ids={t['source_pointer']:'t:'+str(i)for i,t in enumerate(records['terminals'])}
    terminals=[]
    for i,s in enumerate(split):
        s['data']['terminal_id']='t:'+str(i)
        s['data']['occurrence_kind']='primary'if records['terminals'][i].get('primary_occurrence')else'alternate-unresolved-observation'
        terminals.append(s['data'])
    alias_relationships=[]
    for claim in records['alias_claims']:
        observed=_terminal_split(claim['observation'])
        alias_relationships.append({'terminal_id':pointer_ids[claim['target_source_pointer']],
                                    'relationship':'unique-source-mirror','alias_observation':observed['data']})
    pairs=[];groups=[]
    if isinstance(raw_object,dict):
        for i,pair in enumerate(raw_object.get('stub_pairs',[])if isinstance(raw_object.get('stub_pairs'),list)else[]):
            if not isinstance(pair,dict):continue
            base=_ptr(_ptr(source_pointer,'stub_pairs'),i)
            ids=[pointer_ids[_ptr(_ptr(base,'printed_pins'),j)]for j in range(len(pair.get('printed_pins',[])))if _ptr(_ptr(base,'printed_pins'),j)in pointer_ids]
            facts={k:_facts(v)for k,v in pair.items()if k!='printed_pins'and not _history_field(k)}
            pairs.append({'kind':'programmed-ground-stub-pair','terminal_ids':ids,'observed_pair_fields':facts,'electrical_inference_applied':False})
        if isinstance(raw_object.get('pins'),list)and any(k in raw_object for k in ('source_references','routes','input_signals','output_signals','box_location')):
            group_fields=('source_references','routes','input_signals','output_signals','box_location','destination_reference','output_ids','first_row','row_count','ce')
            groups.append({'kind':'declared-container-membership','terminal_ids':[pointer_ids[t['source_pointer']]for t in records['terminals']if t.get('source_collection_field')=='pins'],
                           'observed_group_fields':{k:_facts(raw_object[k])for k in group_fields if k in raw_object},'electrical_inference_applied':False})
            records['source_fields_consumed'].extend(_ptr(source_pointer,k)for k in group_fields if k in raw_object)
    provenance={'source_pointer':source_pointer,'terminals':[s['provenance']for s in split],
                'alias_claims':deepcopy(records['alias_claims']),'source_fields_consumed':list(dict.fromkeys(records['source_fields_consumed'])),
                'issues':deepcopy(records['issues'])}
    if isinstance(raw_object,dict):
        provenance['paired_and_group_source_fields']={k:deepcopy(raw_object[k])for k in ('stub_pairs','source_references','routes','input_signals','output_signals','box_location','destination_reference','output_ids','first_row','row_count','ce')if k in raw_object}
    return {'data':{'terminals':terminals,'alias_relationships':alias_relationships,'terminal_pairs':pairs,'group_memberships':groups},'provenance':provenance}

def normalize_net(raw_net,source_pointer,context=None):
    """Return observed net facts only, with all raw claims/evidence kept separately."""
    record=_net_record(raw_net,source_pointer,context)
    endpoint=[]
    for o in record['endpoint_claims']:
        if not _history_field(o['source_field']):endpoint.append({'role_category':_relationship_category(o['role_claim']),'relationship':o['role_claim'],'order':o['source_ordinal'],'reference':_endpoint_facts(o['value']),'resolution_status':'source-claim-unresolved'})
    extensions={o['field']:_facts(o['value'])for o in record['raw_extensions']if 'field'in o and not _history_field(o['field'])}
    data={'literal_id':deepcopy(record['literal_id']),'endpoint_collections':[{'role_claim':o['field'],'representation':o['raw_type'],'item_count':len(o['value'])if isinstance(o['value'],list)else None}for o in record['endpoint_field_observations']if not _history_field(o['field'])],'endpoint_claims':endpoint,
          'routes':_field_facts(record['route_geometry']),'junctions':_field_facts(record['junction_claims']),
          'crossings':_field_facts(record['crossing_claims']),'unresolved_current_claims':_field_facts(record['uncertainty_claims']),
          'extensions':extensions,'connectivity_inference_applied':False}
    if record['raw_type']!='object':data['uninterpreted_value']=_facts(raw_net);data['projection_status']='unsupported-current-shape-preserved'
    return {'data':data,'provenance':record}

# Endpoint syntax decomposition is representational only. Object/terminal matching
# remains the caller's separate exact-unique lookup, never a connectivity inference.
PORT_SEMANTIC=re.compile(r'(?:input|output|in|out)(?:[-_:](?:upper|lower|[0-9]+)|[0-9]+)?\Z|[io][0-9]+\Z|(?:IN|OUT)[0-9]*\Z')
OBJECT_PORT=re.compile(r'(?P<object>[A-Za-z0-9_-]+)\.(?P<port>.+)\Z')

def _contact_facts(label):
    record=_terminal_record(label,'',{})
    return {k:v for k,v in _terminal_split(record)['data'].items()if k in ('pin_number','pin_number_status','pin_number_alternatives','symbols','border_decorations')}

def _endpoint_facts(value):
    """Source reference syntax only; no source-ID or electrical membership lookup."""
    if isinstance(value,str):
        match=OBJECT_PORT.fullmatch(value)
        obj=match['object']if match else None;port=match['port']if match else value
        role=None
        rolematch=re.fullmatch(r'(input|output)[.:-](.+)',port)
        if rolematch:role=rolematch[1];candidate=rolematch[2]
        else:candidate=port
        rowmatch=re.fullmatch(r'(.+)@(?:row)?([0-9]+)',candidate)
        row_qualifier=rowmatch[2]if rowmatch else None
        if rowmatch:candidate=rowmatch[1]
        if PORT_SEMANTIC.fullmatch(port):return {'kind':'terminal-reference','object_identifier':obj,'port_semantic_id':port,'parse_status':'source-semantic-id-syntax'}
        parsed=_label_parse(candidate)
        if parsed['pin_number']is not None or parsed['status']=='control-only':
            result={'kind':'terminal-reference','object_identifier':obj,'terminal':_contact_facts(candidate),'declared_role':role,'parse_status':'source-contact-syntax'if parsed['status']!='unreadable'else'unreadable-contact-syntax'}
            if row_qualifier is not None:result['row_qualifier_literal']=row_qualifier
            return result
        if PORT_SEMANTIC.fullmatch(port):return {'kind':'terminal-reference','object_identifier':obj,'port_semantic_id':port,'parse_status':'source-semantic-id-syntax'}
        if match:return {'kind':'unparsed-object-reference','object_identifier':obj,'port_reference_text':port,'parse_status':'unresolved-source-syntax'}
        return {'kind':'external-or-unparsed-reference','reference_text':value,'parse_status':'unresolved-source-syntax'}
    if isinstance(value,dict):
        owner_fields=('node','block','owner','object','object_id','node_id','block_id')
        pin_fields=('pin','physical_pin','physical_terminal','printed_pin','printed_label','terminal_pin')
        semantic_fields=('port','terminal','port_id','terminal_id','semantic_id')
        owners=[deepcopy(value[k])for k in owner_fields if k in value]
        unique=[]
        for o in owners:
            if not any(type(o)is type(u)and o==u for u in unique):unique.append(o)
        result={'kind':'structured-terminal-or-reference-claim','object_identifier':unique[0]if len(unique)==1 else None,'parse_status':'declared-fields-unresolved','extensions':{}}
        if len(unique)>1:result['object_identifier_alternatives']=unique;result['parse_status']='conflicting-object-observations'
        projected=set(owner_fields)&set(value)
        terminal_raw={k:deepcopy(value[k])for k in pin_fields if k in value}
        for key in ('side','role','triangle','border_marker','physical_border','border_point','row','absolute_row','point','absolute_point'):
            if key in value:terminal_raw[key]=deepcopy(value[key])
        if terminal_raw:
            terminal=_terminal_split(_terminal_record(terminal_raw,'',{}))['data'];result['terminal']=terminal;projected.update(terminal_raw)
        semantics=[value[k]for k in semantic_fields if k in value]
        if semantics:
            result['port_claims']=[_endpoint_facts(v)for v in semantics];projected.update(k for k in semantic_fields if k in value)
        for k,v in value.items():
            if k in projected or _history_field(k):continue
            if isinstance(k,str)and OBJECT_PORT.fullmatch(k):
                result.setdefault('named_endpoint_members',[]).append({'reference':_endpoint_facts(k),'current_value':_facts(v)});continue
            if k in ('reference','endpoint','source','target','from','to','driver','destination','port_reference'):
                result['extensions'][k]=_endpoint_facts(v)
            else:result['extensions'][k]=_facts(v)
        return result
    if isinstance(value,list):return {'kind':'ordered-reference-group','members':[_endpoint_facts(v)for v in value],'parse_status':'group-preserved-no-union'}
    return {'kind':'opaque-reference-value','value':deepcopy(value),'raw_type':_type(value),'parse_status':'unsupported-reference-syntax'}

def _relationship_category(field):
    if field in ('driver','drivers','source_driver','semantic_driver')or'driver'in field:return 'declared-driver'
    if field in ('targets','destination','destinations','external_destinations'):return 'declared-target'
    if'passive'in field:return 'passive-membership'
    return 'declared-membership-or-reference'

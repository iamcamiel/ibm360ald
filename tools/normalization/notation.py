"""Canonical current notation. Legacy conversion is explicit, never a write fallback."""
from copy import deepcopy
import json,re

PIN_KEYS={'pin','pin_status','printed_label','reference','references','side','row','column','point','label_column',
          'border_point','triangle','border_marker','printed_prefix','printed_suffix',
          'occurrence_kind','source_observations'}
COLLECTIONS=('pins','inputs','outputs','input_pins','output_pins','printed_inputs','printed_outputs',
             'terminals','ports','input_pin','output_pin','input','output','upper_input',
             'lower_input','input_upper','input_lower','output_upper','output_lower','upper_output','lower_output')
HEIGHTS=('height','height_rows','height_including_edges','total_rows','box_height')

def exact(a,b):return type(a)is type(b)and a==b

def convert(raw,text):
    """Return one canonical spelling and an exact old-pointer/new-pointer map.

    Unknown source evidence is retained as typed observations, never interpreted
    as an alternative active pin, coordinate or electrical connection.
    """
    import layout
    from terminals import normalize_terminal,collect_terminals
    old=deepcopy(raw);new=deepcopy(raw);mapping={};changes=[]
    declared_refs=set()
    for net in old.get('nets',[])if isinstance(old.get('nets'),list)else[]:
        if not isinstance(net,dict):continue
        for value in[net.get('driver'),*(net.get('targets')if isinstance(net.get('targets'),list)else[])]:
            if isinstance(value,str):declared_refs.add(value)
    def observe(record,key,value):
        entries=record.setdefault('source_observations',[])
        index=len(entries);entries.append(dict(field=key,value=deepcopy(value)))
        return '/source_observations/'+str(index)+'/value'
    def pin_record(value,role,path):
        source=value if isinstance(value,dict)else{'printed_label':value}
        parsed=normalize_terminal(value,path)['data']
        number=parsed['pin_number'] if parsed['pin_number_status'] in ('resolved','parsed') else parsed['pin_number']
        label=next((source[k]for k in('printed_combined_label','raw_printed_pin_field','printed_pin_label','printed_label','printed_pin','pin','label','display_pin')if isinstance(source.get(k),str)),value if isinstance(value,str)else '')
        row=source.get('row',source.get('absolute_row'))
        point=source.get('point',source.get('absolute_point'))
        border=source.get('border_point',source.get('box_border_point',source.get('triangle_border_point')))
        triangle=source.get('triangle',source.get('triangle_in_border',source.get('triangle_on_border')))
        side=source.get('side',role)
        result=dict(pin=number,pin_status=source.get('pin_status',parsed['pin_number_status']),printed_label=label,reference=source.get('reference'),references=deepcopy(source.get('references',[])),side=side,
                    row=row,column=source.get('column'),point=deepcopy(point),
                    label_column=source.get('label_column',source.get('text_column')),
                    border_point=deepcopy(border),triangle=triangle,
                    border_marker=deepcopy(source.get('border_marker',source.get('printed_border_marker'))),
                    printed_prefix=deepcopy(source.get('printed_prefix',source.get('printed_control_prefix',source.get('control_prefix',source.get('numeric_control_prefix',source.get('printed_numeric_prefix')))))),
                    printed_suffix=deepcopy(source.get('printed_suffix',source.get('control_suffix',source.get('printed_control_suffix',source.get('printed_output_suffix'))))),
                    occurrence_kind=source.get('occurrence_kind','primary'),source_observations=[])
        # Preserve explicit named pinless references. Never invent a pin number.
        if result['reference'] is None and isinstance(source.get('terminal_id'),str):result['reference']=source['terminal_id']
        for key in('row','column','label_column'):
            if type(result[key])is not int:result[key]=None
        for key in('point','border_point'):
            if not(isinstance(result[key],list)and len(result[key])==2 and all(type(n)is int for n in result[key])):result[key]=None
        if result['side']not in('input','output'):result['side']=None
        if type(result['triangle'])is not bool:result['triangle']=None
        if not isinstance(result['reference'],str):result['reference']=None
        pmap={}
        for key,v in source.items():
            if key=='source_observations':
                offset=len(result['source_observations']);result['source_observations']+=deepcopy(v)
                for i in range(len(v)):pmap['/'+key+'/'+str(i)]='/source_observations/'+str(offset+i)
                continue
            preferred={'physical_pin':'pin','printed_pin':'pin','physical_terminal':'pin','terminal_pin':'pin',
                       'absolute_row':'row','absolute_point':'point','box_border_point':'border_point',
                       'triangle_border_point':'border_point','text_column':'label_column',
                       'triangle_in_border':'triangle','triangle_on_border':'triangle'}.get(key,key)
            if preferred in result and exact(result[preferred],v):pmap['/'+key]='/'+preferred
            else:pmap['/'+key]=observe(result,key,v)
        if not isinstance(value,dict):pmap['']='/printed_label' if exact(result['printed_label'],value)else observe(result,'$value',value)
        return result,pmap
    # Exact drawn own-footer geometry establishes one height convention.
    probe=deepcopy(old)
    for field in('nodes','boxes','groups','CAS_boxes'):
        if not isinstance(probe.get(field),list):continue
        for node in probe[field]:
            if isinstance(node,dict):
                for key in HEIGHTS:node.pop(key,None)
    discovered=layout.discover(probe,layout._split_bytes(text)[1])
    frames={b['owner']:b for b in discovered['object_boxes']}
    for container in('nodes','boxes','groups','CAS_boxes'):
        if not isinstance(new.get(container),list):continue
        for ni,node in enumerate(new[container]):
            if not isinstance(node,dict):continue
            base='/'+container+'/'+str(ni);original=old[container][ni]
            frame=frames.get(container+':'+str(ni))
            for key in HEIGHTS:
                if key in node:
                    v=node.pop(key);newkey='height'if frame and v==frame['bottom']-frame['top']else None
                    mapping[base+'/'+key]=base+'/'+newkey if newkey else base+observe(node,key,v)
            node['height']=frame['bottom']-frame['top']if frame else None
            if 'height_rows'in node:raise ValueError('Height alias survived')
            # Primary occurrence order follows the established terminal mapper.
            projected=collect_terminals(original,base)
            primary={t['source_pointer']:t for t in projected['provenance']['terminals']}
            aliases={a['source_pointer']:a for a in projected['provenance']['alias_claims']}
            pins=[];observations=[]
            for field in COLLECTIONS:
                if field not in original:continue
                values=original[field]if isinstance(original[field],list)else[original[field]]
                array=isinstance(original[field],list)
                if array and not values and field!='pins':
                    mapping[base+'/'+field]=base+observe(node,field,values)
                for pi,value in enumerate(values):
                    path=base+'/'+field+('/'+str(pi)if array else'')
                    role='input'if'input'in field else'output'if'output'in field else None
                    pin,pmap=pin_record(value,role,path)
                    if path in aliases:
                        oi=len(observations);observations.append(dict(field=field,value=deepcopy(value)))
                        dest=base+'/terminal_observations/'+str(oi)+'/value'
                        mapping[path]=dest
                        continue
                    record=primary.get(path)
                    if record and not record.get('primary_occurrence'):pin['occurrence_kind']='alternate-unresolved-observation'
                    if isinstance(value,dict)and frame and pin['row']is not None and pin['side']in('input','output')and pin['point']is None:
                        physical=next((value[k]for k in('physical_pin','printed_pin','pin')if isinstance(value.get(k),str)and value[k]),'')
                        border=frame['left']if pin['side']=='input'else frame['right']
                        label_column=value.get('label_column',value.get('text_column'))
                        anchor=label_column-1 if type(label_column)is int and pin['side']=='input'else label_column+len(physical)if type(label_column)is int else border-len(physical)-1 if pin['side']=='input'else border+len(physical)+1
                        pin['point']=[anchor,pin['row']]
                    if pin['reference']is None and isinstance(original.get('id'),str)and pin['side']in('input','output'):
                        owner=original['id'];names={owner+'.'+pin['side']}
                        if pin['row']is not None:names.add(owner+'.'+pin['side']+str(pin['row']))
                        literal=next((value[k]for k in('physical_pin','printed_pin','pin')if isinstance(value,dict)and isinstance(value.get(k),str)and value[k]),'')
                        if literal:names.add(owner+'.'+literal)
                        pin['references']=sorted(names&declared_refs)
                        if len(pin['references'])==1:pin['reference']=pin['references'][0]
                    dest=base+'/pins/'+str(len(pins));pins.append(pin)
                    mapping[path]=dest
                    for suffix,target in pmap.items():mapping[path+suffix]=dest+target
                node.pop(field,None)
            if pins or any(f in original for f in COLLECTIONS):node['pins']=pins
            if observations:node['terminal_observations']=observations
    labels=new.get('printed_labels')
    if isinstance(labels,list):
        for i,value in enumerate(deepcopy(labels)):
            base='/printed_labels/'+str(i)
            if isinstance(value,dict):
                label=deepcopy(value)
                if 'literal'in label:
                    v=label.pop('literal')
                    if 'text'not in label:label['text']=v;mapping[base+'/literal']=base+'/text'
                    elif not exact(label['text'],v):mapping[base+'/literal']=base+observe(label,'literal',v)
                    else:mapping[base+'/literal']=base+'/text'
                label.setdefault('column',None);label.setdefault('row',None);label.setdefault('text','')
            elif isinstance(value,list)and len(value)==3:
                label=dict(column=value[0],row=value[1],text=value[2])
                for j,key in enumerate(('column','row','text')):mapping[base+'/'+str(j)]=base+'/'+key
            else:
                label=dict(column=None,row=None,text=value if isinstance(value,str)else'',source_observations=[dict(field='$value',value=value)])
                mapping[base]=base+'/text'if isinstance(value,str)else base+'/source_observations/0/value'
            labels[i]=label
    # Rewrite every live presentation pointer, preserving its exact glyph value.
    def mapped(pointer):
        candidates=[key for key in mapping if pointer==key or pointer.startswith(key+'/')]
        if not candidates:return pointer
        key=max(candidates,key=len);return mapping[key]+pointer[len(key):]
    bindings=deepcopy(old['text_layout']['bindings'])
    for binding in bindings:
        binding['pointer']=mapped(binding['pointer']);binding['mirrors']=[mapped(p)for p in binding['mirrors']]
        binding['mirrors']=list(dict.fromkeys(p for p in binding['mirrors']if p!=binding['pointer']))
    new.pop('text_layout',None);new['text_layout']=layout.build_layout(new,text,bindings)
    assert layout.render(new)==text
    assert new.get('nets')==old.get('nets')and new.get('wire_paths')==old.get('wire_paths')and new.get('junctions')==old.get('junctions')and new.get('unjoined_crossings')==old.get('unjoined_crossings')
    return new,dict(pointer_mapping=mapping,verified_frames=len(frames),physical_connections_unchanged=True,exact_text_unchanged=True)

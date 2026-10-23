"""Full printed pin literals; explicit repair of historical split metadata."""
from copy import deepcopy

CONTAINERS=('nodes','boxes','groups','CAS_boxes')

def split_records(raw):
    result=[]
    for field in CONTAINERS:
        for i,node in enumerate(raw.get(field,[])if isinstance(raw.get(field),list)else[]):
            if not isinstance(node,dict):continue
            for j,pin in enumerate(node.get('pins',[])if isinstance(node.get('pins'),list)else[]):
                prefix=pin.get('printed_prefix');label=pin.get('printed_label')
                if prefix in(None,'',[],{}):continue
                if type(prefix)not in(str,int)or not isinstance(label,str):
                    raise ValueError('Declared printed prefix and label must be text')
                # Numeric prefixes are part of the pin label. A nonnumeric
                # control such as K can replace the box border; its native
                # classification must not be inferred by concatenating text.
                if not str(prefix).isdecimal():continue
                if not label.startswith(str(prefix)):
                    result.append(dict(pointer=f'/{field}/{i}/pins/{j}/printed_label',prefix=str(prefix),before=label,after=str(prefix)+label))
    return result

def validate(raw):
    if split_records(raw):
        raise ValueError('printed_label must contain the full declared printed prefix; historical review copies require explicit import_review_page')

def repair_raw(raw,text=None):
    """Pure representation repair; no physical identity or source fact inferred.

    Preserve exact text and every field except full printed_label and layout.
    Only an explicit historical-copy import or coordinated migration calls this.
    """
    import layout
    changes=split_records(raw)
    if not changes:return deepcopy(raw),[]
    result=deepcopy(raw);old_layout=result.pop('text_layout',None)
    if old_layout is not None:
        if text is None:text=layout.render(raw)
        bindings=deepcopy(old_layout['bindings']);rows=text.decode('utf8').splitlines()
    else:bindings=[];rows=[]
    removed=set();coordinate_changes=[]
    for change in changes:
        ptr=change['pointer'];value=result
        for token in ptr.strip('/').split('/')[:-1]:value=value[int(token)]if isinstance(value,list)else value[token]
        value['printed_label']=change['after']
        if not change['before'] and type(value.get('label_column'))is int:
            # A formerly empty number-field slot does not locate a pinless
            # marker. Use one already declared canonical marker label only.
            labels=[label for label in result.get('printed_labels',[])
                    if isinstance(label,dict)and label.get('text')==change['after']
                    and label.get('row')==value.get('row')and type(label.get('column'))is int
                    and isinstance(value.get('point'),list)
                    and abs(label['column']-value['point'][0])<=8]
            if len(labels)!=1:raise ValueError('Pinless marker requires one exact declared label position: '+ptr)
            column=labels[0]['column']
            if rows and rows[value['row']][column:column+len(change['after'])]!=change['after']:
                raise ValueError('Declared pinless marker does not match exact source text')
            if column!=value['label_column']:
                coordinate_changes.append(dict(pointer=ptr.rsplit('/',1)[0]+'/label_column',before=value['label_column'],after=column,reason='Full marker label starts at its existing canonical printed_labels position; connection point is unchanged.'))
                value['label_column']=column
        affected=[(i,b)for i,b in enumerate(bindings)if ptr in[b['pointer']]+b['mirrors']]
        for i,b in affected:
            others=[x for x in[b['pointer']]+b['mirrors']if x!=ptr]
            if others:b['pointer']=others[0];b['mirrors']=others[1:]
            else:removed.add(i)
        if affected:
            candidates=[]
            for i,b in affected:
                for column in(b['column']-len(change['prefix']),b['column']):
                    if column>=0 and rows[b['row']][column:column+len(change['after'])]==change['after']:
                        candidates.append((b['row'],column))
            if change['before']and not candidates:
                raise ValueError('Cannot rebind full printed literal without an exact adjacent rendered token: '+ptr)
            if candidates:
                row,column=candidates[0];cells={(row,c)for c in range(column,column+len(change['after']))}
                overlaps=any(i not in removed and cells&{(b['row'],c)for c in range(b['column'],b['column']+b['width'])}for i,b in enumerate(bindings))
                if not overlaps:bindings.append(dict(pointer=ptr,mirrors=[],row=row,column=column,width=len(change['after']),format='string-right-pad'))
    if old_layout is not None:
        result['text_layout']=layout.build_layout(result,text,[b for i,b in enumerate(bindings)if i not in removed])
        if layout.render(result)!=text:raise ValueError('Full printed literal repair changed source text')
    return result,changes+coordinate_changes

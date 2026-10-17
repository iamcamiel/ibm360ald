"""Reviewed source-style component forms, independent of card-number prefixes.

This module does not infer connections, pins, supply rails or circuit symbols.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,re

def reviewed_components(root, path, observations, widths, kinds, part_numbers=None):
    """Select exact reviewed forms, independently of a card-number prefix.

    Current ALD facts remain source-bound by the caller. This small declaration
    carries display authority, not historical proof copies or inferred wiring.
    """
    path = Path(path) if path is not None else Path(root)/'json/Card-ALD/component-forms.json'
    if not path.is_file():return {},None
    raw=path.read_bytes();doc=json.loads(raw.decode('utf-8-sig'))
    if doc.get('schema')!='reviewed-component-forms-v2':
        raise ValueError('Unsupported reviewed component form authority')
    circuits={str(o.get('circuit_identifier','')).strip() for o in observations}
    profiles=doc.get('circuits',{})
    if not circuits or not circuits<=set(profiles):return {},None
    selected={c:deepcopy(profiles[c]) for c in circuits}
    powers=[]
    for code,profile in selected.items():
        width=profile.get('card_width')
        if not re.fullmatch(r'[A-Z]\d\d[A-Z]{2}',code) or width not in {'SINGLE CARD','DOUBLE CARD'}:
            raise ValueError('Invalid exact component profile')
        if widths!={width} or not kinds or not kinds<={width}:
            raise ValueError('Reviewed component mechanical class differs from listing')
        if not profile.get('approved_source_form') or not profile.get('printed_function') or not profile.get('authority'):
            raise ValueError('Component form is not explicitly authorized')
        for o in observations:
            if str(o.get('circuit_identifier','')).strip()!=code:continue
            label=o.get('function_label')
            tokens=label.split() if isinstance(label,str) else []
            if not tokens or tokens[0]!=profile['printed_function']:
                raise ValueError('Component source primary function differs from authority')
        power=profile.get('power_contacts')
        banks=profile.get('contact_banks')
        if banks not in {'BD','BDGJ'} or not isinstance(power,dict) or any(not re.fullmatch('['+banks+r'](?:0[2-9]|1[0-3])',p) or v not in {'GROUND','+3V','-3V','+6V'} for p,v in power.items()):
            raise ValueError('Invalid explicit component power contacts')
        if not power and profile.get('power_contact_role')!='not_established':
            raise ValueError('Missing component power authority status')
        allowed=profile.get('applicable_part_numbers')
        if not allowed or not part_numbers or not set(part_numbers)<=set(allowed):
            raise ValueError('Component form authority lacks this exact part-number scope')
        powers.append(power)
    if any(p!=powers[0] for p in powers):raise ValueError('Component power authorities disagree')
    try: label=path.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError: label=str(path.resolve())
    return selected,{'path':label,'sha256':sha256(raw).hexdigest()}

def source_labels(occurrences,models):
    """Preserve explicit source auxiliary text, not guessed circuit inputs."""
    inside={};above={}
    for occurrence in occurrences:
        model=models.get(occurrence['page'],{})
        matches=[n for n in model.get('nodes',[]) if n.get('id')==occurrence['node']]
        if len(matches)!=1:continue
        raw=matches[0];row=raw.get('absolute_row',raw.get('row'));col=raw.get('absolute_column',raw.get('column'))
        if not isinstance(row,int) or not isinstance(col,int):continue
        for label in model.get('printed_labels',[]):
            if not isinstance(label,dict):continue
            text=str(label.get('text','')).strip()
            if not text:continue
            evidence={'page':occurrence['page'],'node':occurrence['node'],'row':label.get('row'),'column':label.get('column')}
            if label.get('row')==row+2 and col<label.get('column',-1)<col+7 and len(text)<=6:
                inside.setdefault(text,[]).append(evidence)
            elif label.get('row')==row-2 and label.get('column')==col:
                above.setdefault(text,[]).append(evidence)
    return {'interior_line_2':[{'text':text,'evidence':e}for text,e in sorted(inside.items())],
            'source_notes':[{'text':text,'evidence':e}for text,e in sorted(above.items())]}

def minimum_heading_width(model,uncertainties):
    """Reserve a readable factual header without changing normal card layouts."""
    profiles=[n['_reviewed_component'] for n in model['portions'].values() if n.get('_reviewed_component')]
    if not profiles:return 0
    lines=['CARD-ALD '+model['card_type']+'  PRINTED ALD COMPONENT FORMS',
           f"{model['observations']} OCCURRENCES; {len(model['portions'])} OBSERVED PORTIONS; {len(uncertainties)} REVIEW ITEMS",
           'POWER: '+('; '.join(p+' '+v for p,v in model['power_pins'].items()) or 'NOT ESTABLISHED'),
           f"{len(model.get('unobserved_contacts',[]))} CONTACTS WITH NO OBSERVED CONNECTION; SEE EVIDENCE JSON"]
    return max(90,max(map(len,lines)))


def decorate_definition(spec,model,reviewed_overlay=None):
    """Retain source interior labels and generic component captions.

    All connections still come from observed terminals; printed forms do not
    add hidden circuitry. Fixed-geometry variants are handled by the shared
    notation collector, not invented per-label combinations here.
    """
    nodes=model['portions'];boxes={b['portion']:b for b in spec['boxes']}
    roles=set()
    has_components=any(n.get('_reviewed_component')for n in nodes.values())
    if not has_components:
        if reviewed_overlay and any(k in reviewed_overlay for k in ('component_power_authority','box_captions','symbol_standard')):
            raise ValueError('Supplement component display claims lack current reviewed authority')
        return spec
    spec['annotations']=[a for a in spec['annotations']if a.get('kind')!='component-interior-label']
    spec.pop('box_captions',None)
    spec.pop('source_label_variations',None)
    for portion,node in nodes.items():
        profile=node.get('_reviewed_component')
        if not profile:continue
        box=boxes[portion];roles.add(profile['power_contact_role'])
        if box['function']!=profile['printed_function'] or spec['power_contacts']!=profile['power_contacts']:
            raise ValueError('Supplement component function or power contacts differ from reviewed authority')
        interior=node.get('_source_auxiliary_labels',{}).get('interior_line_2',[])
        if len(interior)==1:
            annotation={'x':box['x']+1,'row':box['top']+2,'text':interior[0]['text'],'kind':'component-interior-label'}
            if not any(all(a.get(k)==annotation[k]for k in ('x','row','text'))for a in spec['annotations']):spec['annotations'].append(annotation)
        elif interior:
            spec.setdefault('source_label_variations',[]).append({'portion':portion,'interior_line_2':interior,'display':'No single literal substituted for differing observed source labels.'})
        if profile.get('above_block_caption'):
            spec.setdefault('box_captions',[]).append({'portion':portion,'text':profile['above_block_caption']})
    if roles:
        role=next(iter(roles)) if len(roles)==1 else 'mixed reviewed authority'
        spec['component_power_authority']={'role':'not_established' if role=='not_established' else 'reviewed_special','source_contact_role':role,'contact_set_complete':False,'internal_supply_wiring_inferred':False}
        spec['symbol_standard']='PRINTED ALD FORMS'
        if 'header' in spec:spec['header']['symbol_standard']='PRINTED ALD FORMS'
        annotation=next((a for a in spec['annotations'] if a['row']==2),None)
        if annotation is None:
            annotation={'x':0,'row':2,'text':''};spec['annotations'].append(annotation)
        label={'not_established':'POWER: NOT ESTABLISHED','reserved_system_contact_positions':'RESERVED SYSTEM CONTACTS: '}.get(role,'DOCUMENTED CARD POWER: ')
        annotation['text']=label+('' if role=='not_established' else '; '.join(p+' '+v for p,v in spec['power_contacts'].items()))
    if reviewed_overlay:
        for key in ('component_power_authority','box_captions','symbol_standard'):
            if key in reviewed_overlay and reviewed_overlay[key]!=spec.get(key):
                raise ValueError('Supplement '+key+' differs from current reviewed component authority')
        if reviewed_overlay.get('header',{}).get('symbol_standard','PRINTED ALD FORMS')!='PRINTED ALD FORMS':
            raise ValueError('Supplement component symbol standard differs from current reviewed authority')
    return spec

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
    if doc.get('schema')=='reviewed-component-forms-v3':
        selected=select_v3(doc,observations,widths,kinds,part_numbers)
        if not selected:return {},None
        try: label=path.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError: label=str(path.resolve())
        return selected,{'path':label,'sha256':sha256(raw).hexdigest()}
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

def select_v3(doc, observations, widths, kinds, part_numbers):
    """Select display forms independently from exact-part mechanical facts."""
    parts=doc.get('card_parts',{})
    if not part_numbers or any(p not in parts for p in part_numbers):return {}
    mechanics=[parts[p] for p in part_numbers]
    keys=('card_width','contact_banks','power_contacts','power_contact_role')
    first=mechanics[0]
    if any(any(m.get(k)!=first.get(k)for k in keys)for m in mechanics):
        raise ValueError('Exact part mechanical or power authorities disagree')
    width=first.get('card_width');banks=first.get('contact_banks');power=first.get('power_contacts')
    if width not in {'SINGLE CARD','DOUBLE CARD'} or widths!={width} or not kinds or not kinds<={width}:
        raise ValueError('Reviewed component mechanical class differs from listing')
    if banks not in {'BD','BDGJ','ABCDE'} or not isinstance(power,dict):
        raise ValueError('Invalid explicit component contact scheme')
    if any(not re.fullmatch('['+banks+r'](?:0[2-9]|1[0-3])',p) or v not in {'GROUND','+3V','-3V','+6V'} for p,v in power.items()):
        raise ValueError('Invalid explicit component power contacts')
    if not power and first.get('power_contact_role')!='not_established':
        raise ValueError('Missing component power authority status')
    if any(not m.get('authority')or m.get('supply_connection_inference_allowed')is not False for m in mechanics):
        raise ValueError('Mechanical/power authority lacks explicit no-inference scope')
    circuits={str(o.get('circuit_identifier','')).strip() for o in observations}
    selected={}
    for code in sorted(circuits & set(doc.get('circuits',{}))):
        form=deepcopy(doc['circuits'][code])
        if not re.fullmatch(r'[A-Z]\d\d[A-Z]{2}',code)or not form.get('approved_source_form')or not form.get('printed_function')or not form.get('authority'):
            raise ValueError('Component form is not explicitly authorized')
        for o in observations:
            if str(o.get('circuit_identifier','')).strip()!=code:continue
            tokens=str(o.get('function_label')or'').split()
            if not tokens or tokens[0]!=form['printed_function']:
                raise ValueError('Component source primary function differs from authority')
        # Legacy consumer shape; mechanical data is selected from exact parts,
        # never inherited from the circuit identifier itself.
        form.update({k:deepcopy(first.get(k))for k in keys})
        form['applicable_part_numbers']=list(part_numbers)
        form['mechanical_authority']=[{'part_number':p,**deepcopy(parts[p])}for p in part_numbers]
        selected[code]=form
    return selected


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


def copy_port_decorations(spec,model,reviewed_overlay=None,copy_physical=True,component_only=False):
    """Copy only current typed edge marks, preserving physical port identity."""
    spec.pop('source_notation_profiles',None)
    for box in spec['boxes']:
        node=model['portions'].get(box['portion'],{})
        if node.get('_source_notation_variants')or node.get('_source_notation_baseline_witness'):
            spec.setdefault('source_notation_profiles',[]).append({'portion':box['portion'],
                'baseline_witness':deepcopy(node.get('_source_notation_baseline_witness')),
                'source_variants':deepcopy(node.get('_source_notation_variants',[]))})
        if not copy_physical or (component_only and not node.get('_reviewed_component')):continue
        semantic=node.get('_inputs',[])+node.get('_outputs',[])
        observed={}
        for port in semantic:
            if not port.get('pin'):
                if port.get('border_symbol')or any(port.get('pin_symbols',{}).values()):raise ValueError('Anonymous component decoration needs an explicit terminal mapping')
                continue
            key=(port['side'],port.get('pin'))
            if key in observed:raise ValueError('Ambiguous component semantic port identity')
            observed[key]=port
        claims={p['id']:p for p in (reviewed_overlay or {}).get('reviewed_portions',{}).get(box['portion'],{}).get('ports',[])}
        seen=set()
        for port in box['ports']:
            key=(port['side'],port.get('pin'))
            # Anonymous terminals can share a side, but cannot acquire a physical X.
            current=observed.get(key) if port.get('pin') else None
            claim=claims.get(port['id'])
            # Reviewed components use the exact selected printed form. Ordinary
            # Boolean gates retain their independently established manual form.
            if node.get('_reviewed_component') and current is not None:
                triangle=current.get('triangle')
                if type(triangle)is not bool:
                    raise ValueError('Component source triangle is not established')
                evidence=current.get('source_triangle_observations',[])
                if not any(e.get('terminal_id') and e.get('triangle')is triangle for e in evidence):
                    raise ValueError('Component source triangle lacks a typed terminal witness')
                if claim is not None and claim.get('triangle')is not triangle:
                    raise ValueError('Supplement triangle differs from current selected component source form')
                port['triangle']=triangle
            symbol=current.get('border_symbol') if current else None
            if symbol is not None:
                if symbol!='X' or port.get('triangle'):raise ValueError('Component border symbol conflicts with port decoration')
                evidence=current.get('source_edge_decorations',[])
                if not any(e.get('terminal_id') and e.get('border_symbol')=='X' and
                           any(d.get('glyph')=='X' and d.get('kind')!='triangle' for d in e.get('border_decorations',[]))
                           for e in evidence):
                    raise ValueError('Component X border symbol lacks typed source terminal authority')
                if key in seen:raise ValueError('Ambiguous component physical port identity')
                seen.add(key)
            if port.get('border_symbol') not in (None,symbol):raise ValueError('Component border symbol differs from current source')
            claim=claims.get(port['id'])
            if claim is not None:
                if (claim['side'],claim.get('pin'))!=key:raise ValueError('Supplement component port identity differs from stable layout ID')
                if claim.get('border_symbol')!=symbol:raise ValueError('Supplement border_symbol differs from current typed source')
            if symbol is not None:port['border_symbol']=symbol
            empty_symbols={'prefix':[],'suffix':[]}
            symbols=current.get('pin_symbols',empty_symbols)if current else empty_symbols
            if (not isinstance(symbols,dict)or set(symbols)!=set(empty_symbols)or
                any(not isinstance(symbols[k],list)or any(mark!='✲'for mark in symbols[k])for k in empty_symbols)):
                raise ValueError('Unsupported typed intrinsic pin symbols')
            if any(symbols.values()):
                import card_source
                evidence=[e for e in current.get('source_pin_symbol_observations',[])if e.get('pin_symbols')==symbols]
                if not evidence or any(not e.get('terminal_id')or
                    card_source.terminal_pin_symbols({'_symbols':e.get('source_symbols',{}),'_pin_number':current.get('pin'),'_pin_number_status':'observed'})!=symbols for e in evidence):
                    raise ValueError('Component pin symbols lack selected typed source terminal authority')
            if port.get('pin_symbols',empty_symbols)not in(empty_symbols,symbols):
                raise ValueError('Component pin symbols differ from current source')
            if claim is not None and claim.get('pin_symbols',empty_symbols)!=symbols:
                raise ValueError('Supplement pin_symbols differs from current typed source')
            if any(symbols.values()):port['pin_symbols']=deepcopy(symbols)


def decorate_definition(spec,model,reviewed_overlay=None):
    """Retain source interior labels and generic component captions.

    All connections still come from observed terminals; printed forms do not
    add hidden circuitry. Fixed-geometry variants are handled by the shared
    notation collector, not invented per-label combinations here.
    """
    nodes=model['portions'];boxes={b['portion']:b for b in spec['boxes']}
    roles=set()
    has_components=any(n.get('_reviewed_component')for n in nodes.values())
    # Typed terminals and witnessed notation are shared by ordinary and special
    # circuits. Ordinary canonical port glyphs stay in their accepted form;
    # exact current source profiles describe scoped observed alternatives.
    copy_port_decorations(spec,model,reviewed_overlay,copy_physical=has_components,component_only=has_components)
    if not has_components:
        if reviewed_overlay and any(k in reviewed_overlay for k in ('component_power_authority','box_captions','symbol_standard')):
            raise ValueError('Supplement component display claims lack current reviewed authority')
        if reviewed_overlay and 'source_notation_profiles' in reviewed_overlay and reviewed_overlay['source_notation_profiles']!=spec.get('source_notation_profiles'):
            raise ValueError('Supplement source_notation_profiles differs from current typed source')
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
    symbol_standard='MIXED MANUAL AND PRINTED ALD FORMS' if any(not n.get('_reviewed_component')for n in nodes.values())else'PRINTED ALD FORMS'
    if roles:
        role=next(iter(roles)) if len(roles)==1 else 'mixed reviewed authority'
        spec['component_power_authority']={'role':'not_established' if role=='not_established' else 'reviewed_special','source_contact_role':role,'contact_set_complete':False,'internal_supply_wiring_inferred':False}
        spec['symbol_standard']=symbol_standard
        if 'header' in spec:spec['header']['symbol_standard']=symbol_standard
        if 'header' not in spec:
            annotation=next((a for a in spec['annotations'] if a['row']==2),None)
            if annotation is None:
                annotation={'x':0,'row':2,'text':''};spec['annotations'].append(annotation)
            label={'not_established':'POWER: NOT ESTABLISHED','reserved_system_contact_positions':'RESERVED SYSTEM CONTACTS: '}.get(role,'DOCUMENTED CARD POWER: ')
            annotation['text']=label+('' if role=='not_established' else '; '.join(p+' '+v for p,v in spec['power_contacts'].items()))
    if reviewed_overlay:
        for key in ('component_power_authority','box_captions','symbol_standard','source_notation_profiles'):
            if key in reviewed_overlay and reviewed_overlay[key]!=spec.get(key):
                raise ValueError('Supplement '+key+' differs from current reviewed component authority')
        if reviewed_overlay.get('header',{}).get('symbol_standard',symbol_standard)!=symbol_standard:
            raise ValueError('Supplement component symbol standard differs from current reviewed authority')
    return spec

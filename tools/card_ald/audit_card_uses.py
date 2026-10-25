"""Compare all current uses of a card with its shared renderer definition.

Normal use: python tools/card_ald/audit_card_uses.py 4191
Writes private JSON/CSV/TXT reports; never edits diagrams, page models or catalogs.
Omitted unused inputs, witnessed notation variants and electrically equivalent
AND/OR presentations are distinguished from discrepancies and uncertain print.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys
import card_source as page_reader
from card_source import (accepted_page_context, exact_source_node, node_mentions_card, identity_document, selected_source_nodes, source_identity_issues, catalogue_source_coverage, unambiguous_wiring_documents, recheck_identity_context)

ROOT = Path(__file__).resolve().parents[2]
PIN = re.compile(r'(?P<qualifier>\d*)(?P<pin>[BDGJ](?:0[2-9]|1[0-3]))(?:✲?T?|✲)\Z')
LOCAL = re.compile(r'(?<![A-Za-z0-9_])([A-Za-z0-9_]+)\.([A-Za-z0-9_:✲.]+)')
REMOTE = re.compile(r'\b([A-Z]{2}\d{3})\.?([A-Z0-9]{2})([1-9])\b')
SEVERITY = {'match':0,'equivalent':1,'recorded_variant':2,'source_uncertainty':3,'discrepancy':4}
EXTERNAL_NAMESPACES = {'external','input','output','offpage','off_page','source','target','connector','inputnet','outputnet'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def same_literal(left, right):
    """Compare JSON observations without a tuple/list serialization mismatch."""
    return json.dumps(left,sort_keys=True,separators=(',',':'))==json.dumps(right,sort_keys=True,separators=(',',':'))


def primary(value):
    return str(value or '').strip().split(' ',1)[0].lstrip('✲*')


def physical(value):
    return page_reader.terminal_contact(value) if isinstance(value,dict) else page_reader.physical_contact(value)


def triangle(port):
    # Unknown decorations remain uncertain, rather than becoming False.
    return page_reader.wedge(port)


def finding(status,field,observed,expected,reason,**extra):
    return dict(status=status,field=field,observed=observed,expected=expected,reason=reason,**extra)


def expected_forms(spec):
    """Each form comes from one complete declared variant, never mixed marks."""
    result=defaultdict(list)
    for variant in [None]+spec.get('variants',[]):
        for box in spec['boxes']:
            form=deepcopy(box);override=(variant or {}).get('box_overrides',{}).get(box['portion'],{})
            form['function']=override.get('function',form['function'])
            for port in form['ports']:
                port['triangle']=override.get('port_triangles',{}).get(port['id'],port['triangle'])
                if port['id'] in override.get('port_symbols',{}):port['pin_symbols']=deepcopy(override['port_symbols'][port['id']])
                if port['id'] in override.get('border_symbols',{}):port['border_symbol']=override['border_symbols'][port['id']]
            form['variant_number']=(variant or {}).get('number',0)
            key=(form['function'],tuple((p['id'],p['triangle'],p.get('border_symbol'),
                json.dumps(p.get('pin_symbols',{'prefix':[],'suffix':[]}),sort_keys=True)) for p in form['ports']))
            if not any(x['_key']==key for x in result[box['portion']]):
                form['_key']=key;result[box['portion']].append(form)
    boxes={b['portion']:b for b in spec['boxes']}
    for profile in spec.get('source_notation_profiles',[]):
        box=boxes.get(profile.get('portion'))
        if box is None:continue
        for witness in profile.get('source_variants',[]):
            if not witness.get('model_binding') or not witness.get('node_pointer') or witness.get('conflicting_source_fields'):continue
            form=deepcopy(box);valid=True
            for observation in witness.get('ports',[]):
                choices=[p for p in form['ports'] if p['side']==observation.get('side') and p.get('pin')==observation.get('pin')]
                if len(choices)!=1:valid=False;break
                port=choices[0]
                for field in ('pin_symbols','border_symbol','triangle'):
                    if field in observation:
                        if field=='triangle' and type(observation[field])is not bool:valid=False;break
                        port[field]=deepcopy(observation[field])
            if valid:
                form['variant_number']=0;form['_scoped_source']=deepcopy(witness)
                result[box['portion']].append(form)
    return result


def port_mapping(ports,form):
    """Match physical contacts; pinless equivalent inputs may exchange rows."""
    available={p['id']:p for p in form['ports']};pairs=[]
    for observed in sorted(ports,key=lambda p:(physical(p) is None,p.get('row',0))):
        if page_reader.unresolved_physical_terminal(observed):return None
        pin=physical(observed);side=observed['side']
        candidates=[p for p in available.values() if p['side']==side and p.get('pin')==pin]
        if not candidates:return None
        candidates.sort(key=lambda p:(p['triangle']!=triangle(observed),p['row']))
        expected=candidates[0];pairs.append((observed,expected));del available[expected['id']]
    return pairs


def boolean_output(function,inputs,inversions,output_inversion):
    values=[bool(value)^inv for value,inv in zip(inputs,inversions)]
    if function in ('A','N'):value=all(values)
    elif function=='OR':value=any(values)
    elif function=='AR' and len(values)==1:value=values[0]
    else:return None
    return value^output_inversion


def equivalent_form(node,form,pairs,circuit_matches):
    """Exhaustive positive-level truth comparison on the visible used inputs.

    N is accepted as a one-used-input notation only for the SAME reviewed
    portion and circuit; its voltage inversion is carried by the edge marks.
    Unknown functions are never equated just because their names resemble A/OR.
    """
    pf,ef=primary(node.get('function')),primary(form['function'])
    inputs=[p for p in pairs if p[0]['side']=='input' and page_reader.logical_gate_terminal(p[0]) and page_reader.logical_gate_terminal(p[1])]
    outputs=[p for p in pairs if p[0]['side']=='output' and page_reader.logical_gate_terminal(p[0]) and page_reader.logical_gate_terminal(p[1])]
    if not inputs or not outputs or len(inputs)>12:return False
    if 'N' in (pf,ef) and (len(inputs)!=1 or not circuit_matches):return False
    if pf not in ('A','OR','N','AR') or ef not in ('A','OR','N','AR'):return False
    if 'AR' in (pf,ef) and pf!=ef:return False
    oi=[triangle(o) for o,_ in inputs];ei=[p['triangle'] for _,p in inputs]
    for actual,expected in outputs:
        for values in itertools.product((False,True),repeat=len(inputs)):
            a=boolean_output(pf,values,oi,triangle(actual))
            b=boolean_output(ef,values,ei,expected['triangle'])
            if a is None or b is None or a!=b:return False
    return True


def ground_service_inputs(document,power):
    """Prove anonymous page inputs driven by one reviewed non-card ground service.

    This is installation context only: no physical contact or card-internal net
    is synthesized. Unreviewed/ambiguous sources and mixed drivers prove nothing.
    """
    grouped=defaultdict(list)
    for node in document.get('nodes',[]):grouped[node.get('id')].append(node)
    nodes={key:values[0] for key,values in grouped.items() if key and len(values)==1}
    incidence=defaultdict(set)
    for number,net in enumerate(document.get('nets',[])):
        for target in net.get('targets',[]):
            if not isinstance(target,str):continue
            node=nodes.get(target.split('.',1)[0],{})
            resolved=page_reader.resolve_net_port(node,target,'input')
            if resolved.get('status')=='pinless':incidence[(node['id'],resolved['port_index'])].add(number)
    proofs={}
    for net in document.get('nets',[]):
        if net.get('source_reviewed') is not True:continue
        drivers=[]
        for key in ('driver','drivers','declared_physical_output_drivers','route_owners'):
            value=net.get(key)
            drivers.extend(value if isinstance(value,list) else ([] if value is None else [value]))
        if not drivers or any(not isinstance(v,str) for v in drivers)or len(set(drivers))!=1:continue
        driver=drivers[0];source=nodes.get(driver.split('.',1)[0],{})
        if (source.get('kind')!='service' or source.get('source_reviewed') is not True
            or source.get('card_type') not in (None,'')or source.get('portion') not in (None,'')
            or source.get('unit')!='GND'or not source.get('non_card_evidence')):continue
        supply=page_reader.resolve_net_port(source,driver,'output')
        if supply.get('status')!='numbered' or power.get(supply.get('physical_contact'))!='GROUND':continue
        if supply['raw_port'].get('source_reviewed') is not True:continue
        for target in net.get('targets',[]):
            if not isinstance(target,str):continue
            node=nodes.get(target.split('.',1)[0],{})
            if node.get('source_reviewed') is not True:continue
            resolved=page_reader.resolve_net_port(node,target,'input')
            if resolved.get('status')!='pinless':continue
            port=resolved['raw_port'];index=resolved['port_index']
            anonymous=[p for p in node.get('pins',[])if p.get('side')=='input'and p.get('pin')in(None,'')and page_reader.pinless_terminal(p)]
            if len(anonymous)!=1 or port.get('pin')not in(None,'')or port.get('source_reviewed') is not True:continue
            point=net.get('target_coordinates',{}).get(target)
            if point is not None and (not isinstance(point,(list,tuple))or len(point)!=2 or point[1]!=port.get('row')):continue
            key=(node['id'],index)
            if len(incidence[key])!=1:continue
            proof={'net':net.get('id'),'driver':driver,'target':target,'ground_contact':supply['physical_contact'],
                'source_kind':'reviewed non-card ground service','target_node_pointer':node.get('_source_pointer')}
            if key in proofs and proofs[key]!=proof:proofs[key]=None
            else:proofs[key]=proof
    return {key:proof for key,proof in proofs.items()if proof is not None}


def compare_occurrence(node,box,forms,power,ground_context=None):
    """Pure comparison API used by the CLI and independent fixture tests."""
    findings=[];circuit=node.get('unit',node.get('circuit_identifier'))
    circuit_matches=circuit==box['circuit_identifier']
    if not circuit_matches:
        findings.append(finding('source_uncertainty' if not circuit or '�' in str(circuit) else 'discrepancy',
            'circuit_identifier',circuit,box['circuit_identifier'],'Circuit identifier differs from the reviewed common portion.'))
    ports=[];seen_contacts=set()
    expected_pins={(p['side'],p['pin']) for p in box['ports'] if p.get('pin')}
    observed_pins={(p.get('side'),physical(p)) for p in node.get('pins',[])}
    for index,port in enumerate(node.get('pins',[])):
        if index in page_reader.ar_input_only_aliases(node):
            findings.append(finding('recorded_variant','input_only_AR_contact',physical(port),'input',
                'Repeated AR output stub is the existing input contact, never a block driver.',pin_index=index));continue
        raw=port.get('pin');pin=physical(port);side=port.get('side')
        if page_reader.occurrence_net_role(port):
            findings.append(finding('recorded_variant','occurrence_net_origin',page_reader.documentary_occurrence_net_role(port),None,
                'K identifies an explicitly corroborated external page-net nonorigin. Canonical physical port and intrinsic card nets are unchanged; no Boolean function or active drive capability is inferred.',pin_index=index))
        if side not in ('input','output'):
            findings.append(finding('source_uncertainty','pin_direction',side,['input','output'],'Port has no usable direction.',pin_index=index));continue
        readings=page_reader.physical_readings(port)
        if page_reader.unresolved_physical_terminal(port):
            findings.append(finding('source_uncertainty','pin_identity',
                {'physical_contact':pin,'status':port.get('_pin_number_status',port.get('pin_status'))},None,
                'Physical contact identity is explicitly unresolved; this is not an anonymous terminal.',pin_index=index))
        if len(set(readings.values()))>1:
            findings.append(finding('source_uncertainty','pin_identity',readings,None,'Active physical contact observations disagree.',pin_index=index));continue
        if triangle(port) is None:
            findings.append(finding('source_uncertainty','border_decoration',port.get('_border_decorations',port),None,'Border decoration is absent or contradictory.',pin_index=index));continue
        try:
            symbols=page_reader.terminal_pin_symbols(port)
            edge=page_reader.terminal_border_symbol(port)
        except ValueError as problem:
            findings.append(finding('source_uncertainty','typed_symbols',port,None,str(problem),pin_index=index));continue
        if pin in power:
            findings.append(finding('recorded_variant' if side=='input' else 'discrepancy','power_contact',raw,power[pin],
                'Page-level input supply/bias tie is separate from the card signal graph.' if side=='input' else 'A power contact is modeled as a driven output; inspect the source and module classification.',pin_index=index));continue
        proof=(ground_context or {}).get((node.get('id'),index))
        if proof and side=='input'and pin is None and raw in(None,''):
            findings.append(finding('recorded_variant','page_ground_service_input',None,'GROUND',
                'Exact reviewed ground-service net drives this unique anonymous page input; omitted from the card signal graph without inventing a physical contact.',
                pin_index=index,source_ground_service=proof));continue
        if raw not in (None,'') and (str(raw).isdigit() or str(raw) in ('L','E','K','X')):
            findings.append(finding('recorded_variant','wire_annotation',raw,None,
                'Printed wire/border annotation is not a physical contact; its meaning is not inferred.',pin_index=index))
            raw=None
        if raw not in (None,'') and pin is None and not re.fullmatch(r'(?:IN|OUT|input|output)\d*',str(raw)) and not page_reader.explicit_unprinted_alias(port):
            findings.append(finding('source_uncertainty','pin_identity',raw,None,
                'Not a valid single/double SLT physical contact or an unlabeled port.',pin_index=index));continue
        signature=(side,pin,triangle(port),edge,json.dumps(symbols,sort_keys=True))
        if pin and signature in seen_contacts:
            findings.append(finding('recorded_variant','repeated_same_contact',f'{side}:{pin}',pin,
                'Repeated model terminal uses the same physical contact and polarity; it is one contact, not an extra gate input/output.',pin_index=index));continue
        if pin:seen_contacts.add(signature)
        if pin and (side,pin) not in expected_pins:
            other='output' if side=='input' else 'input'
            findings.append(finding('discrepancy','pin_direction' if (other,pin) in expected_pins else 'pin_identity',
                f'{side}:{pin}',sorted(f'{s}:{p}' for s,p in expected_pins),
                'Physical contact is on the opposite side.' if (other,pin) in expected_pins else 'Contact is absent from this common portion.',pin_index=index))
        clone=deepcopy(port);clone['pin']=pin;clone['_index']=index
        page_reader.project_occurrence_net_role(port,clone,page=node.get('_source_page'),node=node.get('id'),model_binding=node.get('_source_model_binding'))
        ports.append(clone)
    omitted=max(0,len([p for p in box['ports'] if p['side']=='input'])-len([p for p in ports if p['side']=='input']))
    if omitted:findings.append(finding('match','unused_inputs_omitted',omitted,None,'Unused available card inputs may be omitted on an installation ALD.'))
    matching=[]
    for form in forms:
        scope=form.get('_scoped_source')
        if scope and (scope.get('page')!=node.get('_source_page') or scope.get('node')!=node.get('id') or
            scope.get('node_pointer')!=node.get('_source_pointer') or
            not same_literal(scope.get('model_binding'),node.get('_source_model_binding'))):continue
        pairs=port_mapping(ports,form)
        if pairs is None:continue
        if any(page_reader.intrinsic_contact_role(o)!=page_reader.intrinsic_contact_role(p) for o,p in pairs):continue
        if any(triangle(o)!=p['triangle'] for o,p in pairs if not page_reader.logical_gate_terminal(o)):continue
        labels_equal=primary(node.get('function'))==primary(form['function'])
        decorations_equal=all(triangle(o)==p['triangle'] for o,p in pairs)
        symbols_equal=all((page_reader.terminal_pin_symbols(o) is None or
            page_reader.terminal_pin_symbols(o)==p.get('pin_symbols',{'prefix':[],'suffix':[]})) and
            ('_border_decorations' not in o or page_reader.terminal_border_symbol(o)==p.get('border_symbol')) for o,p in pairs)
        if labels_equal and decorations_equal and symbols_equal:
            status='match' if form['variant_number']==0 and not scope else 'recorded_variant'
            matching.append((status,form['variant_number'],scope));continue
        if symbols_equal and equivalent_form(node,form,pairs,circuit_matches):matching.append(('equivalent',form['variant_number'],scope))
    if matching:
        status,number,scope=min(matching,key=lambda x:SEVERITY[x[0]])
        findings.append(finding(status,'function_and_decorations',node.get('function'),box['function'],
            ('Readable partial source notation matches only its exact current-bound page/node/slot witness; no complete-card variant is claimed.' if scope else
             'Visible used-port function/polarity matches a declared complete notation form.') if status!='equivalent' else
            'AND/OR polarity presentation has the same truth table on the visible used inputs; no pin or circuit inference was made.',variant_number=number,
            **({'source_notation_witness':scope} if scope else {})))
    else:
        unmapped=port_mapping(ports,box) is None
        uncertain=any('�' in str(node.get(k,'')) for k in ('function','unit'))
        status='source_uncertainty' if uncertain or unmapped else 'discrepancy'
        findings.append(finding(status,'function_and_decorations',{'function':node.get('function'),'ports':[(p['side'],p['pin'],triangle(p)) for p in ports]},
            {'function':box['function'],'ports':[(p['side'],p['pin'],p['triangle']) for p in box['ports']]},
            'Port identity cannot be uniquely matched; notation comparison remains uncertain.' if unmapped else 'No declared or truth-equivalent function/polarity form matches.'))
    return findings


def resolve_path(root,value):
    p=Path(value);return p if p.is_absolute() else root/p


def load_documents(root,catalog,context=None):
    context=accepted_page_context(root) if context is None else context
    documents={};issues=[]
    for path,entry in page_reader.iter_documents(root,catalog['card_type']):
        doc=identity_document(root,path,entry['document'],context)
        documents[path]={'document':doc,'sha256':entry['sha256'],'original':entry['document']}
        issues.extend(source_identity_issues(doc,catalog['card_type']))
    for occurrence in catalog.get('diagram_occurrences',[]):
        parts=list(Path(occurrence['source_text']).parts)
        if parts and parts[0]=='ALD':parts[0]='json'
        path=resolve_path(root,Path(*parts).with_suffix('.json')).resolve()
        if not path.is_file():issues.append(finding('source_uncertainty','source_model',str(path),None,'Published model is missing.'))
    return documents,issues


def apply_scoped_corrections(root,card,documents,overrides):
    records=[]
    for correction in overrides.get('source_corrections',[]):
        binding=correction.get('model_binding',{});path=resolve_path(root,binding.get('path',''))
        entry=documents.get(path);status='recorded_variant'
        valid=bool(entry and binding.get('sha256')==entry['sha256'])
        node,pointer,problem=exact_source_node((entry or {}).get('document',{}),correction)
        if not valid or problem or node.get('card_type')!=card:
            records.append(dict(page=correction.get('page'),block=correction.get('node'),**finding('source_uncertainty','reviewed_source_correction',correction,None,'Scoped correction evidence is stale, missing or does not uniquely identify a card node.')));continue
        n=node
        if entry['document'].get('page')!=correction.get('page'):
            records.append(finding('source_uncertainty','reviewed_source_correction',correction,None,'Page does not match the model binding.'));continue
        for field,key in (('portion','portion'),('unit','unit'),('function','function')):
            mapping=correction.get(field,{})
            if isinstance(mapping,dict) and n.get(key) in mapping:
                old=n[key];n[key]=mapping[old]
                records.append(dict(page=correction['page'],block=n['id'],**finding(status,field,old,n[key],'Known source-reviewed correction; applied to audit memory only.',basis=correction.get('basis',correction.get('scope')),model_binding=binding)))
        for pin in n.get('pins',[]):
            mapping=correction.get('pins',{});old=pin.get('pin')
            if old in mapping:
                new=mapping[old];pin['pin']=new
                records.append(dict(page=correction['page'],block=n['id'],**finding(status,'pin_identity',old,new,'Known source-reviewed correction; original source files remain unchanged.',row=pin.get('row'),model_binding=binding)))
                # Reconcile local endpoint aliases only for this exact node.
                oldref=n['id']+'.'+str(old);newref=n['id']+'.'+(str(new) if new else 'input'+str(pin.get('row')))
                for net in entry['document'].get('nets',[]):
                    if net.get('driver')==oldref:net['driver']=newref
                    net['targets']=[newref if t==oldref else t for t in net.get('targets',[])]
    return records


def _endpoint_base(node,label,side):
    ports=[p for p in node.get('pins',[]) if p.get('side')==side]
    exact=[p for p in ports if node['id']+'.'+label in (p.get('terminal_id'),p.get('reference')) or p.get('id')==label or str(p.get('pin'))==label]
    if not exact:
        match=re.fullmatch(r'(?:input|output|IN|OUT|i|o)[.:]?(\d+)',label)
        if match:exact=[p for p in ports if p.get('row')==int(match[1])]
        # Several original page-model schemas use input1..input5 as ordinals,
        # whereas input72/IN72 are row references. Resolve only an in-range
        # ordinal after an exact reference/row match has failed.
        if not exact and re.fullmatch(r'(?:input|output)[1-9]',label):
            ordinal=int(label[-1])
            if ordinal<=len(ports):exact=[sorted(ports,key=lambda p:p.get('row',0))[ordinal-1]]
    generic=label in ('input','output','IN','OUT','input1','output1')
    if not exact and len(ports)==1 and generic:exact=ports
    unknown=len(exact)==1 and page_reader.unresolved_physical_terminal(exact[0])
    problem=('Physical contact identity is explicitly unresolved; no anonymous endpoint or common link is certified.'
             if unknown else None if exact else 'Explicit endpoint label/ID has no matching modeled port.')
    listing=node.get('socket_listing_evidence') or {}
    if isinstance(listing,list):
        candidates=[p for p in listing if isinstance(p,dict) and p.get('board') and p.get('sockets')]
        listing=candidates[0] if len(candidates)==1 else {}
    if not isinstance(listing,dict):listing={}
    key=(listing.get('board'),tuple(sorted(listing.get('sockets',[])))) if listing.get('board') and listing.get('sockets') else None
    location=str(node.get('location') or '')
    stable_id=(exact[0].get('id') or str(exact[0].get('terminal_id') or '').split('.')[-1]) if len(exact)==1 else None
    input_only_alias=(len(exact)==1 and side=='output' and any(p is exact[0] for i,p in enumerate(node.get('pins',[])) if i in page_reader.ar_input_only_aliases(node)))
    return {'portion':str(node.get('portion')),'pin':physical(exact[0]) if len(exact)==1 else None,
            'input_only_alias':input_only_alias,'contact_role':page_reader.terminal_contact_role(exact[0]) if len(exact)==1 else None,
            'side':'input' if input_only_alias else side,'label':label,'id':node['id'],'location':location,'card_key':key,'port_resolved':len(exact)==1 and not unknown,'stable_port_id':stable_id,'endpoint_problem':problem,
            **({'physical_identity_unresolved':True}if unknown else {})}


class _WitnessNode(dict):
    # Only the successful private witness-validation path creates this type.
    # A similarly spelled source JSON field cannot authorize a port mapping.
    pass


def endpoint(node,label,side):
    result=_endpoint_base(node,label,side)
    mapping=getattr(node,'anonymous_output_mapping',None) if isinstance(node,_WitnessNode) else None
    if side=='output' and isinstance(mapping,dict):
        resolved=page_reader.resolve_net_port(node,node['id']+'.'+label,side)
        port_id=mapping.get(resolved.get('port_index'))
        if port_id is not None and resolved.get('status')=='pinless':
            result.update(stable_port_id=port_id,port_resolved=True,endpoint_problem=None)
    return result


def audit_wiring(card,spec,documents):
    if not spec.get('anonymous_output_preservation'):
        return _audit_wiring_base(card,spec,documents)
    import anonymous_outputs
    try:
        models={entry['document']['page']:entry['document'] for entry in documents.values()}
        if len(models)!=len(documents):raise ValueError('Duplicate page identity in audit documents')
        mapping=anonymous_outputs.audit_mapping(card,spec,models,page_reader)
    except (ValueError,KeyError,TypeError) as problem:
        findings,observations=_audit_wiring_base(card,spec,documents)
        findings.append(finding('source_uncertainty','anonymous_output_witness',None,None,str(problem)))
        return findings,observations
    private=deepcopy(documents)
    for entry in private.values():
        page=entry['document']['page']
        for ni,node in enumerate(entry['document'].get('nodes',[])):
            slots={i:port_id for (p,n,i),port_id in mapping.items() if (p,n)==(page,node['id'])}
            if slots:
                validated=_WitnessNode(node)
                validated.anonymous_output_mapping=slots
                entry['document']['nodes'][ni]=validated
    return _audit_wiring_base(card,spec,private)


def _audit_wiring_base(card,spec,documents):
    expected=set();terminal_nets=defaultdict(set);boxes={b['portion']:b for b in spec['boxes']}
    for net_index,net in enumerate(spec.get('nets',[])):
        ports=[t.split(':',2) for t in net if t.startswith('PORT:')]
        for _,portion,port_id in ports:terminal_nets[(portion,port_id)].add(net_index)
        outputs=[p for p in ports if next(t for t in boxes[p[1]]['ports'] if t['id']==p[2])['side']=='output']
        inputs=[p for p in ports if next(t for t in boxes[p[1]]['ports'] if t['id']==p[2])['side']=='input']
        expected|={(a[1],b[1]) for a in outputs for b in inputs}
    index={};all_nodes={};findings=[];observations=[]
    for path,entry in documents.items():
        doc=entry['document']
        for n in doc.get('nodes',[]):
            all_nodes[(doc.get('page'),n['id'])]=n
            if n.get('card_type')==card:index[(doc.get('page'),n['id'])]=n
    def possible_nets(port):
        box=boxes.get(port['portion'])
        if not box:return set(),False,False
        possible=[p for p in box['ports'] if p['side']==port['side'] and p.get('pin')==port['pin']]
        if not possible:return set(),False,False
        exact=[p for p in possible if p['id']==port.get('stable_port_id')]
        if exact:possible=exact
        nets=set().union(*(terminal_nets[(box['portion'],p['id'])] for p in possible))
        unambiguous=len(possible)==1 or len(nets)==1
        interchangeable=port['side']=='input' and primary(box['function']) in ('A','OR') and len({p['triangle'] for p in possible})==1
        return nets,unambiguous,interchangeable
    def references(value,page,side):
        result=[]
        for match in LOCAL.finditer(str(value or '')):
            if re.fullmatch(r'[A-Z]{2}\d{3}',match[1]):continue
            if match[1].lower() in EXTERNAL_NAMESPACES and (page,match[1]) not in all_nodes:continue
            n=index.get((page,match[1]))
            if n:result.append(endpoint(n,match[2],side))
        if not result:
            for match in REMOTE.finditer(str(value or '')):
                n=index.get((match[1],match[2]))
                if n:
                    p=endpoint(n,'output'+str(n.get('row',0)+int(match[3])-1),side);p['remote_page']=match[1];result.append(p)
        return result
    for path,entry in documents.items():
        doc=entry['document'];page=doc.get('page')
        for net in doc.get('nets',[]):
            driver_values=[net.get('driver')]+list(net.get('declared_physical_output_drivers') or [])+list(net.get('route_owners') or [])
            driver_map={}
            for value in driver_values:
                for driver in references(value,page,'output'):driver_map[(driver.get('remote_page',page),driver['id'],driver['label'])]=driver
            drivers=list(driver_map.values())
            for first,second in itertools.combinations([d for d in drivers if not d.get('input_only_alias') and d.get('contact_role')!='nonlogical_common'],2):
                if first['location']!=second['location']:continue
                an,ap,_=possible_nets(first);bn,bp,_=possible_nets(second)
                if ap and bp and not an&bn:
                    findings.append(dict(page=page,net=net.get('id'),**finding('discrepancy','multiple_internal_drivers',[(first['portion'],first['label']),(second['portion'],second['label'])],None,'Declared physical drivers or route owners join distinct common-card nets.')))
            for role,value in [('driver',v) for v in driver_values]+[('target',v) for v in net.get('targets',[])]:
                for match in LOCAL.finditer(str(value or '')):
                    if re.fullmatch(r'[A-Z]{2}\d{3}',match[1]):continue
                    if match[1].lower() in EXTERNAL_NAMESPACES and (page,match[1]) not in all_nodes:continue
                    if (page,match[1]) not in all_nodes:
                        findings.append(dict(page=page,net=net.get('id'),**finding('source_uncertainty','unresolved_wire_endpoint',value,None,'Local wire references a block missing from this source model.',endpoint_role=role)))
                for match in REMOTE.finditer(str(value or '')):
                    if any(k[0]==match[1] for k in all_nodes) and (match[1],match[2]) not in all_nodes:
                        findings.append(dict(page=page,net=net.get('id'),**finding('source_uncertainty','unresolved_wire_endpoint',value,None,'Referenced source page is loaded but its block is missing.',endpoint_role=role)))
            for target in net.get('targets',[]):
                for driver in drivers:
                    for sink in references(target,page,'input'):
                        context={'page':page,'net':net.get('id'),'driver':driver,'target':sink,'model':str(path)}
                        if driver['endpoint_problem'] or sink['endpoint_problem']:
                            wrong_contact=bool(driver.get('physical_identity_unresolved') or sink.get('physical_identity_unresolved')
                                or driver['endpoint_problem'] and physical(driver['label']) or sink['endpoint_problem'] and physical(sink['label']))
                            findings.append(dict(context,**finding('source_uncertainty','wire_endpoint_identity' if wrong_contact else 'stale_wire_endpoint',
                                [driver['label'],sink['label']],None,
                                'Physical contact identity is explicitly unresolved; no anonymous endpoint or common link is certified.'
                                if driver.get('physical_identity_unresolved') or sink.get('physical_identity_unresolved')
                                else 'Explicit wire endpoint contradicts current modeled ports; no common link is certified.')));continue
                        same=(driver['card_key'] is not None and driver['card_key']==sink['card_key']) or (driver['location']==sink['location'] and bool(driver['location']) and '�' not in driver['location'])
                        pair=(driver['portion'],sink['portion'])
                        if not same:
                            if not driver['pin'] or not sink['pin']:
                                findings.append(dict(context,**finding('source_uncertainty','internal_wiring',pair,None,'Pinless endpoint appears across different or unreadable card locations; inspect identity and route.')))
                            observations.append(dict(context,classification='between_card_installation_wire'));continue
                        dn,dp,_=possible_nets(driver);sn,sp,interchangeable=possible_nets(sink)
                        if driver.get('input_only_alias'):
                            if driver['pin'] and sink['pin'] and driver['pin']!=sink['pin']:
                                observations.append(dict(context,classification='input_contact_installation_wire'));continue
                            if dn&sn and dp and sp:
                                observations.append(dict(context,classification='input_contact_fanout'));continue
                            findings.append(dict(context,**finding('discrepancy','input_contact_fanout',pair,None,
                                'Input-only AR contact fanout is absent from the common input net.')));continue
                        if pair in expected and dn&sn and dp and sp:
                            observations.append(dict(context,classification='common_nonlogical_contact_link' if driver.get('contact_role')=='nonlogical_common' else 'common_internal_link'));continue
                        if pair in expected and dn&sn and dp and interchangeable:
                            observations.append(dict(context,classification='common_internal_link_equivalent_input_order'));continue
                        if pair in expected and (not dp or not sp):
                            findings.append(dict(context,**finding('source_uncertainty','internal_port_mapping',pair,None,'Portion pair exists, but a specific pinless terminal cannot be proven from the current model; no union-of-ports match is certified.')));continue
                        if driver['pin'] and sink['pin']:
                            observations.append(dict(context,classification='external_contact_installation_wire'));continue
                        findings.append(dict(context,**finding('discrepancy','internal_wiring',pair,sorted(expected),'Same-card pinless connection is absent from the common card graph.')))
    return findings,observations



def apply_reviewed_wiring_exceptions(spec,root,documents,findings,observations):
    """Record exact reviewed source anomalies; never change a net or terminal.

    A source uncertainty alone cannot prove an internal edge.  Each exception
    also needs a different, presently proven same-card witness and an existing
    canonical net.  Failed or changed evidence leaves the finding untouched.
    """
    exceptions=spec.get('audit_policy',{}).get('reviewed_wiring_exceptions',[])
    if not exceptions:return findings,[]
    root=Path(root).resolve();recorded=[];remaining=[]
    def bound_model(binding,page):
        if not isinstance(binding,dict) or set(binding)!={'path','sha256'}:return None
        path=resolve_path(root,binding.get('path','')).resolve()
        if not path.is_relative_to(root) or not path.is_file():return None
        matches=[(p,e)for p,e in documents.items()if Path(p).resolve()==path and e['document'].get('page')==page]
        if len(matches)!=1:return None
        p,entry=matches[0]
        if entry['sha256']!=binding.get('sha256') or digest(p)!=entry['sha256']:return None
        return entry['document']
    def source_net(doc,name):
        matches=[n for n in doc.get('nets',[])if n.get('id')==name]
        return matches[0]if len(matches)==1 else None
    def same_observation(first,second):
        # Only the model path has a portable spelling; every other literal is exact.
        if not isinstance(first,dict) or not isinstance(second,dict):return False
        normalized=[]
        for observation in (first,second):
            model=observation.get('model')
            if not isinstance(model,str) or not model:return False
            path=resolve_path(root,model).resolve()
            if not path.is_relative_to(root) or not path.is_file():return False
            value=deepcopy(observation);value['model']=str(path);normalized.append(value)
        return same_literal(*normalized)
    def valid(exception,flag):
        if not isinstance(exception,dict) or flag.get('status')!='source_uncertainty' or flag.get('field')!='internal_wiring':return False
        if exception.get('page')!=flag.get('page') or exception.get('net')!=flag.get('net'):return False
        expected=exception.get('finding')
        if not isinstance(expected,dict) or not same_literal(expected,{k:v for k,v in flag.items()if k!='model'}):return False
        doc=bound_model(exception.get('model'),flag['page'])
        if doc is None or resolve_path(root,exception['model']['path']).resolve()!=Path(flag.get('model','')).resolve():return False
        net=source_net(doc,flag['net'])
        if net is None or not same_literal(net,exception.get('source_net')):return False
        literals=exception.get('source_endpoints',{})
        if literals!={'driver':flag['driver']['id']+'.'+flag['driver']['label'],'target':flag['target']['id']+'.'+flag['target']['label']}:return False
        if net.get('driver')!=literals['driver'] or net.get('targets',[]).count(literals['target'])!=1:return False
        geometry=exception.get('source_geometry',[])
        if not isinstance(geometry,list) or not geometry:return False
        has_path=False
        for item in geometry:
            if not isinstance(item,dict) or set(item)!={'collection','index','observed'}:return False
            collection=item['collection'];index=item['index']
            if collection not in ('wire_paths','junctions','crossings') or type(index)is not int:return False
            values=doc.get(collection,[])
            if not isinstance(values,list) or not 0<=index<len(values) or not same_literal(values[index],item['observed']):return False
            if collection=='wire_paths' and values[index].get('net')==flag['net'] and not values[index].get('virtual_text'):has_path=True
        if not has_path:return False
        evidence=exception.get('evidence',{});ep=resolve_path(root,evidence.get('path','')).resolve()
        if not ep.is_relative_to(root) or not ep.is_file() or evidence.get('sha256')!=digest(ep):return False
        native=exception.get('native_review',{})
        rect=native.get('rectangle')
        if not native.get('document') or not re.fullmatch(r'[0-9a-f]{64}',str(native.get('sha256',''))) or not isinstance(rect,list) or len(rect)!=4 or any(type(v)is not int for v in rect) or not(rect[0]<rect[2] and rect[1]<rect[3]):return False
        if not isinstance(exception.get('reason'),str) or not exception['reason'].strip():return False
        witness=exception.get('independent_witness',{})
        obs=witness.get('observation')
        if not isinstance(obs,dict) or obs.get('classification')not in ('common_internal_link','common_internal_link_equivalent_input_order'):return False
        if not any(same_observation(o,obs)for o in observations):return False
        if obs.get('page')==flag['page']and obs.get('net')==flag['net']:return False
        wd=bound_model(witness.get('model'),obs.get('page'))
        if wd is None or resolve_path(root,witness['model']['path']).resolve()!=resolve_path(root,obs.get('model','')).resolve():return False
        wn=source_net(wd,obs.get('net'))
        if wn is None or not same_literal(wn,witness.get('source_net')):return False
        first,second=obs.get('driver',{}),obs.get('target',{})
        if not first.get('card_key') or first['card_key']!=second.get('card_key') or first.get('location')!=second.get('location'):return False
        if first.get('portion')!=flag['driver'].get('portion') or second.get('portion')!=flag['target'].get('portion'):return False
        members=witness.get('canonical_members',[])
        if not isinstance(members,list) or len(members)!=2 or len(set(members))!=2:return False
        ports={f"PORT:{b['portion']}:{p['id']}":(b['portion'],p['side'])for b in spec.get('boxes',[])for p in b.get('ports',[])}
        if [ports.get(m)for m in members]!=[(first['portion'],'output'),(second['portion'],'input')]:return False
        if not any(set(members)<=set(n)for n in spec.get('nets',[])):return False
        return True
    for flag in findings:
        matches=[e for e in exceptions if valid(e,flag)]
        if len(matches)!=1:remaining.append(flag);continue
        exception=matches[0]
        recorded.append({'page':flag['page'],'net':flag['net'],'model':flag['model'],
            'classification':'reviewed_source_anomaly','status':'recorded_variant',
            'reason':exception['reason'],'original_finding':deepcopy(flag),
            'source_net':deepcopy(exception['source_net']),'source_geometry':deepcopy(exception['source_geometry']),
            'reviewed_exception':deepcopy(exception)})
    return remaining,recorded





def audit(card,root=ROOT,definition_path=None,catalog_path=None,overrides_path=None,component_authority_path=None):
    root=Path(root).resolve();card=str(card).zfill(4)
    if not re.fullmatch(r'\d{4}',card):raise ValueError('Card number must have four digits.')
    dp=Path(definition_path) if definition_path else root/'json/Card-ALD/definitions'/f'{card}.json'
    cp=Path(catalog_path) if catalog_path else root/'json/Card types current'/f'{card}.json'
    op=Path(overrides_path) if overrides_path else root/'json/Card-ALD/build-overrides'/f'{card}.json'
    spec=read(dp);catalog=read(cp);overrides=read(op) if op.is_file() else {}
    if spec.get('card_type')!=card or catalog.get('card_type')!=card:raise ValueError('Definition/catalog card identity differs.')
    import multicircuit_variants as multi
    multi.check_spec(spec,root)
    context=accepted_page_context(root)
    documents,source_issues=load_documents(root,catalog,context)
    coverage_issues,identity_coverage=catalogue_source_coverage(root,catalog,documents)
    source_issues.extend(coverage_issues)
    corrections=apply_scoped_corrections(root,card,documents,overrides)
    import component_context
    net_context=component_context.apply_context(root,catalog,
        {entry['document'].get('page'):entry['document']for entry in documents.values()},
        {entry['document'].get('page'):{'path':path.relative_to(root).as_posix(),'sha256':entry['sha256']}for path,entry in documents.items()},
        authority_path=component_authority_path)
    source_issues.extend(finding('source_uncertainty','component_occurrence_net_origin',h,None,
        'Component K context lacks an exact current page-net origin proof.')for h in net_context.get('holds',[]))
    forms=expected_forms(spec);boxes={b['portion']:b for b in spec['boxes']};occurrences=[]
    for path,entry in documents.items():
        doc=entry['document']
        ground_context=ground_service_inputs(doc,spec['power_contacts'])
        for node in selected_source_nodes(doc,card):
            portion=str(node.get('portion'));box=boxes.get(portion)
            compared=deepcopy(node);compared['_source_page']=doc.get('page')
            compared['_source_model_binding']={'path':path.relative_to(root).as_posix(),'sha256':entry['sha256']}
            page_reader.attach_typed_terminals(compared,node)
            flags=compare_occurrence(compared,box,forms[portion],spec['power_contacts'],ground_context,defer_amplifier_fallback=True) if box else [finding('source_uncertainty' if '�' in portion else 'discrepancy','portion',portion,sorted(boxes),'Source portion does not exist in the common card definition.')]
            if node.get('source_reviewed')is not True:
                flags.append(finding('source_uncertainty','source_review_acceptance',node.get('source_reviewed'),True,'Occurrence is included, but explicit false/unknown review is not replaced by page acceptance.'))
            # Data-only exceptions require exact scope, literal field value and a current model binding.
            for exception in spec.get('audit_policy',{}).get('reviewed_exceptions',[]):
                if exception.get('page')!=doc.get('page') or exception.get('block')!=node.get('id'):continue
                evidence=exception.get('evidence',{});ep=resolve_path(root,evidence.get('path',''))
                valid=ep.is_file() and evidence.get('sha256')==digest(ep) and exception.get('model_sha256',entry['sha256'])==entry['sha256']
                for flag in flags:
                    if flag['field']==exception.get('field') and same_literal(flag['observed'],exception.get('observed')):
                        if valid:flag.update(status=exception.get('status','recorded_variant'),reason=exception.get('reason',flag['reason']),reviewed_exception=exception)
                        else:flag.update(status='source_uncertainty',reason='Reviewed exception evidence is stale or missing.',reviewed_exception=exception)
            if box:flags=amplifier_equivalence_fallback(compared,box,forms[portion],spec['power_contacts'],flags)
            occurrences.append({'page':doc.get('page'),'block':node.get('id'),'portion':portion,'location':node.get('location'),
                'model':str(path),'model_sha256':entry['sha256'],'node_pointer':node['_source_pointer'],'identity_adaptation':node.get('_identity_adaptation'),'source_reviewed':node.get('source_reviewed'),'source_review_inherited':node.get('_source_review_inherited',False),'findings':flags,
                'status':max((f['status'] for f in flags),key=SEVERITY.get,default='match')})
    wiring_docs,wiring_identity_issues=unambiguous_wiring_documents(documents,card)
    wires,wiring_observations=audit_wiring(card,spec,wiring_docs)
    wires,reviewed_wires=apply_reviewed_wiring_exceptions(spec,root,wiring_docs,wires,wiring_observations)
    wiring_observations.extend(reviewed_wires)
    review=[dict(page=o['page'],block=o['block'],node_pointer=o['node_pointer'],portion=o['portion'],**f) for o in occurrences for f in o['findings'] if f['status'] in ('discrepancy','source_uncertainty')]
    coverage_fields={'unresolved_wire_endpoint','stale_wire_endpoint','internal_port_mapping'}
    coverage=[r for r in wires if r['field'] in coverage_fields]+wiring_identity_issues
    review += [r for r in wires if r['field'] not in coverage_fields]+source_issues+[r for r in corrections if r['status']=='source_uncertainty']
    recheck_identity_context(context,documents)
    report={'schema':'card-use-audit-v1','created_utc':datetime.now(timezone.utc).isoformat(),'card_type':card,
        'read_only':True,'page_reader_tools':[{'path':str(p),'sha256':digest(p)} for p in page_reader.runtime_paths(root)],'definition':{'path':str(dp),'sha256':digest(dp)},'catalog':{'path':str(cp),'sha256':digest(cp)},
        'overrides':{'path':str(op),'sha256':digest(op)} if op.is_file() else None,
        'summary':{'pages':len(documents),'occurrences':len(occurrences),'occurrence_statuses':dict(Counter(o['status'] for o in occurrences)),
            'needs_review':len(review),'new_discrepancies':sum(r['status']=='discrepancy' for r in review),
            'source_uncertainties':sum(r['status']=='source_uncertainty' for r in review),'known_reviewed_source_corrections':sum(r['status']=='recorded_variant' for r in corrections),
            'coverage_limitations':len(coverage),'coverage_limitation_categories':dict(Counter(r['field'] for r in coverage)),
            'wiring_observations':dict(Counter(r['classification'] for r in wiring_observations))},
        'identity_coverage':identity_coverage,'identity_adapter':{'path':str(Path(page_reader.__file__).resolve()),'sha256':digest(page_reader.__file__)},'source_review_bindings':context['bindings'],
        'review':review,'coverage_limitations':coverage,'occurrences':occurrences,'known_reviewed_source_corrections':corrections,
        'wiring_observations':wiring_observations,'source_bindings':[{'path':str(p),'sha256':e['sha256']} for p,e in documents.items()],
        'interpretation':['A report identifies source/model differences; it does not assert every flagged item is a transcription error.',
            'Available unused inputs may be absent; power input annotations remain page-level ties.',
            'Common-graph internal links are checked when the source model actually represents them; omitted source links are not invented or flagged.',
            'AND/OR equivalence requires matching opposite input/output inversions, not merely interchangeable labels.',
            'Scoped reviewed corrections affect this audit memory only, and require current model hashes.']}
    if spec.get('multicircuit_preservation'):report['multicircuit_runtime']={'path':str(Path(multi.__file__).resolve()),'sha256':digest(multi.__file__)}
    return report



def write_reports(report,outdir):
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True);card=report['card_type']
    (outdir/f'{card} use audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    fields=['page','block','node_pointer','portion','status','field','observed','expected','reason']
    with (outdir/f'{card} review.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in report['review']:writer.writerow({k:json.dumps(row[k],ensure_ascii=False) if isinstance(row.get(k),(dict,list,tuple)) else row.get(k,'') for k in fields})
    s=report['summary'];lines=[f"CARD {card}: {s['occurrences']} occurrences on {s['pages']} pages",f"Review: {s['new_discrepancies']} discrepancies; {s['source_uncertainties']} uncertain; {s['known_reviewed_source_corrections']} known reviewed source corrections",f"Technical wiring coverage limitations: {s['coverage_limitations']} (all details retained separately in JSON)",'']
    lines += [f"{r.get('page','?')} {r.get('block','')} {r['field']}: {r['reason']}" for r in report['review']]
    (outdir/f'{card} review.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('card')
    parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--definition',type=Path);parser.add_argument('--catalog',type=Path);parser.add_argument('--overrides',type=Path);parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--component-authority',type=Path)
    args=parser.parse_args();report=audit(args.card,args.root,args.definition,args.catalog,args.overrides,args.component_authority)
    out=args.output_dir or args.root.parent/'tmp/ald-text/ald/card-use-audit'/report['card_type']
    write_reports(report,out);print(json.dumps({'output_directory':str(out),**report['summary']},ensure_ascii=False,indent=2))




_single_circuit_compare_occurrence=compare_occurrence
def compare_occurrence(node,box,forms,power,ground_context=None):
    import multicircuit_variants as multi
    circuit=node.get('unit',node.get('circuit_identifier'))
    if not box.get('_multicircuit_preservation') or circuit==box['circuit_identifier']:
        return _single_circuit_compare_occurrence(node,box,forms,power,ground_context)
    if not multi.match_source(node,box):
        return _single_circuit_compare_occurrence(node,box,forms,power,ground_context)
    canonical_box=deepcopy(box);canonical_box['circuit_identifier']=circuit
    findings=_single_circuit_compare_occurrence(node,canonical_box,forms,power,ground_context)
    findings.append(finding('recorded_variant','circuit_identifier',circuit,box['circuit_identifier'],
        'Exact source-bound alternate literal circuit identity; independently manual-qualified canonical form and unchanged physical wiring. No electrical-rating equivalence inferred.'))
    return findings




def amplifier_equivalent_form(node,form,pairs,circuit_matches):
    """Exhaustive positive-level truth comparison on the visible used inputs.

    N is accepted as a one-used-input notation only for the SAME reviewed
    portion and circuit; its voltage inversion is carried by the edge marks.
    Unknown functions are never equated just because their names resemble A/OR.
    """
    pf,ef=primary(node.get('function')),primary(form['function'])
    inputs=[p for p in pairs if p[0]['side']=='input' and page_reader.logical_gate_terminal(p[0]) and page_reader.logical_gate_terminal(p[1])]
    outputs=[p for p in pairs if p[0]['side']=='output' and page_reader.logical_gate_terminal(p[0]) and page_reader.logical_gate_terminal(p[1])]
    if not inputs or not outputs or len(inputs)>12:return False
    if 'N' in (pf,ef) and (len(inputs)!=1 or not circuit_matches):return False
    if pf not in ('A','OR','N','AR') or ef not in ('A','OR','N','AR'):return False
    if 'AR' in (pf,ef) and pf!=ef:
        # Manual AR is one logical input at indicated polarity. Compare that
        # used-input behavior only within the exact reviewed circuit identity;
        # never replace either literal function or infer an omitted contact.
        circuit=node.get('unit',node.get('circuit_identifier'))
        if (len(inputs)!=1 or not circuit_matches or circuit!=form.get('circuit_identifier')
                or not re.fullmatch(r'[A-Z][0-9]{2}[A-Z]{2}',str(circuit))):return False
    oi=[triangle(o) for o,_ in inputs];ei=[p['triangle'] for _,p in inputs]
    for actual,expected in outputs:
        for values in itertools.product((False,True),repeat=len(inputs)):
            a=boolean_output(pf,values,oi,triangle(actual))
            b=boolean_output(ef,values,ei,expected['triangle'])
            if a is None or b is None or a!=b:return False
    return True



def amplifier_equivalence_fallback(node,box,forms,power,findings):
    """Only a sole unresolved function discrepancy may gain manual AR equivalence.

    Existing exact variants/reviewed exceptions, stale-review holds and every
    physical/source uncertainty keep their original findings and precedence.
    """
    function=[f for f in findings if f.get('field')=='function_and_decorations']
    if len(function)!=1 or function[0].get('status')!='discrepancy':return findings
    if node.get('source_reviewed')is not True:return findings
    if any(f is not function[0]and f.get('status')in('source_uncertainty','discrepancy')for f in findings):return findings
    if primary(node.get('function'))!='AR'and not any(primary(f['function'])=='AR'for f in forms):return findings
    ignored={f.get('pin_index')for f in findings if f.get('field')in('input_only_AR_contact','power_contact','page_ground_service_input')}
    ports=[];seen=set()
    try:
        for index,port in enumerate(node.get('pins',[])):
            if index in ignored or index in page_reader.ar_input_only_aliases(node):continue
            pin=physical(port)
            if pin in power:continue
            side=port.get('side');symbols=page_reader.terminal_pin_symbols(port);edge=page_reader.terminal_border_symbol(port)
            if side not in('input','output')or type(triangle(port))is not bool:return findings
            signature=(side,pin,triangle(port),edge,json.dumps(symbols,sort_keys=True))
            if pin and signature in seen:continue
            if pin:seen.add(signature)
            clone=deepcopy(port);clone['pin']=pin;clone['_index']=index
            page_reader.project_occurrence_net_role(port,clone,page=node.get('_source_page'),node=node.get('id'),model_binding=node.get('_source_model_binding'))
            ports.append(clone)
    except ValueError:return findings
    circuit=node.get('unit',node.get('circuit_identifier'));matches=[]
    for form in forms:
        pf,ef=primary(node.get('function')),primary(form['function'])
        if 'AR'not in(pf,ef)or pf==ef:continue
        scope=form.get('_scoped_source')
        if scope and(scope.get('page')!=node.get('_source_page')or scope.get('node')!=node.get('id')or
            scope.get('node_pointer')!=node.get('_source_pointer')or not same_literal(scope.get('model_binding'),node.get('_source_model_binding'))):continue
        pairs=port_mapping(ports,form)
        if pairs is None:continue
        if any(page_reader.intrinsic_contact_role(o)!=page_reader.intrinsic_contact_role(p)for o,p in pairs):continue
        if any(triangle(o)!=p['triangle']for o,p in pairs if not page_reader.logical_gate_terminal(o)):continue
        symbols_equal=all((page_reader.terminal_pin_symbols(o)is None or page_reader.terminal_pin_symbols(o)==p.get('pin_symbols',{'prefix':[],'suffix':[]}))and
            ('_border_decorations'not in o or page_reader.terminal_border_symbol(o)==p.get('border_symbol'))for o,p in pairs)
        if symbols_equal and amplifier_equivalent_form(node,form,pairs,circuit==box['circuit_identifier']):matches.append(form['variant_number'])
    if not matches:return findings
    replacement=finding('equivalent','function_and_decorations',node.get('function'),box['function'],
        'After existing literal variants and exact reviewed exceptions, the same reviewed circuit has one used logical input and identical manual AR indicated-polarity behavior; both literal functions and all omitted/physical contacts remain unchanged.',variant_number=min(matches))
    return [replacement if f is function[0]else f for f in findings]



_compare_occurrence_before_amplifier_fallback=compare_occurrence
def compare_occurrence(node,box,forms,power,ground_context=None,*,defer_amplifier_fallback=False):
    findings=_compare_occurrence_before_amplifier_fallback(node,box,forms,power,ground_context)
    return findings if defer_amplifier_fallback else amplifier_equivalence_fallback(node,box,forms,power,findings)



if __name__=='__main__':main()

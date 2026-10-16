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


def primary(value):
    return str(value or '').strip().split(' ',1)[0].lstrip('✲*')


def physical(value):
    match = PIN.fullmatch(str(value or '').strip())
    return match['pin'] if match else None


def triangle(port):
    return bool(port.get('triangle')) or port.get('border_marker') == '◺'


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
            form['variant_number']=(variant or {}).get('number',0)
            key=(form['function'],tuple((p['id'],p['triangle']) for p in form['ports']))
            if not any(x['_key']==key for x in result[box['portion']]):
                form['_key']=key;result[box['portion']].append(form)
    return result


def port_mapping(ports,form):
    """Match physical contacts; pinless equivalent inputs may exchange rows."""
    available={p['id']:p for p in form['ports']};pairs=[]
    for observed in sorted(ports,key=lambda p:(physical(p.get('pin')) is None,p.get('row',0))):
        pin=physical(observed.get('pin'));side=observed['side']
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
    inputs=[p for p in pairs if p[0]['side']=='input']
    outputs=[p for p in pairs if p[0]['side']=='output']
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


def compare_occurrence(node,box,forms,power):
    """Pure comparison API used by the CLI and independent fixture tests."""
    findings=[];circuit=node.get('unit',node.get('circuit_identifier'))
    circuit_matches=circuit==box['circuit_identifier']
    if not circuit_matches:
        findings.append(finding('source_uncertainty' if not circuit or '�' in str(circuit) else 'discrepancy',
            'circuit_identifier',circuit,box['circuit_identifier'],'Circuit identifier differs from the reviewed common portion.'))
    ports=[];seen_contacts=set()
    expected_pins={(p['side'],p['pin']) for p in box['ports'] if p.get('pin')}
    observed_pins={(p.get('side'),physical(p.get('pin'))) for p in node.get('pins',[])}
    for index,port in enumerate(node.get('pins',[])):
        raw=port.get('pin');pin=physical(raw);side=port.get('side')
        if side not in ('input','output'):
            findings.append(finding('source_uncertainty','pin_direction',side,['input','output'],'Port has no usable direction.',pin_index=index));continue
        if pin in power:
            findings.append(finding('recorded_variant' if side=='input' else 'discrepancy','power_contact',raw,power[pin],
                'Page-level input supply/bias tie is separate from the card signal graph.' if side=='input' else 'A power contact is modeled as a driven output; inspect the source and module classification.',pin_index=index));continue
        if raw not in (None,'') and (str(raw).isdigit() or str(raw) in ('L','E','K','X')):
            findings.append(finding('recorded_variant','wire_annotation',raw,None,
                'Printed wire/border annotation is not a physical contact; its meaning is not inferred.',pin_index=index))
            raw=None
        if raw not in (None,'') and pin is None and not re.fullmatch(r'(?:IN|OUT|input|output)\d*',str(raw)):
            findings.append(finding('source_uncertainty','pin_identity',raw,None,
                'Not a valid single/double SLT physical contact or an unlabeled port.',pin_index=index));continue
        if pin and (side,pin,triangle(port)) in seen_contacts:
            findings.append(finding('recorded_variant','repeated_same_contact',f'{side}:{pin}',pin,
                'Repeated model terminal uses the same physical contact and polarity; it is one contact, not an extra gate input/output.',pin_index=index));continue
        if pin:seen_contacts.add((side,pin,triangle(port)))
        if pin and (side,pin) not in expected_pins:
            other='output' if side=='input' else 'input'
            if primary(node.get('function'))=='AR' and (other,pin) in observed_pins and (other,pin) in expected_pins:
                findings.append(finding('recorded_variant','shared_contact_passthrough',f'{side}:{pin}',f'{other}:{pin}',
                    'AR repeats the same physical input/output terminal; common drawing omits the redundant stub.',pin_index=index));continue
            findings.append(finding('discrepancy','pin_direction' if (other,pin) in expected_pins else 'pin_identity',
                f'{side}:{pin}',sorted(f'{s}:{p}' for s,p in expected_pins),
                'Physical contact is on the opposite side.' if (other,pin) in expected_pins else 'Contact is absent from this common portion.',pin_index=index))
        clone=deepcopy(port);clone['pin']=pin;clone['_index']=index;ports.append(clone)
    omitted=max(0,len([p for p in box['ports'] if p['side']=='input'])-len([p for p in ports if p['side']=='input']))
    if omitted:findings.append(finding('match','unused_inputs_omitted',omitted,None,'Unused available card inputs may be omitted on an installation ALD.'))
    matching=[]
    for form in forms:
        pairs=port_mapping(ports,form)
        if pairs is None:continue
        labels_equal=primary(node.get('function'))==primary(form['function'])
        decorations_equal=all(triangle(o)==p['triangle'] for o,p in pairs)
        if labels_equal and decorations_equal:
            status='match' if form['variant_number']==0 else 'recorded_variant'
            matching.append((status,form['variant_number']));continue
        if equivalent_form(node,form,pairs,circuit_matches):matching.append(('equivalent',form['variant_number']))
    if matching:
        status,number=min(matching,key=lambda x:SEVERITY[x[0]])
        findings.append(finding(status,'function_and_decorations',node.get('function'),box['function'],
            'Visible used-port function/polarity matches a declared complete notation form.' if status!='equivalent' else
            'AND/OR polarity presentation has the same truth table on the visible used inputs; no pin or circuit inference was made.',variant_number=number))
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


def load_documents(root,catalog):
    documents={};issues=[]
    for occurrence in catalog.get('diagram_occurrences',[]):
        source=Path(occurrence['source_text']);parts=list(source.parts)
        if parts[0]=='ALD':parts[0]='json'
        path=resolve_path(root,Path(*parts).with_suffix('.json'))
        if path in documents:continue
        if not path.is_file():issues.append(finding('source_uncertainty','source_model',str(path),None,'Published model is missing.'));continue
        doc=read(path)
        documents[path]={'document':doc,'sha256':digest(path),'original':deepcopy(doc)}
    # A stale/incomplete catalog must not hide a newly transcribed occurrence.
    # Only actual published page models are eligible; catalogs and card render
    # definitions have their own schemas and are not transcription sources.
    for path in (root/'json').rglob('*.json'):
        if path in documents or any(p in ('Card types','Card types current','Card-ALD') for p in path.relative_to(root/'json').parts[:-1]):continue
        try:doc=read(path)
        except (UnicodeError,json.JSONDecodeError):continue
        if not isinstance(doc,dict) or not isinstance(doc.get('nodes'),list):continue
        if not any(n.get('card_type')==catalog['card_type'] for n in doc['nodes'] if isinstance(n,dict)):continue
        documents[path]={'document':doc,'sha256':digest(path),'original':deepcopy(doc)}
    return documents,issues


def apply_scoped_corrections(root,card,documents,overrides):
    records=[]
    for correction in overrides.get('source_corrections',[]):
        binding=correction.get('model_binding',{});path=resolve_path(root,binding.get('path',''))
        entry=documents.get(path);status='recorded_variant'
        valid=bool(entry and binding.get('sha256')==entry['sha256'])
        nodes=[n for n in (entry or {}).get('document',{}).get('nodes',[]) if n.get('id')==correction.get('node') and n.get('card_type')==card]
        if not valid or len(nodes)!=1:
            records.append(dict(page=correction.get('page'),block=correction.get('node'),**finding('source_uncertainty','reviewed_source_correction',correction,None,'Scoped correction evidence is stale, missing or does not uniquely identify a card node.')));continue
        n=nodes[0]
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


def endpoint(node,label,side):
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
    problem=None if exact else 'Explicit endpoint label/ID has no matching modeled port.'
    listing=node.get('socket_listing_evidence') or {}
    if isinstance(listing,list):
        candidates=[p for p in listing if isinstance(p,dict) and p.get('board') and p.get('sockets')]
        listing=candidates[0] if len(candidates)==1 else {}
    if not isinstance(listing,dict):listing={}
    key=(listing.get('board'),tuple(sorted(listing.get('sockets',[])))) if listing.get('board') and listing.get('sockets') else None
    location=str(node.get('location') or '')
    stable_id=(exact[0].get('id') or str(exact[0].get('terminal_id') or '').split('.')[-1]) if len(exact)==1 else None
    return {'portion':str(node.get('portion')),'pin':physical(exact[0].get('pin')) if len(exact)==1 else None,
            'side':side,'label':label,'id':node['id'],'location':location,'card_key':key,'port_resolved':len(exact)==1,'stable_port_id':stable_id,'endpoint_problem':problem}


def audit_wiring(card,spec,documents):
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
            for first,second in itertools.combinations(drivers,2):
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
                            wrong_contact=bool(driver['endpoint_problem'] and physical(driver['label']) or sink['endpoint_problem'] and physical(sink['label']))
                            findings.append(dict(context,**finding('source_uncertainty','wire_endpoint_identity' if wrong_contact else 'stale_wire_endpoint',
                                [driver['label'],sink['label']],None,'Explicit wire endpoint contradicts current modeled ports; no common link is certified.')));continue
                        same=(driver['card_key'] is not None and driver['card_key']==sink['card_key']) or (driver['location']==sink['location'] and bool(driver['location']) and '�' not in driver['location'])
                        pair=(driver['portion'],sink['portion'])
                        if not same:
                            if not driver['pin'] or not sink['pin']:
                                findings.append(dict(context,**finding('source_uncertainty','internal_wiring',pair,None,'Pinless endpoint appears across different or unreadable card locations; inspect identity and route.')))
                            observations.append(dict(context,classification='between_card_installation_wire'));continue
                        dn,dp,_=possible_nets(driver);sn,sp,interchangeable=possible_nets(sink)
                        if pair in expected and dn&sn and dp and sp:
                            observations.append(dict(context,classification='common_internal_link'));continue
                        if pair in expected and dn&sn and dp and interchangeable:
                            observations.append(dict(context,classification='common_internal_link_equivalent_input_order'));continue
                        if pair in expected and (not dp or not sp):
                            findings.append(dict(context,**finding('source_uncertainty','internal_port_mapping',pair,None,'Portion pair exists, but a specific pinless terminal cannot be proven from the current model; no union-of-ports match is certified.')));continue
                        if driver['pin'] and sink['pin']:
                            observations.append(dict(context,classification='external_contact_installation_wire'));continue
                        findings.append(dict(context,**finding('discrepancy','internal_wiring',pair,sorted(expected),'Same-card pinless connection is absent from the common card graph.')))
    return findings,observations


def audit(card,root=ROOT,definition_path=None,catalog_path=None,overrides_path=None):
    root=Path(root).resolve();card=str(card).zfill(4)
    if not re.fullmatch(r'\d{4}',card):raise ValueError('Card number must have four digits.')
    dp=Path(definition_path) if definition_path else root/'json/Card-ALD/definitions'/f'{card}.json'
    cp=Path(catalog_path) if catalog_path else root/'json/Card types current'/f'{card}.json'
    op=Path(overrides_path) if overrides_path else root/'json/Card-ALD/build-overrides'/f'{card}.json'
    spec=read(dp);catalog=read(cp);overrides=read(op) if op.is_file() else {}
    if spec.get('card_type')!=card or catalog.get('card_type')!=card:raise ValueError('Definition/catalog card identity differs.')
    documents,source_issues=load_documents(root,catalog)
    catalog_ids={(o.get('page'),o.get('node')) for o in catalog.get('diagram_occurrences',[])}
    live_ids={(e['document'].get('page'),n.get('id')) for e in documents.values() for n in e['document'].get('nodes',[]) if n.get('card_type')==card}
    for page,block in sorted(live_ids-catalog_ids):
        source_issues.append(dict(page=page,block=block,**finding('source_uncertainty','catalog_coverage','source occurrence missing from catalog',None,'Occurrence found by inventorying current published models; included in this audit despite the catalog gap.')))
    for page,block in sorted(catalog_ids-live_ids):
        source_issues.append(dict(page=page,block=block,**finding('source_uncertainty','catalog_coverage','catalog occurrence missing from source model',None,'Catalog points to an absent current card occurrence.')))
    corrections=apply_scoped_corrections(root,card,documents,overrides)
    forms=expected_forms(spec);boxes={b['portion']:b for b in spec['boxes']};occurrences=[]
    for path,entry in documents.items():
        doc=entry['document']
        for node in doc.get('nodes',[]):
            if node.get('card_type')!=card:continue
            portion=str(node.get('portion'));box=boxes.get(portion)
            flags=compare_occurrence(node,box,forms[portion],spec['power_contacts']) if box else [finding('source_uncertainty' if '�' in portion else 'discrepancy','portion',portion,sorted(boxes),'Source portion does not exist in the common card definition.')]
            # Data-only exceptions require exact scope, literal field value and a current model binding.
            for exception in spec.get('audit_policy',{}).get('reviewed_exceptions',[]):
                if exception.get('page')!=doc.get('page') or exception.get('block')!=node['id']:continue
                evidence=exception.get('evidence',{});ep=resolve_path(root,evidence.get('path',''))
                valid=ep.is_file() and evidence.get('sha256')==digest(ep) and exception.get('model_sha256',entry['sha256'])==entry['sha256']
                for flag in flags:
                    if flag['field']==exception.get('field') and flag['observed']==exception.get('observed'):
                        if valid:flag.update(status=exception.get('status','recorded_variant'),reason=exception.get('reason',flag['reason']),reviewed_exception=exception)
                        else:flag.update(status='source_uncertainty',reason='Reviewed exception evidence is stale or missing.',reviewed_exception=exception)
            occurrences.append({'page':doc.get('page'),'block':node['id'],'portion':portion,'location':node.get('location'),
                'model':str(path),'model_sha256':entry['sha256'],'findings':flags,
                'status':max((f['status'] for f in flags),key=SEVERITY.get,default='match')})
    wires,wiring_observations=audit_wiring(card,spec,documents)
    review=[dict(page=o['page'],block=o['block'],portion=o['portion'],**f) for o in occurrences for f in o['findings'] if f['status'] in ('discrepancy','source_uncertainty')]
    coverage_fields={'unresolved_wire_endpoint','stale_wire_endpoint','internal_port_mapping'}
    coverage=[r for r in wires if r['field'] in coverage_fields]
    review += [r for r in wires if r['field'] not in coverage_fields]+source_issues+[r for r in corrections if r['status']=='source_uncertainty']
    return {'schema':'card-use-audit-v1','created_utc':datetime.now(timezone.utc).isoformat(),'card_type':card,
        'read_only':True,'definition':{'path':str(dp),'sha256':digest(dp)},'catalog':{'path':str(cp),'sha256':digest(cp)},
        'overrides':{'path':str(op),'sha256':digest(op)} if op.is_file() else None,
        'summary':{'pages':len(documents),'occurrences':len(occurrences),'occurrence_statuses':dict(Counter(o['status'] for o in occurrences)),
            'needs_review':len(review),'new_discrepancies':sum(r['status']=='discrepancy' for r in review),
            'source_uncertainties':sum(r['status']=='source_uncertainty' for r in review),'known_reviewed_source_corrections':sum(r['status']=='recorded_variant' for r in corrections),
            'coverage_limitations':len(coverage),'coverage_limitation_categories':dict(Counter(r['field'] for r in coverage)),
            'wiring_observations':dict(Counter(r['classification'] for r in wiring_observations))},
        'review':review,'coverage_limitations':coverage,'occurrences':occurrences,'known_reviewed_source_corrections':corrections,
        'wiring_observations':wiring_observations,'source_bindings':[{'path':str(p),'sha256':e['sha256']} for p,e in documents.items()],
        'interpretation':['A report identifies source/model differences; it does not assert every flagged item is a transcription error.',
            'Available unused inputs may be absent; power input annotations remain page-level ties.',
            'Common-graph internal links are checked when the source model actually represents them; omitted source links are not invented or flagged.',
            'AND/OR equivalence requires matching opposite input/output inversions, not merely interchangeable labels.',
            'Scoped reviewed corrections affect this audit memory only, and require current model hashes.']}


def write_reports(report,outdir):
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True);card=report['card_type']
    (outdir/f'{card} use audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    fields=['page','block','portion','status','field','observed','expected','reason']
    with (outdir/f'{card} review.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in report['review']:writer.writerow({k:json.dumps(row[k],ensure_ascii=False) if isinstance(row.get(k),(dict,list,tuple)) else row.get(k,'') for k in fields})
    s=report['summary'];lines=[f"CARD {card}: {s['occurrences']} occurrences on {s['pages']} pages",f"Review: {s['new_discrepancies']} discrepancies; {s['source_uncertainties']} uncertain; {s['known_reviewed_source_corrections']} known reviewed source corrections",f"Technical wiring coverage limitations: {s['coverage_limitations']} (all details retained separately in JSON)",'']
    lines += [f"{r.get('page','?')} {r.get('block','')} {r['field']}: {r['reason']}" for r in report['review']]
    (outdir/f'{card} review.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('card')
    parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--definition',type=Path);parser.add_argument('--catalog',type=Path);parser.add_argument('--overrides',type=Path);parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args();report=audit(args.card,args.root,args.definition,args.catalog,args.overrides)
    out=args.output_dir or args.root.parent/'tmp/ald-text/ald/card-use-audit'/report['card_type']
    write_reports(report,out);print(json.dumps({'output_directory':str(out),**report['summary']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()

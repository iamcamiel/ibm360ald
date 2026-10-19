"""Prove distinct anonymous outputs from complete same-card source witnesses.

No physical contacts, Boolean relation, or output short is inferred. This
capability is inactive for the historical single-anonymous-output path.
"""
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
from hashlib import sha256

SCHEMA='complete-joint-anonymous-output-witness-v1'

def _site(node):
    value=node.get('socket_listing_evidence')
    if not isinstance(value,dict):return None
    board=value.get('board');sockets=value.get('sockets')
    if not isinstance(board,str)or not board or '�'in board:return None
    if not isinstance(sockets,list)or not sockets or any(not isinstance(s,str)or not s or '�'in s for s in sockets):return None
    if len(set(sockets))!=len(sockets):return None
    return board,tuple(sorted(sockets))

def _ports(node,reader,side):
    return [(i,p)for i,p in reader.logical_terminal_items(node)
            if p.get('side')==side and reader.pinless_terminal(p)]

def _port_fact(index,p,reader):
    return {'index':index,'terminal_id':p.get('_terminal_id'),'side':p.get('side'),
            'reference':p.get('reference'),'row':p.get('row'),'point':deepcopy(p.get('point')),
            'pin':p.get('pin'),'physical_contact':reader.terminal_contact(p),
            'triangle':reader.wedge(p),'border_symbol':reader.terminal_border_symbol(p),
            'pin_symbols':reader.terminal_pin_symbols(p)}

def _node_fact(node,reader):
    return {'id':node.get('id'),'card_type':node.get('card_type'),'portion':node.get('portion'),
            'function':node.get('function'),'unit':node.get('unit'),'location':node.get('location'),
            'listing_site':_site(node),
            'ports':[_port_fact(i,p,reader)for i,p in enumerate(node.get('pins',[]))if isinstance(p,dict)]}

def _connected_path(model,net,driver_port,target_ports):
    paths=[p for p in model.get('wire_paths',model.get('paths',[]))if isinstance(p,dict)and p.get('net')==net.get('id')]
    if not paths:raise ValueError('Owned source route is absent')
    adjacency=defaultdict(set)
    for path in paths:
        points=path.get('points',[])
        for a,b in zip(points,points[1:]):
            if a==b:continue
            if not isinstance(a,list)or not isinstance(b,list)or len(a)!=2 or len(b)!=2:raise ValueError('Invalid owned route coordinates')
            if (a[0]==b[0])==(a[1]==b[1]):raise ValueError('Nonorthogonal owned source route')
            dx=(b[0]>a[0])-(b[0]<a[0]);dy=(b[1]>a[1])-(b[1]<a[1]);point=tuple(a)
            while point!=tuple(b):
                nxt=point[0]+dx,point[1]+dy;adjacency[point].add(nxt);adjacency[nxt].add(point);point=nxt
    if not isinstance(driver_port.get('point'),list):raise ValueError('Source terminal has no explicit route anchor')
    if tuple(driver_port['point'])not in adjacency:raise ValueError('Owned source route misses its driver anchor')
    start=tuple(driver_port['point']);pending=[start];seen=set()
    while pending:
        point=pending.pop()
        if point in seen:continue
        seen.add(point);pending.extend(adjacency[point]-seen)
    if not set(adjacency)<=seen:raise ValueError('Owned source route is disconnected')
    if any(not isinstance(p.get('point'),list)or tuple(p['point'])not in seen for p in target_ports):raise ValueError('Owned source route misses a declared target anchor')
    return {'paths':deepcopy(paths),'connected_cells':len(seen)}

def plan(card,models,reader):
    """Return an independently reproducible plan or an explicit held result.

    Multiple outputs match across complete physical instances only when every
    resolved source terminal has a unique, identical full target-incidence
    signature. A single output's fanout is one signature, never several slots.
    """
    occurrences=[];index={};groups=defaultdict(dict);counts=defaultdict(set)
    for page,model in sorted(models.items()):
        for node in model.get('nodes',[]):
            if not isinstance(node,dict):continue
            key=page,node.get('id')
            if key in index:return {'schema':SCHEMA,'passed':False,'holds':['Duplicate page/node identity'],'multi_portions':[]}
            index[key]=node
            if node.get('card_type')!=card:continue
            ports=_ports(node,reader,'output');counts[str(node.get('portion'))].add(len(ports))
            occurrences.append((page,node,ports))
    multi=sorted(p for p,values in counts.items()if max(values,default=0)>1)
    if not multi:return {'schema':SCHEMA,'passed':True,'multi_portions':[],'assignments':[],'channels':{},'witnesses':[]}
    holds=[];records=[];relevant=set(multi)
    for page,node,ports in occurrences:
        site=_site(node)
        if site:
            group=groups[page,site]
            portion=str(node.get('portion'))
            if portion in group:holds.append('Duplicate portion in one declared physical instance')
            group[portion]=node
        if str(node.get('portion'))not in multi:continue
        if not site:holds.append('Multi-output occurrence lacks an exact declared listing site');continue
        if len(ports)!=max(counts[str(node['portion'])]):holds.append('Partial multi-output occurrence');continue
        if node.get('source_reviewed')is not True:holds.append('Multi-output object lacks source review');continue
        for net in models[page].get('nets',[]):
            for ref in [net.get('driver')]+list(net.get('drivers')or[])+list(net.get('declared_physical_output_drivers')or[])+list(net.get('route_owners')or[]):
                if isinstance(ref,str)and ref.split('.',1)[0]==node['id']:
                    resolved=reader.resolve_net_port(node,ref,'output')
                    if resolved.get('status')not in ('ok','pinless','input_only_alias'):
                        holds.append('Multi-output owner has an unresolved or ambiguous declared driver')
        for pi,port in ports:
            try:
                fact=_port_fact(pi,port,reader)
                if not isinstance(fact['triangle'],bool):raise ValueError('Unknown output decoration')
                nets=[];target_facts=[];signatures=set();references=[]
                for ni,net in enumerate(models[page].get('nets',[])):
                    ref=net.get('driver')
                    if not isinstance(ref,str)or ref.split('.',1)[0]!=node['id']:continue
                    resolution=reader.resolve_net_port(node,ref,'output')
                    if resolution.get('port_index')!=pi:continue
                    if resolution.get('status')!='pinless':raise ValueError('Source alias is not one exact anonymous output')
                    if net.get('source_reviewed')is not True:raise ValueError('Owned net lacks source review')
                    for field in ('drivers','declared_physical_output_drivers','route_owners','same_block_output_ports'):
                        for other in net.get(field,[])or[]:
                            other_resolution=reader.resolve_net_port(node,other,'output')
                            if other_resolution.get('port_index')!=pi:raise ValueError('Multi-driver or joined-output net needs separate proof')
                    targets=[]
                    for target in net.get('targets',[]):
                        if not isinstance(target,str)or '.'not in target:raise ValueError('Anonymous source has a nonlocal target')
                        target_node=index.get((page,target.split('.',1)[0]))
                        if target_node is None or target_node.get('card_type')!=card or _site(target_node)!=site:raise ValueError('Anonymous output lacks a complete same-card target witness')
                        target_resolution=reader.resolve_net_port(target_node,target,'input')
                        if target_resolution.get('status')!='pinless':raise ValueError('Numbered/ambiguous target is outside this anonymous-output capability')
                        candidates=_ports(target_node,reader,'input')
                        if len(candidates)!=1 or target_resolution.get('port_index')!=candidates[0][0]:raise ValueError('Target anonymous input is ambiguous')
                        ti,tp=candidates[0]
                        if target_node.get('source_reviewed')is not True or not isinstance(reader.wedge(tp),bool):raise ValueError('Target source/decorative evidence is incomplete')
                        role=(str(target_node['portion']),'single-explicit-pinless-input')
                        signatures.add(role);relevant.add(str(target_node['portion']));targets.append(tp)
                        target_facts.append({'reference':target,'portion':target_node['portion'],'port':_port_fact(ti,tp,reader)})
                    if not targets:raise ValueError('Anonymous output has no witnessed intrinsic consumer')
                    route=_connected_path(models[page],net,port,targets)
                    nets.append({'net_index':ni,'net':deepcopy(net),'route':route});references.append(ref)
                if not nets:raise ValueError('Anonymous output lacks a declared source-owned net')
                records.append({'page':page,'node':node['id'],'portion':str(node['portion']),'site':site,
                                'source_port':fact,'references':sorted(set(references)),
                                'signature':sorted(signatures),'targets':target_facts,'owned_nets':nets})
            except (ValueError,KeyError,TypeError)as problem:holds.append(str(problem))
    # Each participating group must jointly show every relevant portion. The
    # check does not combine complementary partial installations into a card.
    active_groups=sorted({(r['page'],r['site'])for r in records})
    witnesses=[]
    for key in active_groups:
        group=groups[key]
        if not relevant<=set(group):holds.append('Joint source witness omits a required output or consumer portion');continue
        ids={group[p]['id']for p in relevant}
        incident=[deepcopy(n)for n in models[key[0]].get('nets',[])if any(isinstance(r,str)and r.split('.',1)[0]in ids for r in [n.get('driver')]+list(n.get('targets')or[])+list(n.get('drivers')or[])+list(n.get('declared_physical_output_drivers')or[])+list(n.get('route_owners')or[]))]
        netids={n.get('id')for n in incident}
        witnesses.append({'page':key[0],'site':key[1],
                          'source_objects':[_node_fact(group[p],reader)for p in sorted(relevant)],
                          'complete_incident_nets':incident,
                          'complete_incident_paths':[deepcopy(p)for p in models[key[0]].get('wire_paths',models[key[0]].get('paths',[]))if p.get('net')in netids],
                          'source_output_records':[r for r in records if(r['page'],r['site'])==key]})
    channels={};assignments=[]
    for portion in multi:
        selected=[r for r in records if r['portion']==portion]
        by_group=defaultdict(list)
        for r in selected:by_group[r['page'],r['site']].append(r)
        if set(by_group)!=set(active_groups):holds.append('Multi-output portions do not co-occur in every joint witness')
        signatures=None
        for group,rr in by_group.items():
            ss=[json.dumps(r['signature'],sort_keys=True)for r in rr]
            if len(ss)!=max(counts[portion])or len(set(ss))!=len(ss):holds.append('Anonymous output incidence does not uniquely distinguish every source terminal')
            if signatures is None:signatures=set(ss)
            elif signatures!=set(ss):holds.append('Multi-output incidence differs across physical instances')
        signatures=sorted(signatures or[])
        channels[portion]=[{'ref':'ANON_OUT:'+str(i+1),'id':'output:anonymous:'+str(i+1),'signature':json.loads(s)}for i,s in enumerate(signatures)]
        for r in selected:
            matches=[c for c in channels[portion]if c['signature']==[list(x)for x in r['signature']]]
            if len(matches)!=1:holds.append('Output assignment has no unique canonical slot');continue
            canonical=matches[0]
            assignments.append({'page':r['page'],'node':r['node'],'portion':portion,'source_port_index':r['source_port']['index'],
                                'source_terminal_id':r['source_port']['terminal_id'],'references':r['references'],
                                'canonical_port_id':canonical['id'],'canonical_ref':canonical['ref']})
    return {'schema':SCHEMA,'implementation':{'module':'anonymous_outputs','sha256':sha256(Path(__file__).read_bytes()).hexdigest()},
            'passed':not holds,'multi_portions':multi,'holds':sorted(set(holds)),
            'channels':channels,'assignments':sorted(assignments,key=lambda r:(r['page'],r['node'],r['source_port_index'])),
            'witnesses':witnesses}

def _networks(model):
    nets=defaultdict(lambda:{'inputs':[],'outputs':[],'exterior_pin':None})
    for portion,node in model['portions'].items():
        for side,key in (('input','_inputs'),('output','_outputs')):
            anonymous=0
            for port in node[key]:
                if port.get('pin'):
                    port.setdefault('id',side+':physical:'+port['pin']);net=nets[port['pin']];net['exterior_pin']=port['pin'];net[side+'s'].append([portion,port['id']])
                else:
                    anonymous+=1;port.setdefault('id',side+':anonymous:'+str(anonymous))
    def add(net,side,portion,port):
        value=[portion,port['id']]
        if value not in net[side+'s']:net[side+'s'].append(value)
    for edge in model['edges']:
        source=model['portions'][edge['source']];target=model['portions'][edge['target']];ref=edge['output_ref']
        if ref=='PINLESS':outputs=[p for p in source['_outputs']if p['pin']is None]
        elif ref.startswith('ANON_OUT:'):outputs=[p for p in source['_outputs']if p.get('ref')==ref]
        else:outputs=[p for p in source['_outputs']if p.get('pin')==ref]
        if len(outputs)!=1:raise ValueError('Canonical output slot is not unique')
        key=('INTERNAL:'+edge['source']+(':'+ref if ref!='PINLESS'else''))if outputs[0]['pin']is None else outputs[0]['pin']
        add(nets[key],'output',edge['source'],outputs[0])
        if edge['input_ref']=='PINLESS':
            inputs=[p for p in target['_inputs']if p['pin']is None and p.get('ref')==edge['source']]
            if len(inputs)!=1:raise ValueError('Canonical anonymous input is not unique')
            add(nets[key],'input',edge['target'],inputs[0])
        elif outputs[0]['pin']!=edge['input_ref']:
            raise ValueError('Numbered target needs an explicit supported contact-network proof')
    for fanout in model.get('input_contact_fanouts',[]):
        if fanout['input_ref']=='PINLESS':
            ports=[p for p in model['portions'][fanout['target']]['_inputs']if p.get('ref')=='INPUT_CONTACT:'+fanout['contact']]
            if len(ports)!=1:raise ValueError('Canonical input fanout is not unique')
            add(nets[fanout['contact']],'input',fanout['target'],ports[0])
    expected={(portion,side,p['id'])for portion,n in model['portions'].items()for side,key in (('input','_inputs'),('output','_outputs'))for p in n[key]}
    actual=[(portion,side,pid)for net in nets.values()for side in ('input','output')for portion,pid in net[side+'s']]
    if set(actual)!=expected or len(actual)!=len(expected):raise ValueError('Semantic port coverage is incomplete or a terminal joins two networks')
    return [{'id':key,**nets[key]}for key in sorted(nets)]

def preserve(model,models,reader,uncertainties):
    proof=plan(model['card_type'],models,reader)
    if not proof['passed']:
        uncertainties.append({'kind':'anonymous output joint witness incomplete','holds':proof['holds']});return model
    if not proof['multi_portions']:return model
    candidate=deepcopy(model);multi=set(proof['multi_portions']);lookup={(a['page'],ref):a for a in proof['assignments']for ref in a['references']}
    edges={}
    for edge in model['edges']:
        if edge['source']not in multi or edge['output_ref']!='PINLESS':
            key=edge['source'],edge['target'],edge['output_ref'],edge['input_ref'];edges[key]=deepcopy(edge);continue
        for evidence in edge['evidence']:
            a=lookup.get((evidence.get('page'),evidence.get('driver')))
            if a is None:raise ValueError('Existing edge lacks a complete source-terminal witness')
            key=edge['source'],edge['target'],a['canonical_ref'],edge['input_ref']
            if key not in edges:edges[key]={**{k:deepcopy(v)for k,v in edge.items()if k!='evidence'},'output_ref':a['canonical_ref'],'evidence':[]}
            edges[key]['evidence'].append(deepcopy(evidence))
    candidate['edges']=[edges[k]for k in sorted(edges)]
    for portion in multi:
        node=candidate['portions'][portion];node['_outputs']=[p for p in node['_outputs']if p['pin']is not None]
        for i,channel in enumerate(proof['channels'][portion]):
            node['_outputs'].append({'pin':None,'triangle':node['_observed_pinless_triangles']['output'],'side':'output','row':i,'ref':channel['ref'],'id':channel['id']})
    candidate['networks']=_networks(candidate);candidate['anonymous_output_preservation']=deepcopy(proof)
    uncertainties[:]=[u for u in uncertainties if not(u.get('kind')=='observed pinless ports have no reconstructed internal edge'and u.get('portion')in multi and u.get('side')=='output'and u.get('maximum_visible_pinless_ports')==len(proof['channels'][u['portion']])and u.get('reconstructed_pinless_ports')==1)]
    return candidate

def _canonical_slots(proof,spec):
    """Validate complete proved output partitions, not just portion pairs."""
    expected_identity={'module':'anonymous_outputs','sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    if proof.get('schema')!=SCHEMA or proof.get('passed')is not True or proof.get('implementation')!=expected_identity:
        raise ValueError('Anonymous-output proof has no current implementation identity')
    boxes={b['portion']:b for b in spec['boxes']}
    if len(boxes)!=len(spec['boxes']):raise ValueError('Duplicate canonical portion identity')
    for portion,channels in proof['channels'].items():
        for channel in channels:
            outputs=[p for p in boxes[portion]['ports']if p['id']==channel['id']and p['side']=='output'and p['pin']is None]
            if len(outputs)!=1:raise ValueError('Canonical anonymous output slot is absent')
            token='PORT:'+portion+':'+channel['id'];expected={token}
            for target,kind in channel['signature']:
                if kind!='single-explicit-pinless-input':raise ValueError('Unsupported anonymous consumer proof')
                inputs=[p for p in boxes[target]['ports']if p['side']=='input'and p.get('pin')is None]
                if len(inputs)!=1:raise ValueError('Canonical anonymous input slot is ambiguous')
                expected.add('PORT:'+target+':'+inputs[0]['id'])
            actual=[n for n in spec['nets']if token in n]
            if len(actual)!=1 or len(actual[0])!=len(expected)or set(actual[0])!=expected:
                raise ValueError('Canonical anonymous output partition differs from its complete source witness')

def attach(spec,model):
    """Attach only a freshly derived model proof, never an overlay copy."""
    proof=model.get('anonymous_output_preservation')
    if not proof:return spec
    _canonical_slots(proof,spec)
    spec['anonymous_output_preservation']=deepcopy(proof)
    spec['provenance']=deepcopy(spec['provenance'])
    spec['provenance']['anonymous_output_runtime']={'path':str(Path(__file__).resolve()),'sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    return spec

def audit_mapping(card,spec,models,reader):
    proof=spec.get('anonymous_output_preservation')
    if not proof:return {}
    current=plan(card,models,reader)
    # JSON normalization only bridges tuples/lists, never omits source facts.
    if not current['passed']or json.dumps(current,sort_keys=True)!=json.dumps(proof,sort_keys=True):raise ValueError('Anonymous-output complete source witness is stale, partial or ambiguous')
    _canonical_slots(current,spec)
    mapping={}
    for a in current['assignments']:
        key=a['page'],a['node'],a['source_port_index']
        mapping[key]=a['canonical_port_id']
    return mapping

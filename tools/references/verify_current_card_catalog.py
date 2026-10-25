"""Independently verify current catalogue coverage and accepted source bindings.

Does not import the catalogue builder. The independent socket verifier checks
the uniform dataset; this verifier compares every physical listing and node
partition directly with those accepted sources, including omitted records.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys
import importlib.util
_HERE=Path(__file__).resolve().parent
_RUNTIME=next((p/'ibm360ald/tools' for p in _HERE.parents if (p/'ibm360ald/tools/normalization').is_dir()),None)
if (_HERE.parent/'normalization').is_dir():_RUNTIME=_HERE.parent
if '--repo' in sys.argv:
    _index=sys.argv.index('--repo')
    if _index+1<len(sys.argv):_RUNTIME=Path(sys.argv[_index+1]).resolve()/'tools'
if _RUNTIME is None:raise ValueError('Normalization runtime unavailable')
sys.path.insert(0,str(_RUNTIME/'references'))
sys.path.insert(0,str(_RUNTIME/'normalization'))
import read_page as page_reader
import re
import verify_uniform_socket_listings as uniform_verifier

DATA = 'json/Socket listings uniform/Socket listings.json'
UNIFORM_MANIFEST = 'notes/Socket listings uniform/Build manifest.json'
UNRESOLVED='notes/Card types current/Unresolved identity occurrences.json'
UNRESOLVED_POLICY='Conflicting source identity is retained without choosing a card portion; excluded from resolved occurrences and profiles, never reclassified as annotation.'
SOURCE_IDENTITY_FIELDS=('card_type','portion','card','part','printed_card_portion','unit')

def independently_derived_conflicts(raw,canonical):
    """Re-derive exact source conflicts; never import the candidate builder."""
    pairs=set()
    for key in ('card','part','printed_card_portion'):
        value=raw.get(key)
        if isinstance(value,str) and re.fullmatch(r'[0-9]{4}[A-Z0-9]{2}',value):pairs.add((value[:4],value[4:]))
    aliases_conflict=len(pairs)>1
    for key,index in [('card_type',0),('portion',1)]:
        if raw.get(key) not in (None,'') and any(raw[key]!=pair[index] for pair in pairs):aliases_conflict=True
    printed=raw.get('printed_card_portion')
    if printed not in (None,'') and any(printed!=c+p for c,p in pairs):aliases_conflict=True
    def matches(pattern,value):return isinstance(value,str) and re.fullmatch(pattern,value) is not None
    legacy_roles=(matches(r'[A-Z][0-9]{2}[A-Z]{2}',raw.get('technology'))
        and matches(r'(?:[0-9]{2})?[A-Z]-[A-Z][0-9][A-Z][0-9](?:[BT])?',raw.get('card'))
        and matches(r'[0-9]+[A-Z]-[A-Z0-9]+',raw.get('location'))
        and matches(r'[0-9]{4}[A-Z0-9]{2}',raw.get('part')))
    circuit_conflict='unit' in raw and legacy_roles and raw['unit']!=raw['technology']
    need((canonical['card_identity']['parse_status']=='conflict')==aliases_conflict,'Canonical/source identity conflict replay differs')
    need((canonical['circuit']['parse_status']=='conflict')==circuit_conflict,'Canonical/source circuit conflict replay differs')
    reasons=[]
    if aliases_conflict:reasons.append('card_identity_conflict')
    if circuit_conflict:reasons.append('circuit_identity_conflict')
    if aliases_conflict:reasons.append('identity_alias_conflict')
    return sorted(reasons)

def unresolved_occurrence(raw,canonical,*,page,source_model,source_model_sha256,source_text,text_sha256,index):
    reasons=independently_derived_conflicts(raw,canonical)
    if not reasons:return None
    return {'page':page,'node':raw.get('id'),'node_pointer':f'/nodes/{index}',
        'source_model':source_model,'source_model_sha256':source_model_sha256,
        'source_text':source_text,'text_sha256':text_sha256,
        'identity_status':'unresolved_identity','reason_codes':reasons,
        'source_fields':{key:deepcopy(raw.get(key)) for key in SOURCE_IDENTITY_FIELDS},
        'canonical_identity_parse_status':canonical['card_identity']['parse_status'],
        'canonical_circuit_parse_status':canonical['circuit']['parse_status'],
        'source_node_json':json.dumps(raw,ensure_ascii=False,sort_keys=True,separators=(',',':')),
        'annotation_flags':[],'profile_eligible':False,'selected_identity':None}

def expected_family_index(observations):
    links=defaultdict(set)
    for occurrence in observations:
        fields=occurrence['source_fields'];families=set()
        for key in ('card_type','card','part','printed_card_portion'):
            value=fields.get(key);pattern=r'[0-9]{4}' if key=='card_type' else r'[0-9]{4}[A-Z0-9]{2}'
            if isinstance(value,str) and re.fullmatch(pattern,value):families.add(value[:4])
        for family in families:links[family].add((occurrence['source_model'],occurrence['node_pointer']))
    return [{'card_type':family,'occurrences':[{'source_model':model,'node_pointer':pointer} for model,pointer in sorted(members)]} for family,members in sorted(links.items())]

def verify_family_index(bucket,expected_observations):
    need(bucket['family_index']==expected_family_index(expected_observations),'Unresolved family index omits, duplicates, invents or chooses a source claim')

def resolved_source_node(raw,canonical):
    """The existing normalized fact projection, only after conflict exclusion."""
    result=deepcopy(raw);identity=canonical['card_identity']
    need(not independently_derived_conflicts(raw,canonical),'Unresolved node reached resolved projection')
    if identity['parse_status']=='resolved':
        result['card_type']=identity['card_type'];result['portion']=identity['portion']
    for key,section,field in [('function','function','label'),('unit','circuit','identifier'),('location','site','label')]:
        if field in canonical[section]:result[key]=deepcopy(canonical[section][field])
    if canonical['site'].get('grid_label') is not None:result['grid']=deepcopy(canonical['site']['grid_label'])
    return result

def expected_pin(pin,widths):
    label=pin.get('pin');printed=pin.get('printed_pin',pin.get('printed_label',label))
    pattern=r'[BDGJ](?:0[2-9]|1[0-3])'
    exact=isinstance(label,str) and re.fullmatch(pattern,label)
    starred=isinstance(label,str) and label.endswith('✲') and re.fullmatch(pattern,label[:-1])
    candidate=label if exact else label[:-1] if starred else None
    status='exact' if exact else 'asterisk suffix' if starred else 'unlabeled' if label in (None,'') else 'unparsed'
    physical=pin.get('physical_pin')
    if isinstance(physical,str) and re.fullmatch(pattern,physical):
        printed_contact=printed[:-1] if isinstance(printed,str) and printed.endswith('✲') else printed
        if (candidate is not None and candidate!=physical) or (isinstance(printed_contact,str) and re.fullmatch(pattern,printed_contact) and printed_contact!=physical):candidate=None;status='conflicting physical contact fields'
        elif candidate is None and 'pin' not in pin:candidate=physical;status='explicit physical_pin'
    letters={'B','D'} if widths==['SINGLE CARD'] else {'B','D','G','J'} if widths==['DOUBLE CARD'] else None
    return {'side':pin.get('side'),'pin':label,'printed_pin':printed,'physical_pin_candidate':candidate,
        'physical_pin_parse_status':status,'valid_physical_pin_syntax':True if candidate else None,
        'triangle':pin.get('triangle'),'border_marker':pin.get('border_marker'),'row':pin.get('row'),
        'net':pin.get('net'),'valid_for_observed_card_width':None if letters is None or candidate is None else candidate[0] in letters}

def expected_occurrence(node,text,pointer,page,widths):
    literal=node.get('function');label=' '.join(literal.split()) if isinstance(literal,str) and literal.strip() else None
    primary=None if label is None or '�' in label else 'R' if label.startswith(('R T','R DR')) else label.split(' ',1)[0]
    pins=[expected_pin(p,widths) for p in node.get('pins',[])];ins=[p for p in pins if p['side']=='input'];outs=[p for p in pins if p['side']=='output']
    value={'page':page,'node':node.get('id'),'node_pointer':pointer,'source_text':text,
        'portion':str(node['portion']) if node.get('portion') is not None else None,
        'printed_card_portion':node.get('printed_card_portion'),'function_literal':literal,
        'function_label':label,'primary_function':primary,'circuit_identifier':node.get('unit'),
        'location':node.get('location'),'grid':node.get('grid'),'pins':pins,
        'observed_shape':{'visible_inputs':len(ins),'visible_outputs':len(outs),
            'input_triangles':sum(p['triangle'] is True for p in ins),'output_triangles':sum(p['triangle'] is True for p in outs),
            'input_pin_labels':sum(bool(p['pin']) for p in ins),'output_pin_labels':sum(bool(p['pin']) for p in outs)},
        'source_reviewed':node['_expected_review']}
    audit=node['_expected_identity_audit']
    if audit['status']=='adapted':value['identity_adaptation']=audit
    if node['_expected_review_inherited']:value['source_review_basis']='Hash-bound accepted page model and TXT; explicit page source_reviewed true, node review absent'
    return value

def expected_profiles(occurrences):
    groups=defaultdict(list)
    for occurrence in occurrences:
        key=(occurrence['portion'],occurrence['primary_function'],occurrence['circuit_identifier'],json.dumps(occurrence['observed_shape'],sort_keys=True))
        groups[key].append(occurrence)
    return [{'portion':portion,'primary_function':function,'circuit_identifier':circuit,'observed_shape':json.loads(shape),
        'occurrences':len(members),'examples':[f"{x['page']} {x['node']}" for x in members[:8]]}
        for (portion,function,circuit,shape),members in sorted(groups.items(),key=lambda item:tuple(str(x) for x in item[0]))]

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _unique_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON key: '+key)
        result[key]=value
    return result

def _finite_constant(value):raise ValueError('Non-finite JSON constant: '+value)

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),object_pairs_hook=_unique_pairs,parse_constant=_finite_constant)
def need(ok,message):
    if not ok:raise ValueError(message)
def inside(root,relative):
    need(isinstance(relative,str) and '\\' not in relative and not Path(relative).is_absolute()
         and Path(relative).as_posix()==relative and '..' not in Path(relative).parts,'Unsafe catalogue/source path')
    path=(root/relative).resolve();need(path.is_relative_to(root),'Path escapes root');return path


def expected_identity(raw):
    view=deepcopy(raw);evidence=[]
    for field in ('card','part','printed_card_portion'):
        text=raw.get(field)
        if isinstance(text,str) and len(text)==6 and text[:4].isascii() and text[:4].isdigit() and re.fullmatch('[A-Z0-9]{2}',text[4:]):
            evidence.append((field,text[:4],text[4:]))
    if not evidence:return view,{'status':'unchanged','source_fields':{}}
    pairs={(c,p)for _,c,p in evidence}
    need(len(pairs)==1,'Conflicting exact combined source identities')
    card,portion=next(iter(pairs))
    for field,value in [('card_type',card),('portion',portion),('printed_card_portion',card+portion)]:
        need(raw.get(field)in(None,'',value),'Combined identity disagrees with declared source field')
    filled=[]
    for field,value in [('card_type',card),('portion',portion),('printed_card_portion',card+portion)]:
        if view.get(field)in(None,''):view[field]=value;filled.append(field)
    return view,{'status':'adapted'if filled else'unchanged','filled_fields':filled,'source_fields':{f:raw.get(f)for f,_,_ in evidence}}

def verify(repo,root,tools_root=None):
    repo,root=Path(repo).resolve(),Path(root).resolve();guards={}
    tools_root=Path(tools_root).resolve() if tools_root is not None else repo
    logical_tools={'tools/references/'+n for n in ['build_current_card_catalog.py','verify_current_card_catalog.py','verify_uniform_socket_listings.py','current_card_identity.py']}
    contract_paths={'catalogue_identity_schema':'Contracts/catalogue_identity.schema.json','auxiliary_catalogue_contracts':'Contracts/auxiliary_catalogue_contracts.py'}
    logical_tools.update(contract_paths.values())
    need((tools_root/'Contracts/auxiliary_catalogue_contracts.py').is_file(),'Central catalogue contract module missing')
    spec=importlib.util.spec_from_file_location('independent_auxiliary_contracts',tools_root/'Contracts/auxiliary_catalogue_contracts.py');contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
    def checked(relative,expected,base=repo):
        path=inside(base,relative);need(digest(path)==expected,'Changed catalogue/source: '+relative)
        guards[path]=expected;return path
    mp=root/'notes/Card types current/Build manifest.json';m=read(mp);guards[mp]=digest(mp)
    need(m['schema']=='current-card-catalog-build-v2','Unsupported catalogue')
    contract.validate_document(m)
    need(set(m['contracts'])==set(contract_paths),'Contract inventory differs')
    for key,relative in contract_paths.items():
        need(m['contracts'][key]=={'path':relative,'sha256':digest(inside(tools_root,relative))},'Stale central contract: '+key)
    bindings=m['source_binding'];provenance=read(checked('notes/Reviewed export provenance.json',bindings['reviewed_export_provenance_sha256']))
    content=read(checked('notes/Content data manifest.json',bindings['content_data_manifest_sha256']))
    um=read(checked(UNIFORM_MANIFEST,bindings['uniform_manifest_sha256']))
    uniform=read(checked(DATA,bindings['uniform_dataset_sha256']))
    uv=uniform_verifier.verify(repo);need(uv['passed'] and not uv['failures'],'Uniform independent verification failed: '+str(uv['failures']))
    inputs={x['path']:x['sha256']for x in um['inputs']}
    for relative,expected in inputs.items():checked(relative,expected)
    accepted,by_scan={},{}
    for entry in provenance['exported']:
        parts=str(entry['destination']).replace('\\','/').split('/ALD/',1);need(len(parts)==2,'Invalid accepted destination')
        rel='ALD/'+parts[1];inside(repo,rel);need(rel not in accepted,'Duplicate accepted source');accepted[rel]=entry
        if rel in inputs:
            scan=str(entry['source_scan_id']);need(scan not in by_scan,'Duplicate uniform scan');by_scan[scan]=rel
    pages,nodes,annotations={}, {},[];counts=Counter();unresolved_nodes=[];partition=[];unresolved_families=set()
    for item in content['files']:
        if item['role']!='Published page content model':continue
        relative=item['path'];need(relative.startswith('json/') and relative.endswith('.json'),'Invalid model path')
        document=read(checked(relative,item['sha256']))
        from pages import validate_current_page
        validate_current_page(document);model=page_reader.source_view(document);text='ALD/'+relative[5:-5]+'.txt'
        canonical={o['source_form']['ordinal']:o for o in document['objects'] if o['source_form']['container']=='nodes' and o['source_form']['value_type']=='object'}
        need(text in accepted and text not in pages,'Missing/duplicate accepted model source')
        entry=accepted[text];checked(text,entry['text_sha256'])
        pages[text]={'page':model.get('page',entry['page']),'model':relative,'model_sha256':item['sha256'],
            'text_sha256':entry['text_sha256'],'source_scan_id':entry.get('source_scan_id'),'source_relative':entry.get('source_relative')}
        counts['models']+=1
        for index,node in enumerate(model.get('nodes',[])):
            counts['diagram_nodes']+=1;pointer=f'/nodes/{index}'
            flags=[key for key in ('symbol_only','annotation_only','annotation_block')if node.get(key)is True]
            if flags:
                partition.append({'source_model':relative,'node_pointer':pointer,'bucket':'annotation','card_type':None})
                counts['annotation_nodes_excluded']+=1
                annotations.append({'page':model.get('page',entry['page']),'node':node.get('id'),'source_text':text,
                    'source_model':relative,'source_model_sha256':item['sha256'],'text_sha256':entry['text_sha256'],
                    'node_pointer':pointer,'card_type_literal':node.get('card_type'),'circuit_identifier':node.get('unit'),
                    'function_literal':node.get('function'),'explicit_flags':flags})
            else:
                need(index in canonical,'Canonical node ownership missing')
                unresolved=unresolved_occurrence(node,canonical[index],page=model.get('page',entry['page']),source_model=relative,source_model_sha256=item['sha256'],source_text=text,text_sha256=entry['text_sha256'],index=index)
                if unresolved is not None:
                    contract.validate_unresolved_occurrence(unresolved);unresolved_nodes.append(unresolved);counts['unresolved_identity_occurrences']+=1
                    partition.append({'source_model':relative,'node_pointer':pointer,'bucket':'unresolved_identity','card_type':None})
                    for key in ('card_type','card','part','printed_card_portion'):
                        value=node.get(key)
                        if isinstance(value,str) and re.fullmatch(r'[0-9]{4}' if key=='card_type' else r'[0-9]{4}[A-Z0-9]{2}',value):unresolved_families.add(value[:4])
                    continue
                node=resolved_source_node(node,canonical[index])
                view,audit=expected_identity(node)
                if isinstance(view.get('card_type'),str)and re.fullmatch('[0-9]{4}',view['card_type']):
                    view['_expected_identity_audit']=audit
                    view['_expected_review']=node.get('source_reviewed',model.get('source_reviewed')is True)
                    view['_expected_review_inherited']='source_reviewed'not in node and model.get('source_reviewed')is True
                    nodes[(text,pointer)]=view;counts['card_occurrences']+=1
                    partition.append({'source_model':relative,'node_pointer':pointer,'bucket':'resolved','card_type':view['card_type']})
                else:
                    counts['nodes_without_card_type']+=1;partition.append({'source_model':relative,'node_pointer':pointer,'bucket':'no_card_type','card_type':None})
    counts['unresolved_identity_occurrences']+=0
    need(len(partition)==counts['diagram_nodes'],'Node partition does not cover every source node')
    need(len({(x['source_model'],x['node_pointer']) for x in partition})==len(partition),'Duplicate source node partition')
    contract.validate_partition(m['node_partition'],m['counts'])
    need(sorted(m['node_partition'],key=lambda x:(x['source_model'],x['node_pointer']))==sorted(partition,key=lambda x:(x['source_model'],x['node_pointer'])),'Complete source node partition differs')
    ub=m['unresolved_identity_occurrences'];need(set(ub)=={'path','sha256'} and ub['path']==UNRESOLVED,'Wrong unresolved bucket binding')
    bucket=read(checked(ub['path'],ub['sha256'],root));contract.validate_document(bucket)
    need(bucket['schema']=='current-card-catalog-unresolved-identities-v1' and bucket['policy']==UNRESOLVED_POLICY,'Unresolved bucket policy/status differs')
    need(bucket['count']==len(unresolved_nodes) and bucket['observations']==sorted(unresolved_nodes,key=lambda x:(x['source_text'],x['node_pointer'])),'Unresolved source identity occurrence omitted, changed, duplicated, or chosen')
    verify_family_index(bucket,unresolved_nodes)
    need(m['source_pages']==pages,'Accepted model coverage differs')
    expected_inputs={**inputs,'notes/Reviewed export provenance.json':bindings['reviewed_export_provenance_sha256'],
        'notes/Content data manifest.json':bindings['content_data_manifest_sha256'],
        UNIFORM_MANIFEST:bindings['uniform_manifest_sha256'],DATA:bindings['uniform_dataset_sha256']}
    for text,binding in pages.items():expected_inputs.update({text:binding['text_sha256'],binding['model']:binding['model_sha256']})
    for name in ['build_current_card_catalog.py','verify_current_card_catalog.py','verify_uniform_socket_listings.py','current_card_identity.py']:
        relative='tools/references/'+name;expected_inputs[relative]=digest(tools_root/relative)
    for relative in contract_paths.values():expected_inputs[relative]=digest(tools_root/relative)
    for path in page_reader.runtime_paths(repo):expected_inputs[path.relative_to(repo).as_posix()]=digest(path)
    actual_inputs={x['path']:x['sha256']for x in m['source_inputs']}
    need(len(actual_inputs)==len(m['source_inputs'])and actual_inputs==expected_inputs,'Declared catalogue source input inventory differs')
    for relative,expected in actual_inputs.items():checked(relative,expected,tools_root if relative in logical_tools else repo)
    output_paths={x['path']for x in m['files']};need(len(output_paths)==len(m['files']),'Duplicate catalogue output')
    for item in m['files']:checked(item['path'],item['sha256'],root)
    generated={p.relative_to(root).as_posix()for branch in ['json/Card types current','csv/Card types current','notes/Card types current']for p in(root/branch).glob('*')if p.is_file()}
    need(generated==output_paths|{'notes/Card types current/Build manifest.json'},'Catalogue output inventory differs')
    records=uniform['records'];need(len({r['id']for r in records})==len(records),'Duplicate uniform record IDs')
    physical={r['id']:(i,r)for i,r in enumerate(records)if r.get('card_type')is not None and 'CARD'in str(r.get('kind_literal'))}
    need(len(physical)==uniform['counts']['card_instances']==um['counts']['card_instances'],'Physical card count differs')
    typed={rid:v for rid,v in physical.items()if isinstance(v[1]['card_type'],str)and re.fullmatch('[0-9]{4}',v[1]['card_type'])}
    counts.update({'listing_records':len(typed),'physical_card_records':len(physical),'unclassified_listing_records':len(physical)-len(typed)})
    def check_listing(listing,index,record):
        header=record['header_source'];source=by_scan[str(header['scan_id'])];refs=deepcopy(record['references'])
        for ref in refs:ref['printed_portions']=deepcopy(ref['portions'])
        expected={'record_id':record['id'],'page':header['page'],'record_pointer':f'/records/{index}',
            'source_text':source,'source_text_sha256':inputs[source],'source_model':DATA,
            'source_model_sha256':bindings['uniform_dataset_sha256'],'board':record['board'],
            'sockets':record['sockets'],'physical_sockets':record['physical_sockets'],
            'kind':{'single_card':'SINGLE CARD','double_card':'DOUBLE CARD'}.get(record['kind']),
            'kind_normalized':record['kind'],'kind_literal':record['kind_literal'],'part_number':record['part_number'],
            'references':refs,'unused_portions':record['unused_portions'],'header_source':header,
            'source_spans':record['source_spans'],'source_reviewed':True,
            'source_review_basis':'Current accepted TXT and uniform source spans; no new visual acceptance'}
        need(listing==expected,'Catalogue listing fields/evidence differ: '+record['id'])
    seen_nodes,seen_records,types=set(),set(),set();profiles=0
    for path in sorted((root/'json/Card types current').glob('*.json')):
        card=read(path);need(re.fullmatch('[0-9]{4}',path.stem)and card['card_type']==path.stem,'Invalid catalogue card');types.add(path.stem)
        for listing in card['listing_records']:
            rid=listing['record_id'];need(rid in typed and rid not in seen_records,'Unknown/duplicate physical listing: '+rid)
            index,record=typed[rid];need(record['card_type']==path.stem,'Listing assigned to wrong type');check_listing(listing,index,record);seen_records.add(rid)
        kinds=sorted({x['kind']for x in card['listing_records']if x['kind']})
        need(card['listing_kinds_observed']==kinds,'Pagination treated as electrical kind')
        need(card['physical_card_widths_observed']==sorted(set(kinds)&{'SINGLE CARD','DOUBLE CARD'}),'Invented physical width')
        for occurrence in card['diagram_occurrences']:
            key=(occurrence['source_text'],occurrence['node_pointer']);need(key in nodes and key not in seen_nodes,'Unknown/duplicate/annotation physical node');node=nodes[key]
            need(node['card_type']==path.stem,'Occurrence card differs')
            audit=node['_expected_identity_audit']
            need(occurrence.get('identity_adaptation')==(audit if audit['status']=='adapted'else None),'Identity alias proof differs')
            need(occurrence.get('source_reviewed')==node['_expected_review'],'Source review inheritance differs')
            expected_basis='Hash-bound accepted page model and TXT; explicit page source_reviewed true, node review absent'if node['_expected_review_inherited']else None
            need(occurrence.get('source_review_basis')==expected_basis,'Source review basis differs')
            for field,raw in [('node','id'),('function_literal','function'),('circuit_identifier','unit'),('location','location'),('grid','grid')]:need(occurrence[field]==node.get(raw),'Occurrence source field differs')
            need(occurrence['portion']==(str(node['portion'])if node.get('portion')is not None else None),'Occurrence portion differs');seen_nodes.add(key)
            need(occurrence==expected_occurrence(node,key[0],key[1],pages[key[0]]['page'],card['physical_card_widths_observed']),'Exact occurrence/pin/physical-status projection differs')
        need(card['portion_profiles']==expected_profiles(card['diagram_occurrences']),'Resolved-only profile partition differs or unresolved identity chosen')
        profiles+=len(card['portion_profiles']);need(sum(x['occurrences']for x in card['portion_profiles'])==len(card['diagram_occurrences']),'Profile partition differs')
    need(seen_records==set(typed),'Catalogue omits physical listings');need(seen_nodes==set(nodes),'Catalogue omits physical diagram nodes')
    need(types=={r['card_type']for _,r in typed.values()}|{n['card_type']for n in nodes.values()}|unresolved_families,'Card type coverage differs')
    a=m['uniform_listing_authority'];need(a['manifest']=={'path':UNIFORM_MANIFEST,'sha256':bindings['uniform_manifest_sha256']}and a['dataset']=={'path':DATA,'sha256':bindings['uniform_dataset_sha256']}and a['inputs']==um['inputs'],'Uniform listing authority bindings differ')
    need(a['logical_records']==len(records)and a['physical_card_records']==len(physical)and a['typed_card_records']==len(typed),'Listing authority count differs')
    unresolved=a['unclassified_card_records'];need(len(unresolved)==len(physical)-len(typed),'Unclassified listing count differs');seen_unknown=set()
    for item in unresolved:
        rid=item['listing_record']['record_id'];need(rid in physical and rid not in typed and rid not in seen_unknown,'Unknown unresolved listing');index,record=physical[rid];check_listing(item['listing_record'],index,record);need(item['card_type_literal']==record['card_type'],'Unresolved card literal changed');seen_unknown.add(rid)
    excluded=read(root/'notes/Card types current/Excluded annotation nodes.json')
    need(excluded['count']==len(annotations)and excluded['observations']==sorted(annotations,key=lambda x:(x['source_text'],x['node_pointer'])),'Annotation exclusion provenance differs')
    for key,value in counts.items():need(m['counts'].get(key,0)==value,'Catalogue count differs: '+key)
    need(m['card_types']==len(types)and m['portion_profiles']==profiles,'Catalogue summary differs')
    with(root/'csv/Card types current/Diagram occurrences.csv').open(encoding='utf-8',newline='')as stream:csv_nodes=list(csv.DictReader(stream))
    need(Counter((r['source_text'],r['node_pointer'])for r in csv_nodes)==Counter(seen_nodes),'Occurrence CSV coverage differs')
    with(root/'csv/Card types current/Card types.csv').open(encoding='utf-8',newline='')as stream:summary=list(csv.DictReader(stream))
    need(len(summary)==len(types)and {r['card_type']for r in summary}==types and sum(int(r['listing_records'])for r in summary)==len(typed),'Listing summary CSV coverage differs')
    for path,expected in guards.items():need(digest(path)==expected,'Input/output changed during verification')
    return {'passed':True,'card_types':len(types),'diagram_occurrences':len(seen_nodes),'portion_profiles':profiles,
        'source_pages':len(pages),'files':len(output_paths)+1,'physical_card_records':len(physical),
        'listing_records':len(seen_records),'annotation_nodes_excluded':len(annotations),'unresolved_identity_occurrences':len(unresolved_nodes),'complete_node_partition':len(partition),'uniform_independent_verification':True}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--catalog',type=Path,required=True);ap.add_argument('--tools-root',type=Path)
    a=ap.parse_args();print(json.dumps(verify(a.repo,a.catalog,a.tools_root)))
if __name__=='__main__':main()

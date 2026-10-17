"""Independently verify current catalogue coverage and accepted source bindings.

Does not import the catalogue builder. The independent socket verifier checks
the uniform dataset; this verifier compares every physical listing and node
partition directly with those accepted sources, including omitted records.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "normalization"))
import read_page as page_reader
import re
import verify_uniform_socket_listings as uniform_verifier

DATA = 'json/Socket listings uniform/Socket listings.json'
UNIFORM_MANIFEST = 'notes/Socket listings uniform/Build manifest.json'

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
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

def verify(repo,root):
    repo,root=Path(repo).resolve(),Path(root).resolve();guards={}
    def checked(relative,expected,base=repo):
        path=inside(base,relative);need(digest(path)==expected,'Changed catalogue/source: '+relative)
        guards[path]=expected;return path
    mp=root/'notes/Card types current/Build manifest.json';m=read(mp);guards[mp]=digest(mp)
    need(m['schema']=='current-card-catalog-build-v1','Unsupported catalogue')
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
    pages,nodes,annotations={}, {},[];counts=Counter()
    for item in content['files']:
        if item['role']!='Published page content model':continue
        relative=item['path'];need(relative.startswith('json/') and relative.endswith('.json'),'Invalid model path')
        model=page_reader.read(checked(relative,item['sha256']));text='ALD/'+relative[5:-5]+'.txt'
        need(text in accepted and text not in pages,'Missing/duplicate accepted model source')
        entry=accepted[text];checked(text,entry['text_sha256'])
        pages[text]={'page':model.get('page',entry['page']),'model':relative,'model_sha256':item['sha256'],
            'text_sha256':entry['text_sha256'],'source_scan_id':entry.get('source_scan_id'),'source_relative':entry.get('source_relative')}
        counts['models']+=1
        for index,node in enumerate(model.get('nodes',[])):
            counts['diagram_nodes']+=1;pointer=f'/nodes/{index}'
            flags=[key for key in ('symbol_only','annotation_only','annotation_block')if node.get(key)is True]
            if flags:
                counts['annotation_nodes_excluded']+=1
                annotations.append({'page':model.get('page',entry['page']),'node':node.get('id'),'source_text':text,
                    'source_model':relative,'source_model_sha256':item['sha256'],'text_sha256':entry['text_sha256'],
                    'node_pointer':pointer,'card_type_literal':node.get('card_type'),'circuit_identifier':node.get('unit'),
                    'function_literal':node.get('function'),'explicit_flags':flags})
            else:
                view,audit=expected_identity(node)
                if isinstance(view.get('card_type'),str)and re.fullmatch('[0-9]{4}',view['card_type']):
                    view['_expected_identity_audit']=audit
                    view['_expected_review']=node.get('source_reviewed',model.get('source_reviewed')is True)
                    view['_expected_review_inherited']='source_reviewed'not in node and model.get('source_reviewed')is True
                    nodes[(text,pointer)]=view;counts['card_occurrences']+=1
                else:counts['nodes_without_card_type']+=1
    need(m['source_pages']==pages,'Accepted model coverage differs')
    expected_inputs={**inputs,'notes/Reviewed export provenance.json':bindings['reviewed_export_provenance_sha256'],
        'notes/Content data manifest.json':bindings['content_data_manifest_sha256'],
        UNIFORM_MANIFEST:bindings['uniform_manifest_sha256'],DATA:bindings['uniform_dataset_sha256']}
    for text,binding in pages.items():expected_inputs.update({text:binding['text_sha256'],binding['model']:binding['model_sha256']})
    for name in ['build_current_card_catalog.py','verify_current_card_catalog.py','verify_uniform_socket_listings.py','current_card_identity.py']:
        relative='tools/references/'+name;expected_inputs[relative]=digest(repo/relative)
    for path in page_reader.runtime_paths(repo):expected_inputs[path.relative_to(repo).as_posix()]=digest(path)
    actual_inputs={x['path']:x['sha256']for x in m['source_inputs']}
    need(len(actual_inputs)==len(m['source_inputs'])and actual_inputs==expected_inputs,'Declared catalogue source input inventory differs')
    for relative,expected in actual_inputs.items():checked(relative,expected)
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
        profiles+=len(card['portion_profiles']);need(sum(x['occurrences']for x in card['portion_profiles'])==len(card['diagram_occurrences']),'Profile partition differs')
    need(seen_records==set(typed),'Catalogue omits physical listings');need(seen_nodes==set(nodes),'Catalogue omits physical diagram nodes')
    need(types=={r['card_type']for _,r in typed.values()}|{n['card_type']for n in nodes.values()},'Card type coverage differs')
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
        'listing_records':len(seen_records),'annotation_nodes_excluded':len(annotations),'uniform_independent_verification':True}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--catalog',type=Path,required=True)
    a=ap.parse_args();print(json.dumps(verify(a.repo,a.catalog)))
if __name__=='__main__':main()

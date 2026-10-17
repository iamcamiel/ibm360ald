"""Read-only, two-way comparison of socket listings with accepted ALD models.

No ALD JSON migration or source correction is performed. Existing models are
adapted in memory; missing pages and unreadable identities stay explicit.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import csv
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "normalization"))
import read_page as page_reader
import re

import socket_ald_matching as matching
import verify_uniform_socket_listings as uniform_verifier
from socket_ald_identity_adapter import adapt_node

ROOT=Path(__file__).resolve().parents[2]
PAGE=re.compile(r'^([A-Z][A-Z0-9][0-9]{3})(?:-[0-9]{2})?(?:\s|$)')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value,pretty=False):
    return (json.dumps(value,ensure_ascii=False,indent=2 if pretty else None,
                       separators=None if pretty else (',',':'))+'\n').encode('utf-8')
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def accepted_path(repo,entry):
    parts=str(entry['destination']).replace('\\','/').split('/ALD/',1)
    if len(parts)!=2:raise ValueError('Accepted path has no ALD suffix')
    path=(repo/'ALD'/parts[1]).resolve()
    if not path.is_relative_to(repo/'ALD'):raise ValueError('Accepted path escapes ALD')
    return path

def load_ald(repo,provenance,content):
    """Read current bound page models without choosing a preferred scan variant."""
    accepted={}
    for entry in provenance['exported']:
        path=accepted_path(repo,entry)
        if path in accepted:raise ValueError('Duplicate accepted text target')
        accepted[path]=entry
    bindings={};wrappers=[];pages=defaultdict(list);issues=[]
    def checked(path,expected):
        raw=path.read_bytes()
        if sha(raw)!=expected:raise ValueError('Changed accepted input: '+str(path))
        key=path.relative_to(repo).as_posix()
        if key in bindings and bindings[key]!=expected:raise ValueError('Conflicting input hash')
        bindings[key]=expected
        return raw
    model_paths=set()
    for entry in content['files']:
        if entry.get('role')!='Published page content model':continue
        relative=entry['path']
        if not relative.startswith('json/') or not relative.endswith('.json'):
            raise ValueError('Unsupported page model target: '+relative)
        path=(repo/relative).resolve()
        if not path.is_relative_to(repo/'json'):raise ValueError('Model escapes JSON root')
        if path in model_paths:raise ValueError('Duplicate page model')
        model_paths.add(path)
        text_path=(repo/'ALD'/relative[5:]).with_suffix('.txt').resolve()
        if text_path not in accepted:raise ValueError('Model without accepted text: '+relative)
        acceptance=accepted[text_path]
        checked(text_path,acceptance['text_sha256'])
        model=page_reader.loads(checked(path,entry['sha256']))
        if not isinstance(model,dict):raise ValueError('Page model is not an object: '+relative)
        match=PAGE.match(text_path.stem)
        if not match:raise ValueError('Unrecognized page filename: '+str(text_path))
        page=match[1];literal=model.get('page')
        model_match=PAGE.match(str(literal)+' ') if literal is not None else None
        conflict=bool(model_match and model_match[1]!=page)
        source={'scan_id':str(acceptance['source_scan_id']),'page':page,
                'scan_page':text_path.stem.split()[0],
                'model_path':relative,'model_sha256':entry['sha256'],
                'text_path':text_path.relative_to(repo).as_posix(),
                'text_sha256':acceptance['text_sha256'],
                'source_relative':acceptance['source_relative'],
                'model_page_literal':literal,'source_page_conflict':conflict,
                'nodes_field_status':('absent' if 'nodes' not in model else
                                      'invalid' if not isinstance(model['nodes'],list) else
                                      'empty' if not model['nodes'] else 'present'),
                'model_node_count':len(model['nodes']) if isinstance(model.get('nodes'),list) else 0}
        pages[page].append(source)
        if conflict:issues.append({'kind':'filename_model_page_conflict',**source})
        nodes=model.get('nodes')
        if nodes is None:continue
        if not isinstance(nodes,list):
            issues.append({'kind':'unsupported_nodes_schema',**source});continue
        for i,node in enumerate(nodes):
            if not isinstance(node,dict):
                issues.append({'kind':'non_object_node',**source,'node_pointer':f'/nodes/{i}'});continue
            matching_node,adaptation=adapt_node(node)
            wrappers.append({**source,'node_pointer':f'/nodes/{i}','node':node,
                             'matching_node':matching_node,'identity_adaptation':adaptation})
    return wrappers,dict(pages),[{'path':p,'sha256':s} for p,s in sorted(bindings.items())],issues

def claims_from(records):
    for record in records:
        for ref_index,ref in enumerate(record['references']):
            for portion_index,portion in enumerate(ref['portions']):
                source=record['header_source']
                yield {'record_id':record['id'],'reference_index':ref_index,
                       'portion_index':portion_index,'board':record['board'],
                       'sockets':record['sockets'],'physical_sockets':record['physical_sockets'],
                       'card_type':record['card_type'],'portion':portion,'page':ref['page'],
                       'listing_page':source['page'],'listing_scan_id':source['scan_id'],
                       'listing_kind':record['kind'],'part_number':record['part_number']}

def compact_candidate(candidate):
    wrapper=candidate['binding'];node=wrapper['node']
    binding={k:v for k,v in wrapper.items() if k!='node' and not k.startswith('_')}
    binding['observed']={k:node.get(k) for k in ['id','grid','location','card_type','portion','printed_card_portion','function','unit']}
    binding.pop('matching_node',None)
    return {'binding':binding,'identity':candidate['identity'],
            **{k:candidate[k] for k in ['axes','matching_axes','differing_axes','unresolved_axes']}}

def match_all(records,wrappers,accepted_pages):
    page_nodes=defaultdict(list)
    for wrapper in matching.prepare_nodes(wrappers):page_nodes[wrapper['page']].append(wrapper)
    results=[];absent=Counter()
    for claim in claims_from(records):
        nodes=page_nodes.get(claim['page'],[])
        if not nodes:
            status='model_unavailable' if claim['page'] in accepted_pages else 'page_unavailable'
            result={'classification':status,'claim':claim,'normalized_claim':matching.normalize_identity(claim),
                    'matches':[],'candidates':[],'same_page_nodes':0,'coverage_issues':[],
                    'source_changes_applied':False}
            if status=='page_unavailable':absent[claim['page']]+=1
        else:
            result=matching.match_claim(claim,nodes)
            result['matches']=[compact_candidate(c) for c in result['matches']]
            result['candidates']=[compact_candidate(c) for c in result['candidates']]
        results.append(result)
    return results,absent

def csv_bytes(rows,fields):
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields)
    writer.writeheader();writer.writerows(rows)
    return stream.getvalue().encode('utf-8-sig')

def record_inventory(records,results):
    """Account for every logical entry, including entries without card portions."""
    expected=Counter((c['record_id'],c['reference_index'],c['portion_index']) for c in claims_from(records))
    actual=Counter((r['claim']['record_id'],r['claim']['reference_index'],r['claim']['portion_index']) for r in results)
    if actual!=expected:raise ValueError('Forward pass did not cover every listed portion exactly once')
    by_record=defaultdict(Counter)
    for result in results:by_record[result['claim']['record_id']][result['classification']]+=1
    rows=[]
    for record in records:
        classes=by_record[record['id']];claims=sum(classes.values())
        pins=len(record.get('pin_references',[]));unused=len(record.get('unused_portions',[]))
        status=('portion_claims_checked' if claims else 'connector_pin_references_inventoried' if pins else
                'unused_portions_only' if unused else 'no_listed_ALD_portion')
        rows.append({'record_id':record['id'],'listing_page':record['header_source']['page'],
            'listing_scan_id':str(record['header_source']['scan_id']),'board':record['board'],
            'sockets':' '.join(record['sockets']),'kind':record['kind'],'card_type':record['card_type'],
            'portion_claims':claims,'exact_claims':classes['exact']+classes['multiple_exact'],
            'outstanding_claims':claims-classes['exact']-classes['multiple_exact'],
            'pin_reference_rows':pins,'unused_portions':unused,'classification':status,
            'portion_classifications':dict(classes)})
    return rows


def page_inventory(repo,provenance,models):
    by_text={x['text_path']:x for group in models.values() for x in group}
    rows=[];bindings=[]
    for acceptance in provenance['exported']:
        path=accepted_path(repo,acceptance);relative=path.relative_to(repo).as_posix()
        if sha(path.read_bytes())!=acceptance['text_sha256']:
            raise ValueError('Changed accepted input: '+relative)
        bindings.append({'path':relative,'sha256':acceptance['text_sha256']})
        model=by_text.get(relative)
        rows.append({'scan_id':str(acceptance['source_scan_id']),'scan_page':path.stem.split()[0],
            'text_path':relative,'model_path':model['model_path'] if model else None,
            'nodes_field_status':model['nodes_field_status'] if model else 'no_published_model',
            'node_count':model['model_node_count'] if model else 0})
    return rows,bindings


def node_inventory(wrappers,forward,reverse):
    hits=defaultdict(set)
    for result in forward:
        if result['classification'] not in {'exact','multiple_exact'}:continue
        for match in result['matches']:
            b=match['binding'];hits[(b['model_path'],b['node_pointer'])].add(result['claim']['record_id'])
    remaining={(r['binding']['model_path'],r['binding']['node_pointer']):r for r in reverse['results']}
    rows=[]
    for wrapper in wrappers:
        key=(wrapper['model_path'],wrapper['node_pointer']);node=wrapper['node'];r=remaining.get(key)
        identity=matching.normalize_identity(wrapper.get('matching_node',node))
        if key not in hits and r is None:raise ValueError('Unaccounted ALD node: '+str(key))
        exact=r['exact_matches'] if r else [];candidates=r['candidates'] if r else []
        rows.append({'page':wrapper['page'],'scan_page':wrapper['scan_page'],'scan_id':wrapper['scan_id'],
            'model_path':key[0],'node_pointer':key[1],'node_id':node.get('id'),
            'location':node.get('location'),'card_type':node.get('card_type'),'portion':node.get('portion'),
            'comparison_board':identity['location']['board'],
            'comparison_sockets':' '.join(identity['location']['sockets']),
            'comparison_card_type':identity['card_type'],'comparison_portion':identity['portion'],
            'identity_issues':'; '.join(identity['issues']),
            'adaptation_rules':'; '.join(wrapper.get('identity_adaptation',{}).get('rules',[])),
            'classification':'forward_exact_hit' if key in hits else r['classification'],
            'exact_listing_record_ids':'; '.join(sorted(hits[key] if key in hits else
                {x['listing']['id'] for x in exact})),
            'candidate_count':len(candidates),'candidate_listing_record_ids':'; '.join(sorted({x['listing']['id'] for x in candidates})),
            'exclusion_reason':r.get('exclusion_reason','') if r else ''})
    return rows


def output_reports(output,report,pins,reverse,reconciliation,records,pages,nodes,tool_sources):
    if output.exists() and any(output.iterdir()):raise ValueError('Output must be new or empty')
    output.mkdir(parents=True,exist_ok=True)
    files=[]
    def put(name,raw):
        path=output/name;path.write_bytes(raw);files.append({'path':name,'sha256':sha(raw)})
    (output/'Tool snapshots').mkdir()
    for name,raw in tool_sources.items():put('Tool snapshots/'+name,raw)
    put('Audit metadata.json',encoded({key:value for key,value in report.items() if key!='results'},True))
    put('Socket to ALD matches.json',encoded(report))
    reverse=dict(reverse,forward_audit={'path':'Socket to ALD matches.json','sha256':files[-1]['sha256']})
    put('ALD to socket matches.json',encoded(reverse))
    put('Reference reconciliation.json',encoded(dict(reconciliation,forward_audit=reverse['forward_audit'])))
    rec_rows=[]
    for r in reconciliation['results']:
        rec_rows.append({'record_id':r['record_id'],'reference_index':r['reference_index'],
            'listing_page':r['listing']['header_source']['page'],'board':r['listing']['board'],
            'sockets':' '.join(r['listing']['sockets']),'card_type':r['listing']['card_type'],
            'literal_page':r['literal_page'],'classification':r['classification'],
            'counterpart_page':r['chosen_counterpart_page'],'candidate_pages':'; '.join(r['common_candidate_pages']),
            'portions':' '.join(str(p['portion']) for p in r['portions']),
            'unmatched_portions':' '.join(str(p['portion']) for p in r['portions'] if not p['candidate_pages']),
            'reason':r['reason']})
    put('Reference reconciliation.csv',csv_bytes(rec_rows,list(rec_rows[0]) if rec_rows else ['classification']))
    for name,rows in [('Socket entry coverage.csv',records),('Page model coverage.csv',pages),('All ALD node checks.csv',nodes)]:
        put(name,csv_bytes(rows,list(rows[0]) if rows else ['classification']))
    excluded={'forward_exact_hit','annotation_excluded','explicit_non_card','exact_same_page'}
    outstanding=[x for x in nodes if x['classification'] not in excluded]
    put('Reverse findings.csv',csv_bytes(outstanding,list(nodes[0]) if nodes else ['classification']))
    fields=['classification','listing_page','listing_scan_id','board','sockets','card_type','portion',
            'ALD_page','record_id','reference_index','portion_index','matches','candidates']
    rows=[]
    for result in report['results']:
        c=result['claim']
        def labels(which):return '; '.join(x['binding']['scan_page']+':'+str(x['binding']['observed']['id'])+' '+x['binding']['node_pointer'] for x in result[which])
        rows.append({'classification':result['classification'],'listing_page':c['listing_page'],
            'listing_scan_id':c['listing_scan_id'],'board':c['board'],'sockets':' '.join(c['sockets']),
            'card_type':c['card_type'],'portion':c['portion'],'ALD_page':c['page'],'record_id':c['record_id'],
            'reference_index':c['reference_index'],'portion_index':c['portion_index'],
            'matches':labels('matches'),'candidates':labels('candidates')})
    put('All portion checks.csv',csv_bytes(rows,fields))
    put('Matching findings.csv',csv_bytes([r for r in rows if r['classification'] not in {'exact','multiple_exact'}],fields))
    put('Absent page references.csv',csv_bytes([{'page':p,'portion_references':n} for p,n in sorted(report['absent_page_references'].items())],['page','portion_references']))
    put('Pin audit.json',encoded(pins))
    # Preserve all pin details in JSON; provide a concise actionable CSV.
    pin_fields=['page','scan_id','model_path','node_pointer','pin_index','side','status','severity','physical_contact','issues']
    pin_rows=[]
    for result in pins.get('results',[]):
        if result.get('severity') not in {'error','review'}:continue
        row={key:result.get(key) for key in pin_fields}
        row['issues']=json.dumps(result.get('issues',[]),ensure_ascii=False,separators=(',',':'))
        pin_rows.append(row)
    put('Pin findings.csv',csv_bytes(pin_rows,pin_fields))
    lines=['SOCKET LISTING TO ALD AUDIT','',
           'Read-only data comparison. Source text, models and scans were not changed.',
           'Unavailable page numbers may be absent sheets or misread references.',
           'Candidate matches and disagreements require source review; they are not automatic corrections.',
           'Repeated exact blocks and separately scanned page variants are retained.','',
           'MATCH COUNTS',json.dumps(report['counts'],ensure_ascii=False,indent=2),'',
           'REVERSE COVERAGE',json.dumps(reverse['coverage'],ensure_ascii=False,indent=2),'',
           'REVERSE COUNTS',json.dumps(reverse['classifications'],ensure_ascii=False,indent=2),'',
           'REFERENCE RECONCILIATION',json.dumps(reconciliation['counts'],ensure_ascii=False,indent=2),'',
           'Entry coverage includes cable/connector and unused records. Connector pin rows',
           'are inventoried, not electrically traced by this card-portion comparison.',
           'Page model coverage explicitly lists missing/empty node models.','',
           'PIN COUNTS',json.dumps(pins.get('counts',{}),ensure_ascii=False,indent=2),'',
           'Pin ranges apply only to resolved single/double SLT cards. Supply contacts,',
           'pinless connections, unused inputs and connector modules are distinguished.',
           'Detailed pin/contact comparisons with canonical Card-ALD definitions are disabled.','']
    put('Audit summary.txt','\n'.join(lines).encode('utf-8'))
    put('Audit files.json',encoded({'schema':'socket-ald-audit-files-v1','files':files},True))

def run(repo,output):
    tool_bindings=[];tool_sources={}
    for name in ['audit_socket_ald.py','socket_ald_matching.py','socket_ald_reverse.py','socket_ald_pin_audit.py',
                 'socket_ald_identity_adapter.py',
                 'socket_ald_reconciliation.py',
                 'socket_pin_validation.py','verify_uniform_socket_listings.py']:
        path=Path(__file__).with_name(name)
        raw=path.read_bytes();tool_sources[name]=raw
        tool_bindings.append({'path':path.relative_to(repo).as_posix(),'sha256':sha(raw)})
    tool_bindings.extend({'path':path.relative_to(repo).as_posix(),'sha256':sha(path.read_bytes())} for path in page_reader.runtime_paths(repo))
    provenance_path=repo/'notes/Reviewed export provenance.json';content_path=repo/'notes/Content data manifest.json'
    index_path=repo/'json/Socket listings uniform/Socket listings.json'
    manifest_path=repo/'notes/Socket listings uniform/Build manifest.json'
    inputs=[]
    def captured(path):
        raw=path.read_bytes();inputs.append({'path':path.relative_to(repo).as_posix(),'sha256':sha(raw)})
        return json.loads(raw.decode('utf-8-sig'))
    provenance=captured(provenance_path);content=captured(content_path);index=captured(index_path);manifest=captured(manifest_path)
    verification=uniform_verifier.verify(repo,repo)
    if not verification['passed']:raise ValueError('Uniform source validation failed: '+str(verification['failures']))
    wrappers,models,bindings,coverage_issues=load_ald(repo,provenance,content)
    pages,page_bindings=page_inventory(repo,provenance,models)
    accepted_pages={PAGE.match(accepted_path(repo,x).stem)[1] for x in provenance['exported'] if PAGE.match(accepted_path(repo,x).stem)}
    results,absent=match_all(index['records'],wrappers,accepted_pages)
    records=record_inventory(index['records'],results)
    from socket_ald_reverse import audit_reverse
    reverse=audit_reverse(index['records'],wrappers,results)
    if not reverse['coverage']['partition_complete']:raise ValueError('Reverse coverage partition failed')
    nodes=node_inventory(wrappers,results,reverse)
    from socket_ald_reconciliation import reconcile_references
    reconciliation=reconcile_references(index['records'],wrappers,results)
    from socket_ald_pin_audit import audit_pins
    pins=audit_pins(index['records'],wrappers)
    statuses=Counter(r['classification'] for r in results)
    counts={'portion_claims':len(results),'classifications':dict(statuses),
        'exact_claims':statuses['exact']+statuses['multiple_exact'],
        'distinct_referenced_pages':len({r['claim']['page'] for r in results}),
        'absent_page_numbers':len(absent),'absent_page_portion_claims':sum(absent.values()),
        'accepted_model_files':len(bindings)//2,'nodes_examined':len(wrappers),
        'coverage_issues':len(coverage_issues),'socket_records':len(records),
        'record_dispositions':dict(Counter(r['classification'] for r in records)),
        'accepted_text_pages':len(pages),'page_model_coverage':dict(Counter(p['nodes_field_status'] for p in pages)),
        'reverse_coverage':reverse['coverage'],'reverse_classifications':reverse['classifications'],
        'identity_adaptation_rules':dict(Counter(rule for w in wrappers for rule in w['identity_adaptation']['rules'])),
        'identity_adaptation_issues':sum(bool(w['identity_adaptation']['issues']) for w in wrappers),
        'reference_reconciliation':reconciliation['counts']}
    all_inputs=merge_input_bindings(inputs,manifest['inputs'],bindings,page_bindings,tool_bindings)
    # A concurrent edit invalidates the whole report, rather than mixing epochs.
    for link in all_inputs.values():
        if sha((repo/link['path']).read_bytes())!=link['sha256']:raise ValueError('Input changed during audit: '+link['path'])
    report={'schema':'socket-ald-audit-v1','created_utc':datetime.now(timezone.utc).isoformat(),
        'source_changes_applied':False,'counts':counts,'inputs':list(all_inputs.values()),
        'uniform_source_verification':verification,'coverage_issues':coverage_issues,
        'absent_page_references':dict(sorted(absent.items())),'results':results}
    output_reports(output,report,pins,reverse,reconciliation,records,pages,nodes,tool_sources)
    return {'output':str(output),'source_changes_applied':False,'counts':counts,'pin_counts':pins.get('counts',{})}


def merge_input_bindings(*groups):
    """Bind every transitive source, rejecting conflicting epochs of one path."""
    merged={}
    for group in groups:
        for link in group:
            path=link['path']
            if path in merged and merged[path]['sha256']!=link['sha256']:
                raise ValueError('Conflicting input epochs: '+path)
            merged[path]=link
    return merged

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path);args=parser.parse_args();repo=args.repo.resolve()
    output=(args.output or repo.parent/'tmp/ald-text/ald/socket-ald-audit'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')).resolve()
    if output.is_relative_to(repo):parser.error('Audit output must be outside the repository')
    print(json.dumps(run(repo,output),ensure_ascii=False,indent=2))

if __name__=='__main__':main()

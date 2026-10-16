"""Find corroborating identities for unavailable page references; never correct print."""
from collections import Counter,defaultdict
from pathlib import Path
import argparse
from datetime import datetime,timezone
import json
import re
import audit_socket_ald as audit
import socket_ald_matching as matching

ROOT=Path(__file__).resolve().parents[2]

def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        out=[i]
        for j,y in enumerate(b,1):out.append(min(out[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=out
    return row[-1]

def investigate(repo,audit_dir,output):
    audit_path=audit_dir/'Socket to ALD matches.json';audit_hash=audit.sha(audit_path.read_bytes())
    tools=[{'path':Path(__file__).relative_to(repo).as_posix(),'sha256':audit.sha(Path(__file__).read_bytes())}]
    report=audit.read(audit_path)
    for binding in report['inputs']:
        if audit.sha((repo/binding['path']).read_bytes())!=binding['sha256']:
            raise ValueError('Audit input epoch changed: '+binding['path'])
    provenance=audit.read(repo/'notes/Reviewed export provenance.json')
    content=audit.read(repo/'notes/Content data manifest.json')
    index=audit.read(repo/'json/Socket listings uniform/Socket listings.json')
    records={r['id']:r for r in index['records']}
    wrappers,_,_,_=audit.load_ald(repo,provenance,content)
    locations=defaultdict(list)
    for wrapper in wrappers:
        identity=matching.normalize_identity(wrapper['node'])
        if identity['issues'] or wrapper['source_page_conflict']:continue
        for socket in identity['location']['sockets']:
            key=(identity['location']['board'],socket,identity['card_type'],identity['portion'])
            locations[key].append(wrapper)
    groups=defaultdict(list)
    for result in report['results']:
        if result['classification']!='page_unavailable':continue
        claim=result['claim'];identity=matching.normalize_identity(claim)
        nodes={}
        if not identity['issues']:
            for socket in identity['location']['sockets']:
                key=(identity['location']['board'],socket,identity['card_type'],identity['portion'])
                for wrapper in locations.get(key,[]):nodes[(wrapper['model_path'],wrapper['node_pointer'])]=wrapper
        candidates=[{k:wrapper[k] for k in ['page','scan_page','scan_id','model_path','node_pointer']}
                    |{'node_id':wrapper['node'].get('id'),'location':wrapper['node'].get('location'),
                      'card_type':wrapper['node'].get('card_type'),'portion':wrapper['node'].get('portion'),
                      'function':wrapper['node'].get('function'),'unit':wrapper['node'].get('unit'),
                      'page_edit_distance':distance(claim['page'],wrapper['page'])}
                    for wrapper in nodes.values()]
        candidates.sort(key=lambda x:(x['page_edit_distance'],x['page'],x['model_path'],x['node_pointer']))
        record=records[claim['record_id']];ref=record['references'][claim['reference_index']]
        proof=[]
        for span in ref['source_spans']:
            for match in re.finditer(r'(?<![A-Z0-9])'+re.escape(claim['page'])+r'(?![A-Z0-9])',span['literal']):
                proof.append({**span,'token_column':span['column']+match.start(),'token':claim['page']})
        groups[claim['page']].append({'claim':claim,'source_reference_spans':proof,
            'exact_identity_candidates':candidates,'candidate_pages':sorted({c['page'] for c in candidates}),
            'status':'identity_unreadable' if identity['issues'] else 'candidate_found' if candidates else 'no_exact_identity_elsewhere'})
    assembled=[]
    for page,claims in sorted(groups.items()):
        votes=Counter(p for c in claims for p in c['candidate_pages'])
        assembled.append({'unavailable_page':page,'portion_claims':len(claims),
            'claims_with_exact_identity_elsewhere':sum(bool(c['candidate_pages']) for c in claims),
            'candidate_page_support':dict(votes.most_common()),'claims':claims})
    doc={'schema':'absent-ald-reference-investigation-v1','created_utc':datetime.now(timezone.utc).isoformat(),
         'policy':'Exact physical identity corroboration only. Candidate pages and edit distances do not establish a misread; inspect original print.',
         'source_changes_applied':False,'source_audit':{'path':str(audit_dir/'Socket to ALD matches.json'),
             'sha256':audit_hash},'inputs':report['inputs']+tools,
         'groups':assembled}
    for binding in doc['inputs']:
        if audit.sha((repo/binding['path']).read_bytes())!=binding['sha256']:
            raise ValueError('Input epoch changed during investigation: '+binding['path'])
    if audit.sha(audit_path.read_bytes())!=audit_hash:raise ValueError('Source audit changed during investigation')
    output.mkdir(parents=True,exist_ok=False)
    (output/'Absent reference candidates.json').write_bytes(audit.encoded(doc,True))
    rows=[]
    for group in assembled:
        refs={}
        for c in group['claims']:
            for span in c['source_reference_spans']:
                key=(span['scan_id'],span['row'],span['token_column']);refs[key]=span
        rows.append({'page':group['unavailable_page'],'portion_claims':group['portion_claims'],
            'claims_with_identity_elsewhere':group['claims_with_exact_identity_elsewhere'],
            'candidate_pages':json.dumps(group['candidate_page_support'],ensure_ascii=False),
            'source_occurrences':len(refs),
            'source_locations':'; '.join(f"{s['page']} R{s['row']} C{s['token_column']}" for s in refs.values())})
    (output/'Absent reference summary.csv').write_bytes(audit.csv_bytes(rows,list(rows[0]) if rows else ['page']))
    print(json.dumps({'output':str(output),'pages':len(assembled),'summary':[{k:g[k] for k in ['unavailable_page','portion_claims','claims_with_exact_identity_elsewhere','candidate_page_support']} for g in assembled]},ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=ROOT)
    p.add_argument('--audit',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();repo=a.repo.resolve();output=a.output.resolve()
    if output.is_relative_to(repo):p.error('Output must be outside repository')
    investigate(repo,a.audit.resolve(),output)

if __name__=='__main__':main()

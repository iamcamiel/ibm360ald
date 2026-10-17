"""Independent final two-way/adapter/reconciliation inventory verification.

Imports only reviewer-owned identity rules. Does not load the giant forward
JSON body or production audit modules, and writes no source/canonical artifact.
"""
from pathlib import Path
from collections import Counter,defaultdict
from functools import lru_cache
from datetime import datetime,timezone
import csv,hashlib,json,re,sys
from independent_identity_review import derive,identity,axes,fully_resolved

repo=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();check_count=0
def need(ok,text):
    global check_count
    check_count+=1
    if not ok:raise ValueError(text)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(4*1024*1024),b''):h.update(data)
    return h.hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def csvread(name):
    with (out/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def metadata(name):
    with (out/name).open(encoding='utf-8') as f:
        text=''
        while True:
            block=f.read(1024*1024)
            if not block:raise ValueError('No result-array delimiter in '+name)
            text+=block
            if ',"results":[' in text:return json.loads(text.split(',"results":[',1)[0]+'}')
@lru_cache(maxsize=16)
def model(path):return read(repo/path)
def rawnode(key):return model(key[0])['nodes'][int(key[1].rsplit('/',1)[1])]
def model_page(path):return re.match(r'^([A-Z][A-Z0-9][0-9]{3})',Path(path).stem)[1]
def claimkey(row):return row['record_id'],int(row['reference_index']),int(row['portion_index'])
def comparison_matches(normal,produced):
    return (normal['board']==produced['location']['board'] and normal['sockets']==produced['location']['sockets']
        and normal['location_resolved']==produced['location']['resolved'] and normal['card_type']==produced['card_type']
        and normal['portion']==produced['portion'] and normal['issues']==produced['issues'])

try:
    # Self checks ensure unproved C remains CPU02C, explicit01C requires matching evidence.
    n={'part':'3312A1','card':'A-D3H7','location':'1B-AA','technology':'T06AA'};v,t=derive(n)
    need(identity(v)['board']=='02A-D3' and identity(v)['card_type']=='3312' and n['location']=='1B-AA','Reviewer ZA alias semantics')
    n={'card':'1125AA','location':'C-D2M6'};need(identity(derive(n)[0])['board']=='02C-D2','CPU C alias unchanged without proof')
    n['A1']={'records':[{'board':'01C-D2','sockets':['M6','M7'],'card_type':'1125','portion':'AA'}]}
    need(identity(derive(n)[0])['board']=='01C-D2','Exact embedded proof permits explicit01C frame')
    n['A1']['records'][0]['sockets']=['M5'];need(identity(derive(n)[0])['board']=='02C-D2','Wrong socket cannot supply explicit frame')
    unresolved=identity({'location':'F-F2D7','card_type':'0141','portion':'B3'})
    need(unresolved['board'] is None and unresolved['sockets']==['D7'] and unresolved['location_resolved'] is False and not fully_resolved(unresolved),'Readable socket retained despite unresolved unit without allowing exact identity')
    manifest=read(out/'Audit files.json');initial_output_hash=sha(out/'Audit files.json')
    for f in manifest['files']:need(sha(out/f['path'])==f['sha256'],'Output hash '+f['path'])
    audit=metadata('Socket to ALD matches.json');counts=audit['counts']
    need(read(out/'Audit metadata.json')==audit,'Compact audit metadata equals full forward report header exactly')
    for link in audit['inputs']:need(sha(repo/link['path'])==link['sha256'],'Current bound input '+link['path'])
    index=read(repo/'json/Socket listings uniform/Socket listings.json');records=index['records'];byrecord={r['id']:r for r in records}
    claims=csvread('All portion checks.csv');entries=csvread('Socket entry coverage.csv');nodes=csvread('All ALD node checks.csv');pages=csvread('Page model coverage.csv')
    claimrows={claimkey(c):c for c in claims};expectedclaims={(r['id'],i,j):{'record':r,'reference':ref,'portion':p} for r in records for i,ref in enumerate(r['references']) for j,p in enumerate(ref['portions'])}
    need(len(claimrows)==len(claims) and set(claimrows)==set(expectedclaims),'Every listed portion exactly once in forward ledger')
    need(Counter(r['record_id'] for r in entries)==Counter(r['id'] for r in records),'Every logical record exactly once')
    need(sum(int(r['portion_claims']) for r in entries)==len(claims),'Entry claim totals')
    need(sum(int(r['pin_reference_rows']) for r in entries)==sum(len(r['pin_references']) for r in records),'All socket pin rows inventoried')
    csvnodes={(n['model_path'],n['node_pointer']):n for n in nodes};need(len(csvnodes)==len(nodes),'Unique node ledger bindings')
    sourcekeys=[];nodefacts={};byidentity=defaultdict(set);page_status=Counter();content=read(repo/'notes/Content data manifest.json');model_count=0;adapt_counts=Counter();adapt_issues=0
    for ent in content['files']:
        if ent.get('role')!='Published page content model':continue
        path=ent['path'];doc=read(repo/path);nd=doc.get('nodes');model_count+=1
        status='absent' if 'nodes' not in doc else 'invalid' if not isinstance(nd,list) else 'empty' if not nd else 'present';page_status[status]+=1
        page=model_page(path);literal=re.match(r'^([A-Z][A-Z0-9][0-9]{3})(?:-[0-9]{2})?(?:\s|$)',str(doc.get('page'))+' ');conflict=bool(literal and literal[1]!=page)
        if not isinstance(nd,list):continue
        for i,raw in enumerate(nd):
            if not isinstance(raw,dict):continue
            key=(path,'/nodes/'+str(i));sourcekeys.append(key);ordinal=len(sourcekeys)-1
            need(key in csvnodes,'Source node present in ledger '+str(key));row=csvnodes[key];view,trail=derive(raw);normal=identity(view)
            adapt_counts.update(trail['rules']);adapt_issues+=bool(trail['issues'])
            need(row['location']==str(raw.get('location') if raw.get('location') is not None else '') and row['card_type']==str(raw.get('card_type') if raw.get('card_type') is not None else '') and row['portion']==str(raw.get('portion') if raw.get('portion') is not None else ''),'Raw node literals retained in CSV')
            need(row['comparison_board']==(normal['board'] or '') and row['comparison_sockets']==' '.join(normal['sockets']) and row['comparison_card_type']==(normal['card_type'] or '') and row['comparison_portion']==(normal['portion'] or ''),'Independent comparison axes from source aliases/frame proof '+str(key)+' raw='+repr(raw)+' independent='+repr(normal)+' produced='+repr(row))
            need(row['adaptation_rules']=='; '.join(trail['rules']) and row['identity_issues']=='; '.join(normal['issues']),'CSV adaptation/issue audit trail independently derived')
            nodefacts[key]={'identity':normal,'trail':trail,'page':page,'conflict':conflict,'ordinal':ordinal,'model_sha256':ent['sha256'],'scan_page':row['scan_page']}
            if fully_resolved(normal) and not conflict:
                for socket in normal['sockets']:byidentity[(normal['board'],socket,normal['card_type'],normal['portion'])].add(ordinal)
    need(set(sourcekeys)==set(csvnodes),'Complete source-node inventory')
    need(dict(adapt_counts)==counts['identity_adaptation_rules'] and adapt_issues==counts['identity_adaptation_issues'],'Adapter aggregate counts')
    need(Counter(p['nodes_field_status'] for p in pages if p['model_path'])==page_status,'Missing/empty node fields inventoried')
    provenance=read(repo/'notes/Reviewed export provenance.json')
    expectedpages=Counter((str(p['source_scan_id']),'ALD/'+p['destination'].replace('\\','/').split('/ALD/',1)[1]) for p in provenance['exported'])
    need(Counter((p['scan_id'],p['text_path']) for p in pages)==expectedpages,'Every accepted scan in page inventory')
    lookup={(row['scan_page'],row['node_pointer']):key for key,row in csvnodes.items()};need(len(lookup)==len(csvnodes),'Scan-page/pointer labels uniquely identify nodes')
    def exact_occurrences(r,portion):
        norm=identity(dict(r,portion=portion));found=set()
        if fully_resolved(norm):
            for socket in norm['sockets']:found.update(byidentity.get((norm['board'],socket,norm['card_type'],norm['portion']),()))
        return found
    hitkeys=set()
    for key,row in claimrows.items():
        source=expectedclaims[key];r,ref,p=source['record'],source['reference'],source['portion']
        need(row['ALD_page']==ref['page'] and row['portion']==p and row['board']==r['board'] and row['sockets']==' '.join(r['sockets']) and row['card_type']==(r['card_type'] or ''),'Forward claim retains all literal identity fields')
        exact={n for n in exact_occurrences(r,p) if nodefacts[sourcekeys[n]]['page']==ref['page']}
        if row['classification'] in {'exact','multiple_exact'}:
            actual=set()
            for text in row['matches'].split('; '):
                m=re.fullmatch(r'([^:]+):.* (/nodes/\d+)',text);need(bool(m),'Exact node label syntax')
                nodekey=lookup[(m[1],m[2])];actual.add(nodefacts[nodekey]['ordinal']);hitkeys.add(nodekey)
            need(actual==exact and len(actual)==(1 if row['classification']=='exact' else len(actual)) and (row['classification']!='multiple_exact' or len(actual)>1),'Exact forward matches equal independently indexed complete literal identities')
        else:need(not exact,'No genuine exact identity hidden by forward non-exact classification')
    need(hitkeys=={k for k,row in csvnodes.items() if row['classification']=='forward_exact_hit'},'Only exact forward hits excluded from reverse')
    coverage=counts['reverse_coverage'];need(coverage['reviewed_overlay_hit_nodes']==0,'No invisible reviewed-page substitution')
    need(len(nodes)==coverage['all_nodes']==sum(coverage[k] for k in ['forward_exact_hit_nodes','reviewed_overlay_hit_nodes','reverse_examined_nodes','annotation_excluded_nodes','non_card_excluded_nodes']),'Full node partition complete')
    reverse=read(out/'ALD to socket matches.json');reversekeys=set()
    for result in reverse['results']:
        b=result['binding'];key=(b['model_path'],b['node_pointer']);need(key not in reversekeys,'Reverse node unique');reversekeys.add(key)
        raw=rawnode(key);view,trail=derive(raw);fact=nodefacts[key]
        need(b['node']==raw and b.get('matching_node',raw)==view and b['identity_adaptation']==trail,'Reverse raw node/matching view/audit proof reproduce exact source')
        need(comparison_matches(fact['identity'],result['observed_identity']),'Reverse comparison identity independently reproduced')
        for group in ['exact_matches','candidates']:
            for e in result[group]:
                record=byrecord[e['listing']['id']];ref=record['references'][e['reference_index']];portion=ref['portions'][e['portion_index']]
                need(records[e['listing']['record_index']]['id']==record['id'] and e['page']==ref['page'] and e['reference_source_spans']==ref['source_spans'],'Reverse exact source reference witness')
                expected=axes(fact['identity'],identity(dict(record,portion=portion)));need(expected==e['axes'],'Reverse candidate axes independently derived')
                if group=='exact_matches':need(all(x is True for x in expected.values()) and not result['issues'],'Reverse exact is fully resolved')
    need(reversekeys==set(sourcekeys)-hitkeys,'Reverse covers precisely forward-unhit nodes')
    need(reverse['forward_audit']['sha256']==sha(out/'Socket to ALD matches.json'),'Reverse bound to exact forward report')
    for rid,proof in reverse['listing_evidence'].items():need(records[proof['record_index']]['id']==rid and all(value==byrecord[rid].get(field) for field,value in proof.items() if field!='record_index'),'Reverse deduplicated source listing proof')
    reverse_classifications=Counter(r['classification'] for r in reverse['results']);del reverse
    reconciliation=read(out/'Reference reconciliation.json');groupkeys=set();usedproofs=set();recclass=Counter();recclaims=0
    for result in reconciliation['results']:
        r=byrecord[result['record_id']];ref=r['references'][result['reference_index']];groupkey=(r['id'],result['reference_index']);need(groupkey not in groupkeys,'Reference group unique');groupkeys.add(groupkey)
        need(records[result['record_index']]['id']==r['id'] and result['literal_page']==ref['page'] and result['reference_source_spans']==ref['source_spans'],'Reconciliation preserves exact printed page and source cells')
        need(len(result['portions'])==len(ref['portions']),'All reference portions retained');sets=[]
        for j,portion in enumerate(result['portions']):
            recclaims+=1;need(portion['portion_index']==j and portion['portion']==ref['portions'][j],'Portion order and repeated occurrences retained')
            expected=exact_occurrences(r,ref['portions'][j]);need(portion['node_evidence_ids']==['node:'+str(x) for x in sorted(expected)],'All exact source occurrences retained once per portion')
            expectedpages=sorted({nodefacts[sourcekeys[x]]['page'] for x in expected});need(portion['candidate_pages']==expectedpages,'Portion candidate pages independently indexed')
            need(portion['forward_classification']==claimrows[(r['id'],result['reference_index'],j)]['classification'],'Reconciliation retains actual forward classification')
            sets.append(set(expectedpages));usedproofs.update(portion['node_evidence_ids'])
        common=set.intersection(*sets) if sets else set();all_supported=bool(sets) and all(sets);verified=all_supported and ref['page'] in common and all(p['forward_classification'] in {'exact','multiple_exact'} for p in result['portions'])
        chosen=None;reason=None
        if verified:status='already_verified';chosen=ref['page']
        elif not any(sets):status='no_counterpart';reason='no_exact_witness' if sets else 'no_listed_portions'
        elif not all_supported:status='incomplete_counterpart';reason='some_portions_without_exact_witness'
        elif not common:status='incomplete_counterpart';reason='no_common_page_for_all_portions'
        elif len(common)==1:status='unique_counterpart_page';chosen=next(iter(common))
        else:status='ambiguous_counterpart_pages'
        need(result['classification']==status and result['reason']==reason and result['chosen_counterpart_page']==chosen and result['common_candidate_pages']==sorted(common) and result['all_portions_supported']==all_supported,'Counterpart selection/classification is exact all-portion intersection')
        need(result['source_changes_applied'] is False and result['source_page_correction_asserted'] is False,'Corroboration does not claim source correction');recclass[status]+=1
    expectedgroups={(r['id'],i) for r in records for i,_ in enumerate(r['references'])};need(groupkeys==expectedgroups and recclaims==len(claims),'Every source reference group and portion reconciled')
    need(set(reconciliation['node_evidence'])==usedproofs,'Reconciliation proof map exactly deduplicated used occurrences')
    identity_fields=['id','grid','location','board','sockets','physical_sockets','occupied_sockets','card_type','portion','printed_card_portion']
    for proof_id,proof in reconciliation['node_evidence'].items():
        key=sourcekeys[int(proof_id.split(':')[1])];b=proof['binding'];raw=rawnode(key);fact=nodefacts[key]
        need((b['model_path'],b['node_pointer'])==key and b['model_sha256']==fact['model_sha256'],'Reconciliation proof binds exact current source node/hash')
        need(proof['observed']=={field:raw.get(field) for field in identity_fields} and b['identity_adaptation']==fact['trail'],'Proof retains raw identity and independently derived adaptation trail')
        need(comparison_matches(fact['identity'],proof['comparison_identity']),'Proof comparison identity independently derived')
    need(reconciliation['counts']['portion_claims']==recclaims and reconciliation['counts']['reference_groups']==len(groupkeys) and reconciliation['counts']['classifications']==dict(recclass),'Reconciliation aggregate counts')
    need(reconciliation['forward_audit']['sha256']==sha(out/'Socket to ALD matches.json'),'Reconciliation binds exact forward report')
    for link in audit['inputs']:need(sha(repo/link['path'])==link['sha256'],'Final input epoch '+link['path'])
    for f in manifest['files']:need(sha(out/f['path'])==f['sha256'],'Final output epoch '+f['path'])
    need(sha(out/'Audit files.json')==initial_output_hash,'Audit inventory unchanged throughout independent review')
    result={'schema':'socket-ald-final-independent-verification-v1','passed':True,'failures':[],'created_utc':datetime.now(timezone.utc).isoformat(),'check_count':check_count,'counts':{'socket_records':len(records),'portion_claims':len(claims),'ALD_models':model_count,'ALD_nodes':len(nodes),'forward_hit_nodes':len(hitkeys),'reverse_classifications':dict(reverse_classifications),'reconciliation_classifications':dict(recclass),'reference_groups':len(groupkeys)},'audit_manifest':{'path':str(out/'Audit files.json'),'sha256':initial_output_hash},'source_or_canonical_writes':False,'review_scope':'All source identities and aliases independently derived, explicit frame context proof reproduced, forward exact-hit completeness, reverse candidates and source bindings, all-portion counterpart intersections, source/output epoch before and after. Individual unresolved print remains a source-review task.','reviewer_diagnostics':{'corrected_representation':'Reviewer initially omitted a readable socket when its unit was unresolved; isolated F-F2D7 fixture now preserves D7 while requiring location_resolved=False and fully_resolved=False. No production or source change.', 'historical_attempt_log':str(out/'Independent reviewer attempt diagnostics.json')},'reviewers':[{'path':str(Path(__file__).resolve()),'sha256':sha(__file__)},{'path':str(Path(__file__).with_name('independent_identity_review.py').resolve()),'sha256':sha(Path(__file__).with_name('independent_identity_review.py'))}]}
except Exception as exc:
    result={'schema':'socket-ald-final-independent-verification-v1','passed':False,'failure':str(exc),'check_count':check_count,'source_or_canonical_writes':False}
(out/'Independent final audit acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result['passed'] else 1)


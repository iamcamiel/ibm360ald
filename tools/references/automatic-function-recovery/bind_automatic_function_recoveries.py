"""Fail-closed automatic function acceptance adapter; dry-run unless --emit.

No source, canonical quartet, or repository file is written by this tool.  The
optional output is an acceptance record consumed by the reviewed exporter.
Application/publication pins must be frozen after independent acceptance.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, copy, hashlib, json, sys
from functools import lru_cache
sys.dont_write_bytecode = True
ROOT = Path('D:/Github/IBM360')
BASE = ROOT/'tmp/ald-text/ald/card-type-database/function-unreadable-resolution-v1'
CANONICAL = ROOT/'ALD_Visual_Transcriptions'
SOURCE = Path('D:/Reference Materials/IBM 360/IBM_360_ALD')
CANDIDATES = BASE/'expanded-shape-takeover-v1/v10-accepted-readonly/Expanded shape unreadable function candidates.json'
CANDIDATE_SHA = '2c3919e8676d585868f5fa4bb48f69bfd846570999e1262e250bfacc11efd981'
CANDIDATE_AUDIT = BASE/'independent-review/Independent expanded unique-fit candidate audit v2.json'
CANDIDATE_AUDIT_SHA = '45006a16ddb965ce264a40c17179fbcc29148871a653723020b8bd4bc9d984e8'
POLICY = BASE.parent/'function-review-batch-8/Direct human automatic unreadable label recovery authorization.json'
POLICY_SHA = 'f8c557571850947ed7ac41eeb53617d7c7a42d30e84f3f9df034ff7a6b0a1789'
RAW_AUTHORITY = BASE.parent/'function-review-batch-8/Direct human batch8 answers.json'
RAW_AUTHORITY_SHA = 'af7c16b321e08d403430ff41e09cf0514ee06880fceee7f3fc95850d2c87854d'
HISTORY = 'source_derived_unique_function_recovery_2c3919e8676d'
SCOPE = 'Source-derived recovery of U+FFFD cells only; no readable text, wiring, geometry or function taxonomy is changed. Derived values are never promoted to independent native witnesses.'
# Intentionally unset until the independent application audit and publication
# are frozen. CLI cannot override these pins to bless an arbitrary document.
APPLICATION_SHA = 'cbd5f512cedea4b09134ea97cfbb2d931f7a4afd4eb29f0f9ec57915106b4dab'
APPLICATION_AUDIT_SHA = '3717f829206a121367ed9af860ebe9e50a86caecba568ad92d61091134907039'
PUBLICATION_SHA = 'c57ebebdb8a70a39162363d826bd9ed2ba4f6e9d6d10956c81722f6917078974'
OUT = ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Automatic unreadable function recovery current audit.json'

def require(condition, message):
    if not condition: raise ValueError(message)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
@lru_cache(maxsize=256)
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def binding(path): return {'file':str(path), 'sha256':sha(path)}
def checked(b):
    p=Path(b.get('path',b.get('file',''))).resolve()
    require(p.is_file() and sha(p)==b['sha256'], 'Missing or changed bound file: '+str(p))
    return p
def pin(path, digest):
    require(bool(digest) and sha(path)==digest,'Unfrozen or wrong acceptance pin: '+str(path))
    return load(path)
def ptr(obj, pointer):
    for k in pointer.strip('/').split('/'):
        obj=obj[int(k)] if isinstance(obj,list) else obj[k.replace('~1','/').replace('~0','~')]
    return obj
def assign(obj,pointer,value):
    parts=pointer.strip('/').split('/'); parent=obj
    for k in parts[:-1]: parent=parent[int(k)] if isinstance(parent,list) else parent[k]
    k=parts[-1]; parent[int(k) if isinstance(parent,list) else k]=value
def fits(a,b):
    return '�' in a and '�' not in b and len(a)==len(b) and all(x=='�' or x==y for x,y in zip(a,b))
def spans(target):
    return {(b['row'],b['column']+i) for b in target['function_literal_bindings'] for i in range(len(b['literal']))}

def expected_model(old, lines, fields):
    """Derive alias permissions from source coordinates, never from allowlist alone."""
    model=copy.deepcopy(old); changes={}
    def change(pointer,before,after):
        require(ptr(model,pointer)==before,'Alias sequence changed: '+pointer)
        if pointer in changes:
            require(changes[pointer]['after']==before,'Alias update is not sequential')
            changes[pointer]['after']=after
        else: changes[pointer]={'json_pointer':pointer,'before':before,'after':after}
        assign(model,pointer,after)
    for f in fields:
        pointer=f['node_pointer']; node=ptr(model,pointer); a=f['function_before']; z=f['function_after']
        r,c=f['row'],f['column']; original=ptr(old,pointer)
        require(original['function']==a and node['id']==f['node'],'Target identity/function changed')
        require(original['row']<r<original['row']+3 and original['column']<c and c+len(a)<=original['column']+original.get('width',8)-1,'Function outside box header')
        for key in ('function','printed_function','function_text'):
            value=node.get(key)
            if isinstance(value,str) and value.strip(' ')==a:
                change(pointer+'/'+key,value,value.replace(a,z))
        layout=node.get('function_layout')
        if isinstance(layout,dict) and isinstance(layout.get('printed_function_literal'),str) and layout['printed_function_literal'].strip(' ')==a:
            value=layout['printed_function_literal'];change(pointer+'/function_layout/printed_function_literal',value,value.replace(a,z))
        for collection in ('printed_labels','labels'):
            for i,label in enumerate(model.get(collection,[])):
                if not isinstance(label,dict) or not isinstance(label.get('text'),str) or label.get('row')!=r or not isinstance(label.get('column'),int):continue
                lc=label['column'];text=label['text']; edits=[e for e in f['exact_meaningful_cell_changes'] if lc<=e['column']<lc+len(text)]
                if not edits:continue
                original_label=old[collection][i]['text']
                require(lines[r][lc:lc+len(original_label)]==original_label,'Display alias is not source-bound')
                chars=list(text)
                for e in edits:
                    require(chars[e['column']-lc]=='�','Display alias alters readable text');chars[e['column']-lc]=e['after']
                change('/'+collection+'/'+str(i)+'/text',text,''.join(chars))
    return model,list(changes.values())

def validate_fields(item,cases,candidate_audit,index):
    fields=item['function_fields']; seen=set(); notes=[]
    for f in fields:
        cid=f['candidate_id']; require(cid not in seen and cid in cases,'Duplicate or unknown candidate');seen.add(cid)
        case=cases[cid];t=case['target']
        require(case['status']=='single_complete_literal_supported' and not case['human_answer_exclusion'] and not case['ineligibility_reasons'],'Held or ambiguous candidate')
        require(fits(f['function_before'],f['function_after']) and f['function_after']==case['proposed_complete_literal'],'Readable character/answer substitution')
        require((item['page'],str(item['source_scan_id']),f['node_pointer'],f['node'],f['function_before'])==(t['page'],str(t['scan_id']),t['node_pointer'],t['node_identifier'],t['function_literal']),'Wrong page/scan/node')
        require(item['source']['sha256']==t['original_source_binding']['sha256'] and Path(item['source']['path']).resolve()==Path(t['original_source_binding']['path']).resolve(),'Wrong original scan')
        for k,tk in [('txt','text_binding'),('json','model_binding')]:require(item['before_quartet'][k]['sha256']==t[tk]['sha256'],'Before differs from accepted V10 target')
        bs=t['function_literal_bindings'];require(len(bs)==1 and (f['row'],f['column'],f['function_before'])==(bs[0]['row'],bs[0]['column'],bs[0]['literal']),'Unbound function text span')
        require(f['exact_function_free_shape']==case['function_free_exact_shape'] and f['shape_sha256']==case['shape_sha256'],'Shape mismatch')
        witnesses={w['observation_id']:w for w in case['matching_witnesses']}
        chosen=f['independent_witness_observation_ids'];require(chosen and len(set(chosen))==len(chosen),'No distinct independent witness')
        require(set(chosen)<=set(candidate_audit['independent_witness_ids'][cid]),'Unapproved independent witness')
        require([w['observation_id'] for w in f['witness_source_model_text_bindings']]==chosen,'Witness binding list mismatch')
        for wb in f['witness_source_model_text_bindings']:
            w=witnesses[wb['observation_id']];same=str(w['scan_id'])==str(t['scan_id'])
            require(w['function_literal']==f['function_after'] and '�' not in w['function_literal'],'Incomplete/wrong independent literal')
            require(w['card_type']==t['card_type'] and w['portion']==t['portion'],'Witness option mismatch')
            if same:require(w['observation_id'] in candidate_audit.get('approved_same_scan_witness_ids',{}).get(cid,[]) and w['node_pointer']!=t['node_pointer'] and not spans(w)&spans(t),'Unapproved same-scan/circular witness')
            require(wb['node_pointer']==w['node_pointer'] and wb['function_literal_bindings']==w['function_literal_bindings'] and wb['same_scan_as_target']==same and wb['same_scan_explicitly_independently_approved']==same,'Witness identity/span mismatch')
            for k,tk in [('model','model_binding'),('text','text_binding'),('original','original_source_binding')]:
                rec=index['sources'][w[tk]['source_id']];require(wb[k]==rec and rec['sha256']==w[tk]['sha256'],'Witness not in frozen accepted V10 registry')
            notes.append({'candidate_id':cid,'target':t,'complete_witness':w,'same_scan_explicitly_approved':same,'evidence_epoch':'Frozen independently audited V10; live witness files may have unrelated later field corrections','derived_values_are_native_witnesses':False})
    return seen,notes

def validate_predecessor(item,planned,app):
    snapshots={Path(b.get('path',b.get('file',''))).name:checked(b) for b in app['snapshot_inputs']}
    ep=snapshots['Reviewed export provenance.json'];cp=snapshots['Content data manifest.json']
    require(sha(ep)=='f024b944e55d558a2fd1a400c2e39d12fe063d3b22c9347ff95b14c9927230b4' and sha(cp)=='9455fef1dd7b8129c81b77295474e5c9767581208ed5d3c1749d9e200dab3f1c','Wrong frozen accepted input epoch')
    entries=[e for e in load(ep)['exported'] if str(e['source_scan_id'])==str(item['source_scan_id']) and e['page']==item['page']]
    require(len(entries)==1,'No unique independently accepted predecessor');entry=entries[0]
    require(entry['text_sha256']==item['before_quartet']['txt']['sha256'],'Predecessor TXT not accepted')
    # Published notes_sha256 belongs to the exporter's provenance-enriched note,
    # not the canonical owner's note. Exact owner notes/preview are independently
    # bound by the application audit's before quartet, checked in validate_page.
    require(Path(entry['transcription_source']).resolve()==Path(planned['canonical_quartet']['txt']['path']).resolve(),'Wrong predecessor canonical filename')
    require((SOURCE/entry['source_relative']).resolve()==checked(item['source']),'Wrong predecessor original source')
    content=[f for f in load(cp)['files'] if f['role']=='Published page content model' and Path(f['source']).resolve()==Path(planned['canonical_quartet']['json']['path']).resolve()]
    require(len(content)==1 and content[0]['sha256']==item['before_quartet']['json']['sha256'],'Predecessor model not accepted')
    prior=load(checked(item['prior_review_record']))
    require(item['prior_review_record']==planned['prior_review_record'],'Predecessor record substituted')
    if planned['prior_review_record_kind']=='Frozen accepted completed-review export entry and exact content binding':
        require(item['page']=='AR301' and str(item['source_scan_id'])=='357' and entry['review_record']=='Completed published review status: native source and rendered layout reviewed; marked unreadable print retained.','Unapproved status-string fallback')
        require(prior['exact_export_entry']==entry and prior['exact_content_entry']==content[0] and prior['before_quartet']==planned['before_quartet'] and prior['original_source']==item['source'],'Completed-review snapshot mismatch')
        require(prior['accepted_export_manifest']['sha256']==sha(ep) and prior['accepted_content_manifest']['sha256']==sha(cp),'Unbound completed-review registry')
    else:
        require(planned['prior_review_record_kind']=='Existing exact independent review record','Unknown predecessor proof schema')
        original=ROOT/entry['review_record']
        require(Path(entry['review_record']).suffix=='.json' and planned['prior_review_record']['sha256']==sha(checked(item['prior_review_record'])),'Unbound file predecessor')
    return {'accepted_export':binding(ep),'accepted_content':binding(cp),'frozen_review_record':item['prior_review_record']}

def validate_page(item,planned,approved,fields,cases,ca,index,app,receipt_path,peer_path):
    require(item['page']==planned['page']==approved['page'] and str(item['source_scan_id'])==str(planned['source_scan_id'])==str(approved['source_scan_id']),'Wrong approved page/scan')
    source=checked(item['source']);require(source.is_relative_to(SOURCE.resolve()),'Source escapes archive')
    require(item['source']==planned['source']==approved['source'] and checked(planned['frozen_original_source']).read_bytes()==source.read_bytes(),'Original source approval mismatch')
    for k in ('txt','json','notes','preview'):
        b=checked(item['before_quartet'][k]);require(item['before_quartet'][k]==planned['before_quartet'][k]==approved['before_quartet'][k],'Independent before quartet mismatch')
        c=checked(item['current_quartet'][k]);p=checked(planned['candidate_quartet'][k]);a=checked(approved['candidate_quartet'][k])
        require(c.is_relative_to(CANONICAL.resolve()) and p.is_relative_to(BASE.resolve()) and c.name==p.name,'Canonical/candidate path escape or rename')
        require(Path(planned['canonical_quartet'][k]['path']).resolve()==c and p==a and sha(c)==sha(a)==item['independently_reviewed_candidate_quartet'][k]['sha256'],'Current bytes not exact independently accepted candidate')
    for key in ('function_fields','exact_meaningful_cell_changes','allowed_active_semantic_changes'):require(item[key]==planned[key]==approved[key],'Approved page details mismatch: '+key)
    require(item['function_fields']==fields,'Field group mismatch')
    oldbytes=checked(item['before_quartet']['txt']).read_bytes();newbytes=checked(item['current_quartet']['txt']).read_bytes()
    old=oldbytes.decode('utf-8').splitlines();new=newbytes.decode('utf-8').splitlines();restored=newbytes.decode('utf-8').splitlines(keepends=True)
    require(len(old)==len(new)==103 and all(len(a)==len(z)<=245 for a,z in zip(old,new)),'Layout/line lengths changed')
    expected=[]
    for f in fields:
        r,c=f['row'],f['column'];a,z=f['function_before'],f['function_after']
        require(old[r][c:c+len(a)]==a and new[r][c:c+len(z)]==z,'Function span mismatch')
        edits=[{'row':r,'column':c+i,'before':x,'after':y} for i,(x,y) in enumerate(zip(a,z)) if x!=y]
        require(edits==f['exact_meaningful_cell_changes'] and all(e['before']=='�' and e['after'] not in '\r\n�' for e in edits),'Non-mask text change')
        expected+=edits;restored[r]=restored[r][:c]+a+restored[r][c+len(a):]
    require(len({(e['row'],e['column'])for e in expected})==len(expected),'Overlapping target changes')
    actual=[{'row':r,'column':c,'before':a,'after':z} for r,(x,y)in enumerate(zip(old,new)) for c,(a,z)in enumerate(zip(x,y)) if a!=z]
    ordered=lambda v:sorted(v,key=lambda e:(e['row'],e['column']))
    require(ordered(expected)==ordered(actual)==ordered(item['exact_meaningful_cell_changes']),'Extra/missing text change')
    require(''.join(restored).encode('utf-8')==oldbytes,'Whitespace/endings/readable bytes changed')
    before=load(checked(item['before_quartet']['json']));current=load(checked(item['current_quartet']['json']))
    expected_model_value,allowed=expected_model(before,old,fields)
    require(sorted(allowed,key=lambda x:x['json_pointer'])==sorted(item['allowed_active_semantic_changes'],key=lambda x:x['json_pointer']),'Unapproved active model alias')
    require(HISTORY not in before,'Recovery history already exists')
    expected_model_value[HISTORY]={'authority':app['authority'],'candidate_manifest':app['candidate_manifest'],'independent_candidate_audit':app['independent_candidate_audit'],'source_sha256':item['source']['sha256'],'fields':fields,'scope':SCOPE}
    require(current==expected_model_value,'Unapproved node/pin/route/geometry/history changes')
    predecessor=validate_predecessor(item,planned,app)
    return {'page':item['page'],'printed_page':item['page'],'source_scan_id':str(item['source_scan_id']),'eligible':True,'artifact_schema':'reviewed-current-quartet-v1','source':item['source'],'current_quartet':item['current_quartet'],
            'owner_receipt':binding(receipt_path),'independent_audit':binding(peer_path),'human_authority':binding(POLICY),'frozen_occurrence_inventory':binding(checked(load(CANDIDATES)['database_manifest'])),
            'root_acceptance':binding(CANDIDATE_AUDIT),'predecessor_acceptance':binding(checked(item['prior_review_record'])),
            'automatic_candidate_manifest':binding(CANDIDATES),'automatic_derivation_script':binding(checked(load(CANDIDATES)['script_binding'])),
            'automatic_database_audit':binding(checked(load(CANDIDATES)['independent_database_acceptance'])),
            'automatic_raw_authority':binding(RAW_AUTHORITY),
            'frozen_predecessor_chain':predecessor,
            'candidate_ids':[f['candidate_id']for f in fields],'changed_cells':actual,
            'checks':{'only_independently_approved_unique_fit_masked_functions':True,'exact_source_before_current_candidate_quartets':True,'exact_readable_bytes_line_lengths_endings':True,'full_other_model_and_route_invariance':True,'coordinate_bound_display_aliases_only':True,'independent_complete_witnesses_frozen_not_live_epoch':True,'derived_values_excluded_from_future_native_witnesses':True}}

def approved_pages(peer,app,manifestpath):
    """Resolve the final audit's explicit approval rows to its exact pinned manifest.

    Both manifest names in the independent audit must agree.  Its compact page
    rows bind every candidate ID/cell, predecessor and preview; its complete
    file inventory additionally binds all original before/candidate artifacts.
    """
    require(checked(peer['manifest'])==checked(peer['application_manifest'])==manifestpath,'Independent manifest aliases disagree')
    require(peer['visual_review_pending'] is False,'Visual acceptance is still pending')
    checked(peer['mechanical_audit'])
    bound={str(Path(b['path']).resolve()):b['sha256']for b in peer['all_bound_files']}
    planned={(str(x['source_scan_id']),x['page']):x for x in app['pages']};approved={}
    require(len(peer['pages'])==len(planned)==61,'Independent page approval count differs')
    for row in peer['pages']:
        key=(str(row['scan_id']),row['page']);require(key in planned and key not in approved,'Duplicate/wrong independent scan approval');page=planned[key]
        ordered=lambda edits:sorted(edits,key=lambda x:(x['row'],x['column']))
        require(row['candidate_ids']==[f['candidate_id']for f in page['function_fields']] and ordered(row['exact_unknown_cell_edits'])==ordered(page['exact_meaningful_cell_changes']),'Independent candidate/cell approval differs')
        require(row['prior_review_record']==page['prior_review_record'] and row['prior_review_record_kind']==page['prior_review_record_kind'],'Independent predecessor approval differs')
        for group in ('before_quartet','candidate_quartet'):
            for b in page[group].values():require(bound.get(str(Path(b['path']).resolve()))==b['sha256'],'Independent file inventory lacks exact quartet: '+b['path'])
        for label,group in [('before','before_quartet'),('candidate','candidate_quartet')]:
            image=row['preview_reproduction'][label];require(image['pixel_identical'] is True and image['image']==page[group]['preview'],'Independent preview acceptance differs')
        require(bound.get(str(Path(page['source']['path']).resolve()))==page['source']['sha256'],'Independent original source binding differs')
        approved[key]=page
    return approved

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--emit',action='store_true');args=p.parse_args()
    candidates=pin(CANDIDATES,CANDIDATE_SHA);ca=pin(CANDIDATE_AUDIT,CANDIDATE_AUDIT_SHA);pin(POLICY,POLICY_SHA);pin(RAW_AUTHORITY,RAW_AUTHORITY_SHA)
    require(ca['passed'] is True and not ca.get('failures'),'Candidate audit did not pass')
    receipt=pin(args.receipt,PUBLICATION_SHA);mp=checked(receipt['manifest']);app=pin(mp,APPLICATION_SHA);peerpath=checked(receipt['independent_audit']);peer=pin(peerpath,APPLICATION_AUDIT_SHA)
    require(receipt['passed'] is True and not receipt.get('failures') and peer['passed'] is True and not peer.get('failures'),'Publication/application acceptance failed')
    require(checked(peer['manifest'])==mp and checked(app['candidate_manifest'])==CANDIDATES.resolve() and checked(app['independent_candidate_audit'])==CANDIDATE_AUDIT.resolve(),'Unbound application/candidate acceptance')
    require(checked(app['authority'])==POLICY.resolve() and app['history_key']==HISTORY,'Wrong automatic authority/history')
    require(not app['held_candidates'] and app['approved_candidate_ids']==ca['approved_candidate_ids'],'Held/missing approved candidate')
    require(set(peer['approved_candidate_ids'])==set(ca['approved_candidate_ids']) and not peer.get('held_candidate_ids'),'Independent application approval differs')
    db=checked(candidates['database_manifest']);checked(candidates['independent_database_acceptance']);index=load(checked(candidates['database_index']));checked(candidates['script_binding'])
    require(sha(db)=='4d9af72870f8ab751786efd73873baac2336b01569d0eaa01006015dd60931ab','Wrong accepted database epoch')
    cases={c['candidate_id']:c for c in candidates['cases']};planned={(str(x['source_scan_id']),x['page']):x for x in app['pages']};approved=approved_pages(peer,app,mp)
    items=receipt['pages'];items=list(items.values())if isinstance(items,dict)else items
    require(len(items)==len(planned)==len(approved)==61,'Missing/duplicate page')
    records=[];allids=set();witnessnotes=[]
    for item in items:
        key=(str(item['source_scan_id']),item['page']);require(key in planned and key in approved,'Wrong source scan')
        ids,notes=validate_fields(item,cases,ca,index);require(not allids&ids,'Duplicate function ID');allids|=ids;witnessnotes+=notes
        records.append(validate_page(item,planned[key],approved[key],item['function_fields'],cases,ca,index,app,args.receipt,peerpath))
    require(allids==set(ca['approved_candidate_ids']) and len(allids)==112 and sum(len(r['changed_cells'])for r in records)==117,'Incomplete function/cell inventory')
    result={'created_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'scope':SCOPE,'pages':records,'counts':{'pages':61,'function_fields':112,'changed_cells':117},'witness_notes':witnessnotes,'candidate_manifest':binding(CANDIDATES),'independent_candidate_approval':binding(CANDIDATE_AUDIT),'authority':binding(POLICY),'application_manifest':binding(mp),'publication':binding(args.receipt),'independent_application_audit':binding(peerpath),'binder':binding(Path(__file__))}
    if args.emit:
        OUT.parent.mkdir(parents=True,exist_ok=True)
        if OUT.exists():
            archive=OUT.parent/'Automatic unreadable function recovery audit history';archive.mkdir(exist_ok=True);f=archive/(sha(OUT)+'.json')
            if not f.exists():f.write_bytes(OUT.read_bytes())
        OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'mode':'emit'if args.emit else'dry-run','counts':result['counts'],'acceptance_record':str(OUT)if args.emit else None,'repository_writes':0,'canonical_writes':0}))
if __name__=='__main__':main()

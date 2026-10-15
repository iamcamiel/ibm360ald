"""Read-only exact-position function reconstruction from accepted complete witnesses.

Only the output manifest/test receipt are written. No source, model, authority or
database changes. Witnesses are frozen accepted observations, never this run's
proposals. Run again after a database refresh to reject superseded evidence.
"""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,copy,hashlib,json,re,sys
from datetime import datetime,timezone
sys.dont_write_bytecode=True
BASE=Path('D:/Github/IBM360/tmp/ald-text/ald/card-type-database')
DB=BASE/'build-accepted-v9-batch7'
REPO=Path('D:/Github/IBM360/ibm360ald')
HERE=Path(__file__).resolve().parent
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
READ=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
def stable(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def literal_matches(pattern,literal):
 return isinstance(pattern,str) and isinstance(literal,str) and len(pattern)==len(literal) and all((b not in '\r\n') if a=='�' else a==b for a,b in zip(pattern,literal))
def shape(o):
 combo=copy.deepcopy(o['function_combination']['value'])
 for k in ('primary_function','unresolved_function_literal','source_review_pending'):combo.pop(k,None)
 return {'connected_count_and_decoration_shape':combo,'physical_pin_names_part_of_shape':False}
def eligibility(o):
 reasons=[]
 if o['page']=='AP319':reasons.append('Held AP319 card/portion identity; no reconstruction')
 if not o['identity_complete'] or not re.fullmatch(r'[0-9]{4}',o['card_type_literal']) or not o['portion_literal'] or '�' in o['portion_literal']:reasons.append('Card/portion identity incomplete')
 if o['source_review_pending'] or any(p['source_review_pending'] for p in o['pins']):reasons.append('Pending native/source finding')
 if any(o['field_recovery_dependencies'].values()):reasons.append('Function/card/portion/unit has recovery or inference dependencies')
 if o['port_annotation_availability']!='available' or o['unassigned_direction_port_count'] or any(o['ports_with_unknown_connection_counts'].values()):reasons.append('Port/count shape is incomplete')
 for p in o['pins']:
  if p['drawn_connected_port'] is None:reasons.append('Unknown port connection')
  pol=p['polarity_decoration']
  if pol['marker'] not in ('none','triangle') or pol['model_consistency']=='conflict':reasons.append('Unknown/conflicting source-bound pin polarity')
  if p['additional_decoration_evidence'].get('status') in ('Unverified separate decoration annotation','Separate model star annotation conflicts with source-bound field'):reasons.append('Conflicting/unverified separate pin decoration')
  if p['field_recovery_dependencies'] or p.get('decoration_field_recovery_dependencies'):reasons.append('Pin or decoration depends on a recovery/inferred field')
  if any('�' in str(p.get(k) or '') for k in ('printed_control_prefix_literal','adjacent_asterisk')):reasons.append('Unreadable control/star decoration')
 return sorted(set(reasons))
def make_field_context(index,repo_root):
 """Return a read-only exact-source, active-alias and typed-history classifier."""
 repo=Path(repo_root);models={};lines={};history_cache={};current_cache={}
 accepted_human_hashes={v['sha256'] for v in index['sources'].values() if v['role'].startswith('Direct human')}
 def current(o):
  for sid in (o['source_id'],o['text_source_id']):
   if sid not in current_cache:
    source=index['sources'][sid];path=repo/source['path']
    current_cache[sid]={'path':str(path),'accepted_sha256':source['sha256'],'actual_sha256':SHA(path) if path.exists() else None}
   if current_cache[sid]['actual_sha256']!=current_cache[sid]['accepted_sha256']:return False
  return True
 def model(o):
  sid=o['source_id']
  if sid not in models:models[sid]=READ(repo/index['sources'][sid]['path'])
  return models[sid]
 def field_context(o):
  oid=o['observation_id']
  if oid in history_cache:return history_cache[oid]
  if not current(o):return {'reasons':['Current source binding superseded; field history cannot be trusted against frozen database'],'matching_history':[],'active_aliases':[]}
  m=model(o);node=m
  for token in o['JSON_pointer'].strip('/').split('/'):node=node[int(token)] if isinstance(node,list) else node[token]
  aliases=[]
  for key in ('function','printed_function','function_text'):
   if key in node:aliases.append({'JSON_pointer':o['JSON_pointer']+'/'+key,'literal':node[key]})
  if isinstance(node.get('function_layout'),dict) and 'printed_function_literal' in node['function_layout']:aliases.append({'JSON_pointer':o['JSON_pointer']+'/function_layout/printed_function_literal','literal':node['function_layout']['printed_function_literal']})
  reasons=[];evidence=[]
  if any(a['literal']!=o['function_literal'] for a in aliases):reasons.append('Active function aliases disagree with exact accepted literal')
  sid=o['text_source_id']
  if sid not in lines:lines[sid]=(repo/index['sources'][sid]['path']).read_text(encoding='utf-8-sig').splitlines()
  spans=o['literal_text_bindings']['function']
  if len(spans)!=1 or spans[0]['literal']!=o['function_literal']:reasons.append('Complete full label lacks a single exact source-text span')
  else:
   v=spans[0]
   if lines[sid][v['row']][v['column']:v['column']+len(v['literal'])]!=v['literal']:reasons.append('Function span is not exact in current source text')
  def hashes(value):
   if isinstance(value,dict):return {v for k,v in value.items() if k=='sha256' and isinstance(v,str)}|set().union(*(hashes(v) for v in value.values()),set())
   if isinstance(value,list):return set().union(*(hashes(v) for v in value),set())
   return set()
  for name,history in m.items():
   if not any(s in name.lower() for s in ('human','recover','repair','correction','resolution','inference','candidate','proposal')):continue
   human='human' in name.lower() and bool(hashes(history)&accepted_human_hashes)
   def walk(value,path):
    if isinstance(value,dict):
     refs=[value.get(k) for k in ('node','node_id','node_identifier','internal_node_identifier')]
     ptrs=[value.get(k) for k in ('node_pointer','JSON_pointer','json_pointer','json_path')]
     exact=any(x in (o['node_identifier'],o['printed_node_identifier']) for x in refs if x) or any(isinstance(x,str) and (x==o['JSON_pointer'] or x.startswith(o['JSON_pointer']+'/')) for x in ptrs)
     if exact:
      relevant={k:v for k,v in value.items() if any(t in k.lower() for t in ('function','card','portion','pin','polarity','decoration','before','after'))}
      if relevant:
       kind='Direct human authority bound in accepted database' if human else 'Inference/proposal/recovery field history; not independent witness evidence'
       evidence.append({'history_pointer':path,'kind':kind,'field_summary':relevant})
       if not human:reasons.append('Exact node fields carry non-human recovery/proposal history')
     for k,v in value.items():walk(v,path+'/'+k)
    elif isinstance(value,list):
     for i,v in enumerate(value):walk(v,path+'/'+str(i))
   walk(history,'/'+name)
  result={'reasons':sorted(set(reasons)),'matching_history':evidence,'active_aliases':aliases};history_cache[oid]=result;return result

 field_context.source_bindings=current_cache
 return field_context

def select(pattern,witnesses):
 by_label=defaultdict(list)
 for w in witnesses:
  if literal_matches(pattern,w['function_literal']):by_label[w['function_literal']].append(w)
 return by_label
def tests():
 cases=[('A� T','AR T',True),('A� T','ART',False),('A� T','A R T',False),('A� T','AR  T',False),('OR U�','OR OR',False),('�R T','AR T',True),('�� T','AR T',True),('✲O�','✲OR',True),('*O�','✲OR',False),('AR �','AR T',True),('AR �','AR\n',False),('OR.�','OR,R',False),('OR �','OR R',True),('OR �','ORR',False)]
 for a,z,want in cases:assert literal_matches(a,z)==want,(a,z,want)
 ws=[{'function_literal':'AR T','id':1},{'function_literal':'AR T','id':2},{'function_literal':'OR T','id':3}]
 assert list(select('A� T',ws))==['AR T']
 assert len(select('�R T',ws))==2
 assert len(select('ZZ �',ws))==0
 assert ws==[{'function_literal':'AR T','id':1},{'function_literal':'AR T','id':2},{'function_literal':'OR T','id':3}]
 # No target/proposal can be appended to accepted witness pool by selection.
 proposed=select('A� T',ws);assert all(w['function_literal']!='A� T' for v in proposed.values() for w in v)
 return {'passed':True,'check_count':len(cases)+5,'scope':'Exact position/length, spaces and literal star preserved; one wildcard cell only; duplicate same-label witnesses count as one label; ambiguity/no-match retained; no proposal becomes witness.'}
def main():
 global DB,HERE
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--database-root',required=True,type=Path)
 parser.add_argument('--expected-database-sha256',required=True)
 parser.add_argument('--independent-acceptance',required=True,type=Path)
 parser.add_argument('--expected-independent-sha256',required=True)
 parser.add_argument('--output-root',required=True,type=Path)
 config=parser.parse_args()
 DB=config.database_root.resolve();HERE=config.output_root.resolve()
 HERE.mkdir(parents=True,exist_ok=True)
 assert not (HERE/'Expanded shape unreadable function candidates.json').exists(),'Frozen output exists; choose a new output folder'

 mp=DB/'notes/Card types/Build manifest.json';ixp=DB/'json/Card types/Card type index.json'
 assert SHA(mp)==config.expected_database_sha256
 independent=config.independent_acceptance.resolve()
 assert SHA(independent)==config.expected_independent_sha256
 assert READ(independent)['passed'] and not READ(independent)['failures']
 ix=READ(ixp);outputs={v['path']:v['sha256'] for v in READ(mp)['outputs']};assert SHA(ixp)==outputs['json/Card types/Card type index.json']
 excluded={};answer_bindings=[]
 for batch in range(1,9):
  path=(BASE/'function-review-answers-v1/Effective human function review answers.json' if batch==1 else BASE/'function-review-batch-2/Effective human answers 1-10.json' if batch==2 else BASE/f'function-review-batch-{batch}/Direct human batch{batch} answers.json')
  if path.exists():
   auth=READ(path);answer_bindings.append({'batch':batch,'path':str(path),'sha256':SHA(path),'basis':'Existing direct/effective human answers'})
   for a in auth['answers']:
    oid=a.get('observation_id') or a.get('target',{}).get('observation_id')
    if oid:excluded[oid]={'batch':batch,'answer':a.get('function_after')}
  elif batch==8:
   # Parent's direct task states that all batch8 answers were confirmed. This
   # excludes those exact issued IDs even before an authority file is saved.
   paths=list((BASE/'function-review-batch-8').glob('Eighth ten function review questions.json'))
   if paths:
    path=paths[0];q=READ(path);answer_bindings.append({'batch':8,'path':str(path),'sha256':SHA(path),'basis':'Parent explicit instruction: all batch8 human answered; exclusion only, no correction authority synthesized'})
    for a in q.get('questions',[]):
     t=a.get('target',a);oid=t.get('observation_id')
     if oid:excluded[oid]={'batch':8,'answer':None}
 obs=[];bindings=[]
 for rec in ix['card_types']:
  p=DB/rec['file'];assert SHA(p)==outputs[rec['file']];bindings.append({'path':str(p),'sha256':SHA(p)})
  obs.extend(READ(p)['diagram_observations'])
 assert len(obs)==46445 and len({o['observation_id'] for o in obs})==len(obs)
 cache={};models={};lines={};history_cache={}
 def live_binding(sid):
  if sid not in cache:
   source=ix['sources'][sid];path=REPO/source['path'];actual=SHA(path) if path.exists() else None
   cache[sid]={'source_id':sid,'path':str(path),'sha256':source['sha256'],'accepted_database_sha256':source['sha256'],'current_sha256':actual,'matches_accepted_database':actual==source['sha256']}
  return cache[sid]
 def current(o):return all(live_binding(o[sid])['matches_accepted_database'] for sid in ('source_id','text_source_id'))
 field_context=make_field_context(ix,REPO)
 def compact(o):
  p=ix['pages'][str(o['scan_id'])];original=ix['sources'][p['original_source_id']]
  return {'observation_id':o['observation_id'],'page':o['page'],'scan_id':o['scan_id'],'block':o['printed_node_identifier'] or o['node_identifier'],'node_identifier':o['node_identifier'],'node_pointer':o['JSON_pointer'],'station':o['station'],'card_type':o['card_type_literal'],'portion':o['portion_literal'],'printed_card_portion':o['printed_card_portion_literal'],'unit':o['unit_code_literal'],'location':o['location_literal'],'function_literal':o['function_literal'],'function_literal_bindings':o['literal_text_bindings']['function'],'occurrence_signature_id':o['occurrence_signature']['signature_id'],'function_combination_id':o['function_combination']['combination_id'],'model_binding':live_binding(o['source_id']),'text_binding':live_binding(o['text_source_id']),'original_source_binding':{'source_id':p['original_source_id'],'path':str(Path('D:/Reference Materials/IBM 360/IBM_360_ALD')/original['path']),'sha256':original['sha256'],'basis':'Frozen independently accepted original-source registry; no new native review'},'field_recovery_dependencies':o['field_recovery_dependencies'],'source_review_pending':o['source_review_pending'],'field_history_and_aliases':field_context(o),
          'pin_names_retained_as_evidence_only':[{'pin_pointer':p['JSON_pointer'],'direction':p['direction'],'physical_pin':p['physical_pin'],'printed_label_literal':p['printed_label_literal'],'drawn_connected_port':p['drawn_connected_port'],'polarity_marker':p['polarity_decoration']['marker'],'adjacent_asterisk':p['adjacent_asterisk'],'printed_control_prefix_literal':p['printed_control_prefix_literal'],'literal_text_bindings':p['literal_text_bindings'],'wire_boundary_text_binding':p['wire_boundary_text_binding']} for p in o['pins']]}
 pools=defaultdict(list);pool_rejected=Counter();rejected_witnesses=defaultdict(list)
 for o in obs:
  literal=o['function_literal']
  if not isinstance(literal,str) or not literal or '�' in literal:continue
  key=(o['card_type_literal'],o['portion_literal'],stable(shape(o)))
  reasons=eligibility(o)
  if not o['literal_text_bindings']['function']:reasons.append('No exact function source-text binding')
  if not reasons and not current(o):reasons.append('Current model/text no longer matches accepted database witness binding')
  if not reasons:reasons.extend(field_context(o)['reasons'])
  if reasons:
   pool_rejected.update(set(reasons));rejected_witnesses[key].append({'observation_id':o['observation_id'],'function_literal':literal,'reasons':sorted(set(reasons))});continue
  pools[key].append(o)
 cases=[];counts=Counter()
 for o in obs:
  pattern=o['function_literal']
  if not isinstance(pattern,str) or '�' not in pattern:continue
  key=(o['card_type_literal'],o['portion_literal'],stable(shape(o)));accepted=pools.get(key,[]);reasons=eligibility(o)
  if o['observation_id'] in excluded:reasons.append('Exact observation already human answered; never repeat or auto-overwrite')
  if not current(o):reasons.append('Target current model/text no longer matches accepted database binding')
  else:reasons.extend(field_context(o)['reasons'])
  if not o['literal_text_bindings']['function']:reasons.append('No exact target function text binding')
  matching=select(pattern,accepted);labels=sorted(matching)
  mismatches=Counter()
  for literal in sorted({w['function_literal'] for w in accepted}):
   if len(pattern)!=len(literal):mismatches['different_character_count']+=1
   elif not literal_matches(pattern,literal):mismatches['readable_character_position_conflict']+=1
  if reasons:status='excluded_or_ineligible'
  elif len(labels)==1:status='single_complete_literal_supported'
  elif len(labels)>1:status='ambiguous_multiple_complete_literals'
  else:status='no_matching_complete_literal'
  counts[status]+=1
  case={'candidate_id':'FU-'+o['observation_id'],'target':compact(o),'status':status,'function_before':pattern,'function_after':labels[0] if status=='single_complete_literal_supported' else None,'proposed_complete_literal':labels[0] if status=='single_complete_literal_supported' else None,'human_answer_exclusion':excluded.get(o['observation_id']),'ineligibility_reasons':sorted(set(reasons)),'function_free_exact_shape':shape(o),'shape_sha256':hashlib.sha256(key[2].encode()).hexdigest(),'complete_accepted_witness_count':len(accepted),'complete_accepted_literal_inventory':sorted({w['function_literal'] for w in accepted}),'matching_complete_literals':labels,'matching_witnesses':[compact(w) for label in labels for w in sorted(matching[label],key=lambda w:w['observation_id'])],'nonmatching_literal_counts':dict(mismatches),'rejected_same_shape_witnesses':sorted(rejected_witnesses.get(key,[]),key=lambda w:w['observation_id']),'application_performed':False}
  cases.append(case)
 cases.sort(key=lambda x:(x['target']['page'],x['target']['station'],x['target']['block'],x['target']['observation_id']))
 # A current-binding race may not produce an apparently safe proposal.
 races=[]
 for sid,binding in cache.items():
  path=Path(binding['path']);end=SHA(path) if path.exists() else None
  if end!=binding['current_sha256']:races.append({'source_id':sid,'before':binding['current_sha256'],'after':end})
 assert not races,('Live source bindings changed during read-only derivation',races)
 test=tests();tp=HERE/'Expanded deterministic matcher tests.json';tp.write_text(json.dumps(test,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 out={'schema':'Read-only expanded count-decoration shape unreadable function candidates v1','created_utc':datetime.now(timezone.utc).isoformat(),'database_manifest':{'path':str(mp),'sha256':SHA(mp)},'independent_database_acceptance':{'path':str(independent),'sha256':SHA(independent)},'database_index':{'path':str(ixp),'sha256':SHA(ixp)},'script_binding':{'path':str(Path(__file__).resolve()),'sha256':SHA(__file__)},'deterministic_tests':{'path':str(tp),'sha256':SHA(tp)},'policy':'Discovery only: exact card+portion and observed input/output counts with full known decoration multisets, zero unknown connections; physical pin names retained as evidence but excluded from the shape key. Only � is one character wildcard, never a deletion or whitespace normalization. Witnesses are accepted complete observations only; inferred proposals never join the witness pool. Direct human exact-field history is explicitly typed and authority-hash-bound; non-human recovery/proposal history and dependent identity/pin/decorations cannot serve as independent evidence. Human-answered targets, AP319 identity hold, native/conflicting findings, incomplete shapes and superseded live bindings remain excluded. No application performed.','answer_exclusion_bindings':answer_bindings,'frozen_card_bindings':bindings,'summary':{'diagram_observations':len(obs),'human_answered_observation_ids_excluded':len(excluded),'unreadable_targets':len(cases),**dict(counts),'rejected_complete_witness_reasons':dict(pool_rejected),'live_source_bindings_checked':len(cache),'live_binding_races':len(races)},'cases':cases}
 reference=BASE/'function-unreadable-resolution-v1'
 now={x['target']['observation_id']:x for x in cases};observations={o['observation_id']:o for o in obs}
 comparisons={}
 for label,path,expected in [('strict_V9',reference/'Unreadable function reconstruction candidates.json','1ad064966e64694bfbe0b301816ee352f73930425bcdd89922623dc0f05bccbd'),('expanded_V9',reference/'expanded-shape/Expanded shape unreadable function candidates.json','29f6f1cf36db10bae65b09b9ef9e982072c0a5bd9520f3549fccb0a68ecef54d')]:
  assert SHA(path)==expected
  old={x['target']['observation_id']:x for x in READ(path)['cases']};diff=[]
  for oid,a in old.items():
   if oid not in now:
    current_observation=observations[oid]
    assert '�' not in current_observation['function_literal']
    diff.append({'candidate_id':a['candidate_id'],'observation_id':oid,'page':a['target']['page'],'block':a['target']['block'],'function_before':a['function_before'],'baseline_status':a['status'],'expanded_status':'no_longer_unreadable','baseline_proposal':a['function_after'],'expanded_proposal':None,'current_complete_literal':current_observation['function_literal'],'human_answer_exclusion':excluded.get(oid),'category':'Resolved in current accepted source epoch'})
    continue
   z=now[oid]
   if a['status']=='single_complete_literal_supported':
    category='Baseline unique retained with same literal' if z['status']=='single_complete_literal_supported' and z['function_after']==a['function_after'] else 'Baseline unique became ambiguous' if z['status']=='ambiguous_multiple_complete_literals' else 'Baseline unique no longer eligible or changed'
   elif z['status']=='single_complete_literal_supported':category='New expanded unique'
   elif z['status']=='ambiguous_multiple_complete_literals' and a['status']!='ambiguous_multiple_complete_literals':category='New expanded ambiguity'
   elif z['status']=='ambiguous_multiple_complete_literals':category='Prior ambiguity remains'
   else:category='Still unresolved or ineligible'
   diff.append({'candidate_id':z['candidate_id'],'observation_id':oid,'page':z['target']['page'],'block':z['target']['block'],'function_before':z['function_before'],'baseline_status':a['status'],'expanded_status':z['status'],'baseline_proposal':a['function_after'],'expanded_proposal':z['function_after'],'baseline_matching_literals':a['matching_complete_literals'],'expanded_matching_literals':z['matching_complete_literals'],'category':category})
  comparisons[label]={'baseline_manifest':{'path':str(path),'sha256':SHA(path)},'category_counts':dict(Counter(x['category'] for x in diff)),'cases':diff,'new_unreadable_target_ids':sorted(set(now)-set(old))}
 out['baseline_comparisons']=comparisons
 out['derivation_arguments']={'database_root':str(DB),'expected_database_sha256':config.expected_database_sha256,'independent_acceptance':str(independent),'expected_independent_sha256':config.expected_independent_sha256,'output_root':str(HERE)}
 for case in cases:
  distinct=[w for w in case['matching_witnesses'] if str(w['scan_id'])!=str(case['target']['scan_id'])]
  case['matching_witness_count_on_other_scans']=len(distinct)
  case['single_label_supported_only_on_same_scan']=case['status']=='single_complete_literal_supported' and not distinct
 same_scan_only=[c['candidate_id'] for c in cases if c['single_label_supported_only_on_same_scan']]
 out['summary']['unique_candidates_without_other_scan_witness']=len(same_scan_only)
 out['same_scan_only_unique_candidate_ids']=same_scan_only
 out['read_only_matching_api']={'shape':'shape(observation)','eligibility':'eligibility(observation)','literal_matches':'literal_matches(pattern, complete_literal)','field_context_factory':'make_field_context(accepted_index, repository_root) returns cached read-only callable; .source_bindings exposes checked source hashes','physical_pin_names':'Retained as explicit target/witness evidence, never part of shape key'}
 out['application_authorized']=False
 out['shape_establishment_basis']='An unreadable physical pin number does not change known observed connected-port count or source-bound polarity/star/prefix decoration. Eligibility still requires actual accepted source-bound contacts, available annotations, zero unknown connections, all known decorations and no conflicting/pending/inferred shape evidence. No complete card pinout inferred.'
 dest=HERE/'Expanded shape unreadable function candidates.json';dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'path':str(dest),'sha256':SHA(dest),'summary':out['summary'],'baseline_delta':{k:v['category_counts'] for k,v in out['baseline_comparisons'].items()}},ensure_ascii=False))
if __name__=='__main__':main()

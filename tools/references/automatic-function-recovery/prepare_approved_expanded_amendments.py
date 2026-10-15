"""Guarded PRIVATE staging for independently approved exact unreadable-function recoveries.

Never derives candidates or writes canonical sources. Each U+FFFD is exactly one
cell; readable characters, spaces and Unicode glyphs are immutable.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import argparse,copy,hashlib,importlib.util,json,re,sys
from PIL import Image,ImageChops
BASE=Path(__file__).resolve().parent;ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';REF=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')
sys.dont_write_bytecode=True
sp=importlib.util.spec_from_file_location('shared',BASE.parent/'prepare_non_ap_OR_corrections.py');u=importlib.util.module_from_spec(sp);sp.loader.exec_module(u)
def require(ok,reason):
 if not ok:raise ValueError(reason)
def checked(binding):
 path=Path(binding['path']);require(u.sha(path)==binding['sha256'],'Stale binding: '+str(path));return path
def fits(before,after):
 return isinstance(before,str) and isinstance(after,str) and bool(before) and '�' in before and '�' not in after and '\n' not in before+after and '\r' not in before+after and len(before)==len(after) and all(a=='�' or a==b for a,b in zip(before,after))
def stable(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def separate_occurrences(target,witness):
 if target['observation_id']==witness['observation_id'] or target['JSON_pointer']==witness['JSON_pointer']:return False
 spans=lambda o:{(b['row'],b['column']+i) for b in o['literal_text_bindings']['function'] for i in range(len(b['literal']))}
 return bool(spans(target)) and bool(spans(witness)) and not spans(target)&spans(witness)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--manifest',type=Path);ap.add_argument('--candidate-audit',type=Path);ap.add_argument('--authorization',type=Path);ap.add_argument('--validate-only',action='store_true');ap.add_argument('--self-test',action='store_true');args=ap.parse_args()
 if args.self_test:
  tests=[('A� T','AR T',True),('�� T','AR T',True),('�R T','AR T',True),('A� T','ART',False),('A� T','A R T',False),('A� T','OR T',False),('A� T','AR  T',False),('*O�','✲OR',False),('✲O�','✲OR',True),('OR.�','OR,R',False),('AR �','AR\n',False),('AR T','AR T',False),('A� T','A� T',False),('OR �','OR R',True)]
  for a,b,want in tests:require(fits(a,b)==want,repr((a,b,want)))
  def obs(oid,pointer,row,col,literal):return {'observation_id':oid,'JSON_pointer':pointer,'literal_text_bindings':{'function':[{'row':row,'column':col,'literal':literal}]}}
  t=obs('target','/nodes/1',3,51,'�R')
  separated=[(obs('w','/nodes/2',10,51,'OR'),True),(obs('target','/nodes/2',10,51,'OR'),False),(obs('w','/nodes/1',10,51,'OR'),False),(obs('w','/nodes/2',3,52,'OR'),False),(obs('w','/nodes/2',3,53,'OR'),True)]
  for w,want in separated:require(separate_occurrences(t,w)==want,'Same-scan node/text independence boundary failed')
  print(json.dumps({'passed':True,'checks':len(tests)+len(separated),'source_writes':0}));return
 require(args.manifest and args.candidate_audit and args.authorization,'Manifest, independent candidate audit and direct human authorization are required')
 manifest=u.load(args.manifest);audit=u.load(args.candidate_audit);authorization=u.binding(args.authorization)
 require(audit.get('passed') and not audit.get('failures'), 'Independent candidate audit must pass')
 bound=audit.get('candidate_manifest',audit.get('manifest'));require(bound and bound['sha256']==u.sha(args.manifest),'Audit must bind this exact frozen candidate manifest')
 require(audit.get('authorization',{}).get('sha256')==authorization['sha256'],'Audit must bind the direct human recovery authorization')
 approved=audit.get('approved_candidate_ids',[]);require(approved and len(approved)==len(set(approved)),'Explicit unique approved candidate IDs are required')
 require(isinstance(audit.get('independent_witness_ids'),dict),'Audit must identify independently accepted complete witnesses per approved candidate')
 database=checked(manifest['database_manifest']);dbroot=database.parents[2];build=u.load(database);index=u.load(checked(manifest['database_index']))
 db_acceptance=u.load(checked(manifest['independent_database_acceptance']));require(db_acceptance.get('passed') and not db_acceptance.get('failures'),'Independent database acceptance must still pass')
 outputs={b['path']:b['sha256'] for b in build['outputs']};require(outputs['json/Card types/Card type index.json']==u.sha(manifest['database_index']['path']),'Index not bound to database build')
 for b in build['input_manifests']:require(u.sha(REPO/b['path'])==b['sha256'],'Accepted repository snapshot changed: '+b['path'])
 for b in manifest['answer_exclusion_bindings']:checked(b)
 derive=checked(manifest['script_binding']);spec=importlib.util.spec_from_file_location('frozen_derivation',derive);proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(proof)
 require(callable(getattr(proof,'make_field_context',None)),'Bound derivation must export make_field_context(index, repo_root)')
 field_context=proof.make_field_context(index,REPO)
 cached_hashes={};model_cache={};text_cache={}
 def current_hash(path):
  path=Path(path)
  if str(path) not in cached_hashes:cached_hashes[str(path)]=u.sha(path)
  return cached_hashes[str(path)]
 observations={};cards={}
 def card(code):
  if code not in cards:
   path=dbroot/f'json/Card types/{code}.json';require(u.sha(path)==outputs[f'json/Card types/{code}.json'],'Stale frozen card')
   cards[code]=u.load(path)
   for o in cards[code]['diagram_observations']:observations[o['observation_id']]=o
  return cards[code]
 def current(o):
  for sid in (o['source_id'],o['text_source_id']):
   b=index['sources'][sid];require(current_hash(REPO/b['path'])==b['sha256'],'Current source differs from accepted witness/target')
  spans=o['literal_text_bindings']['function'];require(len(spans)==1 and spans[0]['literal']==o['function_literal'],'Complete function must have one exact source-text span')
  span=spans[0]
  if o['text_source_id'] not in text_cache:text_cache[o['text_source_id']]=(REPO/index['sources'][o['text_source_id']]['path']).read_text(encoding='utf-8').splitlines()
  text=text_cache[o['text_source_id']];require(text[span['row']][span['column']:span['column']+len(span['literal'])]==span['literal'],'Witness/target complete literal is not present in current text')
  if o['source_id'] not in model_cache:model_cache[o['source_id']]=u.load(REPO/index['sources'][o['source_id']]['path'])
  model=model_cache[o['source_id']];require(model['nodes'][int(o['JSON_pointer'].split('/')[-1])]['function']==o['function_literal'],'Witness/target semantic function differs from accepted complete literal')
 def independent_shape(o):
  require(not proof.eligibility(o),'Unresolved identity/pin/source eligibility: '+o['observation_id'])
  require(not field_context(o)['reasons'],'Bound typed field-history/alias eligibility failed: '+o['observation_id'])
  require(not o['field_recovery_dependencies'].get('printed_card_portion'),'Inferred card/portion cannot establish automatic identity')
  require(not o['field_recovery_dependencies'].get('unit'),'Inferred unit cannot establish independent exact shape')
  for p in o['pins']:require(not p.get('field_recovery_dependencies') and not p.get('decoration_field_recovery_dependencies'),'Recovered pin/decoration cannot establish independent shape')
 cases={c['candidate_id']:c for c in manifest['cases']};validated=[];held=[]
 for cid in approved:
  require(cid in cases,'Approved candidate ID is absent');case=cases[cid];t=case['target'];code=t['card_type'];card(code);target=observations[t['observation_id']]
  require(cid=='FU-'+target['observation_id'] and target['card_type_literal']==code and target['portion_literal']==t['portion'] and target['scan_id']==t['scan_id'] and target['JSON_pointer']==t['node_pointer'],'Frozen compact target identity disagrees with accepted observation')
  require(case['status']=='single_complete_literal_supported' and not case['human_answer_exclusion'] and not case['ineligibility_reasons'],'Case is not eligible for automatic application')
  before=target['function_literal'];after=case['proposed_complete_literal'];require(fits(before,after) and proof.literal_matches(before,after),'Length/readable-character/wildcard violation: '+cid)
  require(target['page']!='AP319' and re.fullmatch(r'[0-9]{4}',code) and re.fullmatch(r'[A-Z0-9]{2}',target['portion_literal']),'Held or incomplete card identity')
  independent_shape(target);current(target);shape=proof.shape(target)
  require(shape==case['function_free_exact_shape'] and hashlib.sha256(stable(shape).encode()).hexdigest()==case['shape_sha256'],'Target exact shape mismatch')
  inventory=[]
  for witness in cards[code]['diagram_observations']:
   if witness['portion_literal']!=target['portion_literal'] or witness['observation_id']==target['observation_id']:continue
   literal=witness['function_literal']
   if not isinstance(literal,str) or not literal or '�' in literal or proof.eligibility(witness) or proof.shape(witness)!=shape:continue
   if field_context(witness)['reasons']:continue
   current(witness)
   inventory.append(witness)
  require(len(inventory)==case['complete_accepted_witness_count'] and sorted({w['function_literal'] for w in inventory})==case['complete_accepted_literal_inventory'],'Complete accepted literal inventory changed')
  matching={w['function_literal'] for w in inventory if fits(before,w['function_literal'])}
  require(matching=={after} and case['matching_complete_literals']==[after],'No unique complete accepted literal fits all readable positions')
  independent=[]
  for wid in audit['independent_witness_ids'].get(cid,[]):
   require(wid in observations,'Unknown approved witness');w=observations[wid]
   require(w in inventory and w['function_literal']==after,'Witness must be a complete accepted source observation')
   if w['scan_id']==target['scan_id']:
    if wid not in audit.get('approved_same_scan_witness_ids',{}).get(cid,[]):continue
    require(separate_occurrences(target,w),'Same-scan witness must be a separate source-bound node and nonoverlapping full function text span')
   independent_shape(w);original=index['sources']['t'+w['scan_id']];require(current_hash(REF/original['path'])==original['sha256'],'Independent original witness scan changed');independent.append(w)
  if not independent:
   held.append({'candidate_id':cid,'page':target['page'],'node_pointer':target['JSON_pointer'],'reason':'No distinct-scan witness or independently approved separate same-scan occurrence remains','approved_witness_ids':audit['independent_witness_ids'].get(cid,[]),'matching_complete_witness_ids':[w['observation_id'] for w in inventory if w['function_literal']==after],'target_scan_id':target['scan_id']});continue
  validated.append((case,target,independent))
 out=BASE/'expanded-applications'/(u.sha(args.manifest)[:16]+'-accepted-review-v2');require(not (out/'Private approved unreadable function application manifest.json').exists(),'Frozen stage already exists')
 for path,expected in cached_hashes.items():require(u.sha(path)==expected,'Input changed during independent validation: '+path)
 for source in field_context.source_bindings.values():require(u.sha(source['path'])==source['accepted_sha256']==source['actual_sha256'],'Typed field-context input changed during independent validation: '+source['path'])
 for b in build['input_manifests']:require(u.sha(REPO/b['path'])==b['sha256'],'Accepted repository epoch changed during validation')
 report={'candidate_manifest':u.binding(args.manifest),'independent_candidate_audit':u.binding(args.candidate_audit),'imported_derivation_script':u.binding(derive),'shape_policy':manifest['policy'],'approved_candidate_ids':approved,'staging_eligible_candidate_ids':[r[0]['candidate_id'] for r in validated],'held_candidates':held,'complete_label_inventories_recomputed':True,'readable_positions_and_complete_length_unchanged':True,'canonical_writes':0}
 out.mkdir(parents=True,exist_ok=True);report_path=out/'Guarded expanded validation report.json';u.save(report_path,report)
 if args.validate_only:print(json.dumps({'passed':True,'eligible_candidates':len(validated),'held_candidates':len(held),'validation_report':u.binding(report_path),'canonical_writes':0}));return
 require(validated,'No distinct-scan-supported candidate remains; see explicit validation report')
 export=u.load(REPO/'notes/Reviewed export provenance.json');content=u.load(REPO/'notes/Content data manifest.json');groups=defaultdict(list)
 for rec in validated:groups[rec[1]['scan_id']].append(rec)
 protected=[u.binding(p) for p in (args.manifest,args.candidate_audit,args.authorization,database,Path(manifest['database_index']['path']),Path(manifest['independent_database_acceptance']['path']),derive,u.FONT,report_path,REPO/'notes/Reviewed export provenance.json',REPO/'notes/Content data manifest.json')]
 app={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'PRIVATE; requires independent application/layout acceptance and root release before canonical publication','authority':authorization,'candidate_manifest':u.binding(args.manifest),'independent_candidate_audit':u.binding(args.candidate_audit),'protected_inputs':protected,'snapshot_inputs':[u.freeze(b['path'],out/'Immutable input receipts') for b in protected if Path(b['path']).suffix=='.json'],'pages':[],'history_key':'source_derived_unique_function_recovery_'+u.sha(args.manifest)[:12],'held_candidates':held,'approved_candidate_ids':approved,'validation_report':u.binding(report_path),'flagged_fields':[]}
 for scan,records in groups.items():
  entry=next(e for e in export['exported'] if str(e['source_scan_id'])==scan);first=records[0][1];mfile=index['sources'][first['source_id']]['path'];f=next(f for f in content['files'] if f['path'].replace('\\','/')==mfile)
  tp=Path(entry['transcription_source']);mp=Path(f['source']);require(u.sha(tp)==entry['text_sha256'] and u.sha(mp)==f['sha256'],'Canonical/accepted before binding mismatch')
  require(u.sha(tp)==u.sha(REPO/index['sources'][first['text_source_id']]['path']) and u.sha(mp)==u.sha(REPO/mfile),'Working and published epochs differ')
  np=tp.with_name(tp.stem+' review notes.txt');lines=tp.read_bytes().decode('utf-8').splitlines();rawrows=tp.read_bytes().decode('utf-8').splitlines(keepends=True);endings=[r[len(s):] for r,s in zip(rawrows,lines)];newlines=list(lines)
  possibilities=[tp.with_name(tp.stem+' preview.png'),tp.with_suffix('.png'),tp.with_name(tp.stem+' JuliaMono preview.png'),tp.with_name(tp.stem+' JuliaMono.png')];previews=[]
  for pp in possibilities:
   if not pp.exists():continue
   with Image.open(pp) as im:
    size=list(im.size);cfg={'size':size,'font_size':20,'row_height':18,'x':(size[0]-2940)//2,'y':(size[1]-1854)//2}
    if size==[2956,1870]:cfg['anchor']='lt'
    if ImageChops.difference(im.convert('RGB'),u.render(lines,cfg)).getbbox() is None:previews.append((pp,cfg))
  require(len(previews)==1,'One exact accepted preview reproduction is required');pp,config=previews[0]
  source=REF/entry['source_relative'];original=index['sources'][index['pages'][scan]['original_source_id']];require(u.sha(source)==original['sha256'],'Original source changed')
  canonical={'txt':tp,'json':mp,'notes':np,'preview':pp};folder=out/(entry['page']+'-'+scan);before={k:u.freeze(p,folder/'before') for k,p in canonical.items()};frozen_source=u.freeze(source,folder/'before/Original source snapshot');model=u.load(mp);updated=copy.deepcopy(model);allowed=[];fields=[];cells=[]
  for case,target,witnesses in records:
   cid=case['candidate_id'];pointer=target['JSON_pointer'];ni=int(pointer.split('/')[-1]);node=model['nodes'][ni];old=target['function_literal'];new=case['proposed_complete_literal'];require(node['function']==old,'Semantic function changed')
   binds=target['literal_text_bindings']['function'];require(len(binds)==1,'Multirow/ambiguous function needs manual staging');b=binds[0];r,c=b['row'],b['column'];require(b['literal']==old and lines[r][c:c+len(old)]==old,'Exact UTF-8 function span mismatch')
   require(node['row']<r<node['row']+3 and node['column']<c and c+len(old)<=node['column']+node.get('width',8)-1,'Function not uniquely within current box header')
   edits=[{'row':r,'column':c+i,'before':a,'after':z} for i,(a,z) in enumerate(zip(old,new)) if a!=z];require(edits and all(x['before']=='�' for x in edits),'Only unreadable cells may change')
   require(not {(x['row'],x['column']) for x in edits}&{(x['row'],x['column']) for x in cells},'Overlapping approved targets');cells+=edits;newlines[r]=newlines[r][:c]+new+newlines[r][c+len(old):]
   for key in ('function','printed_function','function_text'):
    value=node.get(key)
    if isinstance(value,str) and value.strip(' ')==old:
     replacement=value.replace(old,new);updated['nodes'][ni][key]=replacement;allowed.append({'json_pointer':pointer+'/'+key,'before':value,'after':replacement})
   layout=node.get('function_layout')
   if isinstance(layout,dict) and isinstance(layout.get('printed_function_literal'),str) and layout['printed_function_literal'].strip(' ')==old:
    value=layout['printed_function_literal'];replacement=value.replace(old,new);updated['nodes'][ni]['function_layout']['printed_function_literal']=replacement;allowed.append({'json_pointer':pointer+'/function_layout/printed_function_literal','before':value,'after':replacement})
   for collection in ('printed_labels','labels'):
    for li,label in enumerate(updated.get(collection,[])):
     if not isinstance(label,dict) or not isinstance(label.get('text'),str) or label.get('row')!=r or not isinstance(label.get('column'),int):continue
     lc=label['column'];text=label['text'];overlap=[x for x in edits if lc<=x['column']<lc+len(text)]
     if not overlap:continue
     original_label=model[collection][li]['text'];require(lines[r][lc:lc+len(original_label)]==original_label,'Printed-label alias not exactly source-bound');chars=list(text)
     for e in overlap:require(chars[e['column']-lc]=='�','Alias would alter readable text');chars[e['column']-lc]=e['after']
     label['text']=''.join(chars);allowed.append({'json_pointer':f'/{collection}/{li}/text','before':text,'after':label['text']})
   fields.append({'candidate_id':cid,'node_pointer':pointer,'node':node['id'],'function_before':old,'function_after':new,'row':r,'column':c,'exact_meaningful_cell_changes':edits,'exact_function_free_shape':case['function_free_exact_shape'],'shape_sha256':case['shape_sha256'],'independent_witness_observation_ids':[w['observation_id'] for w in witnesses],'witness_source_model_text_bindings':[{'observation_id':w['observation_id'],'node_pointer':w['JSON_pointer'],'function_literal_bindings':w['literal_text_bindings']['function'],'same_scan_as_target':w['scan_id']==target['scan_id'],'same_scan_explicitly_independently_approved':w['scan_id']==target['scan_id'] and w['observation_id'] in audit.get('approved_same_scan_witness_ids',{}).get(cid,[]),'model':index['sources'][w['source_id']],'text':index['sources'][w['text_source_id']],'original':index['sources']['t'+w['scan_id']]} for w in witnesses]})
  merged={}
  for change in allowed:
   ptr=change['json_pointer']
   if ptr in merged:require(merged[ptr]['after']==change['before'],'Alias updates are not sequential');merged[ptr]['after']=change['after']
   else:merged[ptr]=change
  allowed=list(merged.values())
  history=app['history_key'];require(history not in updated,'This exact recovery was already staged');updated[history]={'authority':authorization,'candidate_manifest':u.binding(args.manifest),'independent_candidate_audit':u.binding(args.candidate_audit),'source_sha256':original['sha256'],'fields':fields,'scope':'Source-derived recovery of U+FFFD cells only; no readable text, wiring, geometry or function taxonomy is changed. Derived values are never promoted to independent native witnesses.'}
  diffs=u.diff(model,updated);require(sorted([d for d in diffs if not d['json_pointer'].startswith('/'+history)],key=lambda d:d['json_pointer'])==sorted(allowed,key=lambda d:d['json_pointer']),'Unexpected active model delta')
  paths={k:folder/'candidate'/p.name for k,p in canonical.items()};paths['txt'].parent.mkdir(parents=True,exist_ok=True);require(len(lines)==len(newlines) and all(len(a)==len(z) for a,z in zip(lines,newlines)),'Visible layout changed');paths['txt'].write_bytes(''.join(s+e for s,e in zip(newlines,endings)).encode('utf-8'));u.save(paths['json'],updated)
  notes=np.read_bytes().decode('utf-8');nl='\r\n' if '\r\n' in notes else '\n';paths['notes'].write_bytes((notes+nl+'Independently approved exact unreadable function recoveries: '+', '.join(f['candidate_id'] for f in fields)+'. Only U+FFFD cells changed; complete independent witnesses and original readings are bound in the application receipt.'+nl).encode('utf-8'));u.render(newlines,config).save(paths['preview'])
  predecessor=ROOT/entry['review_record']
  if predecessor.is_file():prior=u.freeze(predecessor,folder/'before/Immutable predecessor');prior_kind='Existing exact independent review record'
  else:
   require(scan=='357' and entry['page']=='AR301' and entry['review_record']=='Completed published review status: native source and rendered layout reviewed; marked unreadable print retained.','Only the exact accepted AR301 scan357 completed-review representation has a fallback')
   predecessor_snapshot=folder/'before/Immutable predecessor/Accepted completed review export entry.json'
   payload={'kind':'Accepted completed-review export entry; literal review status is not a filename','accepted_export_manifest':u.binding(REPO/'notes/Reviewed export provenance.json'),'accepted_content_manifest':u.binding(REPO/'notes/Content data manifest.json'),'exact_export_entry':entry,'exact_content_entry':f,'before_quartet':before,'original_source':u.binding(source),'independent_database_acceptance':manifest['independent_database_acceptance']}
   if predecessor_snapshot.exists():require(u.load(predecessor_snapshot)==payload,'Frozen completed-review predecessor changed')
   else:u.save(predecessor_snapshot,payload)
   prior=u.binding(predecessor_snapshot);prior_kind='Frozen accepted completed-review export entry and exact content binding'
  app['pages'].append({'page':entry['page'],'source_scan_id':scan,'source':u.binding(source),'frozen_original_source':frozen_source,'canonical_quartet':{k:u.binding(p) for k,p in canonical.items()},'before_quartet':before,'candidate_quartet':{k:u.binding(p) for k,p in paths.items()},'prior_review_record':prior,'prior_review_record_kind':prior_kind,'function_fields':fields,'exact_meaningful_cell_changes':cells,'allowed_active_semantic_changes':allowed,'metadata_changes':[d for d in diffs if d['json_pointer'].startswith('/'+history)],'render_config':config,'line_lengths_before':[len(s) for s in lines],'trailing_space_padding':0,'line_endings_preserved':True})
 app['counts']={'pages':len(groups),'function_fields':len(validated),'character_corrections':sum(len(p['exact_meaningful_cell_changes']) for p in app['pages'])};app['preparation_helper']=u.binding(Path(__file__));dest=out/'Private approved unreadable function application manifest.json';u.save(dest,app);print(json.dumps({'manifest':u.binding(dest),'counts':app['counts'],'canonical_writes':0}))
if __name__=='__main__':main()

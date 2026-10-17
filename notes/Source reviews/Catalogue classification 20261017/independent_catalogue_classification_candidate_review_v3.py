"""Verify classification-only catalogue delta; no canonical mutation."""
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime,timezone
import copy,json,csv,hashlib
ROOT=Path(__file__).parent;FOLDER=ROOT/'Catalogue classification refresh';OLD=FOLDER/'Predecessors';NEW=FOLDER/'Candidate';REPO=Path('D:/Github/IBM360/ibm360ald')
MP=FOLDER/'Refresh manifest.json';EXPECTED='c10632f283ae3d410a0cec6b84bae1c02b869320ad07e7b3533078a03e4b6310';REL='notes/Card types current/Build manifest.json'
checks=0;epochs={}
def need(v,m):
 global checks
 checks+=1
 if not v:raise AssertionError(m)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def checked(l):
 p=Path(l['path']).resolve();need(p.is_file() and sha(p)==l['sha256'],'Exact bound current file '+str(p));epochs[p]=l['sha256'];return p
def cards(base):return {p.stem:read(p) for p in (base/'json/Card types current').glob('*.json')}
need(sha(MP)==EXPECTED,'Exact frozen classification-only refresh manifest');checked(bind(MP));m=read(MP)
for l in m['inputs']:checked(l)
for r in m['records']:
 if r['before']:checked(r['before']);need(sha(REPO/r['relative'])==r['before']['sha256'],'Current existing catalogue predecessor')
 else:need(not(REPO/r['relative']).exists(),'New candidate target absent')
 if r['candidate']:checked(r['candidate'])
for l in m['protected_nested_notes_history']:checked({'path':l['path'],'sha256':l['sha256']})
need(len(m['protected_nested_notes_history'])==14 and m['source_writes']==0 and not m['published'],'Only derived catalogue with all14historical files protected')
prep=ROOT/'Catalogue classification tool preparation.json';need(sha(prep)=='b984bab5e405adbdcdd889750178344e8b4614271ca65ad332a7f1f12fced64e','Frozen4file tool change receipt');p=read(checked(bind(prep)))
for f in p['files']:
 if f['before']:checked(f['before'])
 checked(f['after'])
helper=read(checked(bind(ROOT/'Independent refresh helper review.json')));need(helper['passed'] is True and helper['fixture_count']==12,'Independent narrow helper review passed')
regpath=ROOT/'Independent catalogue regression results v2.json';reg=read(checked(bind(regpath)));need(reg['passed'] is True and reg['testsRun']==35 and not reg['errors'] and not reg['failures'],'13classification plus22independentuniformfixtures passed');checked(reg['log'])
om,nm=read(OLD/REL),read(NEW/REL);need(om['source_pages']==nm['source_pages'],'Accepted ALD source epoch/path coverage unchanged')
old,new=cards(OLD),cards(NEW);need(set(old)==set(new) and len(new)==199,'Same199cardtypes; classification adds no inferred type')
uniformpath=REPO/'json/Socket listings uniform/Socket listings.json';uniform=read(checked(bind(uniformpath)))
uniform_digest=sha(uniformpath)
physical={r['id']:(i,r) for i,r in enumerate(uniform['records']) if r.get('card_type') is not None and 'CARD' in str(r.get('kind_literal'))}
need(len(physical)==3990 and len(uniform['records'])==7217,'All3990physicalrecords among7217logicalrecords')
prov=read(REPO/'notes/Reviewed export provenance.json');scans={str(e['source_scan_id']):e for e in prov['exported']}
facts={c:{'template':copy.deepcopy(d),'occurrences':[],'listings':[]} for c,d in old.items()}
annotations={}
for text,b in nm['source_pages'].items():
 doc=read(REPO/b['model'])
 for index,node in enumerate(doc.get('nodes',[])):
  flags=[key for key in ['symbol_only','annotation_only','annotation_block'] if node.get(key) is True]
  if flags:annotations[text,'/nodes/'+str(index)]=(node,flags)
need(len(annotations)==39,'Exactly39explicitannotationnodes, never inferred from carddigits')
removed=[];retained=0
for card,d in old.items():
 for ob in d['diagram_occurrences']:
  key=ob['source_text'],ob['node_pointer']
  if key in annotations:removed.append((card,copy.deepcopy(ob)));continue
  facts[card]['occurrences'].append(copy.deepcopy(ob));retained+=1
need(len(removed)==1 and removed[0][0]=='0000' and removed[0][1]['page']=='KX111' and removed[0][1]['circuit_identifier']=='GROUND','Only previously numeric explicitGROUNDpseudo-node excluded; real0000cards kept')
need(retained==46247,'All46247realexistingcardoccurrences retained')
for rid,(index,r) in physical.items():
 need(r['card_type'] in facts,'Everyuniformphysicaltypealreadyobservedorlisted')
 header=r['header_source'];entry=scans[str(header['scan_id'])];source='ALD/'+str(entry['destination']).replace('\\','/').split('/ALD/',1)[1]
 refs=copy.deepcopy(r['references'])
 for ref in refs:ref['printed_portions']=copy.deepcopy(ref['portions'])
 listing={'record_id':rid,'page':header['page'],'record_pointer':f'/records/{index}','source_text':source,'source_text_sha256':entry['text_sha256'],'source_model':'json/Socket listings uniform/Socket listings.json','source_model_sha256':uniform_digest,'board':r['board'],'sockets':r['sockets'],'physical_sockets':r['physical_sockets'],'kind':{'single_card':'SINGLE CARD','double_card':'DOUBLE CARD'}.get(r['kind']),'kind_normalized':r['kind'],'kind_literal':r['kind_literal'],'part_number':r['part_number'],'references':refs,'unused_portions':r['unused_portions'],'header_source':header,'source_spans':r['source_spans'],'source_reviewed':True,'source_review_basis':'Current accepted TXT and uniform source spans; no new visual acceptance'}
 facts[r['card_type']]['listings'].append(listing)
seen=set();width_changes=0;profiles_total=0;unknown=[]
for card,f in sorted(facts.items()):
 occ=sorted(f['occurrences'],key=lambda x:(x['page'] or '',x['node'] or '',x['source_text']))
 listings=sorted(f['listings'],key=lambda x:(x.get('board') or '',str(x.get('sockets')),x.get('source_text',x.get('source_model',''))))
 d=f['template'];d['listing_records']=listings
 d['full_part_numbers_observed']=sorted({str(l['part_number']) for l in listings if l.get('part_number')})
 d['listing_kinds_observed']=sorted({str(l['kind']) for l in listings if l.get('kind')});widths=sorted(set(d['listing_kinds_observed'])&{'SINGLE CARD','DOUBLE CARD'});d['physical_card_widths_observed']=widths
 letters={'B','D'} if widths==['SINGLE CARD'] else {'B','D','G','J'} if widths==['DOUBLE CARD'] else None
 for ob in occ:
  key=ob['source_text'],ob['node_pointer'];need(key not in seen,'Retained occurrence identity unique');seen.add(key)
  for pin in ob['pins']:
   contact=pin['physical_pin_candidate'];valid=None if letters is None or contact is None else contact[0] in letters
   if valid!=pin['valid_for_observed_card_width']:width_changes+=1
   pin['valid_for_observed_card_width']=valid
 d['diagram_occurrences']=occ;d['observed_portions']=sorted({x['portion'] for x in occ if x['portion']})
 d['listing_portions']=sorted({str(p) for l in listings for ref in l['references'] for p in ref.get('printed_portions',[])})
 groups=defaultdict(list)
 for ob in occ:groups[(ob['portion'],ob['primary_function'],ob['circuit_identifier'],json.dumps(ob['observed_shape'],sort_keys=True))].append(ob)
 profiles=[]
 for (portion,fn,circuit,shape),members in sorted(groups.items(),key=lambda kv:tuple(str(x) for x in kv[0])):profiles.append(dict(portion=portion,primary_function=fn,circuit_identifier=circuit,observed_shape=json.loads(shape),occurrences=len(members),examples=[f"{x['page']} {x['node']}" for x in members[:8]]))
 d['portion_profiles']=profiles;profiles_total+=len(profiles)
 need(d==new[card],'Complete cardJSON independently reconstructed: retained pinlabels/functions/circuits/portion/location unchanged; listing authority and derived width-only differences '+card)
 for l in listings:
  if l['kind'] is None:unknown.append({'card_type':card,'record_id':l['record_id'],'literal':l['kind_literal']})
expected_unknown=[{'card_type':r['card_type'],'record_id':rid,'literal':r['kind_literal']} for rid,(_,r) in physical.items() if r['kind'] not in {'single_card','double_card'}]
need(profiles_total==5706 and unknown==expected_unknown and len(unknown)==1 and unknown[0]['card_type']=='0505','OnlyexplicitGROUNDprofile removed; actual source-bound unknownprintedwidth record/literal retained without invented identity')
need(new['0479']['listing_kinds_observed']==['SINGLE CARD'],'Continuation pagination not a new electrical width')
exclude=read(NEW/'notes/Card types current/Excluded annotation nodes.json')
need(exclude['count']==39 and {(r['source_text'],r['node_pointer']) for r in exclude['observations']}==set(annotations),'Allandonlyexplicitannotationexclusionledger')
unold=read(OLD/'notes/Card types current/Unclassified card identifiers.json');unnew=read(NEW/'notes/Card types current/Unclassified card identifiers.json')
remaining=[o for o in unold['observations'] if (o['source_text'],o['node_pointer']) not in annotations]
need(unnew['observations']==remaining and unnew['count']==len(remaining) and len(remaining)==208,'Exact original208nonemptyunclassifiedobservations unchanged; no real identifier repaired')
need(om['counts']['nodes_without_card_type']-nm['counts']['nodes_without_card_type']==38,'38previouslynoncardannotations excluded from noncard nodecount, not invented as nonempty observations')
baseline=read(checked(bind(ROOT/'Baseline and scope.json')))
frozen=read(checked(bind(ROOT.parent/'card-rerun-20261017/Rerun frozen inputs.json')))
for l in frozen['tool_sources']:checked(l)
for l in frozen['protected_reviewed_outputs']:checked(l)
protected={Path(l['path']).resolve() for l in frozen['protected_reviewed_outputs']};need(protected=={p.resolve() for branch in ['Card-ALD','json/Card-ALD'] for p in (REPO/branch).rglob('*') if p.is_file()},'All232reviewedoutputs namespace+bytes unchanged')
need(len(nm['source_inputs'])==4431 and len({i['path'] for i in nm['source_inputs']})==4431,'4431uniqueexplicitcurrentcataloginputs')
for l in nm['source_inputs']:checked({'path':str(REPO/l['path']),'sha256':l['sha256']})
for p,h in epochs.items():need(sha(p)==h,'Final exact source/tool/output epoch '+str(p))
receipt={'schema':'independent-catalogue-classification-refresh-acceptance-v1','passed':True,'independent_review':True,'failures':[],'created_utc':datetime.now(timezone.utc).isoformat(),'manifest':bind(MP),'reviewer_program':bind(__file__),'check_count':checks,'tool_preparation':bind(prep),'reviewed_tool_files':read(prep)['files'],'regressions':bind(regpath),'helper_review':bind(ROOT/'Independent refresh helper review.json'),'card_types':199,'physical_listing_records':3990,'retained_physical_occurrences':46247,'excluded_explicit_annotation_nodes':39,'excluded_previously_numeric_pseudo_nodes':1,'previously_noncard_annotation_nodes_excluded':38,'unclassified_nonempty_observations_unchanged':208,'portion_profiles':profiles_total,'width_assessment_cells_changed':width_changes,'unknown_width_records':unknown,'protected_reviewed_outputs_unchanged':232,'card_tools_unchanged':64,'source_inputs':4431,'source_and_canonical_writes':False,'scope':'Classification-only: complete existing accepted uniform listing coverage, retained unknownwidth, pagination handled as source structure, explicit annotation exclusion. Complete retained occurrence fields including physical pinlabels/functions/circuits/portions/locations unchanged. No internal-net assembly or powerpolicy changes, no source transcription changes, no publication.'}
dest=FOLDER/'Independent classification acceptance.json';need(not dest.exists(),'Never overwrite independent review history');dest.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'passed':True,'checks':checks,'receipt':bind(dest),'width_cells':width_changes,'unknown_width_records':unknown},indent=2))

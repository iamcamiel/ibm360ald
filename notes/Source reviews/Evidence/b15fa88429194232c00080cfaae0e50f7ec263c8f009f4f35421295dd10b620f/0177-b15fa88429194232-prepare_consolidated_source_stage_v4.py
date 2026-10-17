"""Compose accepted explicit source proposals into one new private guarded stage.

No owner/repository file is written. The canonical source-review tool produces
only private candidates after all current preimages and previews reproduce.
"""
from pathlib import Path
from collections import defaultdict,Counter
from copy import deepcopy
from datetime import datetime,timezone
import ast,json,re,sys,hashlib
from PIL import Image
ROOT=Path('D:/Github/IBM360');R=ROOT/'ibm360ald';B=Path(__file__).parent;S=B.parent/'source-flag-visual-review-20261017';O=B/'Consolidated source correction preparation v4'
sys.path.insert(0,str(R/'tools/reviews'));import source_review as sr
def read(p):return sr.read_json(p)
def bind(p):return sr.binding(p)
def need(v,m):
 if not v:raise ValueError(m)
def put(p,d):p.write_bytes(sr.encode(d))
need(not O.exists(),'Preserve frozen predecessor output');O.mkdir()
pages={};inputs={};facts=[];overlap=[];filtered=[];superseded=[];counts=Counter();fontprobe=B.parent/'pin-letter-visual-20261016/Predecessor preview configuration probe.json'
def evidence(p):
 link=p if isinstance(p,dict)else bind(p);path,raw=sr.checked(link,B);need(path.suffix.lower()not in ['.tif','.tiff'],'Native scans are page-source bindings, not copied evidence');inputs[str(path)]=bind(path);return bind(path)
def normalize(x):
 y={k:deepcopy(x[k])for k in ['op','before','after']if k in x};y['pointer']=x.get('pointer',x.get('path'));need(y['pointer'],'JSON pointer required');y.setdefault('op','replace');return y
provenance=R/'notes/Reviewed export provenance.json';content=R/'notes/Content data manifest.json';accepted={str(Path(x['destination']).resolve()):x for x in read(provenance)['exported']};models={x['path']:x['sha256']for x in read(content)['files']if x['role']=='Published page content model'}
def quartet_from_model(mp):
 mp=Path(mp);tp=R/('ALD/'+mp.relative_to(R).as_posix()[5:-5]+'.txt');entry=accepted[str(tp.resolve())];work=Path(entry['transcription_source']);png=[work.with_name(work.stem+suffix)for suffix in [' preview.png',' JuliaMono preview.png','.png',' JuliaMono.png']];png=[p for p in png if p.exists()];need(len(png)==1,'One exact preview '+str(mp));q={k:bind(p)for k,p in [('txt',work),('json',work.with_suffix('.json')),('notes',work.with_name(work.stem+' review notes.txt')),('preview',png[0])]};need(q['json']['sha256']==bind(mp)['sha256']==models[mp.relative_to(R).as_posix()],'Accepted current JSON '+str(mp));need(q['txt']['sha256']==bind(tp)['sha256']==entry['text_sha256'],'Accepted current TXT '+str(mp));return q
def feed(tag,artifact,page,quartet,source,cells,patches,notes='',links=(),config=None):
 counts[tag]+=1
 for q in quartet.values():sr.checked(q,B)
 sr.checked(source,B);need(Path(source['path']).suffix.lower()in ['.tif','.tiff'],'Original sourceTIFF')
 p=pages.setdefault(page,{'page':page,'prior_quartet':quartet,'source':source,'cells':{},'patches':{},'patch_order':[],'notes':[],'evidence':{},'components':[],'configs':[]})
 need(p['prior_quartet']==quartet and p['source']==source,'One current quartet/source per page '+page);p['components'].append(tag)
 for link in [evidence(artifact),*links]:
  if link:
   e=evidence(link);p['evidence'][e['path']]=e
 if notes and notes not in p['notes']:p['notes'].append(notes)
 if config is not None:p['configs'].append(config)
 for x in cells:
  need(len(x['before'])==len(x['after']),'Same-width TXT source edit')
  for offset,(a,z)in enumerate(zip(x['before'],x['after'])):
   if a==z:continue
   key=(x['row'],x['column']+offset);value={'row':key[0],'column':key[1],'before':a,'after':z};need(key not in p['cells']or p['cells'][key]==value,'Conflicting sourcecell '+page+str(key));p['cells'][key]=value
 for item in patches:
  x=normalize(item);pointer=x['pointer']
  if pointer in ['/transcription_sha256','/rendered_text_sha256','/review_notes_sha256','/preview_sha256']:
   filtered.append({'page':page,'component':tag,'patch':x,'reason':'Recomputed once from final combined derivative bytes'});continue
  if pointer in p['patches']:
   need(p['patches'][pointer]==x,'Conflicting exact JSON scope '+page+pointer);overlap.append({'page':page,'pointer':pointer,'kind':'identical duplicate','component':tag});continue
  for existing in p['patches']:need(not(pointer.startswith(existing+'/')or existing.startswith(pointer+'/')),'Parent/leaf JSON collision '+page+pointer+' '+existing)
  p['patches'][pointer]=x;p['patch_order'].append(pointer)

compact_paths=[
 (S/'Paired literal proposals v4/Paired TXT JSON proposals.json','literal48','a0d08597039a9ede69580fbe3f9337dae82425a78dfd78b54b1b1edb837a2590'),
 (B/'Compact ready paired proposals v3/Paired TXT JSON proposals.json','pin_site73','bc60502ba5ef01bb1f7c2ce7266d3643d6b90f81c91eb3263e6c8e0d147b889c'),
 (B/'Compact corroborated successor/Paired TXT JSON proposals.json','corroborated37','d3a0e2d041bb31359ecea4fa5a6f642fdd8c1171c50d525d9e99b1831cd60866')]
for path,tag,sha in compact_paths:
 need(bind(path)['sha256']==sha,'Frozen input '+tag);doc=read(path)
 for field in doc['proposals']:
  if tag=='corroborated37'and field['page']=='CT041':continue
  if field.get('ready_for_later_stage',True):facts.append({'component':tag,'page':field['page'],'node':field['node'],'field':field['field'],'before':field['before'],'after':field['after'],'case_id':field['case_id']})
 for p in doc['page_plans_for_later_staging']:
  if tag=='corroborated37'and p['page']=='CT041':
   superseded.append({'component':tag,'page':'CT041','prior_after':'D03','replacement_after':'D06','reason':'Latest direct human corrected reading at ledger revision81. Original frozen compact37 remains evidence, but its CT041 edits are not applied.'});continue
  fs=[x for x in doc['proposals']if x['page']==p['page']and x.get('ready_for_later_stage',True)];links=[x.get('source_crop',x.get('native_crop'))for x in fs];links=[x for x in links if x]
  note='\n'.join(str(x['case_id'])+': '+x['node']+' '+x['field']+' '+repr(x['before'])+' → '+repr(x['after']) for x in fs)
  feed(tag,path,p['page'],p['prior_quartet'],p['source'],p['cell_edits'],p['json_patches'],note,links)

placement=B/'Seven placement proposals/Exact seven placement proposals.json';need(bind(placement)['sha256']=='afca43003a296ccc7e4be3e9781f1ad27101ec3e1f96f7f1c253eed1b33e4c2c','Seven placement input')
for p in read(placement)['pages']:
 links=[c['native_crop']for c in p['cases']];source=p['cases'][0]['source'];feed('placement7',placement,p['page'],p['current_quartet'],source,p['cell_edits'],p['json_patches'],p['notes_append'],links,p.get('preview_config'))
 for c in p['cases']:facts.append({'component':'placement7','page':p['page'],'node':c['node'],'field':'function_and_anonymous_pin_context','case_id':c['case_id']})
wiring=B/'Paired proposals successor BH/Exact paired proposals.json';need(bind(wiring)['sha256']=='e0299b308bea6251b58093fe8a06bef9d67d62c43cd83902b97fe6c4c639eda2','Seven wiring input')
for p in read(wiring)['pages']:
 feed('wiring7',wiring,p['page'],p['current_working_quartet'],p['source'],p['cell_edits'],p['json_patches'],p['notes_append'],p['native_evidence']);facts.append({'component':'wiring7','page':p['page'],'node':None,'field':'source_wiring','case_id':p['page']+'-wiring'})

for path,tag,sha in [
 (B/'E pin human authority addendum/Exact paired proposals.json','E_human2','36e622f27688f345c0085d3777fecd04a0531dd67091da5d9e64b0589da773e6'),
 (B/'Human location answers addendum/Exact paired proposals.json','human_location4','6ea801696e4534cb0a0527604d39d9de954de87870ea550c4ab66bb13a81366c'),
 (B/'Additional exact physical-instance recoveries/Exact paired proposals.json','additional_instance5','11a8a4fe03730e49317bd6170725c97b2c02fcd3f5b08486f7cf230a33d9e751')]:
 need(bind(path)['sha256']==sha,'Frozen raw input '+tag)
 for c in read(path)['cases']:
  q=quartet_from_model(c['model']['path']);source=c['native_source'];links=[c['source_crop']]
  if c.get('human_ledger_snapshot'):links.append(c['human_ledger_snapshot'])
  if c.get('same_instance_native_witness'):links.append(c['same_instance_native_witness']['native_crop'])
  feed(tag,path,c['page'],q,source,c['text_edits'],c['json_patches'],c['case_id']+': '+c['node']+' '+c['field']+' '+repr(c['observed'])+' → '+repr(c['proposed']),links);facts.append({'component':tag,'page':c['page'],'node':c['node'],'field':c['field'],'before':c['observed'],'after':c['proposed'],'case_id':c['case_id']})

ku=B/'Independent unresolved cross-reference review/KU411 AU B4 context recovery proposal.json';kr=B/'Independent corroborated site review/Independent corroborated successor review.json';kd=read(ku);review=read(kr);need(review['passed']and review['separate_KU411']['context_recovery_accepted'],'Independent KU411 context accepted');need(review['KU411_proposal']==bind(ku),'KU411 exact reviewed input');q=quartet_from_model(kd['model']['path']);feed('KU411',ku,kd['page'],q,kd['source_TIFF'],review['separate_KU411']['required_paired_TXT_edits'],kd['json_patches'],kd['literal_observation']+'\n'+kd['proposed_recovery'],[bind(kr),kd['target_native_crop'],kd['full_group_native']['crop']]);facts.append({'component':'KU411','page':'KU411','node':'AU','field':'portion_and_location','before':'0500R4 / F-A3J6','after':'0500B4 / E-A3J6','case_id':'focused-117'})

# All final direct human answers are preserved in one immutable snapshot.
lp=S/'Manual source review answers.json';ledger=read(lp);sr.verify_ledger(ledger);need(ledger['revision']==81,'Expected complete corrected human ledger revision81');answers={e['question_id']:e for e in ledger['events']if e['kind']=='answer'};need(set(answers)==set(ledger['questions'])and len(answers)==39,'All39 human questions answered');need(answers['P0-CT041-AE-pin']['normalized']=='D06','Latest CT041 answer is D06');snapshot=O/'Human ledger revision81.json';snapshot.write_bytes(lp.read_bytes());evidence(snapshot)
H=B/'freeze_focused_findings_v3.py';tree=ast.parse(H.read_text());ns={'Path':Path,'json':json,'hashlib':hashlib,'re':re,'excluded_keys':{'evidence','notes','note','history','historical','provenance','acceptance','source_evidence','native_socket_discrepancy','socket_listing_discrepancy'}};names={'read','bind','historical','escape','walk','physical','plan'};exec(compile(ast.Module(body=[x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name in names],type_ignores=[]),str(H),'exec'),ns);frozen=B/'Frozen pin and site findings v3/Findings.json';by={c['case_id']:c for c in read(frozen)['cases']}
for cid,qid in [('site-030','P0-MC068-AA-location'),('site-015','P0-RE171-AG-location'),('focused-176','P0-RF101-AC-location'),('focused-210','P0-RW341-AC-location'),('focused-165','P0-PX201-AS-location'),('focused-018','P0-CT041-AE-pin')]:
 c=deepcopy(by[cid]);new=answers[qid]['normalized'];p=ns['plan'](c,new);need(p['ready'],'Final human exact plan '+qid);feed('final_human6',snapshot,c['page'],quartet_from_model(c['model']['path']),c['native_source'],p['text_edits'],p['json_patches'],qid+': '+repr(c['observed'])+' → '+repr(new),[c['source_crop'],bind(frozen)]);facts.append({'component':'final_human6','page':c['page'],'node':c['node'],'field':c['field'],'before':c['observed'],'after':new,'case_id':qid})


# Root-owned 0479 circuit questions were outside literal48. Bind their exact
# recorded answers and native evidence explicitly instead of assuming membership.
for qid,ni in [('P0-XM009-AA-circuit',0),('P0-RR001-CA-circuit',6)]:
 question=ledger['questions'][qid];context=question['context'];pg=context['page'];matches=list((R/'json').rglob(pg+' *.json'));need(len(matches)==1,'One human target model '+qid);mp=matches[0];model=read(mp);node=model['nodes'][ni];need(node['id']==context['node']and node['unit']==context['current'],'Human exact circuit target '+qid);after=answers[qid]['normalized'];q=quartet_from_model(mp);lines=Path(q['txt']['path']).read_text('utf-8-sig').splitlines();row=node.get('absolute_row',node['row'])+3;column=node.get('absolute_column',node['column'])+1;before=node['unit'];need(lines[row][column:column+len(before)]==before,'Human circuit exact TXT field '+qid);cells=[{'row':row,'column':column+i,'before':a,'after':z}for i,(a,z)in enumerate(zip(before,after))if a!=z];need(len(before)==len(after),'Same-width human circuit');patches=[{'op':'replace','pointer':'/nodes/'+str(ni)+'/unit','before':before,'after':after}];need(not any(k in node for k in ['circuit_identifier','unit_code','unit_literal','printed_unit','circuit']),'No omitted circuit aliases '+qid);sources=[e for e in question['evidence']if Path(e['path']).suffix.lower()in['.tif','.tiff']];need(len(sources)==1,'One human native source '+qid);links=[e for e in question['evidence']if Path(e['path']).suffix.lower()not in['.tif','.tiff']];feed('root_human_circuit2',snapshot,pg,q,sources[0],cells,patches,qid+': '+repr(before)+' → '+repr(after),links);facts.append({'component':'root_human_circuit2','page':pg,'node':node['id'],'field':'unit','before':before,'after':after,'case_id':qid})

# Narrow retained-literal addendum is inserted here only after its source-bound
# exact proposal has been independently prepared and reviewed.
annotation=B/'Five retained annotation corrections/Exact four-page control proposals.json';need(bind(annotation)['sha256']=='42bfbc1d7308e0a61f6079db895c0caa2f1adb3c348b9e8d34fc9885bde680b0','Frozen four-page annotation input');annotation_doc=read(annotation);need(annotation_doc['passed_preparation'],'Annotation preparation passed')
for p in annotation_doc['page_plans_for_later_staging']:
 matching=[c for c in annotation_doc['proposals']if c['page']==p['page']];links=[]
 for c in matching:links.extend([c['native_crop'],*c.get('additional_native_crops',[])])
 feed('literal_control4',annotation,p['page'],p['prior_quartet'],p['source'],p['cell_edits'],p['json_patches'],p.get('notes_append','Literal standalone control annotations retained separately from anonymous physical contacts.'),links)
 for c in matching:facts.append({'component':'literal_control4','page':c['page'],'node':c['node'],'field':c['field'],'case_id':c['case_id']})

receipts=[S/'Paired literal proposals v4/Independent literal proposal review v4.json',B/'Independent seven placement review/Independent seven placement review.json',S/'Independent wiring proposal review/Independent seven-page successor review.json',S/'Independent wiring proposal review/Exact topology scope addendum.json',B/'Independent pin site review/Independent pin site proposal review.json',kr,B/'Independent additional physical-instance review/Independent five exact-instance review.json']
for p in receipts:evidence(p)
for p in [B/'Consolidated source correction preparation v3/stage/manifest.json', B/'Independent consolidated stage review ledger81/Independent final source stage acceptance.json', B/'Independent consolidated stage review ledger81/Human completeness diagnostic.json']:evidence(p)
for p in [provenance,content,fontprobe,H,frozen,lp,Path(__file__),R/'tools/reviews/source_review.py',R/'tools/reviews/source_review_guards.py']:evidence(p)
final_models={};configs={tuple(x['dimensions']):x['configuration']for x in read(fontprobe)['configurations']};records=[];preview_checks=[];patch_authority=[]
for index,(pg,p)in enumerate(sorted(pages.items())):
 q=p['prior_quartet'];raw=Path(q['txt']['path']).read_bytes();model=read(q['json']['path']);lines=raw.decode('utf-8-sig').splitlines();grid={'width':max(map(len,lines)),'height':len(lines)};dimensions=Image.open(q['preview']['path']).size;need(dimensions in configs,'Known exact preview dimensions '+pg);config=deepcopy(configs[dimensions]);need(all(x==config for x in p['configs']),'Provided preview configurations agree '+pg);need(sr.same_pixels(sr.render_preview(raw,config,B),Path(q['preview']['path']).read_bytes()),'Accepted preview preimage reproduces '+pg);preview_checks.append({'page':pg,'dimensions':list(dimensions),'configuration':config,'passed':True});cells=[p['cells'][k]for k in sorted(p['cells'])];patches=[p['patches'][k]for k in p['patch_order']];aftertxt=sr.patch_text(raw,cells,grid)
 notes='SOURCE VISUAL REVIEW 2026-10-17\n'+ '\n\n'.join(p['notes'])
 if pg=='CT041':notes+='\n\nOn closer inspection the human corrected the earlier D03 response to D06 (ledger revision81). K and existing common-wire geometry remain. The prior private D03/power-contact concern is superseded by this corrected glyph reading; historical responses and observations are retained.'
 if pg=='PX201':notes+='\n\nHuman confirmed E-D2G7 for AS, preserving G7. Socket-listing F7 remains a source cross-reference conflict; G7 is not normalized to F7.'
 if pg=='RW341':notes+='\n\nHuman confirmed E-C2D4 for AC. Source portion 0515A1 remains unchanged; socket-listing RW341 B1 is retained as a separate cross-reference concern.'
 finalhashes={'transcription_sha256':sr.digest(aftertxt),'rendered_text_sha256':sr.digest(aftertxt),'review_notes_sha256':sr.digest(sr.append_note(Path(q['notes']['path']).read_bytes(),notes))}
 if 'preview_sha256'in model:finalhashes['preview_sha256']=sr.digest(sr.render_preview(aftertxt,config,B))
 for key,value in finalhashes.items():
  if key in model and model[key]!=value:patches.append({'op':'replace','pointer':'/'+key,'before':model[key],'after':value})
 aftermodel=sr.patch_model(model,patches);final_models[pg]=aftermodel;page={'page':pg,'model_schema':'ald-page-nodes-v1','source':p['source'],'prior_quartet':q,'grid':grid,'cell_edits':cells,'json_patches':patches,'notes_append':notes,'preview_config':config,'evidence':list(p['evidence'].values())};issues=sr.validate_pin_edits(model,aftermodel,page);need(not issues,'Combined pin mirror guard '+pg+' '+json.dumps(issues,ensure_ascii=False));records.append(page)
 for role,b in q.items():sr.checked(b,B)
 if index%10==0:print('Validated current source and preview',index+1,'/',len(pages),pg,flush=True)


# Verify every latest recorded human field against the actual fully composed
# candidate, independently of component membership. A bad-locator question is
# retained as superseded, with the corrected-crop question owning the one field.
human_coverage=[];active_fields={};superseded_questions={q['supersedes_locator_for']:qid for qid,q in ledger['questions'].items()if q.get('supersedes_locator_for')}
for qid,question in ledger['questions'].items():
 c=question['context'];pg=c['page'];mp=list((R/'json').rglob(pg+' *.json'));need(len(mp)==1,'Human complete target model '+qid);before=read(mp[0]);after=final_models.get(pg,before);matches=[i for i,n in enumerate(before['nodes'])if n.get('id')==c['node']];need(len(matches)==1,'Human exact node '+qid);ni=matches[0];on=before['nodes'][ni];field=c.get('field');pointer=c.get('field_pointer')
 if not pointer:
  if field in ['unit','circuit identifier','circuit_identifier']:pointer='/nodes/'+str(ni)+'/unit'
  elif field in ['function','location']:pointer='/nodes/'+str(ni)+'/'+field
  else:
   pins=[i for i,p in enumerate(on.get('pins',[]))if p.get('pin')==c.get('current',c.get('observed'))];need(len(pins)==1,'Human unique original physical pin '+qid);pointer='/nodes/'+str(ni)+'/pins/'+str(pins[0])+'/pin'
 actual=after
 for key in pointer.strip('/').split('/'):actual=actual[int(key)]if isinstance(actual,list)else actual[key]
 expected=answers[qid]['normalized'];need(actual==expected,'Latest human answer not composed '+qid+' '+repr(actual)+' != '+repr(expected));item={'question_id':qid,'page':pg,'node':c['node'],'pointer':pointer,'expected':expected,'candidate_value':actual,'model_preimage':bind(mp[0]),'response_id':answers[qid]['response_id'],'status':'verified_latest_human_answer'}
 if qid in superseded_questions:item.update(status='superseded_locator_retained',superseded_by=superseded_questions[qid])
 else:
  key=(pg,pointer);need(key not in active_fields,'Duplicate active human field '+qid);active_fields[key]=qid
 human_coverage.append(item)
need(len(human_coverage)==39 and len(active_fields)==38,'Complete39 questions/38unique active human fields');put(O/'Human semantic coverage verification.json',{'schema':'consolidated-human-answer-semantic-coverage-v1','passed':True,'ledger':bind(snapshot),'questions':39,'unique_active_fields':38,'superseded_locator_questions':superseded_questions,'rows':human_coverage});evidence(O/'Human semantic coverage verification.json')

unique_facts={json.dumps({k:f.get(k)for k in ['page','node','field','before','after']},sort_keys=True):f for f in facts};intent={'schema':'source-review-intent-v1','review_id':'remaining-source-visual-review-20261017-complete','target_root':str(ROOT/'ALD_Visual_Transcriptions'),'unresolved_questions':[],'evidence':list(inputs.values()),'pages':records};ip=O/'Intent.json';put(ip,intent)
receipt={'schema':'private-consolidated-source-correction-preparation-v1','passed':True,'source_writes':0,'staging_performed':False,'human_ledger':bind(snapshot),'human_questions':39,'answer_events':42,'input_component_counts':dict(counts),'source_facts_raw':len(facts),'deduplicated_source_facts':len(unique_facts),'facts':facts,'source_pages':len(records),'TXT_cells':sum(len(p['cell_edits'])for p in records),'JSON_operations':sum(len(p['json_patches'])for p in records),'identical_scope_deduplication':overlap,'superseded_selections':superseded,'filtered_intermediate_derivative_hashes':filtered,'preview_reproductions':preview_checks,'intent':bind(ip),'input_union':[bind(Path(p))for p in inputs],'parent_leaf_collisions':0,'all_current_quartets_unchanged':True};rp=O/'Preparation verification.json';put(rp,receipt);print(json.dumps({'preparation':bind(rp),'intent':bind(ip),'pages':len(records),'cells':receipt['TXT_cells'],'ops':receipt['JSON_operations'],'facts':receipt['deduplicated_source_facts']},indent=2),flush=True)
result=sr.create_stage(ip,O/'stage');put(O/'Staging verification.json',result);print(json.dumps({'stage_manifest':bind(O/'stage/manifest.json'),'verification':bind(O/'Staging verification.json'),'passed':result.get('passed')},indent=2),flush=True)

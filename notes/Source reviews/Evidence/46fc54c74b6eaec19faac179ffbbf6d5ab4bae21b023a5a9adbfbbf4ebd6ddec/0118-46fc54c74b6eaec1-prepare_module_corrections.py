"""Prepare exact reviewed module corrections privately; never publish."""
from pathlib import Path
from copy import deepcopy
import json,sys
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald';BASE=Path(__file__).parent
sys.path.insert(0,str(REPO/'tools/reviews'));import source_review as sr
from PIL import Image
def read(p):return sr.read_json(p)
def need(x,m):
 if not x:raise ValueError(m)
def at(d,p):
 for k in p.strip('/').split('/'):d=d[int(k)]if isinstance(d,list)else d[k]
 return d
def checked(b):return sr.checked(b,ROOT)[0]
def bind(p):return sr.binding(p)
evidence={};native_checks=[]
def add(p):
 p=Path(p);evidence[str(p.resolve())]=bind(p)
def native(proof):
 source=checked(proof['source']);crop=proof['native_crop'];p=checked(crop);box=crop.get('box',crop.get('bounds'));need(box is not None,'Missing native bounds')
 with Image.open(source)as im,Image.open(p)as tile:need(im.convert('RGB').crop(box).tobytes()==tile.convert('RGB').tobytes(),'Crop does not equal source '+str(p))
 add(p);native_checks.append({'source':proof['source'],'native_crop':crop,'pixels_equal':True})
def case_base(page,node_pointer,model,text,source,crop,cid):
 return {'case_id':cid,'page':page,'node_pointer':node_pointer,'model':model,'text':text,'source':source,'native_crop':crop,'status':'resolved_native_or_recorded_human','source_changes_applied':False}
def card_case(page,node_pointer,model,text,proof,cid,after,note):
 doc=read(checked(model));node=at(doc,node_pointer);old=node['printed_card_portion'];need(after[4:]==old[4:],'Portion unexpectedly changes');raw=checked(text).read_text('utf-8-sig').splitlines();row=node['row']+4;col=node['column']+1;need(raw[row][col:col+len(old)]==old,'Card field grid locator differs '+page)
 c=case_base(page,node_pointer,model,text,proof['source'],proof['native_crop'],cid);c.update({'json_patches':[{'op':'replace','pointer':node_pointer+'/card_type','before':node['card_type'],'after':after[:4]},{'op':'replace','pointer':node_pointer+'/printed_card_portion','before':old,'after':after}],'text_edits':[{'row':row,'column':col,'before':old,'after':after}],'note':note});native(proof);return c
def main():
 out=BASE/'Combined source corrections';need(not out.exists(),'Fresh preparation directory required')
 findings_path=BASE/'Malformed circuit review/Findings.json';physical_path=BASE/'Physical page questions and answers.json';conflicts_path=BASE/'Source conflict questions and answers.json';clear_path=BASE/'No listing review/Clear ALD repair proposals.json';native_path=BASE/'No listing review/Final native findings.json';register_path=BASE/'No listing review/ALD native/Native crop candidates.json'
 for p in [Path(__file__),findings_path,physical_path,conflicts_path,clear_path,native_path,register_path,BASE/'Malformed circuit review/Mechanical proposal verification.json']:add(p)
 physical=read(physical_path);answers={q['page']:q for q in physical['questions']};conflicts=read(conflicts_path);cases=[]
 for old in read(findings_path)['cases']:
  c=case_base(old['page'],old['node_pointer'],old['model_preimage'],old['text_preimage'],old['source'],old['proof']['target']['native_crop'],old['case_id']);c.update({'json_patches':deepcopy(old['json_patches']),'text_edits':deepcopy(old['text_edits']),'note':old['literal_notes']+' Reading basis: '+old['reading_basis']})
  if old['case_id']=='malformed-025':
   q=answers['XM013'];need(q.get('status',q.get('answer_status'))=='answered'and q['answer']=='U61AB','Missing literal XM013 answer');c['json_patches']=[{'op':'replace','pointer':c['node_pointer']+'/unit','before':old['old_unit'],'after':'U61AB'}];c['text_edits']=[{'row':12,'column':97,'before':old['old_unit'],'after':'U61AB'}];c['note']='Physical-page human answer, preserved literally in the bound response ledger: U61AB. Earlier uncertainty is resolved by this answer.'
  native(old['proof']['target'])
  witness=old['proof'].get('corroborating_native_witness')
  if witness:
   native(witness)
   for k in ['current_model','request_model_preimage']:
    if k in witness:checked(witness[k]);add(checked(witness[k]))
  cases.append(c)
 for old in read(clear_path)['cases']:
  c=deepcopy(old);c.update({'case_id':'native-card-'+old['page']+'-'+old['node'],'status':'resolved_native_and_exact_A1_corroboration','note':'Native target and exact-site A1 card header corroborate '+old['card_type_after']+'. Any earlier disagreement observation is retained as history, superseded by this review.'});native({'source':old['source'],'native_crop':old['native_crop']});native(old['A1_native_evidence']);cases.append(c)
 q=answers['KS021'];need(q['answer']=='0518D1'and q.get('status',q.get('answer_status'))=='answered','Missing KS021 answer');reg=next(c for c in read(register_path)['cases']if c['case_id']=='module-0513-001');model=q['model'];textp=REPO/'ALD'/Path(model['path']).relative_to(REPO/'json').with_suffix('.txt');cases.append(card_case('KS021',q['node_pointer'],model,bind(textp),reg,'human-card-KS021-AW','0518D1','Physical-page human answer: 0518D1, preserved literally in the bound response ledger.'))
 native_findings=read(native_path)['findings']
 for q in conflicts['questions']:
  need(q.get('status',q.get('answer_status'))=='answered','Conflict answer missing');old=q['diagram_reading'];entry=next(c for c in native_findings if c['card_type']==old[:4]);rep=entry['representative_ALD'];textp=REPO/rep['source_text'];modelp=REPO/'json'/textp.relative_to(REPO/'ALD').with_suffix('.json');proof=next(x for x in entry['ALD_native_evidence']if x['node_pointer']==rep['node_pointer']);cases.append(card_case(q['page'],rep['node_pointer'],bind(modelp),bind(textp),proof,q['id'],q['normalized_card_portion'],'Human physical-page answer '+repr(q['answer'])+' determines '+q['normalized_card_portion']+'. Prior documented ALD/listing disagreement is preserved as historical evidence and is resolved by this answer.'))
 need(len(cases)==34,'Expected 34 blocks');checks=0
 for c in cases:
  m=read(checked(c['model']));txt=checked(c['text']).read_bytes();rows=txt.decode('utf-8-sig').splitlines()
  for p in c['json_patches']:need(at(m,p['pointer'])==p['before'],'Stale JSON before '+c['case_id']);checks+=1
  for e in c['text_edits']:need(rows[e['row']][e['column']:e['column']+len(e['before'])]==e['before'],'Stale TXT before '+c['case_id']);need(len(e['before'])==len(e['after']),'Width differs');checks+=2
  checked(c['source']);checks+=1
 out.mkdir();plan={'schema':'exact-module-circuit-and-card-corrections-v1','source_changes_applied':False,'cases':cases,'documentary_evidence':list(evidence.values()),'human_answers_are_literal':True,'historical_conflict_observations_preserved':True,'derived_catalogues':'Rebuild after accepted source publication/import; no direct derived catalogue edits.'};sr.atomic_write(out/'Exact correction plan.json',sr.encode(plan));sr.atomic_write(out/'Preparation native and preimage checks.json',sr.encode({'passed':True,'checks':checks,'cases':34,'pages':len({c['page']for c in cases}),'native_checks':native_checks,'source_changes_applied':False,'plan':bind(out/'Exact correction plan.json')}))
 print(json.dumps({'plan':bind(out/'Exact correction plan.json'),'cases':34,'pages':len({c['page']for c in cases}),'checks':checks,'native_checks':len(native_checks)},indent=2))
if __name__=='__main__':main()

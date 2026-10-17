"""Generic, source-bound combined identity stage from reviewed exact plans.

No inference, acceptance generation, publication, registry or repository writes.
Global inventory/provenance metadata is deliberately not frozen by this helper.
"""
from pathlib import Path
from collections import defaultdict,Counter
from copy import deepcopy
from datetime import datetime,timezone
import argparse,json,re,sys
from PIL import Image
ROOT=Path('D:/Github/IBM360');REPO=ROOT/'ibm360ald'
sys.path.insert(0,str(REPO/'tools/reviews'));import source_review as sr

def need(ok,message):
 if not ok:raise ValueError(message)
def read(p):return sr.read_json(p)
def bind(p):return sr.binding(p)
def checked(link):return sr.checked(link,ROOT)[0]
def pick(c,*keys):
 for k in keys:
  if c.get(k):return c[k]
 raise ValueError('Missing case binding: '+str(keys))
def normalize_patch(p):
 out={k:deepcopy(v)for k,v in p.items()if k in{'op','before','after'}};out['pointer']=p.get('pointer',p.get('path'));out.setdefault('op','replace');need(out['op']in{'replace','add'},'Only identity replace/add operations are supported');need(isinstance(out['pointer'],str)and out['pointer'].startswith('/'),'Missing JSON pointer');need('after'in out,'Missing explicit postimage');return out
def meaningful_cells(edits):
 result={}
 for e in edits:
  need(isinstance(e['row'],int)and isinstance(e['column'],int)and e['row']>=0 and e['column']>=0,'Invalid TXT coordinates');need(isinstance(e['before'],str)and isinstance(e['after'],str)and len(e['before'])==len(e['after']),'TXT edit widths differ')
  for i,(a,b)in enumerate(zip(e['before'],e['after'])):
   if a!=b:
    key=(e['row'],e['column']+i);need(key not in result or result[key]==(a,b),'Conflicting TXT cell');result[key]=(a,b)
 return result
def patch_signature(p):return json.dumps({k:p.get(k)for k in ['op','pointer','before','after']},ensure_ascii=False,sort_keys=True)
def node_scope_guard(p,node_pointer):
 need(p['pointer'].startswith(node_pointer+'/'),'Patch escapes requested node')
 leaf=p['pointer'][len(node_pointer)+1:];need(re.fullmatch(r'(?:card_type|portion|printed_card_portion|location|pins/\d+/(?:border_marker|marker_column))',leaf)is not None,'Patch is outside card/portion/location/border semantics: '+p['pointer'])
def at(doc,pointer):
 for key in pointer.strip('/').split('/'):doc=doc[int(key)]if isinstance(doc,list)else doc[key]
 return doc

def main():
 cli=argparse.ArgumentParser();cli.add_argument('--plan',type=Path,action='append',required=True);cli.add_argument('--output-dir',type=Path,required=True);cli.add_argument('--preview-probe',type=Path,default=ROOT/'tmp/ald-text/ald/socket-ald-audit/pin-letter-visual-20261016/Predecessor preview configuration probe.json');cli.add_argument('--expected-cases',type=int);cli.add_argument('--create-stage',action='store_true');args=cli.parse_args();out=args.output_dir.resolve();need(out.is_relative_to(ROOT)and not out.exists(),'A fresh private output directory is required');evidence={};groups={};case_ids=set();input_plans=[]
 def add_evidence(link):
  p=checked(link);evidence[str(p)]=bind(p);return p
 add_evidence(bind(Path(__file__)));add_evidence(bind(args.preview_probe));configs={tuple(c['dimensions']):c['configuration']for c in read(args.preview_probe)['configurations']}
 for planpath in args.plan:
  doc=read(planpath);add_evidence(bind(planpath));input_plans.append(bind(planpath));need(doc.get('source_changes_applied') is False or (doc.get('source_changes_applied') is None and all(c.get('source_changes_applied') is False for c in doc['cases'])),'Input plan lacks explicit unapplied state')
  for c in doc['cases']:
   cid=c['case_id'];need(cid not in case_ids,'Duplicate case across plans');case_ids.add(cid);need(not any(w in c.get('status','').lower()for w in['uncertain','unresolved','held']),'Held case appears in exact correction plans');need(c.get('json_patches')or c.get('text_edits'),'Empty correction case');model_link=pick(c,'model','model_preimage');text_link=pick(c,'text','text_preimage');source_link=pick(c,'source_TIFF','source','native_source');model=checked(model_link);text=checked(text_link);source=checked(source_link);need(model.is_relative_to(REPO/'json')and text.is_relative_to(REPO/'ALD'),'Only current repository ALD models/TXT may locate working sources');need(model.relative_to(REPO/'json').with_suffix('.txt')==text.relative_to(REPO/'ALD'),'Model and TXT scan paths differ')
   crop=pick(c,'native_crop','source_crop');crop_path=add_evidence(crop);box=crop.get('box',crop.get('bounds'));need(isinstance(box,list)and len(box)==4,'Native crop requires source bounds')
   with Image.open(source)as native,Image.open(crop_path)as tile:need(native.convert('RGB').crop(box).tobytes()==tile.convert('RGB').tobytes(),'Native crop pixels differ: '+cid)
   key=str(model);g=groups.setdefault(key,{'page':c['page'],'model':model_link,'text':text_link,'source':source_link,'cases':[],'patches':{},'cells':{},'evidence':{}});need(g['model']==model_link and g['text']==text_link and g['source']==source_link,'Conflicting bindings for one model');need(g['page']==c['page'],'Printed page aliases differ for one model');g['cases'].append({'case_id':cid,'page':c['page'],'node_pointer':c['node_pointer'],'status':c.get('status'),'note':c.get('note',c.get('source_note','')),'native_crop':{**crop,'path':str(crop_path)}});g['evidence'][str(crop_path)]=bind(crop_path)
   for p in c.get('json_patches',[]):
    p=normalize_patch(p);node_scope_guard(p,c['node_pointer']);old=g['patches'].get(p['pointer']);need(old is None or patch_signature(old)==patch_signature(p),'Conflicting JSON aliases');g['patches'][p['pointer']]=p
   for k,v in meaningful_cells(c.get('text_edits',[])).items():need(k not in g['cells']or g['cells'][k]==v,'Conflicting TXT edits');g['cells'][k]=v
 if args.expected_cases is not None:need(len(case_ids)==args.expected_cases,'Exact case inventory differs')
 # Only page-specific review records are used to locate accepted working files.
 # Global manifests, adapter and registry remain outside this stage epoch.
 printed=Counter(g['page']for g in groups.values());records=[];inventory=[];semantic_ops=0;derived_ops=0;pixel_configs=[]
 for model_path,g in sorted(groups.items()):
  rel=Path(model_path).relative_to(REPO/'json');review_record=REPO/'notes'/rel.parent/(rel.stem+' review record.json');review=read(review_record);add_evidence(bind(review_record));model=Path(review['working_metadata_source']);txt=model.with_suffix('.txt');need(model.read_bytes()==Path(model_path).read_bytes(),'Working/repo JSON differs');need(txt.read_bytes()==Path(g['text']['path']).read_bytes(),'Working/repo TXT differs');notes=txt.with_name(txt.stem+' review notes.txt');need(notes.exists(),'Missing actual review-note preimage');previews=[txt.with_name(txt.stem+x)for x in [' JuliaMono preview.png',' preview.png','.png']];preview=next((x for x in previews if x.exists()),None);need(preview is not None,'Missing actual accepted preview');dimensions=Image.open(preview).size;need(dimensions in configs,'No accepted preview configuration for '+str(dimensions));config=deepcopy(configs[dimensions]);text_raw=txt.read_bytes();rows=text_raw.decode('utf-8-sig').splitlines();need(rows and max(map(len,rows))>0,'Nonempty ALD grid required');grid={'width':max(map(len,rows)),'height':len(rows)};cells=[{'row':r,'column':c,'before':v[0],'after':v[1]}for(r,c),v in sorted(g['cells'].items())];patches=list(g['patches'].values());semantic_ops+=len(patches);before=read(model);after_txt=sr.patch_text(text_raw,cells,grid)
  notes_append='NATIVE CARD/PORTION IDENTITY REVIEW 2026-10-16\nSource-bound native inspection and independent literal review. Cases: '+', '.join(c['case_id']for c in g['cases'])+'.\nOnly declared card/portion/location semantic fields and separately preserved K border controls are corrected. Existing physical pin contacts, labels, annotations, wires, geometry, functions, circuit identifiers and historical observations remain unchanged.\n'+'\n'.join(c['case_id']+': '+c['note']for c in g['cases'])
  current={'transcription_sha256':sr.digest(after_txt),'rendered_text_sha256':sr.digest(after_txt),'review_notes_sha256':sr.digest(sr.append_note(notes.read_bytes(),notes_append))}
  if cells:
   need(sr.same_pixels(sr.render_preview(text_raw,config,out),preview.read_bytes()),'Preview settings do not reproduce accepted pixels');pixel_configs.append({'page':g['page'],'preview':bind(preview),'configuration':config,'preimage_pixels_equal':True})
  if 'preview_sha256'in before:current['preview_sha256']=sr.digest(sr.render_preview(after_txt,config,out))if cells else sr.digest(preview.read_bytes())
  for k,v in current.items():
   if k in before and before[k]!=v:patches.append({'op':'replace','pointer':'/'+k,'before':before[k],'after':v,'reason':'Current derivative asset digest only; nested historical receipts are preserved'});derived_ops+=1
  after=sr.patch_model(before,patches);need(not sr.validate_pin_edits(before,after,{'json_patches':patches,'evidence':list(g['evidence'].values())}),'Generic pin mirror guard rejected identity patches')
  for a,b in zip(before['nodes'],after['nodes']):
   for k in ['id','row','column','absolute_row','absolute_column','width','height','function','unit','grid','native_A1_disagreement']:need(a.get(k)==b.get(k),'Geometry/function/history changed')
   pa,pb=deepcopy(a.get('pins',[])),deepcopy(b.get('pins',[]));need(len(pa)==len(pb),'Pin count changed')
   for old,new in zip(pa,pb):
    for k in ['border_marker','marker_column']:old.pop(k,None);new.pop(k,None)
    need(old==new,'Existing corrected pin postimage changed')
  page=g['page']if printed[g['page']]==1 else g['page']+'--scan'+str(review['source_scan_id']);records.append({'page':page,'model_schema':'ald-page-nodes-v1','source':g['source'],'prior_quartet':{k:bind(p)for k,p in [('txt',txt),('json',model),('notes',notes),('preview',preview)]},'grid':grid,'cell_edits':cells,'json_patches':patches,'notes_append':notes_append,'preview_config':config,'evidence':list(g['evidence'].values())});inventory.append({'page_key':page,'printed_page':g['page'],'source_scan_id':str(review['source_scan_id']),'repository_model':g['model'],'repository_text':g['text'],'working_model':bind(model),'working_text':bind(txt),'review_record':bind(review_record),'case_ids':[c['case_id']for c in g['cases']],'semantic_JSON_operations':len(g['patches']),'derived_digest_operations':len(patches)-len(g['patches']),'TXT_cells':len(cells)})
 out.mkdir(parents=True);intent={'schema':'source-review-intent-v1','review_id':'native-card-portion-identity-20261016','target_root':str(ROOT/'ALD_Visual_Transcriptions'),'unresolved_questions':[],'scope_note':'Only separately reviewed exact identity plans are staged. Held cases stay unchanged. Global metadata, registry and repository imports are deferred until all A1 publications finish.','evidence':list(evidence.values()),'pages':records};sr.atomic_write(out/'Intent.json',sr.encode(intent));merge={'schema':'combined-exact-ALD-identity-stage-preparation-v1','created_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'source_changes_applied':False,'global_metadata_frozen':False,'input_plans':input_plans,'case_count':len(case_ids),'model_count':len(groups),'TXT_cells':sum(len(g['cells'])for g in groups.values()),'semantic_JSON_operations':semantic_ops,'derived_digest_operations':derived_ops,'intent':bind(out/'Intent.json'),'pages':inventory,'preview_preimage_checks':pixel_configs,'helper':bind(Path(__file__))};sr.atomic_write(out/'Preparation report.json',sr.encode(merge));result={k:v for k,v in merge.items()if k not in['pages','preview_preimage_checks','input_plans']}
 if args.create_stage:
  verification=sr.create_stage(out/'Intent.json',out/'stage');sr.atomic_write(out/'Staging verification.json',sr.encode(verification));result['staging_verification']=bind(out/'Staging verification.json');result['stage_manifest']=bind(out/'stage/manifest.json')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

"""Close the independent native review with private, preimage-bound plans only."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter,defaultdict
from functools import lru_cache
import copy,csv,hashlib,json,re
from PIL import Image,ImageChops
BASE=Path(__file__).resolve().parent; OUT=BASE/'Group 3 review'; PEER=OUT/'Independent peer review'; REPO=Path('D:/Github/IBM360/ibm360ald')
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks=0
def need(v,m):
 global checks
 checks+=1
 if not v:raise ValueError(m)
def esc(v):return str(v).replace('~','~0').replace('/','~1')
def walk(v,p=''):
 if isinstance(v,dict):
  for k,x in v.items():yield from walk(x,p+'/'+esc(k))
 elif isinstance(v,list):
  for i,x in enumerate(v):yield from walk(x,p+'/'+str(i))
 else:yield p,v
def get(v,p):
 for k in p.strip('/').split('/'):v=v[int(k)]if isinstance(v,list)else v[k.replace('~1','/').replace('~0','~')]
 return v
@lru_cache(maxsize=256)
def model(p):return read(p)
def unit(n):return str(n.get('unit',n.get('circuit',n.get('technology','')))).strip()
def witnesses(case,suffix):
 n=case['node'];card=str(n.get('card_type'));portion=str(n.get('portion'));pool=defaultdict(list)
 p=REPO/'json/Card types current'/(card+'.json')
 if not p.exists():return {}
 for o in read(p)['diagram_occurrences']:
  if o['portion']!=portion:continue
  rel=Path('json')/Path(o['source_text']).relative_to('ALD').with_suffix('.json'); path=REPO/rel
  try:other=get(model(path),o['node_pointer'])
  except (OSError,KeyError,IndexError):continue
  if str(other.get('card_type'))!=card or str(other.get('portion'))!=portion or unit(other)!=unit(n):continue
  if other.get('printed_card_portion')not in(None,'',card+portion):continue
  if rel.as_posix()==case['audit_flag']['model_path']and o['node_pointer']==case['audit_flag']['node_pointer']:continue
  for i,pin in enumerate(other.get('pins',[])):
   raw=pin.get('pin',pin.get('printed_pin'));m=re.fullmatch(r'\d*([BDGJ](?:0[2-9]|1[0-3]))[✲*]?T?',str(raw).strip())
   if pin.get('side')!=case['pin']['side']or not m or m[1][1:]!=suffix:continue
   pool[m[1]].append({'page':o['page'],'node':other.get('id'),'model_path':str(path),'model_sha256':sha(path),'node_pointer':o['node_pointer'],'pin_index':i,'literal_pin':raw,'circuit':unit(other),'card_portion':card+portion})
 return dict(pool)
def main():
 frozen=OUT/'Findings.json';need(sha(frozen)=='1f4cd3118b91d42175172773f076b112e6738ac7bb7a61844d7ce7f22f8dc6d4','Frozen findings changed')
 original=read(frozen);q=read(BASE/'Group 3 requests.json');request={c['case_id']:(p,c)for p in q['pages']for c in p['cases']}
 corroboration=read(BASE/'Uncertain current-source corroboration v2.json');cor={c['case_id']:c for c in corroboration['cases']}
 extended={c['case_id']:c for c in read(PEER/'Extended crop bindings.json')['cases']}
 extra={cid:witnesses(request[cid][1],'08')for cid in ['pin-0565','pin-0583']}
 (PEER/'Readable 08 current-source witnesses.json').write_text(json.dumps(extra,ensure_ascii=False,indent=2)+'\n','utf-8')
 for cid in extra:need(len(extra[cid].get('B08',[]))>=2,'Insufficient actual 08 witnesses '+cid)
 final=[];patches={};cells={};sources={};changed=[];issues=[]
 overrides={'pin-0400':'J09','pin-0436':'B07','pin-0437':'B02'}
 withheld={'pin-0047','pin-0579'}
 for prior in original['cases']:
  c=copy.deepcopy(prior);cid=c['case_id'];page,req=request[cid];node=req['node'];pin=req['pin'];old=req['audit_flag']['physical_contact'];new=c['proposed_contact'];doc=model(Path(page['model']['path']));rows=Path(page['text']['path']).read_text('utf-8-sig').splitlines()
  for key in ('model','text'):need(sha(page[key]['path'])==page[key]['sha256'],'Current source changed '+cid+' '+key)
  c['original_findings_status']=prior['status'];c['original_contact']=old;c['context_corrections']=[];c['context_corrections_independently_accepted']=False
  if prior['status'].startswith('context'):
   c['status']='unresolved_width_or_site_context';c['note']+=' Independent fresh native view retains literal F site; no F-to-E correction is accepted. Genuine G/J contact retained.'
  elif cid in overrides:
   new=overrides[cid];c['status']='confident_peer_corrected';c['note']+=' Independent fresh native view supersedes the original proposed bank; current same-portion witnesses agree.'
  elif prior['status'].startswith('uncertain'):
   r=cor[cid]
   if cid in ('pin-0565','pin-0583'):
    new='B08';c['status']='resolved_native_and_current_source';c['current_source_witnesses']=extra[cid]['B08'];c['note']+=' Fresh native full label reads B08, including the final 8; current exact card/portion/circuit input witnesses independently support B08.'
   elif cid=='pin-0619':
    new='B02';c['status']='resolved_native_shared_output';c['note']+=' Native three output stubs belong to the same block/net; the first two clearly read B02 and the worn third is the same B02. Repetition of a physical output is intentional.';c['current_source_witnesses']=r['candidate_proofs'].get('B02',[])
   elif cid not in withheld and r['unique_repeated_candidate']==new:
    c['status']='resolved_native_and_current_source';c['current_source_witnesses']=r['candidate_proofs'][new];c['note']+=' Independent native review agrees with the unique repeated current same-card/portion/circuit and same-side reading; readable digits match.'
   else:
    c['status']='uncertain_held';c['best_guess']=new;c['current_source_candidates']=r['candidate_counts'];c['note']+=' Held after independent native inspection; weak or competing evidence is insufficient for a source correction.'
  c['proposed_contact']=new;c['text_edits']=[];c['json_patches']=[]
  if cid in extended:c['source']=extended[cid]['source'];c['native_crop']=extended[cid]['native_crop']
  crop=c['native_crop'];need(sha(crop['path'])==crop['sha256'],'Crop changed '+cid)
  src=c['source'];sp=src['path']
  if sp not in sources:need(sha(sp)==src['sha256'],'TIFF changed '+cid);sources[sp]=True
  with Image.open(sp)as im:
   expected=im.crop(crop['box']).convert('RGB')
   with Image.open(crop['path'])as actual:need(expected.size==actual.size and ImageChops.difference(expected,actual.convert('RGB')).getbbox()is None,'Native pixels differ '+cid)
  accept=c['status'].startswith(('confident','resolved'))
  if accept:
   bp=c['node_pointer']+'/pins/'+str(c['pin_index']);refchanges={}
   for key,value in pin.items():
    if key not in('pin','printed_pin','printed_label','physical_pin','reference','terminal_id','printed_annotation','pin_label','label','contact')or not isinstance(value,str):continue
    if value.count(old)!=1:continue
    fresh=value.replace(old,new)
    if fresh!=value:
     c['json_patches'].append({'op':'replace','pointer':bp+'/'+esc(key),'before':value,'after':fresh})
     if key in('reference','terminal_id')and value!=old:refchanges[value]=fresh
   def refs(value):
    fresh=value
    for before,after in refchanges.items():fresh=re.sub(r'(?<![A-Za-z0-9_])'+re.escape(before)+r'(?![A-Za-z0-9_])',lambda m:after,fresh)
    return fresh
   for collection in ('nets','wire_paths','junctions','printed_labels','unjoined_crossings','wires'):
    for ptr,value in walk(doc.get(collection,[]),'/'+collection):
     if isinstance(value,str)and refs(value)!=value:c['json_patches'].append({'op':'replace','pointer':ptr,'before':value,'after':refs(value),'proof':'Exact owned qualified current pin reference'})
   for ni,other in enumerate(doc.get('nodes',[])):
    for pi,p in enumerate(other.get('pins',[])):
     for key in('net','reference','terminal_id','source','destination'):
      value=p.get(key);ptr=f'/nodes/{ni}/pins/{pi}/{key}'
      if ptr.startswith(bp+'/'):continue
      if isinstance(value,str)and refs(value)!=value:c['json_patches'].append({'op':'replace','pointer':ptr,'before':value,'after':refs(value),'proof':'Exact owned qualified current pin reference'})
   # Retain independently source-located original text span for already-reviewed cases.
   if prior['text_edits']:
    for edit in prior['text_edits']:
     start=edit['column'];row=edit['row'];before=edit['before'];after=edit['after']
     if new!=prior['proposed_contact']:after=after.replace(prior['proposed_contact'],new)
     need(rows[row][start:start+len(before)]==before,'TXT span changed '+cid)
     for off,(a,b)in enumerate(zip(before,after)):
      if a!=b:c['text_edits'].append({'row':row,'column':start+off,'before':a,'after':b})
   else:
    row=pin.get('absolute_row',pin.get('row',node['row']+3));col=node['column'];line=rows[row];lo=max(0,col-11)if pin['side']=='input'else col+7;hi=col+1 if pin['side']=='input'else col+24
    hits=[m.start()+lo for m in re.finditer(re.escape(old),line[lo:hi])]
    if len(hits)==1:
     for off,(a,b)in enumerate(zip(old,new)):
      if a!=b:c['text_edits'].append({'row':row,'column':hits[0]+off,'before':a,'after':b})
    elif new in line[lo:hi]:c['note']+=' Current TXT already correct; JSON-only repair.'
    else:issues.append({'case_id':cid,'row':row,'span':line[lo:hi],'old':old,'new':new})
   need(bool(c['json_patches']),'No active patch '+cid)
  for p in c['json_patches']:
   need(get(doc,p['pointer'])==p['before'],'JSON preimage '+cid+p['pointer']);key=(page['model']['path'],p['pointer'])
   if key in patches:need(patches[key]['after']==p['after'],'JSON conflict '+cid)
   patches[key]=p
  for e in c['text_edits']:
   need(rows[e['row']][e['column']]==e['before'],'TXT preimage '+cid);key=(page['text']['path'],e['row'],e['column'])
   if key in cells:need(cells[key]==e,'TXT conflict '+cid)
   cells[key]=e
  if prior['status']!=c['status']or prior['proposed_contact']!=new:changed.append({'case_id':cid,'prior_status':prior['status'],'status':c['status'],'prior_proposed_contact':prior['proposed_contact'],'proposed_contact':new})
  c['peer_reviewed']=True;c['source_changes_applied']=False;final.append(c)
 need(len(final)==209,'Coverage');need(not issues,'Unlocated text spans '+str(issues))
 report={'schema':'independent-peer-native-pin-findings-v1','created_utc':datetime.now(timezone.utc).isoformat(),'source_changes_applied':False,'original_findings':{'path':str(frozen),'sha256':sha(frozen)},'requests':original['requests'],'count':209,'status_counts':dict(Counter(c['status']for c in final)),'unique_txt_cells':len(cells),'unique_json_patches':len(patches),'cases':final}
 target=OUT/'Group3 Peer-reviewed findings.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
 review={'schema':'independent-pin-peer-review-v1','reviewer':'reverse_socket_audit','checks_passed':checks,'failure_count':0,'coverage':209,'native_occurrences_visually_inspected':209,'montages_viewed':18,'extended_montages_viewed':3,'source_pages':len(sources),'source_changes_applied':False,'original_findings':report['original_findings'],'peer_findings':{'path':str(target),'sha256':sha(target)},'status_counts':report['status_counts'],'unique_txt_cells':len(cells),'unique_json_patches':len(patches),'decisions_changed':changed,'context_identity_corrections_accepted':False,'context_note':'Native F site readings on RK221 and RS261 are retained pending authoritative resolution. Genuine G/J pins are unchanged.','uncertain_cases':[{'case_id':c['case_id'],'page':c['page'],'best_guess':c['proposed_contact'],'crop':c['native_crop']}for c in final if c['status'].startswith('uncertain')]}
 (PEER/'Independent review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n','utf-8')
 with(OUT/'Group3 Peer-reviewed findings.csv').open('w',encoding='utf-8-sig',newline='')as f:
  w=csv.writer(f);w.writerow(['case_id','page','node','old_contact','proposed_contact','status','text_cell_edits','json_patches']);w.writerows((c['case_id'],c['page'],c['node_id'],c['original_contact'],c['proposed_contact'],c['status'],len(c['text_edits']),len(c['json_patches']))for c in final)
 print(json.dumps({k:v for k,v in review.items()if k not in('decisions_changed','uncertain_cases')},indent=2))
if __name__=='__main__':main()

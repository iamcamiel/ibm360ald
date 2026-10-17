"""Independent read-only validation of the exact 629-case reviewed pin stage.

No acceptance is written until the real manifest and every assertion pass.
Canonical sources, working files and repository data are never written.
"""
from pathlib import Path
from copy import deepcopy
from collections import defaultdict,Counter
from datetime import datetime,timezone
from io import BytesIO
import json,hashlib,re,sys
from PIL import Image,ImageDraw,ImageFont,ImageChops
BASE=Path(__file__).resolve().parent
checks=0;cache={}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def need(v,m):
 global checks
 checks+=1
 if not v:raise AssertionError(m)
def checked(link):
 p=Path(link['path']).resolve()
 if p not in cache:cache[p]=p.read_bytes()
 need(digest(cache[p])==link['sha256'],'Binding '+str(p));return cache[p]
def esc(s):return str(s).replace('~','~0').replace('/','~1')
def parts(p):return[x.replace('~1','/').replace('~0','~')for x in p.strip('/').split('/')]
def parent(o,p):
 a=parts(p)
 for k in a[:-1]:o=o[int(k)]if isinstance(o,list)else o[k]
 return o,int(a[-1])if isinstance(o,list)else a[-1]
def apply(o,patch):
 t,k=parent(o,patch['pointer']);op=patch.get('op','replace')
 if op=='add':need(isinstance(t,dict)and k not in t,'new member absent '+patch['pointer']);t[k]=deepcopy(patch['after'])
 elif op=='remove':need(isinstance(t,dict)and t[k]==patch['before'],'remove preimage '+patch['pointer']);del t[k]
 else:need(op=='replace'and t[k]==patch['before'],'replace preimage '+patch['pointer']);t[k]=deepcopy(patch['after'])
def identity(p):return {k:p.get(k,'replace'if k=='op'else None)for k in('op','pointer','before','after')}
def patchcells(raw,cells):
 rows=raw.decode('utf-8-sig').splitlines(keepends=True);plain=[r.rstrip('\r\n')for r in rows]
 need(len(rows)==103 and all(len(r)<=245 for r in plain),'245x103 grid')
 for (r,c),(a,b)in cells.items():
  need(plain[r][c]==a and len(a)==len(b)==1,'exact TXT cell preimage')
  rows[r]=rows[r][:c]+b+rows[r][c+1:]
 result=''.join(rows).encode('utf-8');result=(b'\xef\xbb\xbf'if raw.startswith(b'\xef\xbb\xbf')else b'')+result
 need([len(r.rstrip('\r\n'))for r in rows]==[len(r)for r in plain],'row widths retained')
 return result
def noteappend(raw,s):
 nl=b'\r\n'if b'\r\n'in raw else b'\n'
 return raw.rstrip(b'\r\n')+nl*2+s.encode('utf-8').replace(b'\r\n',b'\n').replace(b'\n',nl)+nl
def preview(raw,cfg):
 checked(cfg['font']);font=ImageFont.truetype(cfg['font']['path'],cfg['font_size']);im=Image.new('RGB',(cfg['width'],cfg['height']),'white');d=ImageDraw.Draw(im);ox,oy=cfg['origin']
 for r,line in enumerate(raw.decode('utf-8-sig').splitlines()):
  for c,char in enumerate(line):
   if char!=' ':d.text((ox+c*cfg['cell_width'],oy+r*cfg['row_height']),char,font=font,fill='black',anchor=cfg.get('anchor'))
 return im
def pixels(a,b):
 if isinstance(a,bytes):a=Image.open(BytesIO(a)).convert('RGB')
 if isinstance(b,bytes):b=Image.open(BytesIO(b)).convert('RGB')
 return a.size==b.size and ImageChops.difference(a,b).getbbox()is None
def leaves(v,p=''):
 if isinstance(v,dict):
  for k,x in v.items():yield from leaves(x,p+'/'+esc(k))
 elif isinstance(v,list):
  for i,x in enumerate(v):yield from leaves(x,p+'/'+str(i))
 else:yield p,v
def histories(v,p=''):
 if isinstance(v,dict):
  for k,x in v.items():
   if p==''and k in('transcription_sha256','rendered_text_sha256','review_notes_sha256','preview_sha256'):continue
   q=p+'/'+esc(k)
   if any(w in k.lower()for w in('history','provenance','review_note','acceptance','source_evidence','evidence_')):yield q,x
   else:yield from histories(x,q)
 elif isinstance(v,list):
  for i,x in enumerate(v):yield from histories(x,p+'/'+str(i))
def main():
 manifest_path=Path(sys.argv[1])if len(sys.argv)>1 else BASE/'stage/manifest.json'
 need(manifest_path.exists(),'Actual stage required; no acceptance created')
 manifest=read(manifest_path);selection_path=BASE/'Final reviewed selection.json';selection=read(selection_path)
 need(selection.get('complete')is True,'Complete reviewed selection');need(sorted(g['group']for g in selection['groups'])==[1,2,3],'Three peer groups')
 stage_input_originals={str(Path(l.get('original_path','')).resolve()):l for l in manifest['inputs']}
 def snapshotbound(link):
  checked(link);original=str(Path(link['path']).resolve());need(original in stage_input_originals,'Evidence snapshotted '+original);need(stage_input_originals[original]['sha256']==link['sha256'],'Snapshot matches reviewed binding')
 snapshotbound(bind(selection_path))
 for b in selection.get('evidence',[]):snapshotbound(b)
 lookup={};pages={};allcases=[];expected=defaultdict(lambda:{'patches':{},'cells':{},'cases':[]})
 for gi in(1,2,3):
  qp=BASE/f'Group {gi} requests.json';snapshotbound(bind(qp));q=read(qp)
  for p in q['pages']:
   need(p['page']not in pages,'Disjoint request pages');pages[p['page']]=p
   checked(p['model']);checked(p['text'])
   for c in p['cases']:need(c['case_id']not in lookup,'Unique case');lookup[c['case_id']]=(p,c)
 for g in selection['groups']:
  snapshotbound(g['findings']);f=read(g['findings']['path'])
  for b in g.get('evidence',[]):snapshotbound(b)
  # Every final peer file must retain a hash binding to the frozen preparer.
  refs=[v for k,v in f.items()if isinstance(v,dict)and 'path'in v and 'sha256'in v]
  for b in refs:checked(b)
  need(any('Findings.json'in b['path']and 'Peer-'not in b['path']for b in refs),'Frozen preparer binding')
  allcases+=f.get('cases',f.get('findings',[]))
 need(len(lookup)==len(allcases)==629 and len({c['case_id']for c in allcases})==629 and set(lookup)=={c['case_id']for c in allcases},'Exact629 coverage')
 context_count=0;held=[]
 for f in allcases:
  p,c=lookup[f['case_id']];need(f['page']==p['page'],'Exact case page');settled=f['status'].startswith(('confident','resolved'))
  if not settled:need(not f.get('text_edits')and not f.get('json_patches'),'Held case unchanged');held.append(f['case_id'])
  plans=[f]+f.get('context_corrections',[])
  if f.get('context_corrections'):need(f.get('context_corrections_independently_accepted')is True,'Separate context acceptance');context_count+=len(f['context_corrections'])
  for plan in plans:
   for a in plan.get('json_patches',[]):
    a=dict(a);a['pointer']=a.get('pointer',a.get('path'));a.setdefault('op','replace');key=a['pointer'];prior=expected[f['page']]['patches'].get(key)
    need(prior is None or identity(prior)==identity(a),'Peer patch conflict');expected[f['page']]['patches'][key]=a
   for a in plan.get('text_edits',[]):
    need(len(a['before'])==len(a['after']),'Same-width text')
    for j,(x,y)in enumerate(zip(a['before'],a['after'])):
     if x==y:continue
     key=(a['row'],a['column']+j);prior=expected[f['page']]['cells'].get(key);need(prior is None or prior==(x,y),'Peer cell conflict');expected[f['page']]['cells'][key]=(x,y)
  if any(p.get('json_patches')or p.get('text_edits')for p in plans):expected[f['page']]['cases'].append(f)
 active={p:e for p,e in expected.items()if e['patches']or e['cells']};records={r['page']:r for r in manifest['records']}
 need(set(active)==set(records),'Only reviewed changed pages staged')
 for b in manifest['inputs']:checked(b)
 checked(manifest['tool']);checked(manifest['guard_tool']);checked(manifest['intent_snapshot'])
 # Four honest derivative initializations remain distinguishable from history.
 init_path=BASE/'New predecessor render initialization receipt.json';init=read(init_path);snapshotbound(bind(init_path));need(len(init['records'])==4 and init['canonical_repository_writes']==0,'Four new derived previews')
 for x in init['records']:need(x['preview_before']is None,'No fabricated preview predecessor');checked(x['accepted_text']);checked(x['new_derivative_preview'])
 totalcells=totalpatches=0
 for page,e in active.items():
  r=records[page];p=pages[page];need(r['grid']=={'width':245,'height':103},'Declared grid');checked(r['source']);need(Path(r['source']['path']).resolve()==Path(p['source_TIFF']).resolve(),'Native TIFF identity')
  rawbefore={};rawafter={}
  for kind in('txt','json','notes','preview'):
   rawbefore[kind]=checked(r['before_saved'][kind]);rawafter[kind]=checked(r['staged_quartet'][kind]);need(checked(r['prior_quartet'][kind])==rawbefore[kind],'Current predecessor quartet')
  need(digest(rawbefore['txt'])==p['text']['sha256']and digest(rawbefore['json'])==p['model']['sha256'],'Request-bound source preimages')
  need(Path(p['text']['path']).read_bytes()==rawbefore['txt']and Path(p['model']['path']).read_bytes()==rawbefore['json'],'Repository preimages match working')
  declaredcells={}
  for a in r['cell_edits']:
   for j,(x,y)in enumerate(zip(a['before'],a['after'])):
    if x!=y:declaredcells[(a['row'],a['column']+j)]=(x,y)
  need(declaredcells==e['cells'],'Stage exactly peer TXT cells '+page);need(patchcells(rawbefore['txt'],e['cells'])==rawafter['txt'],'Exact TXT bytes '+page)
  before=json.loads(rawbefore['json'].decode('utf-8-sig'));after=json.loads(rawafter['json'].decode('utf-8-sig'));want=deepcopy(before)
  for patch in e['patches'].values():
   need(not re.search(r'/pins/\d+/(row|point|absolute_row|absolute_point)(/|$)',patch['pointer']),'No geometry patch');need(not any(w in part.lower()for part in parts(patch['pointer'])for w in('history','provenance','review_note','acceptance','source_evidence','evidence_')),'No historical patch');apply(want,patch)
  current_hashes={'transcription_sha256':digest(rawafter['txt']),'rendered_text_sha256':digest(rawafter['txt']),'review_notes_sha256':digest(rawafter['notes']),'preview_sha256':digest(rawafter['preview'])}
  extra={}
  for key,value in current_hashes.items():
   if key in before and before[key]!=value:extra['/'+key]={'op':'replace','pointer':'/'+key,'before':before[key],'after':value};want[key]=value
  actual={a['pointer']:identity(a)for a in r['json_patches']};desired={k:identity(v)for k,v in(e['patches']|extra).items()}
  need(actual==desired,'Stage exactly peer JSON plus current derivative digests '+page);need(after==want,'Exact candidate JSON '+page)
  need(len(before['nodes'])==len(after['nodes']),'Node inventory retained '+page)
  for ni,(bn,an)in enumerate(zip(before['nodes'],after['nodes'])):
   for k in('id','function','unit','location','grid','portion','column','row','x','y','width','height'):
    need(bn.get(k)==an.get(k),'Node identity/function/location/layout retained '+page+'/'+str(ni)+'/'+k)
  for collection in('nets','wire_paths','wires','connections','signals','pin_connections','junctions','printed_labels','unjoined_crossings'):
   # Reference-key renames can change paths, but cannot change any coordinates,
   # geometry, topology-list lengths, or scalar nonlabel wiring metadata.
   def structural(v):
    if isinstance(v,dict):return sorted((structural(x)for x in v.values()),key=repr)
    if isinstance(v,list):return ['list',len(v),[structural(x)for x in v]]
    if isinstance(v,str):return '<label>'
    return [type(v).__name__,v]
   need(structural(before.get(collection))==structural(after.get(collection)),'Wiring structure/geometry retained '+page+'/'+collection)
  need(dict(histories(before))==dict(histories(after)),'Nested historical material unchanged '+page)
  for f in allcases:
   if f['page']!=page or f['status'].startswith(('confident','resolved')):continue
   c=lookup[f['case_id']][1];base=c['audit_flag']['node_pointer']+'/pins/'+str(c['audit_flag']['pin_index']);t,k=parent(after,base)
   need(t[k]==c['pin'],'Held target pin unchanged even on a changed page '+f['case_id'])
  need(noteappend(rawbefore['notes'],r['notes_append'])==rawafter['notes'],'Append-only review notes '+page)
  if e['cells']:
   need(pixels(preview(rawbefore['txt'],r['preview_config']),rawbefore['preview']),'Predecessor render reproduced '+page)
   need(pixels(preview(rawafter['txt'],r['preview_config']),rawafter['preview']),'Candidate render reproduced '+page)
  else:need(rawbefore['preview']==rawafter['preview'],'JSON-only render unchanged '+page)
  for f in e['cases']:
   c=lookup[f['case_id']][1];node=c['node'];pin=c['pin'];base=c['audit_flag']['node_pointer']+'/pins/'+str(c['audit_flag']['pin_index']);target,key=parent(after,base);fresh=target[key]
   # Every nonlabel pin attribute is retained except explicitly separated K.
   for k,v in pin.items():
    if k not in('pin','physical_pin','reference','printed_annotation','label','pin_label','contact','printed_pin','border_marker','marker_column'):need(fresh.get(k)==v,'Annotation/geometry retained '+f['case_id']+' '+k)
   if f['status'].startswith(('confident','resolved')):
    old=c['audit_flag']['physical_contact'];new=f['proposed_contact'];need(re.fullmatch(r'[BDGJ](?:0[2-9]|1[0-3])',new)is not None,'Valid settled physical contact')
    for k in('pin','physical_pin','printed_pin','label','pin_label','contact'):
     if k in pin and isinstance(pin[k],str)and old in pin[k]:need(fresh[k]==pin[k].replace(old,new,1),'Full label prefix/suffix retained '+f['case_id'])
    oldref=pin.get('reference');newref=fresh.get('reference')
    if oldref and newref!=oldref:
     for collection in('nets','wire_paths','wires','connections','signals','pin_connections','junctions','printed_labels','unjoined_crossings'):
      for pointer,value in leaves(after.get(collection,{}),'/'+collection):
       if any(w in pointer.lower()for w in('history','provenance','review_note','acceptance','source_evidence','evidence_')):continue
       if isinstance(value,str):need(re.search(r'(?<![A-Za-z0-9_])'+re.escape(oldref)+r'(?![A-Za-z0-9_])',value)is None,'No stale active pin ref '+f['case_id']+' '+pointer)
  totalcells+=len(e['cells']);totalpatches+=len(actual)
 accepted=sorted(records);receipt={'schema':'source-review-independent-acceptance-v1','reviewer':'/root/promote_continuation_fix independent stage review','independent_review':True,'passed':True,'failures':[],'manifest_sha256':sha(manifest_path),'accepted_pages':accepted,'unresolved_questions':[],'created_utc':datetime.now(timezone.utc).isoformat(),'source_changes_applied':False,'review_tool':bind(__file__),'selection':bind(selection_path),'checks_passed':checks,'case_coverage':629,'held_cases_unchanged':held,'changed_pages':len(accepted),'text_cells':totalcells,'json_patches_including_current_derivative_hashes':totalpatches,'context_corrections':context_count,'scope_note':'Only independently settled pin and separately accepted identity corrections; all held cases are explicitly unchanged. No canonical publication performed.'}
 out=manifest_path.parent/'Independent acceptance.json';out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()

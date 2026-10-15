"""Export reviewed UTF-8 transcriptions without changing their text cells."""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import csv, io, json, hashlib, re, sys

ROOT=Path('D:/Github/IBM360')
SOURCE=Path('D:/Reference Materials/IBM 360/IBM_360_ALD')
EXPORTS=ROOT/'ALD_Visual_Transcriptions'
REPO=ROOT/'ibm360ald'
AUDIT=ROOT/'tmp/ald-text/ald/repository-export'
PAGE=re.compile(r'^[A-Z][A-Z0-9]\d{3}(?:-\d\d)?$')
ACTIVE_FAMILIES={'AP','DS','LS','MA','MC','RB','RF','KT','KU','RK','PX','RE','RQ','RR','RT','RW','RY','RX','XM','XL','XN','XX','ZA','ZB','ZC','ZE','ZL'}
sha=lambda b:hashlib.sha256(b).hexdigest()

def read_json(p):
 try:return json.loads(p.read_text(encoding='utf-8-sig'))
 except (ValueError,OSError):return None

def canonical(candidates):
 # Retire the three old pilot copies in favour of the current family exports.
 priority={'ALD Diagrams':0,'CAS Diagrams':0}
 return sorted(candidates,key=lambda p:(priority.get(p.parent.name,1),len(p.relative_to(EXPORTS).parts),str(p)))[0]

def xx_independent_acceptance(review):
 # The final five XX receipts express full native/grid acceptance as named
 # checks instead of the earlier pair of top-level completion flags. Match
 # only these independently audited schemas; quartet/source binding remains
 # mandatory in receipts() for either representation.
 if all(review.get(k) is True for k in ['accepted','independent_review_complete','final_printer_grid_placement_accepted']):return True
 if review.get('accepted') is not True:return False
 page=review.get('page');checks=review.get('checks',{})
 if page in {'XX391','XX431','XX471'}:
  required=['native_full_source_compared','all_gate_fields','pins_controls_wedges',
   'all_wires_diamonds_crossings','all_labels_footer_connector_table',
   'printed_upper_right_header_id','full_preview_compared','canvas_245_by_103_grid',
   'grid_geometry_and_glyph_validation','exact_artifact_hash_binding','source_sha256']
  native=review.get('native_manual_review',{})
  evidence=(review.get('reviewer')=='/root/cw011' and native.get('evidence_files')
   and 'checked independently' in native.get('method',''))
 elif page in {'XX631','XX641'}:
  required=['full_native_page_overview_viewed',
   'all_external_names_header_connector_footer_revisions_compared','canvas_245_by_103_grid',
   'allowed_utf8_alphabet','unique_physical_ports','one_owner_every_input',
   'no_shared_different_net_edges','no_hidden_diamonds_or_fields',
   'source_sha256_matches','root_artifact_check_passed']
  required += (['all_native_30_gate_fields_and_ports_compared','all_45_inputs_independently_traced',
   'all_four_source_register_loops_compared','full_preview_compared'] if page=='XX631' else
   ['all_native_36_gate_fields_and_ports_compared','all_51_inputs_independently_traced',
   'all_source_register_and_auxiliary_loops_compared','corrected_full_preview_and_four_panels_compared',
   'K_semantics_null_and_no_added_logical_driver'])
  status=('Accepted after complete independent native-source and final-preview comparison'
   if page=='XX631' else 'Accepted after complete independent native-source and corrected full-preview comparison')
  evidence=(review.get('reviewer')=='/root/cw021' and review.get('review_status')==status
   and bool(review.get('native_evidence')))
 else:return False
 return bool(evidence) and all(checks.get(k) is True for k in required)

def receipts():
 records=defaultdict(list)
 def application_target(item,page):
  # Printed page codes can be shared by independently scanned subpages.
  # A specific application supersedes only its exact canonical TXT path.
  quartet=item.get('current_quartet',{})
  paths=[Path(v.get('path','')) for v in quartet.values() if isinstance(v,dict)]
  texts=[p for p in paths if p.suffix=='.txt' and not p.stem.endswith(' review notes')]
  if len(texts)!=1:return None
  target=texts[0];file_page=target.name.split(' ',1)[0]
  if not target.resolve().is_relative_to(EXPORTS.resolve()) or not PAGE.fullmatch(file_page):return None
  if file_page!=page and (('-' in page) or file_page.split('-',1)[0]!=page):return None
  return target
 def supersede_target(page,target,blocked):
  if target is None:
   records[page]=[{'blocked':True}];return page
  key=target.name.split(' ',1)[0]
  records[key]=[p for p in records[key] if not p.get('text_path') or Path(p['text_path']).resolve()!=target.resolve()]
  if blocked:records[key].insert(0,{'blocked':True,'text_path':str(target)})
  return key
 patterns=['*root reviews.json','*root layout review.json','*visual reviews.json',
           '*root final review.json','*final visual review.json',
           '*final review completion.json','DS native independent review ledger.json',
           'final source and preview reviews.json','root verification.json',
           '*independent reviews.json','*independent review.json']
 paths=set()
 import fnmatch
 for p in (ROOT/'tmp/ald-text').rglob('*.json'):
  if any(fnmatch.fnmatch(p.name,pattern) for pattern in patterns):paths.add(p)
 paths={p for p in paths if 'worker' not in p.name.lower() and ('independent' in p.name.lower() or ('mid' not in p.parts and 'low' not in p.parts))}
 # These owners supplied authoritative acceptance formats. Do not substitute
 # owner validation or a request for acceptance for their final receipts.
 paths={p for p in paths if not any(family in p.parts for family in ['ls','ma','mc','rr','rw','px','ry','rx','xm','xl','xn','xx','za','zb','zc','ze'])}
 def walk(d,path,page=None,group_complete=False):
  if isinstance(d,list):
   for x in d:walk(x,path,page,group_complete)
  elif isinstance(d,dict):
   page=d.get('page',page)
   positive=(d.get('passed') is not False and d.get('completed') is not False and d.get('accepted') is not False)
   if not positive:return
   if page and PAGE.match(page) and positive:
    hashes=[]
    for key in ['text_sha256','expected_hash']:
     if isinstance(d.get(key),str):hashes.append(d[key])
    for key in ['file_sha256','hashes','sha256','artifact_sha256']:
     if isinstance(d.get(key),dict):
      hashes += [v for k,v in d[key].items() if str(k).lower().endswith('.txt') and isinstance(v,str)]
    if hashes:records[page].append({'receipt':str(path.relative_to(ROOT)),'hashes':hashes})
    elif group_complete or d.get('root_source_versus_render_review') is True or d.get('status')=='passed' or d.get('independent_review_complete') is True or (d.get('completed') is True and d.get('independent_review')=='completed' and d.get('reviewer')=='root'):
     records[page].append({'receipt':str(path.relative_to(ROOT)),'hashes':None})
   complete=group_complete or d.get('all_owners_frozen') is True or d.get('complete') is True or d.get('all_complete') is True
   if complete and isinstance(d.get('pages'),list):
    for pg in d['pages']:
     if isinstance(pg,str) and PAGE.match(pg):records[pg].append({'receipt':str(path.relative_to(ROOT)),'hashes':None})
   for k,v in d.items():
    if PAGE.match(k):
     if isinstance(v,str):records[k].append({'receipt':str(path.relative_to(ROOT)),'hashes':None})
     else:walk(v,path,k,complete)
    elif isinstance(v,(dict,list)):walk(v,path,page,complete)
 for p in sorted(paths):walk(read_json(p),p)
 # RQ's independent root ledger binds each accepted canonical quartet and
 # source scan, even while the rest of the family's draft review continues.
 p=ROOT/'tmp/ald-text/rq/RQ independent root acceptance.json'
 for d in (read_json(p) or {}).get('pages',[]):
  artifacts=d.get('artifacts',{})
  source=Path(d.get('source',''))
  if d.get('accepted') is not True or d.get('reviewer')!='root' or len(artifacts)!=4:continue
  if not source.is_file() or sha(source.read_bytes())!=d.get('source_sha256'):continue
  if not all(a.get('path') and a.get('sha256') and Path(a['path']).is_file() and sha(Path(a['path']).read_bytes())==a['sha256'] for a in artifacts.values()):continue
  t=artifacts.get('text',{})
  if t.get('path') and t.get('sha256'):
   records[d['page']].append({'receipt':str(p.relative_to(ROOT)),'hashes':[t['sha256']],
                            'text_path':t['path'],'source_path':str(source)})
 # XX uses a current published quartet ledger plus the corresponding
 # independently accepted source/full-preview receipt, including post-review
 # metadata promotion hashes rather than older construction history.
 p=EXPORTS/'ALD Diagrams'/'XX acceptance ledger.json'
 for d in (read_json(p) or {}).get('pages',[]):
  review=read_json(Path(d.get('receipt_path',''))) or {}
  artifacts=d.get('artifact_sha256',{})
  if not xx_independent_acceptance(review) or review.get('page')!=d.get('page'):continue
  if review.get('source_sha256')!=d.get('source_sha256'):continue
  if len(artifacts)!=4 or not all(Path(path).is_file() and sha(Path(path).read_bytes())==digest for path,digest in artifacts.items()):continue
  text=Path(d.get('txt_path',''));source=Path(d.get('source_path',''))
  if not text.is_file() or not source.is_file() or sha(source.read_bytes())!=d.get('source_sha256') or sha(text.read_bytes())!=d.get('txt_sha256'):continue
  final=review.get('artifact_sha256',{})
  if not all(final.get(suffix)==artifacts.get(str(text.with_name(text.stem+suffix))) for suffix in ['.txt','.json',' preview.png',' review notes.txt']):continue
  records[d['page']].append({'receipt':str(p.relative_to(ROOT)),'hashes':[d['txt_sha256']],
                           'text_path':str(text),'source_path':str(source)})
 # LS requires a current hash-bound root review plus passing root geometry.
 p=EXPORTS/'ALD Diagrams'/'LS transcription index.json'
 geometry={d['page']:d for d in (read_json(ROOT/'tmp/ald-text/ls/root/LS root geometry audit.json') or {}).get('pages',[])}
 visual=read_json(ROOT/'tmp/ald-text/ls/root/LS visual reviews.json') or {}
 for d in (read_json(p) or {}).get('pages',[]):
  h=d.get('text_sha256');g=geometry.get(d['page'],{});v=visual.get(d['page'],{})
  # A documented source wire gap can leave graph continuity unverified while
  # the faithful printed text and layout are independently accepted.
  if d.get('layout_final') is True and h and g.get('layout_checks_passed') is True and g.get('text_sha256')==h and v.get('text_sha256')==h:
   records[d['page']].append({'receipt':str(p.relative_to(ROOT)),'hashes':[d['text_sha256']]})
 # MA's ledger binds the reviewed original scan to the exact text, including
 # repeated scan subpages whose published text omits a subpage suffix.
 p=EXPORTS/'ALD Diagrams'/'MA acceptance ledger.json'
 for d in (read_json(p) or {}).get('pages',[]):
  if d.get('txt_sha256'):
   records[d['page']].append({'receipt':str(p.relative_to(ROOT)),'hashes':[d['txt_sha256']],
                            'text_path':d['txt_path'],'source_path':d['source_path']})
 p=ROOT/'tmp/ald-text/mc/root/MC accepted TXT hashes.json'
 for page,d in (read_json(p) or {}).items():
  records[page].append({'receipt':str(p.relative_to(ROOT)),'hashes':[d['sha256']]})
 # Final RR and PX ledgers bind each frozen quartet, rather than relying on
 # earlier review status that may predate a source correction.
 p=EXPORTS/'RR transcription index.json';ledger=read_json(p) or {}
 for d in ledger.get('pages',[]):
  if d.get('accepted') is not True:continue
  pairs=[(d.get(k),d.get(h)) for k,h in [('text_file','text_sha256'),('model_file','model_sha256'),('review_notes','review_notes_sha256'),('preview_file','preview_sha256')]]
  if all(path and digest and Path(path).is_file() and sha(Path(path).read_bytes())==digest for path,digest in pairs):
   records[d['page']].append({'receipt':str(p.relative_to(ROOT)),'hashes':[d['text_sha256']],'text_path':d['text_file'],'source_path':d['source']})
 p=EXPORTS/'ALD Diagrams'/'PX transcription index.json'
 for d in (read_json(p) or {}).get('pages',[]):
  review=read_json(EXPORTS/'PX review reports'/(d['page']+' independent audit.json')) or {}
  artifacts=d.get('artifacts',[])
  if d.get('final_complete') is not True or review.get('passed') is not True or len(artifacts)!=4:continue
  if not all(Path(a['path']).is_file() and sha(Path(a['path']).read_bytes())==a['sha256'] for a in artifacts):continue
  text=next(a for a in artifacts if Path(a['path']).suffix=='.txt' and 'review notes' not in a['path'])
  records[d['page']].append({'receipt':str(p.relative_to(ROOT)),'hashes':[text['sha256']],'text_path':text['path'],'source_path':d['source']})
 p=EXPORTS/'ALD Diagrams'/'RW transcription index.json'
 for d in (read_json(p) or {}).get('pages',[]):
  r=d.get('root_review',{});t=Path(d['text_file'])
  pairs=[(t,r.get('text_sha256')),(t.with_suffix('.json'),r.get('evidence_sha256')),
         (t.with_name(t.stem+' review notes.txt'),r.get('notes_sha256')),
         (t.with_name(t.stem+' preview.png'),r.get('preview_sha256'))]
  if d.get('status')=='complete' and r.get('passed') is True and all(h and p.is_file() and sha(p.read_bytes())==h for p,h in pairs):
   records[d['page']].append({'receipt':str(p.relative_to(ROOT)),'hashes':[r['text_sha256']],'text_path':str(t),'source_path':d['source']})
 # DN's whole-page follow-up review supersedes the prior corrected TXT hashes.
 p=ROOT/'tmp/ald-text/mc/early/dn-audit/Independent whole-page review ledger.json'
 for d in read_json(p) or []:
  if d.get('status')=='PASS' and Path(d['text_path']).is_file() and sha(Path(d['text_path']).read_bytes())==d['text_sha256']:
   records[d['page']].append({'receipt':str(p.relative_to(ROOT)),'hashes':[d['text_sha256']],'text_path':d['text_path'],'source_path':d['source']})
 # RY publishes individual frozen quartet receipts with source/visual review.
 # Do not infer acceptance for other RY drafts from an inventory or identity audit.
 for p in sorted((ROOT/'tmp/ald-text/ry/review').glob('RY??? acceptance receipt.json')):
  d=read_json(p) or {};page=d.get('page');check=d.get('independent_check',{})
  quartet=d.get('working_files',{})
  if not page or not PAGE.match(page) or not str(d.get('status','')).startswith('accepted') or not d.get('visual_review') or check.get('passed') is not True:continue
  if not quartet or not all(Path(v['path']).is_file() and sha(Path(v['path']).read_bytes())==v['sha256'] for v in quartet.values()):continue
  text=quartet.get('text',{})
  if text.get('sha256'):
   records[page].append({'receipt':str(p.relative_to(ROOT)),'hashes':[text['sha256']],
                        'text_path':text['path'],'source_path':d['source']})
 # RX was directly assigned to the completed RY owner. Its per-page receipts
 # require independent native/preview review and the complete current quartet.
 for p in sorted((ROOT/'tmp/ald-text/rx/review').glob('RX??? acceptance receipt.json')):
  d=read_json(p) or {};page=d.get('page');check=d.get('independent_check',{})
  quartet=d.get('working_files',{});source=Path(d.get('source',''))
  if not page or not PAGE.match(page) or not str(d.get('status','')).startswith('accepted') or not d.get('visual_review') or check.get('passed') is not True:continue
  if set(quartet)!={'text','evidence','preview','review_notes'} or check.get('structural_check',{}).get('passed') is not True:continue
  if not source.is_file() or sha(source.read_bytes())!=d.get('source_sha256') or check.get('source_sha256')!=d.get('source_sha256'):continue
  if not all(Path(v['path']).is_file() and sha(Path(v['path']).read_bytes())==v['sha256'] for v in quartet.values()):continue
  text=quartet['text']
  records[page].append({'receipt':str(p.relative_to(ROOT)),'hashes':[text['sha256']],
                       'text_path':text['path'],'source_path':str(source)})
 # XL/ZA require current independently accepted text and evidence hashes.
 # Native source hash remains bound through the evidence or initial inventory.
 for family,ledger_name in [('xl','XL root reviews.json'),('za','root reviews.json')]:
  p=ROOT/'tmp/ald-text'/family/ledger_name
  inventory=read_json(ROOT/'tmp/ald-text'/family/(family.upper()+' source inventory.json')) or []
  source_hashes={r['page']:r.get('source_sha256') for r in inventory} if isinstance(inventory,list) else {}
  for page,d in (read_json(p) or {}).items():
   if d.get('passed') is not True or not d.get('text_sha256') or not d.get('evidence_sha256'):continue
   for text in (EXPORTS/'ALD Diagrams').glob(page+' *.txt'):
    if text.name.endswith('review notes.txt') or sha(text.read_bytes())!=d['text_sha256']:continue
    model=text.with_suffix('.json')
    if not model.is_file() or sha(model.read_bytes())!=d['evidence_sha256']:continue
    if d.get('preview_sha256') and (not text.with_name(text.stem+' preview.png').is_file() or sha(text.with_name(text.stem+' preview.png').read_bytes())!=d['preview_sha256']):continue
    meta=read_json(model) or {};source=meta.get('source');digest=meta.get('source_sha256',source_hashes.get(page))
    if source and digest and Path(source).is_file() and sha(Path(source).read_bytes())==digest:
     records[page].append({'receipt':str(p.relative_to(ROOT)),'hashes':[d['text_sha256']],'text_path':str(text),'source_path':source})
 # Independently inspected passive socket geometry, literal TXT and source.
 for family in ['ZB','ZE']:
  p=ROOT/'tmp/ald-text'/family.lower()/'root'/(family+' native independent review ledger.json')
  for page,d in (read_json(p) or {}).items():
   model=Path(d.get('json',''));meta=read_json(model) or {};text=model.with_suffix('.txt')
   if d.get('review',{}).get('kind')!='independent_native_review' or not d.get('review',{}).get('evidence') or meta.get('validation',{}).get('passed') is not True:continue
   if not str(meta.get('review_status','')).startswith('Reviewed:') or not text.is_file() or sha(text.read_bytes())!=d.get('text_sha256'):continue
   core={k:meta.get(k) for k in ['printer_grid','boxes','printed_labels']}
   if sha(json.dumps(core,ensure_ascii=False,sort_keys=True).encode('utf-8'))!=d.get('core_sha256'):continue
   source=meta.get('source')
   if source and Path(source).is_file() and sha(Path(source).read_bytes())==d.get('source_sha256')==meta.get('source_sha256'):
    records[page].append({'receipt':str(p.relative_to(ROOT)),'hashes':[d['text_sha256']],'text_path':str(text),'source_path':source})
 # ZL's completed registry binds native independent review and each quartet.
 p=EXPORTS/'ALD Diagrams/ZL transcription index.json'
 ledger=read_json(p) or {}
 for d in ledger.get('pages',[]):
  if d.get('independent_review',{}).get('result')!='accepted' or d.get('validation',{}).get('passed') is not True:continue
  artifacts=d.get('files',{})
  if len(artifacts)!=4 or not all(Path(a['path']).is_file() and sha(Path(a['path']).read_bytes())==a['sha256'] for a in artifacts.values()):continue
  source=d.get('source')
  if source and Path(source).is_file() and sha(Path(source).read_bytes())==d.get('source_sha256'):
   text=artifacts['text'];records[d['page']].append({'receipt':str(p.relative_to(ROOT)),'hashes':[text['sha256']],'text_path':text['path'],'source_path':source})
 # XN's final registry includes post-package companion hashes.
 p=EXPORTS/'XN transcription index.json';ledger=read_json(p) or {}
 source_hashes={}
 manifests={r.get('owner_manifest') for r in ledger.get('owner_freeze_verification',{}).get('pages',{}).values() if r.get('checks_passed') is True}
 for manifest in manifests:
  for r in (read_json(Path(manifest)) or {}).get('pages',[]):
   if r.get('source_sha256'):source_hashes[r['page']]=r['source_sha256']
 for d in ledger.get('pages',[]):
  acceptance=ledger.get('review_registry',{}).get('pages',{}).get(d['page'],{})
  if d.get('accepted') is not True or acceptance.get('combined_layout_accepted') is not True or acceptance.get('text_sha256')!=d.get('text_sha256'):continue
  pairs=[(d.get(k),d.get(h)) for k,h in [('text_file','text_sha256'),('model_file','model_sha256'),('review_notes','review_notes_sha256'),('preview_file','preview_sha256')]]
  if all(path and digest and Path(path).is_file() and sha(Path(path).read_bytes())==digest for path,digest in pairs) and Path(d['source']).is_file() and sha(Path(d['source']).read_bytes())==source_hashes.get(d['page']):
   records[d['page']].append({'receipt':str(p.relative_to(ROOT)),'hashes':[d['text_sha256']],'text_path':d['text_file'],'source_path':d['source']})
 # ZC keeps pre-review candidate hashes and final stamped companion hashes
 # separately; require the final package snapshot and source/core review.
 p=ROOT/'tmp/ald-text/zc/root/ZC native independent review ledger.json'
 reviews=read_json(p) or {};package=read_json(EXPORTS/'ZC transcription validation.json') or {}
 if package.get('passed') is True:
  for d in package.get('pages',[]):
   rec=reviews.get(d['page'],{});model=Path(rec.get('json',''));meta=read_json(model) or {}
   if rec.get('review',{}).get('kind')!='independent_native_review' or not rec.get('review',{}).get('evidence'):continue
   hashes=d.get('companion_sha256',{})
   if len(hashes)!=4 or not all((model.parent/name).is_file() and sha((model.parent/name).read_bytes())==digest for name,digest in hashes.items()):continue
   core={k:meta.get(k) for k in ['printer_grid','boxes','printed_labels']}
   if sha(json.dumps(core,ensure_ascii=False,sort_keys=True).encode('utf-8'))!=rec.get('core_sha256'):continue
   source=meta.get('source');text=model.with_suffix('.txt')
   if source and Path(source).is_file() and sha(Path(source).read_bytes())==rec.get('source_sha256')==d.get('source_sha256') and sha(text.read_bytes())==rec.get('text_sha256'):
    records[d['page']].append({'receipt':str(p.relative_to(ROOT)),'hashes':[rec['text_sha256']],'text_path':str(text),'source_path':source})
 # XM's independent native receipts bind each source and the complete quartet.
 for p in sorted((ROOT/'tmp/ald-text/xm/audits').glob('XM???.json')):
  d=read_json(p) or {};page=d.get('page');artifacts=d.get('accepted_artifact_sha256',{})
  if not page or d.get('status') not in ('accepted_after_independent_native_review','accepted_after_independent_native_review_and_correction') or not d.get('source_review') or len(artifacts)!=4:continue
  if not all((EXPORTS/'ALD Diagrams'/name).is_file() and sha((EXPORTS/'ALD Diagrams'/name).read_bytes())==digest for name,digest in artifacts.items()):continue
  name=next((n for n in artifacts if n.endswith('.txt') and not n.endswith('review notes.txt')),None)
  if name:
   text=EXPORTS/'ALD Diagrams'/name
   meta=read_json(text.with_suffix('.json')) or {}
   source=meta.get('source')
   if isinstance(source,dict):source=source.get('path')
   if source and Path(source).is_file() and sha(Path(source).read_bytes())==d.get('source_sha256'):
    records[page].append({'receipt':str(p.relative_to(ROOT)),'hashes':[artifacts[name]],'text_path':str(text),'source_path':source})
 # Independently audited source-derived revisions use several owner schemas.
 # The coordinator's named-schema audit records the exact source, full current
 # quartet and receipt chain. Recheck those bytes on every export; a changed
 # quartet cannot fall back to an older text-only receipt.
 for audit_name in ['Source-derived acceptance adapter audit.json',
                    'Supplementary source-derived acceptance adapter audit.json',
                    'Next source-derived acceptance adapter audit.json',
                    'WA accepted current audit.json',
                    'V3 current publication audit.json',
                    'KT V2 unchanged current rebind audit.json',
                    'WA final current audit.json',
                    'WA301 current authority audit.json',
                    'WA glyph and footer current audit.json',
                    'FX RT V3 current publication audit.json',
                    'C2A human correction current audit.json',
                    'AP001 human socket correction current audit.json',
                    'Recorded and recovered UTF8 application current audit.json',
                    'OR function human correction current audit.json',
                    'CA211 human primary function correction current audit.json',
                    'R TU human function correction current audit.json',
                    'Returned function answers current audit.json',
                    'Function review batch 2 current audit.json',
                    'Function review batch 3 current audit.json',
                    'Function review batch 4 current audit.json',
                    'Function review batch 5 current audit.json',
                    'Function review batch 6 current audit.json',
                    'Function review batch 7 current audit.json',
                    'Function review batch 8 current audit.json',
                    'Automatic unreadable function recovery current audit.json',
                    'H function port rule current audit.json',
                    'Native three source corrections current audit.json',
                    'Eleven function corrections current audit.json',
                    'AP041 three-way portion current audit.json',
                    'Circuit identifier source current audit.json',
                    'Physical circuit confirmation current audit.json',
                    'Tied circuit clarification current audit.json',
                    'PX511 BB physical current audit.json',
                    'Second-pass circuit current audit.json']:
  audit_path=ROOT/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3'/audit_name
  audit=read_json(audit_path) or {}
  if audit_name=='Circuit identifier source current audit.json':
   # Every staged page supersedes its old acceptance, even if the new audit
   # is missing or stale. Never fall back to an older text-only receipt.
   stage_path=ROOT/'tmp/ald-text/ald/card-type-database/circuit-identifier-review/pipeline/private-stage/Circuit identifier private stage manifest.json'
   stage=read_json(stage_path)
   if not isinstance(stage,dict) or stage.get('schema')!='circuit-identifier-source-bound-private-stage-v1' or stage.get('counts',{}).get('staged_pages')!=77:
    raise ValueError('Circuit identifier source stage is missing or invalid; export refused')
   for staged in stage.get('pages',[]):
    page=staged.get('page')
    target=Path(staged.get('canonical_before_quartet',{}).get('txt',{}).get('path',''))
    if not page or not PAGE.fullmatch(page) or not target.resolve().is_relative_to(EXPORTS.resolve()):
     raise ValueError('Circuit identifier source stage has an invalid page target')
    supersede_target(page,target,True)
   if audit.get('passed') is not True:continue
  if audit_name=='Physical circuit confirmation current audit.json':
   stage_path=ROOT/'tmp/ald-text/ald/card-type-database/circuit-identifier-review/pipeline/physical-confirmations-private-stage/Physical circuit confirmations private stage manifest.json'
   stage=read_json(stage_path)
   if not isinstance(stage,dict) or stage.get('schema')!='physical-circuit-confirmations-private-stage-v1' or len(stage.get('pages',[]))!=3:
    raise ValueError('Physical circuit confirmation stage is missing or invalid; export refused')
   for staged in stage['pages']:
    page=staged.get('page')
    target=Path(staged.get('canonical_before_quartet',{}).get('txt',{}).get('path',''))
    if not page or not PAGE.fullmatch(page) or not target.resolve().is_relative_to(EXPORTS.resolve()):
     raise ValueError('Physical circuit confirmation stage has an invalid page target')
    supersede_target(page,target,True)
   if audit.get('passed') is not True:continue
  if audit_name=='Tied circuit clarification current audit.json':
   stage_path=ROOT/'tmp/ald-text/ald/card-type-database/circuit-identifier-review/pipeline/tied-clarification-private-stage/Tied circuit clarifications private stage manifest.json'
   stage=read_json(stage_path)
   if not isinstance(stage,dict) or stage.get('schema')!='tied-circuit-clarifications-private-stage-v1' or len(stage.get('pages',[]))!=2:
    raise ValueError('Tied circuit clarification stage is missing or invalid; export refused')
   for staged in stage['pages']:
    page=staged.get('page')
    target=Path(staged.get('canonical_before_quartet',{}).get('txt',{}).get('path',''))
    if not page or not PAGE.fullmatch(page) or not target.resolve().is_relative_to(EXPORTS.resolve()):
     raise ValueError('Tied circuit clarification stage has an invalid page target')
    supersede_target(page,target,True)
   if audit.get('passed') is not True:continue
  if audit_name=='PX511 BB physical current audit.json':
   stage_path=ROOT/'tmp/ald-text/ald/card-type-database/circuit-identifier-review/pipeline/px511-bb-physical-private-stage/PX511 BB physical private stage manifest.json'
   stage=read_json(stage_path)
   if not isinstance(stage,dict) or stage.get('schema')!='px511-bb-physical-circuit-private-stage-v1':
    raise ValueError('PX511 BB physical stage is missing or invalid; export refused')
   target=Path(stage.get('canonical_before_quartet',{}).get('txt',{}).get('path',''))
   if not target.resolve().is_relative_to(EXPORTS.resolve()):
    raise ValueError('PX511 BB physical stage has an invalid page target')
   supersede_target('PX511',target,True)
   if audit.get('passed') is not True:continue
  if audit_name=='Second-pass circuit current audit.json':
   # This newer source-bound quartet supersedes each predecessor only after
   # its guarded canonical publication receipt exists. A missing or stale
   # current audit may not fall back to an older accepted text.
   receipt_path=ROOT/'tmp/ald-text/ald/card-type-database/circuit-identifier-review/pipeline/Second-pass accepted circuit canonical publication receipt.json'
   receipt=read_json(receipt_path)
   if not isinstance(receipt,dict):
    if audit:raise ValueError('Second-pass circuit audit exists without a publication receipt')
    continue
   if receipt.get('schema')!='second-pass-accepted-circuit-canonical-publication-v1' or len(receipt.get('pages',[]))!=11:
    raise ValueError('Second-pass circuit publication receipt is invalid')
   for published in receipt['pages']:
    page=published.get('page')
    target=Path(published.get('canonical_quartet',{}).get('txt',{}).get('path',''))
    if not page or not PAGE.fullmatch(page) or not target.resolve().is_relative_to(EXPORTS.resolve()):
     raise ValueError('Second-pass circuit publication has an invalid page target')
    supersede_target(page,target,True)
   if audit.get('passed') is not True:continue
  if audit_name=='AP041 three-way portion current audit.json':
   # The newest AP041 source reading supersedes older approval even if this
   # exact full-quartet audit is missing, malformed or stale.
   for target in EXPORTS.rglob('AP041 *.txt'):
    if not target.stem.endswith(' review notes'):supersede_target('AP041',target,True)
   if audit.get('passed') is not True:continue
  if audit_name=='Eleven function corrections current audit.json' and audit.get('passed') is not True:
   # This newest source-specific acceptance supersedes the prior text receipts
   # even if the binder disappears or fails to load. Never resurrect old copy.
   for page in {'AP737','AP181','RQ683','KU601','RQ781','MC371','AP441','AP531','XM181','AS201','AP313'}:
    for target in EXPORTS.rglob(page+' *.txt'):
     if not target.stem.endswith(' review notes'):supersede_target(page,target,True)
   continue
  if audit_name in {'Function review batch 3 current audit.json','Function review batch 4 current audit.json','Function review batch 5 current audit.json','Function review batch 6 current audit.json','Function review batch 7 current audit.json','Function review batch 8 current audit.json','Automatic unreadable function recovery current audit.json','H function port rule current audit.json','Native three source corrections current audit.json'} and audit.get('passed') is not True:
   # A failed latest source-specific review cannot restore an older approval.
   for item in audit.get('pages',[]):
    if item.get('page') and PAGE.fullmatch(item['page']):supersede_target(item['page'],application_target(item,item['page']),True)
   continue
  if audit.get('passed') is not True:continue
  for item in audit.get('pages',[]):
   page=item.get('page')
   if not page or not PAGE.fullmatch(page):continue
   application_schema=(audit_name in {'Recorded and recovered UTF8 application current audit.json',
                                     'OR function human correction current audit.json',
                                     'CA211 human primary function correction current audit.json',
                                     'R TU human function correction current audit.json',
                                     'Returned function answers current audit.json',
                                     'Function review batch 2 current audit.json',
                                     'Function review batch 3 current audit.json',
                                     'Function review batch 4 current audit.json',
                                     'Function review batch 5 current audit.json',
                                     'Function review batch 6 current audit.json',
                                     'Function review batch 7 current audit.json',
                                     'Function review batch 8 current audit.json',
                                     'Automatic unreadable function recovery current audit.json',
                                     'H function port rule current audit.json',
                                     'Native three source corrections current audit.json',
                                     'Eleven function corrections current audit.json',
                                     'AP041 three-way portion current audit.json',
                                     'Circuit identifier source current audit.json',
                                     'Physical circuit confirmation current audit.json',
                                     'Tied circuit clarification current audit.json',
                                     'PX511 BB physical current audit.json',
                                     'Second-pass circuit current audit.json'})
   target=application_target(item,page) if application_schema else None
   record_page=supersede_target(page,target,True) if application_schema else page
   if not application_schema:records[page]=[]
   checks=item.get('checks',{})
   if item.get('eligible') is not True or not checks or not all(value is True for value in checks.values()):continue
   source=item.get('source',{});sp=Path(source.get('path',''))
   if not sp.is_file() or not sp.resolve().is_relative_to(SOURCE.resolve()) or sha(sp.read_bytes())!=source.get('sha256'):continue
   valid=True
   for key in ['root_acceptance','owner_receipt','legacy_ledger','independent_audit','human_authority','frozen_occurrence_inventory','original_answers','human_amendment','returned_workbook','batch2_raw_first','batch2_raw_rest','batch2_questions','batch3_questions','batch4_questions','batch5_questions','batch6_questions','batch7_questions','batch8_questions','predecessor_acceptance','predecessor_approval','automatic_candidate_manifest','automatic_derivation_script','automatic_database_audit','automatic_raw_authority','function_rule_unreadable_review','function_rule_application_manifest','native_three_manifest','native_three_source_evidence','native_three_crop','eleven_manifest','eleven_authority_record','eleven_source_crop','eleven_broad_context_crop','ap041_manifest','ap041_source_evidence','ap041_source_crop','ap041_publication','circuit_stage_manifest','circuit_source_review','physical_stage_manifest','physical_authority','tied_stage_manifest','tied_human_authority','tied_BB_source_review','px511_bb_stage_manifest','px511_bb_human_authority']:
    chain=item.get(key)
    if not isinstance(chain,dict) or not chain.get('file'):continue
    cp=Path(chain['file'])
    if not cp.is_file() or not cp.resolve().is_relative_to(ROOT.resolve()) or sha(cp.read_bytes())!=chain.get('sha256'):
     valid=False;break
   quartet={k:v for k,v in item.get('current_quartet',{}).items() if v is not None}
   paths=[Path(x.get('path','')) for x in quartet.values()]
   text_paths=[p for p in paths if p.suffix=='.txt' and not p.stem.endswith(' review notes')]
   if not valid or len(text_paths)!=1:continue
   text_path=text_paths[0]
   expected={text_path,text_path.with_suffix('.json'),text_path.with_name(text_path.stem+' review notes.txt'),text_path.with_name(text_path.stem+' preview.png')}
   if application_schema:
    if item.get('artifact_schema')=='reviewed-existing-A1-table-and-auxiliary-data-v1':
     if text_path.parent.name!='A1 Socket Listing' or text_path.with_suffix('.json').exists():continue
     expected.remove(text_path.with_suffix('.json'))
    elif item.get('artifact_schema')!='reviewed-current-quartet-v1':continue
    # Several original published previews used the text basename. This one
    # explicitly registered schema binds that exact legacy path and hash.
    preview=Path(quartet.get('preview',{}).get('path',''))
    if preview in {text_path.with_suffix('.png'),text_path.with_name(text_path.stem+' JuliaMono preview.png'),
                   text_path.with_name(text_path.stem+' JuliaMono.png')}:
     expected.remove(text_path.with_name(text_path.stem+' preview.png'));expected.add(preview)
    auxiliary=item.get('current_auxiliary_existing_data',[])
    if len(expected)==3 and not auxiliary:continue
    if not all(Path(a.get('path','')).is_file()
      and (Path(a['path']).resolve().is_relative_to(EXPORTS.resolve())
        or Path(a['path']).resolve().is_relative_to((ROOT/'tmp/ald-text/a1').resolve()))
      and sha(Path(a['path']).read_bytes())==a.get('sha256') for a in auxiliary):continue
   if len(quartet)!=len(expected):continue
   if set(paths)!=expected:continue
   if application_schema:
    if target is None or text_path.resolve()!=target.resolve():continue
   elif text_path.name.split(' ',1)[0]!=page:continue
   if not all(p.is_file() and p.resolve().is_relative_to(EXPORTS.resolve()) and sha(p.read_bytes())==value.get('sha256') for p,value in zip(paths,quartet.values())):continue
   if application_schema:record_page=supersede_target(page,target,False)
   records[record_page].insert(0,{'receipt':str(audit_path.relative_to(ROOT)),'hashes':[sha(text_path.read_bytes())],
                         'text_path':str(text_path),'source_path':str(sp)})
 return records

def companion_metadata(txt):
 key=txt.name.split(' ',1)[0]
 for p in [txt.with_suffix('.json'),txt.with_name(txt.stem+' verification.json'),
           txt.with_name(key+' verification.json'),txt.with_name(key+' review.json')]:
  d=read_json(p)
  if isinstance(d,dict):return p,d
 return None,{}

def reviewed(txt,page,hash_value,meta,proofs):
 holds=read_json(AUDIT/'Coordinator source review holds.json') or {}
 if page[:2] in holds.get('families',{}) or page in holds.get('pages',{}):return None
 matching=[proof for proof in proofs.get(page,[]) if not proof.get('text_path') or Path(proof['text_path']).resolve()==txt.resolve()]
 if any(proof.get('blocked') for proof in matching):return None
 for proof in matching:
  if proof['hashes'] is None or hash_value in proof['hashes']:return proof['receipt']
 # Table/CAS pages have their own completed visual verification, rather than
 # the later ALD circuit root-review receipts.
 if txt.parent.name in ['A1 Socket Listing','A6 Indices','A7 Cabling and Timing',
                        'A8 Adjustment and Configuration','CAS Diagrams','QZ ROS Listing','EF Socket Listing']:
  status=str(meta.get('review_status',meta.get('status',''))).lower()
  if ('review' in status or 'verif' in status or 'complete' in status or 'visually reconstructed' in status or (txt.parent.name=='CAS Diagrams' and status.startswith('visually transcribed;'))) and not any(x in status for x in ['pending','draft','provisional']):return 'Published visual verification: '+status
  if txt.parent.name=='A1 Socket Listing':
   key=txt.name.split(' ',1)[0];board=key.split('-')[0]
   p=ROOT/'tmp/ald-text/a1'/(key+' columns reviewed.json')
   if p.exists():return str(p.relative_to(ROOT))
  if txt.parent.name=='QZ ROS Listing':
   p=ROOT/'tmp/ald-text/qz'/(txt.stem+' reviewed.json')
   if p.exists():return str(p.relative_to(ROOT))
 status=str(meta.get('review_status',meta.get('status',''))).lower()
 if page[:2] not in ACTIVE_FAMILIES and meta.get('source_reviewed') is True and ('review' in status or 'complete' in status) and not any(x in status for x in ['pending','draft','provisional','awaiting']):
  return 'Completed published review status: '+status
 return None

def note_content(source,txt,meta,row,previous,following,proof):
 parts=[source.stem+' - TRANSLATION NOTES','',
        'Reference scan: '+str(source.relative_to(SOURCE)),
        'Original scan: '+Path(row['path']).name,
        'Original scan timestamp: '+row['scan_timestamp'],
        'Preceding scan: '+previous,'Following scan: '+following,
        'Review record: '+proof,'']
 note=txt.with_name(txt.stem+' review notes.txt')
 if note.exists():
  parts.extend(['PAGE NOTES','',note.read_text(encoding='utf-8-sig').rstrip(),''])
 else:
  for key in ['review_notes','uncertainties','unresolved_print','layout_notes','symbols_notes']:
   value=meta.get(key)
   if value:
    parts.extend([key.replace('_',' ').upper(),'',json.dumps(value,ensure_ascii=False,indent=2),''])
 for key in ['notes','revision_notes','unresolved','source_unreadable_cells',
             'unreadable_entries','layout_note','verification_note',
             'A1_literal_conflicts','uncertain_connections']:
  if meta.get(key):
   parts.extend([key.replace('_',' ').upper(),'',json.dumps(meta[key],ensure_ascii=False,indent=2),''])
 count=txt.read_text(encoding='utf-8-sig').count('�')
 if count:parts.extend([f'Unreadable printed characters retained as �: {count}.',''])
 return ('\n'.join(parts).rstrip()+'\n').encode('utf-8')

def supplemental_notes():
 folders={p.name:p for p in SOURCE.iterdir() if p.is_dir()}
 by_family={name[:2]:name for name in folders}
 entries=[]
 for p in sorted(EXPORTS.rglob('*.txt')):
  name=p.stem.lower()
  meaningful=(name.endswith('review notes') or name.endswith('notes') or
              'physical copy check' in name or name.endswith('readme') or
              name=='unreadable print' or name=='confirmed filename corrections')
  if not meaningful:continue
  # Paired page notes are already carried in the page-specific note files.
  if name.endswith('review notes') and p.with_name(p.stem[:-len(' review notes')]+'.txt').is_file():continue
  if name=='confirmed filename corrections':folder=None
  elif p.parent.name in folders:folder=p.parent.name
  elif p.name[:2] in by_family:folder=by_family[p.name[:2]]
  else:continue
  # Do not retain an empty placeholder physical-copy report.
  raw=p.read_bytes();body=raw.decode('utf-8-sig')
  if 'physical copy check' in name and len(body.strip().splitlines())<6:continue
  dest=REPO/'notes'
  if folder:dest=dest/folder
  dest=dest/p.name
  entries.append({'source':str(p),'destination':str(dest),'sha256':sha(raw),'_bytes':raw})
 return entries

def main():
 assert REPO.is_dir() and (REPO/'.git').is_dir()
 original_csv=(SOURCE/'ALD Scan Order.csv').read_bytes()
 rows=list(csv.DictReader(io.StringIO(original_csv.decode('utf-8-sig'))))
 by_name=defaultdict(list)
 for p in EXPORTS.rglob('*.txt'):by_name[p.name.lower()].append(p)
 proofs=receipts();plan=[];unavailable=[];conflicts=[]
 for i,row in enumerate(rows):
  source=Path(row['newpath'])
  if source.suffix.lower() not in ['.tif','.tiff']:continue
  if not source.is_file():
   unavailable.append({'page':row['page'],'source':str(source),'reason':'Source catalogue path missing; recheck rename'});continue
  rel=source.relative_to(SOURCE);file_page=source.name.split(' ',1)[0]
  candidates=by_name.get(source.stem.lower()+'.txt',[])
  if not candidates:
   # Published filenames can preserve the literal title (e.g. diamond rather
   # than catalogue AND). Match the exact page/subpage, never a neighbouring bit.
   candidates=[p for ps in by_name.values() for p in ps
               if p.name.split(' ',1)[0]==file_page and not any(s in p.stem.lower() for s in ['review notes','transcription index','manifest','readme','physical copy','progress'])]
  if not candidates:
   candidates=[Path(proof['text_path']) for ps in proofs.values() for proof in ps
               if proof.get('source_path') and Path(proof['source_path'])==source and Path(proof['text_path']).is_file()]
  if not candidates:
   unavailable.append({'page':row['page'],'source':str(rel),'reason':'No matching published transcription'});continue
  txt=canonical(candidates);raw=txt.read_bytes();raw.decode('utf-8-sig')
  metadata_path,meta=companion_metadata(txt);h=sha(raw)
  proof=reviewed(txt,txt.name.split(' ',1)[0],h,meta,proofs)
  if not proof:
   unavailable.append({'page':row['page'],'source':str(rel),'text':str(txt),'reason':'No matching completed review record'});continue
  destination=REPO/'ALD'/rel.parent/txt.name
  notes=REPO/'notes'/rel.parent/(txt.stem+' review notes.txt')
  previous=rows[i-1]['newname'] if i else '(none)';following=rows[i+1]['newname'] if i+1<len(rows) else '(none)'
  note_bytes=note_content(source,txt,meta,row,previous,following,proof)
  plan.append({'page':row['page'],'source_relative':str(rel),'transcription_source':str(txt),
               'destination':str(destination),'notes_destination':str(notes),'text_sha256':h,
               'review_record':proof,'source_scan_id':row['id'],'original_scan_name':Path(row['path']).name,
               'scan_timestamp':row['scan_timestamp'],'notes_sha256':sha(note_bytes),'_text':raw,'_notes':note_bytes})
 # Every existing differing destination is a conflict, never silently replaced.
 supplemental=supplemental_notes()
 prior=read_json(AUDIT/'last export manifest.json') or {};owned=dict(prior.get('managed_files',{}))
 for x in prior.get('exported',[]):
  owned[x['destination']]=x['text_sha256'];owned[x['notes_destination']]=x['notes_sha256']
 for x in prior.get('supplemental_notes',[]):owned[x['destination']]=x['sha256']
 for x in plan:
  for key,rawkey in [('destination','_text'),('notes_destination','_notes')]:
   p=Path(x[key])
   if p.exists() and p.read_bytes()!=x[rawkey] and sha(p.read_bytes())!=owned.get(str(p)):
    conflicts.append(str(p))
 for x in supplemental:
  p=Path(x['destination'])
  if p.exists() and p.read_bytes()!=x['_bytes'] and sha(p.read_bytes())!=owned.get(str(p)):
   conflicts.append(str(p))
 # Reopened reviews can invalidate a previously accepted working hash. Keep
 # their old mirrored bytes recoverably outside production, never as an extra
 # unlisted diagram. Independently edited or unowned files are not moved.
 expected={Path(x['destination']).resolve() for x in plan}
 retired=[];stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 archive=(AUDIT/'held accepted snapshots'/stamp).resolve()
 for p in (REPO/'ALD').rglob('*.txt'):
  if p.resolve() in expected:continue
  h=sha(p.read_bytes())
  if owned.get(str(p))!=h:conflicts.append(str(p));continue
  destination=archive/p.relative_to(REPO)
  assert p.resolve().is_relative_to((REPO/'ALD').resolve()) and destination.is_relative_to(AUDIT.resolve())
  assert not destination.exists()
  retired.append({'old_path':str(p),'preserved_path':str(destination),'sha256':h,'reason':'Not in current accepted export; prior owned bytes preserved pending current review'})
 safeplan=[{k:v for k,v in x.items() if not k.startswith('_')} for x in plan]
 report={'created_utc':datetime.now(timezone.utc).isoformat(),'policy':'Reviewed transcriptions only; retain exact text bytes and source folder names',
         'source_catalogue_rows':len(rows),'eligible':len(plan),'unavailable':unavailable,'conflicts':conflicts,
         'counts_by_source_folder':dict(Counter(Path(x['source_relative']).parts[0] for x in plan)),'exported':safeplan,
         'supplemental_notes':[{k:v for k,v in x.items() if not k.startswith('_')} for x in supplemental]}
 report['retired_files']=prior.get('retired_files',[])+retired
 # Keep ownership when a previously exported page is temporarily excluded
 # during a corrected source review. An independently edited file still fails
 # the hash check above; a later acceptance can replace our own old snapshot.
 report['managed_files']=dict(owned)
 for x in plan:
  report['managed_files'][x['destination']]=x['text_sha256']
  report['managed_files'][x['notes_destination']]=x['notes_sha256']
 for x in supplemental:report['managed_files'][x['destination']]=x['sha256']
 AUDIT.mkdir(parents=True,exist_ok=True)
 (AUDIT/'export plan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 if '--write' in sys.argv:
  if '--expect-eligible' in sys.argv:
   expected_count=int(sys.argv[sys.argv.index('--expect-eligible')+1])
   assert len(plan)==expected_count, 'Current acceptance count differs from the complete scoped snapshot; no repository files written'
  assert not conflicts, 'Repository files have independent changes; inspect conflicts before export'
  report['export_in_progress']=True
  (AUDIT/'last export manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  for folder in SOURCE.iterdir():
   if folder.is_dir():
    (REPO/'ALD'/folder.name).mkdir(parents=True,exist_ok=True)
    (REPO/'notes'/folder.name).mkdir(parents=True,exist_ok=True)
  for x in plan:
   # Detect concurrent changes before a page is exported.
   assert Path(x['transcription_source']).read_bytes()==x['_text'], 'Transcription changed during export'
   for key,rawkey in [('destination','_text'),('notes_destination','_notes')]:
    p=Path(x[key]);p.parent.mkdir(parents=True,exist_ok=True)
    if not p.exists() or p.read_bytes()!=x[rawkey]:p.write_bytes(x[rawkey])
    assert p.read_bytes()==x[rawkey]
  for x in supplemental:
   p=Path(x['destination']);p.parent.mkdir(parents=True,exist_ok=True)
   assert Path(x['source']).read_bytes()==x['_bytes'],'Supplemental note changed during export'
   if not p.exists() or p.read_bytes()!=x['_bytes']:p.write_bytes(x['_bytes'])
   assert p.read_bytes()==x['_bytes']
  for x in retired:
   p=Path(x['old_path']);destination=Path(x['preserved_path'])
   assert sha(p.read_bytes())==x['sha256'],'Prior accepted copy changed during export'
   destination.parent.mkdir(parents=True,exist_ok=True);p.rename(destination)
   assert sha(destination.read_bytes())==x['sha256']
  for branch in ['ALD','notes']:
   for folder in (REPO/branch).iterdir():
    if folder.is_dir() and not any(folder.iterdir()):(folder/'.gitkeep').write_text('',encoding='utf-8')
  assert (SOURCE/'ALD Scan Order.csv').read_bytes()==original_csv,'Source catalogue changed during export; refresh inventory'
  report['bytewise_copy_verified']=True
  report['export_in_progress']=False
  (AUDIT/'last export manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:report[k] for k in ['eligible','counts_by_source_folder','conflicts']},ensure_ascii=False))
 print('unavailable',len(unavailable),'write','--write' in sys.argv)

if __name__=='__main__':main()

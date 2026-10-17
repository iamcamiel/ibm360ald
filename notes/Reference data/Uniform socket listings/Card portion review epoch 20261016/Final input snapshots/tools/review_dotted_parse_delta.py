"""Independent, read-only old/new parser delta on one accepted current TXT epoch."""
from pathlib import Path
from collections import Counter
import json,hashlib,importlib.util
R=Path('D:/Github/IBM360');REPO=R/'ibm360ald';H=Path(__file__).resolve().parent/'Dotted continuation independent review';H.mkdir(exist_ok=True)
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def module(name,p):
 spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def need(v,m):
 if not v:raise ValueError(m)
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def added_dropped(a,b):
 aa,bb=Counter(map(canon,a)),Counter(map(canon,b));return {'added':[json.loads(x)for x,n in(bb-aa).items()for _ in range(n)],'dropped':[json.loads(x)for x,n in(aa-bb).items()for _ in range(n)]}
oldp=REPO/'notes/Reference data/Uniform socket listings/Pin letter review epoch 20261016/Final input snapshots/tools/references/socket_text_parser.py';mp=REPO/'notes/Reference data/Uniform socket listings/Pin letter review epoch 20261016/Current build manifest.json';manifest=read(mp);need(sha(oldp)==next(x['sha256']for x in manifest['inputs']if x['path']=='tools/references/socket_text_parser.py'),'Old parser does not match preserved build manifest')
newp=REPO/'tools/references/socket_text_parser.py';bp=REPO/'tools/references/build_uniform_socket_listings.py';builder=module('accepted_builder',bp);pages,inputs=builder.load_pages(REPO);old=module('old_parser',oldp).parse_listings(pages);new=module('new_parser',newp).parse_listings(pages)
before={r['id']:r for r in old['records']};after={r['id']:r for r in new['records']};need(len(before)==len(old['records'])and len(after)==len(new['records']),'Duplicate record identity');changed=[]
for rid in sorted(before.keys()&after.keys()):
 a,b=before[rid],after[rid]
 if a==b:continue
 structural={k:v for k,v in a.items()if k not in['references','source_spans','raw_lines']};need(structural=={k:v for k,v in b.items()if k not in['references','source_spans','raw_lines']},'Unexpected record identity/other-field change '+rid)
 claims=lambda r:[{'page':ref['page'],'portion':portion}for ref in r['references']for portion in ref['portions']]
 changed.append({'record_id':rid,'board':b['board'],'sockets':b['sockets'],'card_type':b['card_type'],'before':a,'after':b,'claim_delta':added_dropped(claims(a),claims(b)),'source_span_delta':added_dropped(a['source_spans'],b['source_spans']),'raw_line_delta':added_dropped(a['raw_lines'],b['raw_lines'])})
need(not(before.keys()-after.keys())and not(after.keys()-before.keys()),'Unexpected records added/dropped');need(old['tables']==new['tables'],'Supplementary tables changed');need(not old['issues']and not new['issues'],'Parser issues require review');need(all(not c['claim_delta']['dropped']and not c['source_span_delta']['dropped']and not c['raw_line_delta']['dropped']for c in changed),'Unexpected dropped claim/span')
for c in changed:
 for s in c['source_span_delta']['added']:
  need(s['literal'].count('.')>len(s['literal'])*.65,'New evidence is not dotted continuation')
  page=next(p for p in pages if p['scan_id']==s['scan_id']);need(page['lines'][s['row']][s['column']:s['end_column']]==s['literal'],'Added span differs from accepted TXT')
for b in inputs:need(sha(REPO/b['path'])==b['sha256'],'Accepted input epoch changed during full comparison')
for name,value in [('Before parse.json',old),('After parse.json',new)]:
 p=H/name;need(not p.exists(),'Preserve frozen parse result');p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')
report={'schema':'independent-dotted-continuation-parser-delta-v1','passed':True,'source_writes':False,'uniform_publication':False,'reviewer':bind(Path(__file__)),'old_parser':bind(oldp),'old_parser_manifest':bind(mp),'new_parser':bind(newp),'accepted_loader':bind(bp),'accepted_current_inputs':inputs,'source_pages':len(pages),'before_parse':bind(H/'Before parse.json'),'after_parse':bind(H/'After parse.json'),'before_counts':old['coverage'],'after_counts':new['coverage'],'added_records':[],'dropped_records':[],'changed_records':changed,'added_claims':sum(len(c['claim_delta']['added'])for c in changed),'dropped_claims':sum(len(c['claim_delta']['dropped'])for c in changed),'added_source_spans':sum(len(c['source_span_delta']['added'])for c in changed),'native_verification_pending':True};p=H/'Full parser delta.json';need(not p.exists(),'Preserve frozen delta');p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps({'delta':bind(p),'source_pages':len(pages),'records':len(after),'changed_records':len(changed),'added_claims':report['added_claims'],'added_source_spans':report['added_source_spans'],'claims':[{k:c[k]for k in['record_id','board','sockets','card_type','claim_delta','source_span_delta']}for c in changed]},ensure_ascii=False,indent=2))

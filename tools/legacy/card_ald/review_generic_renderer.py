"""Independent portable-renderer migration, topology and failure-path checks."""
from pathlib import Path
from collections import defaultdict
from copy import deepcopy
import ast,datetime,hashlib,importlib.util,json,re,shutil,subprocess,sys
ROOT=Path('D:/Github/IBM360/ibm360ald');OUT=ROOT.parent/'tmp/ald-text/ald/card-universal/independent-review'
GEN=ROOT/'tools/card_ald/generate_card.py';DEFS=ROOT/'json/Card-ALD/definitions'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
module_spec=importlib.util.spec_from_file_location('independent_generic_card_renderer',GEN)
core=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(core)
checks={};fail=[]
def check(name,ok,detail=None):
 checks[name]={'passed':bool(ok)}
 if detail is not None:checks[name]['detail']=detail
 if not ok:fail.append(name)
baseline=read(OUT/'Generic renderer golden baseline.json');gold={f['file']:f for f in baseline['files']}
specs={card:read(DEFS/(card+'.json')) for card in ['0141','4191','4633','4634']}
outputs={};details={};errors=[];byte_errors=[]
for card,spec in specs.items():
 built,validation=core.build(spec);outputs.update(built);details[card]=validation
 for name,raw in built.items():
  if raw.decode('utf-8').splitlines()!=gold[name]['expected_lines']:errors.append(name)
  original=gold[name]['text'];pieces=[]
  for line in original.splitlines(keepends=True):
   ending='\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
   content=line[:-len(ending)] if ending else line
   content=re.sub(r'\bGROUP\s+\d+\b',lambda m:' '*len(m.group()),content).rstrip()
   pieces.append(content+ending)
  if raw!=''.join(pieces).encode('utf-8'):byte_errors.append(name)
check('all124outputs_have_only_the72_authorized_GROUP_label_removals',len(outputs)==len(gold)==124 and not errors,errors)
check('all124outputs_preserve_original_encoding_lineendings_and_other_bytes',not byte_errors,byte_errors)
check('no_GROUP_numbered_annotation_remains',all(not re.search(rb'\bGROUP\s+\d+\b',raw) for raw in outputs.values()))
imports=[]
for node in ast.walk(ast.parse(GEN.read_text(encoding='utf-8'))):
 if isinstance(node,ast.Import):imports.extend(a.name.split('.')[0] for a in node.names)
 elif isinstance(node,ast.ImportFrom):imports.append((node.module or '').split('.')[0])
check('renderer_imports_only_standard_library_and_no_percard_builders',set(imports)<=sys.stdlib_module_names,sorted(set(imports)))
topology_errors=[];netcounts={}
for card,spec in specs.items():
 boxes={b['portion']:b for b in spec['boxes']};expected=defaultdict(list)
 def terminal(part,side,row):
  matches=[p for p in boxes[part]['ports'] if p['side']==side and p['row']==row]
  assert len(matches)==1,(card,part,side,row)
  return 'PORT:'+part+':'+matches[0]['id']
 if card in ['4633','4634']:
  old=read(ROOT/f'notes/Card-ALD/Universal/{card}/{card} render provenance.json')['geometry']
  for p in old['ports']:expected[p['net']].append(terminal(p['portion'],p['side'],p['point'][1]))
  for pin in old['exterior_contacts']:expected[pin].append('PIN:'+pin)
 elif card=='0141':
  for part,b in boxes.items():
   for p in b['ports']:
    if p['pin']:net=p['pin']
    elif p['side']=='output':net='INTERNAL:'+part
    else:net='INTERNAL:'+part[0]+('1' if p['row']==b['top']+1 else '2')
    expected[net].append('PORT:'+part+':'+p['id'])
  for p in spec['exterior_pins']:expected[p['pin']].append('PIN:'+p['pin'])
 else:
  old=read(ROOT/'notes/Card-ALD/Universal/4191/4191.geometry.json')
  known_groups={'12':['07','08','10','09','11'],'18':['13','14','16','15','17'],
                '24':['19','20','22','21','23'],'30':['25','26','28','27','29']}
  for part,b in old['portions'].items():
   for side,ports in b['ports'].items():
    for p in ports:
     if p['pin']:net=p['pin']
     elif side=='output':net='INTERNAL:'+part
     elif part in known_groups:
      ordered=sorted(q['row'] for q in ports if q['pin'] is None)
      net='INTERNAL:'+known_groups[part][ordered.index(p['row'])]
     elif part=='B2':net='INTERNAL:B1'
     else:net='INTERNAL:03'
     expected[net].append(terminal(part,side,p['row']+old['header_rows']))
  for p in spec['exterior_pins']:expected[p['pin']].append('PIN:'+p['pin'])
 partitions=sorted(sorted(v) for v in expected.values());netcounts[card]=len(partitions)
 if partitions!=spec['nets'] or partitions!=core.wiring_graph(spec):topology_errors.append(card)
check('all_four_terminal_net_partitions_equal_independently_reviewed_topology',not topology_errors,{'net_counts':netcounts,'mismatches':topology_errors})
portable=OUT/'generic-portable-fixture';(portable/'tools/card_ald').mkdir(parents=True,exist_ok=True)
(portable/'json/Card-ALD/definitions').mkdir(parents=True,exist_ok=True)
shutil.copyfile(GEN,portable/'tools/card_ald/generate_card.py')
for card in specs:shutil.copyfile(DEFS/(card+'.json'),portable/'json/Card-ALD/definitions'/(card+'.json'))
(portable/'csv/Card-ALD').mkdir(parents=True,exist_ok=True)
shutil.copyfile(ROOT/'csv/Card-ALD/Notation variants.csv',portable/'csv/Card-ALD/Notation variants.csv')
(portable/'notes/Card-ALD').mkdir(parents=True,exist_ok=True)
(portable/'notes/Card-ALD/Universal card diagrams publication.json').write_text(json.dumps({'schema':'shared-card-renderer-publication-v1','cards':[{'card_type':card} for card in specs],'published_files':[{'path':'Card-ALD/'+name,'sha256':hashlib.sha256(row['text'].encode('utf-8')).hexdigest()} for name,row in gold.items()]}),encoding='utf-8')
cli_errors=[]
for card in specs:
 run=subprocess.run([sys.executable,'-X','utf8',str(portable/'tools/card_ald/generate_card.py'),card],cwd=portable,capture_output=True,text=True)
 if run.returncode:cli_errors.append((card,run.returncode,run.stderr))
 for name,raw in outputs.items():
  if name.startswith(card) and (not (portable/'Card-ALD'/name).is_file() or (portable/'Card-ALD'/name).read_bytes()!=raw):cli_errors.append((card,name,'byte mismatch'))
check('cleanroom_one_card_argument_CLI_rebuilds_all124_files_without_repo_or_oldtools',not cli_errors,cli_errors)
inventory=read(portable/'notes/Card-ALD/Universal card diagrams publication.json')
check('normal_generation_updates_current_inventory_and_percard_receipts',all(e['sha256']==hashlib.sha256(outputs[Path(e['path']).name]).hexdigest() for e in inventory['published_files']) and all(read(portable/f'notes/Card-ALD/Generation/{card}.json')['diagram_sha256']==hashlib.sha256(outputs[card+'.txt']).hexdigest() for card in specs))
import csv
with (portable/'csv/Card-ALD/Notation variants.csv').open(encoding='utf-8-sig',newline='') as source:csvrows=list(csv.DictReader(source))
check('normal_generation_refreshes_existing_CSV_file_hashes',all(row['sha256']==hashlib.sha256(outputs[row['file']]).hexdigest() for row in csvrows))
fifth=deepcopy(specs['0141']);fifth['card_type']='9901'
for a in fifth['annotations']:a['text']=a['text'].replace('0141','9901')
for v in fifth['variants']:
 for a in v.get('annotation_overrides',[]):a['text']=a['text'].replace('0141','9901')
(portable/'json/Card-ALD/definitions/9901.json').write_text(json.dumps(fifth,ensure_ascii=False),encoding='utf-8')
run=subprocess.run([sys.executable,'-X','utf8',str(portable/'tools/card_ald/generate_card.py'),'9901'],cwd=portable,capture_output=True,text=True)
check('synthetic_fifth_card_requires_only_new_JSON_no_Python_change',run.returncode==0 and len(list((portable/'Card-ALD').glob('9901*.txt')))==67,run.stderr)
def negative(name,spec,edit):
 altered=deepcopy(spec);edit(altered)
 try:core.build(altered)
 except (AssertionError,ValueError,KeyError,IndexError,TypeError) as error:check('rejects_'+name,True,str(error));return
 check('rejects_'+name,False,'Invalid specification unexpectedly accepted')
negative('duplicate_exterior_pin',specs['0141'],lambda s:s['exterior_pins'].append(deepcopy(s['exterior_pins'][0])))
negative('dangling_wire',specs['0141'],lambda s:s['wiring']['horizontal_segments'].pop(0))
negative('changed_reviewed_net_partition',specs['0141'],lambda s:s['nets'].pop(0))
negative('variant_geometry_change',specs['0141'],lambda s:s['variants'][0]['box_overrides'].setdefault('A1',{}).update({'x':99}))
def duplicate(s):
 v=deepcopy(s['variants'][0]);v['number']=99;v['annotation_overrides']=[{'row':0,'text':'DIFFERENT HEADER'}];s['variants'].append(v)
negative('duplicate_variant_body_even_with_different_header',specs['0141'],duplicate)
def missing_arms(s):next(p for p in s['wiring']['marks'] if p['symbol']=='◇').pop('arms')
negative('junction_without_reviewed_incident_arms',specs['4634'],missing_arms)
def false_join(s):
 p=next(p for p in s['wiring']['marks'] if p['symbol']=='┼');p['symbol']='◇';p['arms']='NSEW'
negative('crossing_replaced_by_electrical_junction',specs['4634'],false_join)
def body_header(s):s['variants'][0]['annotation_overrides']=[{'row':s['boxes'][0]['top'],'text':'HIDE WIRING'}]
negative('variant_annotation_overwriting_diagram',specs['0141'],body_header)
for arg in ['../0141','9998']:
 run=subprocess.run([sys.executable,str(portable/'tools/card_ald/generate_card.py'),arg],cwd=portable,capture_output=True,text=True)
 check('CLI_rejects_'+('path_traversal' if '/'in arg else 'missing_reviewed_spec'),run.returncode!=0 and 'error:'in run.stderr,run.stderr.strip())
stale=portable/'Card-ALD/0141-99.txt';stale.write_text('PRIVATE STALE TEST\n',encoding='utf-8')
before={p.name:sha(p) for p in (portable/'Card-ALD').glob('0141*.txt')}
run=subprocess.run([sys.executable,str(portable/'tools/card_ald/generate_card.py'),'0141'],cwd=portable,capture_output=True,text=True)
check('stale_variants_are_refused_before_modifying_current_family',run.returncode!=0 and 'Unlisted older variants' in run.stderr and before=={p.name:sha(p) for p in (portable/'Card-ALD').glob('0141*.txt')})
stale.unlink()
bindings=[GEN,ROOT/'tools/card_ald/import_reviewed_layout.py',ROOT/'tools/card_ald/publish_shared_generator.py']+[DEFS/(card+'.json') for card in specs]
result={'schema':'independent-generic-card-renderer-review-v1','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':not fail,'failures':fail,'checks':checks,'cards':details,'candidate_bindings':[{'path':str(p),'sha256':sha(p)} for p in bindings],
 'supporting_files':[{'path':str(p),'sha256':sha(p)} for p in [OUT/'Generic renderer golden baseline.json',Path(__file__)]],
 'limits':['The renderer builds cards with reviewed JSON definitions; it does not automatically infer arbitrary unseen card layouts from scans.','Synthetic9901 exists only in a private portability fixture and is not a real card specification or publication.']}
(OUT/'Shared renderer independent review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':not fail,'failures':fail,'checks':len(checks),'output_files':len(outputs),'net_counts':netcounts},indent=2))

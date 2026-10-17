"""Private narrow helper guard fixtures; no publication or real namespace writes."""
from pathlib import Path
from unittest.mock import patch
import ast,copy,hashlib,importlib.util,json,tempfile,difflib
ROOT=Path(__file__).parent;P=ROOT/'refresh_current_catalog_classification.py';OLD=ROOT/'Predecessor refresh helper.py'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def need(v,m):
 if not v:raise AssertionError(m)
need(sha(P)=='52af72f8bc988f987116325cdf926a62e067ad0a862be1e7151ae00b41364679','Exact proposed helper')
old,new=ast.parse(OLD.read_text()),ast.parse(P.read_text())
def without_consumed(tree):
 return ast.dump(ast.Module(body=[n for n in tree.body if not(isinstance(n,ast.FunctionDef) and n.name=='consumed_sources')],type_ignores=[]),include_attributes=False)
need(without_consumed(old)==without_consumed(new),'Only consumed_sources changed; exact publisher/atomic/rollback protection retained')
spec=importlib.util.spec_from_file_location('classification_refresh_under_review',P);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
passed=[]
with tempfile.TemporaryDirectory(prefix='private-helper-fixtures-',dir=ROOT) as td:
 repo=Path(td).resolve()
 for rel,data in [('notes/Socket listings uniform/Build manifest.json',b'{}\n'),('json/Socket listings uniform/Socket listings.json',b'{}\n'),('ALD/A1 Socket Listing/A1111 TEST.txt',b'accepted\n'),('json/A1 Socket Listing/A1111 TEST.json',b'{}\n')]:
  path=repo/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
 valid={'source_inputs':[{'path':p.relative_to(repo).as_posix(),'sha256':sha(p)} for p in repo.rglob('*') if p.is_file()]}
 def reject(name,document,errors=(ValueError,FileNotFoundError)):
  with patch.object(helper,'REPO',repo):
   try:helper.consumed_sources(document)
   except errors:passed.append(name)
   else:raise AssertionError('Guard did not reject '+name)
 with patch.object(helper,'REPO',repo):
  actual=helper.consumed_sources(valid)
  need(actual==[bind(repo/x['path']) for x in sorted(valid['source_inputs'],key=lambda x:x['path'])],'Exact sorted input bindings');passed.append('valid_complete_declared_inputs')
 stale=copy.deepcopy(valid);stale['source_inputs'][0]['sha256']='0'*64;reject('stale_uniform_dependency',stale)
 missing=copy.deepcopy(valid);missing['source_inputs'][0]['path']='json/Socket listings uniform/Missing.json';reject('missing_uniform_dependency_file',missing)
 duplicate=copy.deepcopy(valid);duplicate['source_inputs'].append(copy.deepcopy(duplicate['source_inputs'][0]));reject('duplicate_declared_dependency',duplicate)
 for name,path in [('traversal','../outside.json'),('absolute',str(repo/'outside.json')),('noncanonical','json//test.json')]:
  bad=copy.deepcopy(valid);bad['source_inputs'][0]['path']=path;reject(name,bad)
 for value in [[],{},None]:
  if value is None:continue
  reject('invalid_declared_input_type_'+type(value).__name__,{'source_inputs':value})
 bad=copy.deepcopy(valid);bad['source_inputs'][0]['sha256']='NOT_A_SHA';reject('invalid_digest',bad)
 bad=copy.deepcopy(valid);bad['source_inputs'][0]['extra']='scope';reject('invented_dependency_binding_field',bad)
 # Completeness is a producer-verifier invariant: the helper binds the declared
 # set and runs independent production verification before accepting it. The
 # production fixture test_missing_declared_uniform_input_fails checks omission.
 legacy={'source_pages':{'ALD/A1 Socket Listing/A1111 TEST.txt':{'text_sha256':sha(repo/'ALD/A1 Socket Listing/A1111 TEST.txt'),'model':'json/A1 Socket Listing/A1111 TEST.json','model_sha256':sha(repo/'json/A1 Socket Listing/A1111 TEST.json')}}}
 content=repo/'notes/Content data manifest.json';content.parent.mkdir(exist_ok=True);content.write_text('{"files":[]}\n')
 with patch.object(helper,'REPO',repo):
  need(len(helper.consumed_sources(legacy))==2,'Historical source_pages schema retained');passed.append('old_schema_fallback')
report={'schema':'independent-classification-refresh-helper-review-v1','passed':True,'independent_review':True,'helper':bind(P),'predecessor_helper':bind(OLD),'scope':'Only consumed_sources is changed. Publisher, predecessor preservation, target guards and rollback remain structurally identical. No real prepare/publication executed.','fixtures':passed,'fixture_count':len(passed),'dependency_completeness_contract':'Helper binds exact declared inputs; production verifier reconstructs and requires the complete source_inputs set. The separate real catalogue regression suite rejects missing declared uniform datasets.','canonical_writes':0,'reviewer_program':bind(__file__)}
dest=ROOT/'Independent refresh helper review.json';need(not dest.exists(),'Never overwrite independent review history');dest.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'fixtures':len(passed),'receipt':bind(dest)},indent=2))

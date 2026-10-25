"""Read-only portable auxiliary runtime inventory verifier.
The caller pins the registry SHA; a successful inventory is never admission.
"""
from pathlib import Path, PurePosixPath
import argparse,hashlib,json,re,sys
sys.dont_write_bytecode=True
REGISTRY_PATH='notes/Auxiliary formats/Release registry.json'
CHECKER_PATH='tools/references/verify_auxiliary_release.py'
SCHEMA_PATH='Contracts/auxiliary_release.schema.json'
RUNTIME_PATHS=['Contracts/auxiliary_catalogue_contracts.py', 'Contracts/catalogue_identity.schema.json', 'Contracts/held_derived_card.schema.json', 'Contracts/legacy_index_mutation_guard.py', 'Contracts/typed_current_status_gate.py', 'auxiliary_held_cards.py', 'auxiliary_held_contracts.py', 'tools/card_ald/adopt_card_layout.py', 'tools/card_ald/audit_card_uses.py', 'tools/card_ald/card_source.py', 'tools/card_ald/generate_card.py', 'tools/card_ald/publish_card_candidate.py', 'tools/card_ald/publish_shared_generator.py', 'tools/card_ald/publish_universal_cards.py', 'tools/references/build_current_card_catalog.py', 'tools/references/current_card_identity.py', 'tools/references/verify_current_card_catalog.py', 'tools/references/verify_uniform_socket_listings.py']
GATE_PATHS=['tools/card_ald/build_card_data.py', 'tools/normalization/ALD page schema.json', 'tools/normalization/read_page.py', 'tools/reviews/current_checkpoint.py']
FORMATS=['card-ald-generation-v1', 'current-card-catalog-build-v2', 'current-card-catalog-unresolved-identities-v1', 'held-derived-card-audit-findings-v1', 'held-derived-card-capture-v1', 'held-derived-card-generation-v2', 'held-derived-card-index-v3', 'held-derived-card-source-event-v1', 'held-derived-card-source-proposal-v1']
SCOPE={'kind':'runtime-and-format-inventory-only','format_inventory':'auxiliary-extensions-and-legacy-generation-consumed-not-all-repository-schemas','source_contract':'ibm360-ald-page-v3','source_contract_change':False,'native_identity_change':False,'family_classifications':'not-contained-or-modified','ordinary_typed_publication_supported':False}
POLICY={'authority':'inventory-only-no-installation-or-publication-authority','legacy_mutators':'reject-typed-index-before-canonical-write','unresolved_physical_contact':'not-anonymous-and-not-inferred-from-printed-alias','source_unknown_identity':'retain-unresolved-never-select-portion','trust_anchor':'caller-pinned-registry-sha256','evidence':'not-carried-in-public-inventory'}

def need(ok,message):
 if not ok:raise ValueError(message)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def pairs(items):
 result={}
 for key,value in items:
  need(key not in result,'Duplicate JSON key: '+key);result[key]=value
 return result
def constant(value):raise ValueError('Nonfinite JSON value: '+value)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=constant)
def exact(value,keys,label):need(isinstance(value,dict)and set(value)==set(keys),'Missing or unknown '+label+' fields')
def safe_path(value):
 need(isinstance(value,str)and value and value.isascii(),'Path must be nonempty ASCII relative POSIX')
 need('\\'not in value and ':'not in value and not value.startswith('/'),'Absolute or backslash path')
 parts=value.split('/')
 need(all(x and x not in ('.','..')and x==x.strip()and not x.endswith('.')for x in parts),'Noncanonical or traversal path')
 need(PurePosixPath(value).as_posix()==value,'Noncanonical path')
 return value
def checked_file(root,path):
 safe_path(path);file=root/path
 component=root
 for part in path.split('/'):
  component=component/part
  try:attributes=getattr(component.lstat(),'st_file_attributes',0)
  except FileNotFoundError:raise ValueError('Missing path component: '+path)
  need(not component.is_symlink()and not attributes&0x400,'Symlink/reparse/junction component rejected: '+path)
 need(file.is_file(),'Missing file: '+path)
 need(file.resolve().is_relative_to(root),'File escapes release root: '+path)
 return file
def inventory(value,expected,label,root):
 need(isinstance(value,list)and len(value)==len(expected),'Incorrect '+label+' inventory count')
 seen=set();actual=[]
 for row in value:
  exact(row,('path','sha256'),label+' binding');path=safe_path(row['path']);key=path.casefold()
  need(key not in seen,'Duplicate/case-alias inventory path');seen.add(key)
  need(isinstance(row['sha256'],str)and re.fullmatch('[0-9a-f]{64}',row['sha256']),'Invalid SHA256')
  file=checked_file(root,path);need(digest(file)==row['sha256'],'File hash mismatch: '+path);actual.append(path)
 need(actual==sorted(expected),'Unknown, missing or reordered '+label+' paths')
 return seen

def schema_document():
 binding={'type':'object','additionalProperties':False,'required':['path','sha256'],'properties':{'path':{'type':'string'},'sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'}}}
 def inv(paths):return {'type':'array','minItems':len(paths),'maxItems':len(paths),'uniqueItems':True,'items':{**binding,'properties':{**binding['properties'],'path':{'enum':sorted(paths)}}}}
 properties={'schema':{'const':'ibm360-auxiliary-release-registry-v1'},'release_id':{'const':'auxiliary-consumers-004'},'scope':{'const':SCOPE},'policy':{'const':POLICY},'formats':{'const':FORMATS},'authoritative_index_path':{'const':'notes/Card-ALD/Universal card diagrams publication.json'},'runtime_files':inv(RUNTIME_PATHS),'unchanged_gates':inv(GATE_PATHS),'companions':inv([CHECKER_PATH,SCHEMA_PATH])}
 return {'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:ibm360:auxiliary-release-registry:v1','type':'object','additionalProperties':False,'required':sorted(properties),'properties':properties}

def verify(root,expected_registry_sha,registry=None):
 root=Path(root).resolve();need(root.is_dir(),'Release root missing')
 need(isinstance(expected_registry_sha,str)and re.fullmatch('[0-9a-f]{64}',expected_registry_sha),'Caller must pin registry SHA256')
 canonical=root/REGISTRY_PATH;path=Path(registry).resolve()if registry is not None else canonical
 need(path.resolve()==canonical.resolve(),'Registry must occupy canonical release-relative path')
 need(path.resolve().is_relative_to(root),'Registry escapes release root')
 need(digest(path)==expected_registry_sha,'Registry SHA256 differs from caller pin')
 doc=read(path);expected=schema_document();exact(doc,expected['properties'],'registry')
 for key in ('schema','release_id','scope','policy','formats','authoritative_index_path'):
  need(json.dumps(doc[key],sort_keys=True,separators=(',',':'))==json.dumps(expected['properties'][key]['const'],sort_keys=True,separators=(',',':')),'Unsupported or forged '+key)
 seen=set()
 for key,paths in (('runtime_files',RUNTIME_PATHS),('unchanged_gates',GATE_PATHS),('companions',[CHECKER_PATH,SCHEMA_PATH])):
  current=inventory(doc[key],paths,key,root);need(not seen.intersection(current),'Cross-inventory duplicate/case alias');seen.update(current)
 checker=checked_file(root,CHECKER_PATH)
 need(Path(__file__).resolve()==checker.resolve(),'Executed checker is outside selected release root')
 need(json.dumps(read(checked_file(root,SCHEMA_PATH)),sort_keys=True,separators=(',',':'))==json.dumps(expected,sort_keys=True,separators=(',',':')),'Schema does not implement exact closed companion contract')
 return {'schema':'auxiliary-release-inventory-check-v1','release_id':doc['release_id'],'runtime_files_verified':len(RUNTIME_PATHS),'unchanged_gates_verified':len(GATE_PATHS),'companions_verified':2,'classification':'runtime-inventory-only','installation_authorized':False,'publication_authorized':False,'family_classifications_changed':False}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--expected-registry-sha',required=True);p.add_argument('--registry',type=Path);a=p.parse_args()
 try:print(json.dumps(verify(a.root,a.expected_registry_sha,a.registry),sort_keys=True));return 0
 except (ValueError,OSError,TypeError,KeyError)as exc:print(str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())

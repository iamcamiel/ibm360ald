import argparse,ast,hashlib,importlib.util,json,sys,datetime
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=P.parents[4]/"ibm360ald"
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def ptr(o,p):
 for k in p.strip("/").split("/"):o=o[int(k)]if isinstance(o,list)else o[k]
 return o
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--preparation",required=True);ap.add_argument("--sha",required=True);ap.add_argument("--output",required=True);args=ap.parse_args();prep=Path(args.preparation);out=Path(args.output);assert not out.exists();assert sha(prep)==args.sha
 j=read(prep);checks=0
 def check(c,msg):
  nonlocal checks
  checks+=1
  if not c:raise AssertionError(msg)
 for item in j["files"]:
  for k in ["before","after","private_candidate"]:
   b=item.get(k)
   if b:check(sha(b["path"])==b["sha256"],str((k,b["path"])))
 sys.path.insert(0,str(ROOT/"tools/card_ald"));import build_card_data as B
 old=ast.parse((P/"Predecessors/build_card_data.py").read_text("utf8"));new=ast.parse((ROOT/"tools/card_ald/build_card_data.py").read_text("utf8"))
 def functions(t):return{n.name:ast.dump(n,include_attributes=False)for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 a,b=functions(old),functions(new);check([k for k in a if a[k]!=b[k]]==["derive_semantics"],"changed existing builder functions")
 check(sha(ROOT/"tools/card_ald/render_composite_card.py")=="b9933f9ca8cbeebb04457bb5192514278710ed39c6cfd22fd9acc8d610f0c3da","renderer/router drift")
 baseline=read(P.parent/"blocker-remediation-20261017/Classification recheck/Rerun frozen inputs.json")
 for item in baseline["protected_reviewed_outputs"]:
  path=Path(item["path"]);path=path if path.is_absolute()else ROOT/path;check(sha(path)==item["sha256"],"reviewed output changed: "+str(path))
 protected={Path(x["path"]).resolve()for x in baseline["protected_reviewed_outputs"]}
 check(protected=={p.resolve()for branch in["Card-ALD","json/Card-ALD"]for p in(ROOT/branch).rglob("*")if p.is_file()},"reviewed output namespace drift")
 planned={Path(x["after"]["path"]).resolve():x["after"]["sha256"]for x in j["files"]}
 tool_inventory={Path(x["path"]).resolve():x["sha256"]for x in baseline["tool_sources"]};tool_inventory.update(planned)
 actual_tools={p.resolve()for p in(ROOT/"tools/card_ald").rglob("*.py")}
 check(actual_tools==set(tool_inventory),"unexpected card tool namespace change")
 for path,digest in tool_inventory.items():check(sha(path)==digest,"unexpected card tool change: "+str(path))
 heldpath=P.parent/"blocker-remediation-20261017/internal-net-assembly/Held mixed-port raw source checks.json";held=read(heldpath);check(sha(heldpath)=="c00e8474dc7fda817626636756c5d12c2c526fc4418cb987da8d341f00a2f6bd","held evidence drift")
 cases=[]
 for case in held["cases"]:
  path=Path(case["source_model"]["path"]);check(sha(path)==case["source_model"]["sha256"],"held source drift");m=read(path)
  for side,refkey,np,pp,expected in [("output","driver","source_node_pointer","source_port_pointer","source_output_port"),("input","target","target_node_pointer","target_port_pointer","source_input_port")]:
   node=ptr(m,case[np]);raw=ptr(m,case[pp]);check(raw==case[expected],"immutable raw pointer mismatch")
   result=B.resolve_net_port(node,case["claim"]["evidence"][refkey],side)
   check(result["status"]=="numbered","held endpoint not numbered")
   check(result["raw_port"]==raw,"resolved wrong raw port")
   check(result["port_index"]==int(case[pp].split("/")[-1]),"resolved wrong port index")
  cases.append({"card":case["card_type"],"page":case["page"],"driver":case["claim"]["evidence"]["driver"],"target":case["claim"]["evidence"]["target"]})
 manifest=read(ROOT/"notes/Content data manifest.json");check(sha(ROOT/"notes/Content data manifest.json")==held["accepted_content_manifest"]["sha256"],"source epoch changed")
 source_count=0
 for item in manifest["files"]:
  if item.get("role")in {"Published page content model","Published page transcription","Published page text","Published UTF-8 page transcription"}or item["path"].startswith("ALD/"):
   check(sha(ROOT/item["path"])==item["sha256"],"source manifest hash: "+item["path"]);source_count+=1
 inventory_path=ROOT/"notes/Repository records manifest.json";check(sha(inventory_path)=="ae316dd60122b76e11b42ba8d169519d39a7086a8f41d3409848b3c037f854f9","accepted inventory epoch changed")
 inventory=read(inventory_path);source_text_count=0
 for item in inventory["files"]:
  if item["path"].startswith("ALD/")and item["path"].endswith(".txt"):
   check(sha(ROOT/item["path"])==item["sha256"],"source TXT changed: "+item["path"]);source_text_count+=1
 derivations=[]
 for card in sorted({c["card_type"]for c in held["cases"]}):
  cat,obs,models,power,bindings,changes,u=B.load_evidence(card,{})
  before=json.dumps(models,ensure_ascii=False,sort_keys=True);model,_=B.derive_semantics(card,cat,obs,models,power,u)
  check(before==json.dumps(models,ensure_ascii=False,sort_keys=True),"derive mutated raw models")
  for case in [c for c in held["cases"]if c["card_type"]==card]:
   ev=case["claim"]["evidence"]
   rejected=[r for r in model["rejected_installation_or_unmapped_edges"]if r.get("page")==ev["page"]and r.get("driver")==ev["driver"]and r.get("target")==ev["target"]]
   check(any("strap"in r["reason"]for r in rejected),"held numbered strap rejected for wrong reason")
  derivations.append({"card":card,"edges":len(model["edges"]),"unresolved_endpoint_diagnostics":sum(x.get("kind")=="net endpoint identity unresolved"for x in u)})
 check(sha(prep)==args.sha,"preparation changed during review")
 for item in j["files"]:check(sha(item["after"]["path"])==item["after"]["sha256"],"candidate changed during review")
 report={"schema":"independent-parser-source-scope-replay-v1","passed":True,"independent_review":True,"preparation":{"path":str(prep),"sha256":args.sha},"reviewer":{"path":str(Path(__file__).resolve()),"sha256":sha(__file__)},"check_count":checks,"held_occurrences":len(cases),"source_files_hash_verified":source_count,"source_texts_hash_verified":source_text_count,"derivations":derivations,"reviewed_outputs_verified":len(baseline["protected_reviewed_outputs"]),"card_tool_namespace_verified":len(tool_inventory),"raw_source_or_reviewed_diagram_mutations":False,"DR191_topology_correction_claimed":False,"created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8");print(out,sha(out),checks)
if __name__=="__main__":main()


"""Publish a source-bound independently reviewed card candidate through the shared generator.

python tools/card_ald/publish_card_candidate.py CARD --definition FILE
    --overrides FILE --audit FILE --review FILE [--check]

The independent review must pass and bind the exact definition, supplement and
use-audit bytes in candidate_bindings. A variant_index binding supplies the
complete witnessed notation index. No card-specific branches are used.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import csv,io,json,re,sys
from pathlib import Path
import build_card_data
import generate_card as renderer
import audit_card_uses

ROOT=renderer.ROOT

def read(path):return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def digest(path):return renderer.digest(Path(path).read_bytes())
def write_json(path,value):renderer.write_protected(Path(path),(json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode("utf8"))
def resolved(root,value):
 p=Path(value);return p.resolve()if p.is_absolute()else(root/p).resolve()
def binding(path):return dict(path=str(Path(path).resolve()),sha256=digest(path))
def binding_list(value):
 return list(value.values())if isinstance(value,dict)else list(value or [])
def verify_binding(root,item):
 path=resolved(root,item.get("path",item.get("file","")))
 assert path.is_file()and digest(path)==item["sha256"],("Stale or missing bound evidence",str(path))
 return path

def recursive_bindings(root,value):
 if isinstance(value,dict):
  if("path"in value or"file"in value)and value.get("sha256"):
   verify_binding(root,value)
  for child in value.values():recursive_bindings(root,child)
 elif isinstance(value,list):
  for child in value:recursive_bindings(root,child)

def review_inputs(root,review,paths):
 receipt=read(review)
 assert receipt.get("passed")is True and not receipt.get("failures"),"Independent review has not passed"
 candidates=binding_list(receipt.get("candidate_bindings"))
 assert candidates,"Independent review must name exact candidate_bindings"
 bound={str(verify_binding(root,b)):b["sha256"]for b in candidates}
 for path in paths:
  assert bound.get(str(path.resolve()))==digest(path),("Candidate not covered by independent review",str(path))
 for b in binding_list(receipt.get("supporting_files")):verify_binding(root,b)
 return receipt,candidates

def other_card_state(root,card):
 result={}
 for folder,pattern in[(root/"Card-ALD","*.txt"),(root/"notes/Card-ALD/Generation","*.json")]:
  if not folder.exists():continue
  for path in folder.glob(pattern):
   if re.fullmatch(r"\d{4}(?:-\d+)?",path.stem)and not path.stem.split("-")[0]==card:
    result[path]=path.read_bytes()
 return result

def index_rows(root,card):
 path=root/"csv/Card-ALD/Notation variants.csv"
 if not path.exists():return []
 with path.open(encoding="utf-8-sig",newline="")as stream:
  return[e for e in csv.DictReader(stream)if e["card_type"]!=card]

def invoke_default_generator(root,card):
 oldroot,oldargv=renderer.ROOT,sys.argv
 try:
  renderer.ROOT=root
  sys.argv=[str(Path(renderer.__file__)),card]
  renderer.main()
 finally:renderer.ROOT,sys.argv=oldroot,oldargv

def publish(card,definition,overrides,audit,review,root=ROOT,check_only=False):
 assert re.fullmatch(r"[0-9]{4}",str(card)),"Use exactly four ASCII digits"
 root=Path(root).resolve();definition,overrides,audit,review=map(lambda p:Path(p).resolve(),[definition,overrides,audit,review])
 approval,bound=review_inputs(root,review,[definition,overrides,audit])
 spec,supplement,source_audit=map(read,[definition,overrides,audit])
 assert all(d.get("card_type")==card for d in[spec,supplement,source_audit]),"Card identity differs across candidates"
 outputs,checks=renderer.build(spec)
 assert source_audit.get("schema")=="card-use-audit-v1"and source_audit.get("read_only")is True
 assert not source_audit.get("review")and source_audit["summary"]["needs_review"]==0,"Unresolved source findings prevent publication"
 assert source_audit["definition"]["sha256"]==digest(definition),"Audit is for another definition"
 assert source_audit.get("overrides",{}).get("sha256")==digest(overrides),"Audit is for another supplement"
 recursive_bindings(root,spec.get("provenance",{}));recursive_bindings(root,supplement.get("source_bindings",[]));recursive_bindings(root,source_audit)
 # Re-run all source comparisons. A fabricated or stale zero-findings JSON cannot pass.
 fresh=audit_card_uses.audit(card,root=root,definition_path=definition,overrides_path=overrides)
 assert not fresh["review"]and fresh["summary"]["needs_review"]==0,"Current sources no longer pass the card-use audit"
 for key in["catalog","source_bindings","occurrences","coverage_limitations","known_reviewed_source_corrections"]:
  assert fresh.get(key)==source_audit.get(key),("Current use audit differs",key)
 rebuilt,evidence=build_card_data.build(card,root=root,overrides_path=overrides)
 assert rebuilt is not None and renderer.build(rebuilt)[0]==outputs,"Default data builder does not reproduce the reviewed candidate"
 variant_index=None;index_source=None
 if approval.get("variant_index"):
  index_source=verify_binding(root,approval["variant_index"])
  assert str(index_source)in{str(verify_binding(root,b))for b in bound+binding_list(approval.get("supporting_files"))},"Variant index lacks reviewed binding"
  variant_index=read(index_source)
  assert variant_index.get("card_type")==card
  indexed={int(v["number"]):v for v in variant_index.get("variants",[])}
  assert set(indexed)=={v["number"]for v in spec["variants"]},"Witness index does not cover every rendered variant"
  for v in spec["variants"]:
   w=indexed[v["number"]]
   assert w.get("witnesses")and w.get("source_pages")and w.get("source_locations"),"Numbered variants require source witnesses"
   if"variant_definition"in w:assert w["variant_definition"]==v,"Witness pattern differs from rendered variant"
 elif spec["variants"]:
  raise AssertionError("An independently bound variant_index is required for numbered notation variants")
 stale=[p.name for p in(root/"Card-ALD").glob(card+"-[0-9]*.txt")if re.fullmatch(card+r"-\d+\.txt",p.name)and p.name not in outputs]
 assert not stale,("Unlisted older notation files require review",stale)
 assert not list((root/"Card-ALD").glob(card+".*.txt")),"Unexpected card namespace"
 summary=dict(card_type=card,files=len(outputs),variants=len(spec["variants"]),source_occurrences=fresh["summary"]["occurrences"],renderer_checks=checks,coverage_limitations=fresh["summary"]["coverage_limitations"],checked=True,published=False)
 if check_only:return summary
 stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ");run=stamp+"-"+digest(review)[:12]
 accepted=root/"notes/Card-ALD/Generation/Accepted candidates"/run/card
 history=root/"notes/Card-ALD/history"/("Before candidate publication "+run)/card
 relatives=[f"json/Card-ALD/definitions/{card}.json",f"json/Card-ALD/build-overrides/{card}.json",f"json/Card-ALD/{card}.json",
  f"notes/Card-ALD/Notation witnesses/{card}.json",f"notes/Card-ALD/Generation/{card}.json",f"notes/Card-ALD/{card} drawing provenance.json",f"notes/Card-ALD/{card} diagram publication receipt.json",
  "csv/Card-ALD/Notation variants.csv","notes/Card-ALD/Universal card diagrams publication.json",*["Card-ALD/"+name for name in outputs]]
 before={root/rel:(root/rel).read_bytes()if(root/rel).exists()else None for rel in relatives}
 other=other_card_state(root,card);other_index=index_rows(root,card)
 accepted.mkdir(parents=True,exist_ok=False);history.mkdir(parents=True,exist_ok=False)
 for path,raw in before.items():
  if raw is not None:renderer.write_protected(history/path.relative_to(root),raw)
 evidence_copies=[]
 for label,path in[("Definition.json",definition),("Reviewed supplement.json",overrides),("Source use audit.json",audit),("Independent review.json",review)]+([("Observed notation index.json",index_source)]if index_source else[]):
  dest=accepted/label;renderer.write_protected(dest,path.read_bytes());evidence_copies.append(dict(original=binding(path),accepted=binding(dest)))
 for item in binding_list(approval.get("supporting_files")):
  path=verify_binding(root,item)
  if path.is_relative_to(root)or path in[definition,overrides,audit,review,index_source]or path.suffix.lower()in[".tif",".tiff",".pdf"]:continue
  dest=accepted/"Supporting evidence"/(digest(path)[:16]+"-"+path.name)
  renderer.write_protected(dest,path.read_bytes());evidence_copies.append(dict(original=binding(path),accepted=binding(dest)))
 try:
  renderer.write_protected(root/f"json/Card-ALD/definitions/{card}.json",definition.read_bytes())
  renderer.write_protected(root/f"json/Card-ALD/build-overrides/{card}.json",overrides.read_bytes())
  if index_source:renderer.write_protected(root/f"notes/Card-ALD/Notation witnesses/{card}.json",index_source.read_bytes())
  invoke_default_generator(root,card)
  assert all((root/"Card-ALD"/name).read_bytes()==raw for name,raw in outputs.items()),"Generated family differs from reviewed build"
  assert all(path.read_bytes()==raw for path,raw in other.items()),"Unrelated card body or generation receipt changed"
  assert index_rows(root,card)==other_index,"Unrelated notation index rows changed"
  result=dict(schema="reviewed-card-candidate-publication-v1",created_utc=datetime.now(timezone.utc).isoformat(),**summary)
  result.update(published=True,independent_review=binding(accepted/"Independent review.json"),accepted_evidence=evidence_copies,
   outputs=[dict(path="Card-ALD/"+name,sha256=renderer.digest(raw))for name,raw in outputs.items()],
   preserved_predecessors=[dict(path=str((history/path.relative_to(root)).relative_to(root)),original_path=str(path.relative_to(root)),sha256=renderer.digest(raw))for path,raw in before.items()if raw is not None],
   default_generator_used=True,unrelated_cards_and_index_rows_unchanged=True,publisher=binding(Path(__file__)))
  write_json(accepted/"Publication receipt.json",result)
 except Exception:
  for path,raw in before.items():
   if raw is not None:renderer.write_protected(path,raw)
   elif path.exists():path.unlink()
  raise
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("card_type")
 for name in["definition","overrides","audit","review"]:p.add_argument("--"+name,type=Path,required=True)
 p.add_argument("--root",type=Path,default=ROOT,help="Repository root; useful for isolated publication fixtures")
 p.add_argument("--check",action="store_true",help="Validate all evidence and regeneration without publication")
 a=p.parse_args();print(json.dumps(publish(a.card_type,a.definition,a.overrides,a.audit,a.review,root=a.root,check_only=a.check),ensure_ascii=False))
if __name__=="__main__":main()

from pathlib import Path
from collections import Counter,defaultdict
from hashlib import sha256
from datetime import datetime,timezone
import json,re,sys
ROOT=Path("D:/Github/IBM360/ibm360ald");BASE=Path(__file__).parent
sys.path.insert(0,str(ROOT/"tools/card_ald"))
import generate_card as G,build_card_data as B,audit_card_uses as A,collect_card_variants as C
CACHE={};verified={};failures=[];checks=[]
def read(p):
 p=Path(p).resolve()
 if p not in CACHE:CACHE[p]=json.loads(p.read_text(encoding="utf-8-sig"))
 return CACHE[p]
def digest(p):return sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return dict(path=str(Path(p).resolve()),sha256=digest(p))
def need(condition,label,detail=None):
 if not condition:failures.append(dict(check=label,detail=detail))
def pathof(b):
 p=Path(b.get("path",b.get("file","")));return p if p.is_absolute()else ROOT/p
def verify(b):
 p=pathof(b).resolve()
 if str(p)not in verified:
  actual=digest(p)if p.is_file()else None;verified[str(p)]=actual
 need(verified[str(p)]==b["sha256"],"current bound bytes",str(p))
 return p
def recursive(value):
 if isinstance(value,dict):
  if("path"in value or"file"in value)and value.get("sha256"):verify(value)
  for v in value.values():recursive(v)
 elif isinstance(value,list):
  for v in value:recursive(v)
def loc(v):
 m=re.fullmatch(r"(?:02)?([ABCEKL])-([A-Z]\d)([A-Z]\d)(?:[BT])?",str(v));return"02"+m[1]+"-"+m[2]+m[3]if m else None
CONTACT=re.compile(r"\d*([BDGJ](?:0[2-9]|1[0-3]))(?:[✲*]?T?|[✲*])$")
def actual_contact(port):
 values={m[1]for field in["pin","printed_pin","printed_label","physical_pin","physical_pin_candidate"]if port.get(field)is not None for m in[CONTACT.fullmatch(str(port[field]).strip())]if m}
 need(len(values)<=1,"no contradictory pin mirrors",port)
 return next(iter(values))if len(values)==1 else None
prep=read(BASE/"Candidate preparation.json");recursive(prep)
dp,op,ap,ip=[pathof(prep[k])for k in["definition","overrides","audit","variant_index"]]
spec,overlay,audit,index=map(read,[dp,op,ap,ip]);outputs,renderer_checks=G.build(spec)
need(spec["card_type"]==overlay["card_type"]==audit["card_type"]==index["card_type"]=="3308","typed3308 namespace")
need(len(spec["boxes"])==10 and{b["portion"]for b in spec["boxes"]}==set("ABCDEFGHJK"[i]+"1"for i in range(10)),"all ten3308portions")
need(spec["power_contacts"]=={"D08":"GROUND","D03":"+3V","B06":"-3V","B11":"+6V"},"single SLT supplies listed separately")
need(len(spec["exterior_pins"])==20 and len({p["pin"]for p in spec["exterior_pins"]})==20,"all20signal contacts once exterior")
need(all(len(net)==2 and sum(t.startswith("PIN:")for t in net)==1 and sum(t.startswith("PORT:")for t in net)==1 for net in spec["nets"]),"ten independent inverters; no invented interportion connection")
manual=read(ROOT/"notes/Card-ALD/Manual canonical circuit forms.json")["circuits"]["U03AF"]
need(manual["canonical_form"]=={"primary_function":"A","all_input_triangles":False,"all_output_triangles":True,"basis":manual["canonical_form"]["basis"]},"manual AND-inverter canonical definition")
need(all(b["function"]=="A"and b["circuit_identifier"]=="U03AF"and len(b["ports"])==2 and all(p["triangle"]==(p["side"]=="output")for p in b["ports"])for b in spec["boxes"]),"canonical3308manual symbols")
need(spec["canvas"].get("grid_step")==1 and all(b["height"]==7 for b in spec["boxes"]),"free-row seven-line boxes")
need(index.get("publication_policy")=="complete-witnesses","explicit complete-witness publication policy")
selected=index["variants"];excluded=index["excluded_partial_profiles"];need(len(selected)==78 and len(excluded)==72,"78complete profiles;72partial-only preserved")
need({v["number"]for v in spec["variants"]}=={v["number"]for v in selected},"all and only selected variants rendered")
need(not({v["number"]for v in selected}&{v["number"]for v in excluded}),"excluded profiles never renumbered into selection")
need(all(v["complete_witnesses"]>0 for v in selected)and all(v["complete_witnesses"]==0 for v in excluded),"selected complete; excluded partial-only")
need(all(next(vv for vv in spec["variants"]if vv["number"]==v["number"])==v["variant_definition"]for v in selected),"definition has exact independently indexed notation overrides")
recursive(spec.get("provenance",{}));recursive(overlay["source_bindings"]);recursive(audit);recursive(index)
# Reconstruct observed fields independently of the collector's mapping/merge implementation.
boxes={b["portion"]:b for b in spec["boxes"]};all_occurrences=Counter();complete_verified=0;partial_verified=0
for profile in selected+excluded:
 variant=profile["variant_definition"];effective={portion:dict(function=variant.get("box_overrides",{}).get(portion,{}).get("function",box["function"]),**{p["id"]:variant.get("box_overrides",{}).get(portion,{}).get("port_triangles",{}).get(p["id"],p["triangle"])for p in box["ports"]})for portion,box in boxes.items()}
 full_count=0
 for w in profile["witnesses"]:
  observed=defaultdict(dict)
  for record in w["nodes"]:
   doc=read(verify(record["model"]));node=next(n for n in doc["nodes"]if n["id"]==record["node"])
   all_occurrences[doc["page"],node["id"]]+=1
   need(node["card_type"]=="3308"and loc(node.get("location"))==w["location"],"same current physical card only",(doc["page"],node["id"]))
   portion=node["portion"];box=boxes[portion]
   need(node["unit"]==box["circuit_identifier"],"witness circuit identity",(doc["page"],node["id"]))
   values={"function":str(node["function"]).strip()}
   for port in node.get("pins",[]):
    pin=actual_contact(port)
    if pin in spec["power_contacts"]:continue
    if pin is None:continue
    ports=[p for p in box["ports"]if p["pin"]==pin and p["side"]==port["side"]]
    need(len(ports)==1,"witness unique pin mapping",(doc["page"],node["id"],pin))
    if not ports:continue
    triangle=True if port.get("border_marker")=="◺"else bool(port.get("triangle"))
    values[ports[0]["id"]]=triangle
   for field,value in values.items():
    need(field not in observed[portion]or observed[portion][field]==value,"compatible cross-page fields only",(w["location"],portion,field))
    observed[portion][field]=value
    need(effective[portion][field]==value,"profile agrees with actual source field",(profile["number"],doc["page"],node["id"],field))
  full=set(observed)==set(boxes)and all(set(values)=={"function"}|{p["id"]for p in boxes[portion]["ports"]}for portion,values in observed.items())
  need(full==w["complete_field_observation"],"independently recomputed complete witness",(profile["number"],w["location"]))
  full_count+=full;complete_verified+=full;partial_verified+=not full
  need(all(values==w["observed_fields"].get(portion)for portion,values in observed.items()),"stored observed fields equal reconstructed fields",(profile["number"],w["location"]))
 need(full_count==profile["complete_witnesses"],"complete witness count accurate",profile["number"])
 need(len(profile["witnesses"])-full_count==profile["partial_witnesses"],"partial witness count accurate",profile["number"])
need(not index["canonical_pattern_witnesses"],"no omitted canonical-pattern witnesses")
catalog=read(ROOT/"json/Card types current/3308.json");catalog_ids={(o["page"],o["node"])for o in catalog["diagram_occurrences"]}
audit_ids={(o["page"],o["block"])for o in audit["occurrences"]}
need(set(all_occurrences)==catalog_ids==audit_ids and len(all_occurrences)==2486 and all(v==1 for v in all_occurrences.values()),"all2486current uses covered exactly once; none omitted")
need(len(index["model_bindings"])==len(audit["source_bindings"])==668,"668 current pages covered")
need(not audit["review"]and audit["summary"]["needs_review"]==audit["summary"]["source_uncertainties"]==0,"zero unresolved source findings")
fresh=A.audit("3308",root=ROOT,definition_path=dp,overrides_path=op)
need(all(json.dumps(fresh[k],sort_keys=True,ensure_ascii=False)==json.dumps(audit[k],sort_keys=True,ensure_ascii=False)for k in["summary","source_bindings","occurrences","review","coverage_limitations"]),"fresh independent source audit exactly matches report")
need(audit["summary"]["coverage_limitations"]==716,"716 technical wire-mapping limitations retained")
# Only circuit function cells and border triangles may change below the header.
base=G.render(spec);allowed={(b["x"]+i,b["top"]+1)for b in spec["boxes"]for i in range(1,7)}|{(b["x"]if p["side"]=="input"else b["x"]+7,p["row"])for b in spec["boxes"]for p in b["ports"]}
for v in spec["variants"]:
 rows=G.render(spec,v)
 delta={(x,y)for y in range(spec["canvas"]["header_rows"],len(rows))for x,(a,b)in enumerate(zip(base[y].ljust(spec["canvas"]["width"]),rows[y].ljust(spec["canvas"]["width"])))if a!=b}
 need(delta<=allowed,"all variant changes limited to function and inversion cells",v["number"])
seed=read(pathof(index["definition"]));need(G.render(seed)[7:]==base[7:],"canonical body unchanged from independently accepted seed")
rebuilt,report=B.build("3308",root=ROOT,overrides_path=op)
need(rebuilt is not None and G.build(rebuilt)[0]==outputs,"default builder and shared renderer exact79file roundtrip")
need(not report["uncertainties"],"no default builder uncertainties",report["uncertainties"])
# Portable source inputs must live in the repository rather than in temporary generation state.
need(all(pathof(b).resolve().is_relative_to(ROOT)for b in overlay["source_bindings"]),"portable reviewed supplement source bindings")
checks=["Manual U03AF canonical NAND form and single-card supply contacts verified","Ten portions, twenty signal contacts, exact terminal graph and all79rendered files validated","All2486current occurrences across668pages covered once by audit and direct witness reconstruction","78selected profiles each have an independently reconstructed complete physical-card field witness","72partial-only profiles retained as excluded evidence with stable numbering","All source fields mapped by physical pin; compatible cross-page merges only; no conflicting mirror priority","All78variant bodies change function/border cells only; no geometry/pin/net changes","Canonical body unchanged; default builder/renderer79file roundtrip with no uncertainties","Current source-use audit has zero findings and retains716technical mapping limitations","Exact bound evidence checked; supplement inputs portable within repository"]
receipt=dict(schema="independent-card-candidate-review-v1",card_type="3308",created_utc=datetime.now(timezone.utc).isoformat(),passed=not failures,failures=failures,
 candidate_bindings=[bind(p)for p in[dp,op,ap,ip]],variant_index=bind(ip),supporting_files=[bind(BASE/"Candidate preparation.json"),bind(Path(__file__)),bind(ROOT/"tools/card_ald/collect_card_variants.py"),bind(ROOT/"tools/card_ald/test_collect_card_variants.py"),bind(ROOT/"tools/card_ald/generate_card.py"),bind(ROOT/"tools/card_ald/build_card_data.py"),bind(ROOT/"tools/card_ald/audit_card_uses.py")],
 checks=checks,counts=dict(variants=78,excluded_partial_profiles=72,rendered_files=len(outputs),source_occurrences=len(all_occurrences),source_pages=668,complete_witnesses=complete_verified,partial_witnesses=partial_verified,bound_files=len(verified)),renderer_checks=renderer_checks,repository_writes=0)
(BASE/"Independent candidate review.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
print(json.dumps({k:v for k,v in receipt.items()if k in["passed","failures","counts"]},ensure_ascii=False))

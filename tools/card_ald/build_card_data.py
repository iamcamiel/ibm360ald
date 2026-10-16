"""Derive a private card render definition from current ALD evidence.

Example: python tools/card_ald/build_card_data.py 4633 --render

Current reviewed card layouts are portable declarative supplements, not an
input rendering definition or a text template. New cards remain private
candidates, including when their evidence or layout needs human review.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

import generate_card
import render_composite_card

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT.parent / "tmp/ald-text/ald/card-data"
PIN = re.compile(r"[BDGJ](?:0[2-9]|1[0-3])\Z")
SINGLE_POWER = {"D08": "GROUND", "D03": "+3V", "B06": "-3V", "B11": "+6V"}
DOUBLE_POWER = {**SINGLE_POWER, "J08": "GROUND", "J03": "+3V", "G06": "-3V", "G11": "+6V"}
DIR_NAMES = ("E", "S", "W", "N")

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()

def binding(path):
    path = Path(path).resolve()
    try:
        label = path.relative_to(ROOT).as_posix()
    except ValueError:
        label = str(path)
    return {"path": label, "sha256": digest(path)}

def verify_binding(item):
    path = Path(item["path"])
    if not path.is_absolute(): path = ROOT / path
    actual = digest(path) if path.is_file() else None
    return {**item, "actual_sha256":actual, "current":actual==item.get("sha256")}

def physical_contact(raw):
    """Parse a physical name without interpreting its numeric annotation."""
    if raw is None:
        return None
    text = str(raw).strip().rstrip("✲*")
    if PIN.fullmatch(text):
        return text
    if len(text) == 4 and text[0].isdigit() and PIN.fullmatch(text[1:]):
        return text[1:]
    return None

def primary(label):
    text = str(label or "").strip()
    return text.split()[0] if text else "�"

def parse_location(text):
    match = re.fullmatch(r"(?:02)?([ABCEKL])-([A-Z]\d)([A-Z]\d)(?:[BT])?", str(text or "").upper())
    if match:
        frame, board, socket = match.groups()
        return "02" + frame + "-" + board, socket
    return None

def correction_records(overlay):
    """Accept the portable explicit source-correction list and pointer form.

    Corrections never modify source files. Their original fields and review
    rationale remain in the evidence report, alongside the current readings.
    """
    result = defaultdict(list)
    for item in overlay.get("source_corrections", []):
        page, node = item.get("page"), item.get("node", item.get("block"))
        if page and node:
            result[page, node].append(item)
    return result

def normalize_occurrence(raw, corrections, uncertainties):
    item = deepcopy(raw)
    changes = []
    for correction in corrections:
        for old, new in correction.get("portion", {}).items():
            if item["portion"] == old:
                changes.append({"field": "portion", "before": old, "after": new})
                item["portion"] = new
        pins = correction.get("pins", {})
        for index, pin in enumerate(item.get("pins", [])):
            old = pin.get("pin")
            if old in pins:
                pin["pin"] = pins[old]
                changes.append({"field": f"pins/{index}/pin", "before": old, "after": pin["pin"]})
        # Portable row-bound native verdicts are more precise than token-wide
        # corrections when one block prints the same token more than once.
        if "pin_index" in correction and correction.get("verdict") == "clear_model_misread":
            index = correction["pin_index"]
            if index is not None and index < len(item.get("pins", [])):
                pin = item["pins"][index]
                expected = correction.get("minority_pin", correction.get("old"))
                new = correction.get("native_reading", correction.get("new"))
                if pin.get("pin") in (expected, new) and ("row" not in correction or pin.get("row") == correction["row"]):
                    if pin.get("pin") != new:
                        changes.append({"field": f"pins/{index}/pin", "before": pin.get("pin"), "after": new})
                    pin["pin"] = new
                else:
                    uncertainties.append({"kind": "reviewed correction no longer matches source field", "page": item["page"], "node": item["node"], "correction": correction})
        for pointer, new in correction.get("set", {}).items():
            keys = pointer.strip("/").split("/")
            target = item
            for key in keys[:-1]:
                target = target[int(key)] if isinstance(target, list) else target[key]
            final = int(keys[-1]) if isinstance(target, list) else keys[-1]
            changes.append({"field": pointer, "before": target[final], "after": new})
            target[final] = new
    return item, changes

def load_evidence(card, overlay):
    catalog_path = ROOT / "json/Card types current" / f"{card}.json"
    if not catalog_path.is_file():
        raise ValueError(f"No current occurrence catalog for {card}")
    catalog = read(catalog_path)
    uncertainties = []
    corrections = correction_records(overlay)
    valid_corrections = defaultdict(list)
    for key, items in corrections.items():
        for item in items:
            source = item.get("model_binding")
            if not source:
                uncertainties.append({"kind":"missing source correction model binding; not applied","page":key[0],"node":key[1],"correction":item})
            elif not verify_binding(source)["current"]:
                uncertainties.append({"kind":"stale source correction binding; not applied","page":key[0],"node":key[1],"binding":verify_binding(source)})
            else: valid_corrections[key].append(item)
    observations, changes = [], []
    for original in catalog.get("diagram_occurrences", []):
        if not original.get("source_reviewed"):
            uncertainties.append({"kind": "occurrence not independently source reviewed", "page": original.get("page"), "node": original.get("node")})
            continue
        scoped = valid_corrections[original["page"], original["node"]]
        normalized, delta = normalize_occurrence(original, scoped, uncertainties)
        observations.append(normalized)
        if delta:
            changes.append({"page": original["page"], "node": original["node"], "changes": delta, "reviewed_authority": scoped})
    pages = {o["page"] for o in observations}
    manifest_path = ROOT / "notes/Content data manifest.json"
    manifest = read(manifest_path)
    models = {}
    bindings = [binding(catalog_path), binding(manifest_path)]
    for entry in manifest["files"]:
        if entry.get("role") != "Published page content model":
            continue
        path = ROOT / entry["path"]
        page = path.stem.split()[0]
        if page not in pages:
            continue
        if digest(path) != entry["sha256"]:
            uncertainties.append({"kind": "current model differs from published hash", "page": page, "path": str(path)})
            continue
        models[page] = read(path)
        bindings.append(binding(path))
    for page in sorted(pages - set(models)):
        uncertainties.append({"kind": "current source model unavailable", "page": page})
    for raw in catalog.get("diagram_occurrences", []):
        page=raw.get("page")
        if page not in models:continue
        node=next((n for n in models[page].get("nodes",[]) if n.get("id")==raw.get("node")),None)
        if node is None:
            uncertainties.append({"kind":"catalog node missing from current hash-bound model","page":page,"node":raw.get("node")})
            continue
        differences=[]
        if str(node.get("card_type"))!=card:
            differences.append({"field":"card_type","catalog":card,"model":node.get("card_type")})
        for catalog_field,model_field in (("portion","portion"),("circuit_identifier","unit"),("location","location")):
            if str(raw.get(catalog_field) or "").strip()!=str(node.get(model_field) or "").strip():
                differences.append({"field":catalog_field,"catalog":raw.get(catalog_field),"model":node.get(model_field)})
        if " ".join(str(raw.get("function_label") or "").split())!=" ".join(str(node.get("function") or "").split()):
            differences.append({"field":"function_label","catalog":raw.get("function_label"),"model":node.get("function")})
        raw_pins=[(p.get("side"),p.get("pin"),p.get("row"),bool(p.get("triangle"))) for p in raw.get("pins",[])]
        model_pins=[(p.get("side"),p.get("pin"),p.get("row"),bool(p.get("triangle"))) for p in node.get("pins",[])]
        if raw_pins!=model_pins:differences.append({"field":"pins","catalog":raw_pins,"model":model_pins})
        if differences:uncertainties.append({"kind":"catalog facts differ from current hash-bound model","page":page,"node":raw.get("node"),"differences":differences})
    # Socket listing board/pair facts identify two halves of a double card.
    socket_pairs = defaultdict(set)
    for listing in catalog.get("listing_records", []):
        board = str(listing.get("board", ""))
        sockets = tuple(sorted(listing.get("sockets", [])))
        for socket in sockets:
            socket_pairs[board, socket].add((board, sockets))
        text = ROOT / listing.get("source_text", "")
        if text.is_file():
            bindings.append(binding(text))
    for o in observations:
        location = parse_location(o.get("location"))
        pairs = socket_pairs.get(location, set()) if location else set()
        o["_instance"] = sorted(pairs)[0] if len(pairs) == 1 else location
        if location is None:
            uncertainties.append({"kind": "unreadable board/socket prevents internal-edge matching", "page": o["page"], "node": o["node"], "location": o.get("location")})
    widths = set(catalog.get("physical_card_widths_observed", []))
    kinds = set(catalog.get("listing_kinds_observed", []))
    circuit_codes = {str(o.get("circuit_identifier") or "") for o in observations}
    module_is_slt = bool(circuit_codes) and all(re.fullmatch(r"[UT]\d\d[A-Z]{2}",code) for code in circuit_codes)
    ordinary_card_kind = bool(kinds) and kinds <= {"SINGLE CARD","DOUBLE CARD"}
    # A four-digit identity or mechanical card width alone does not identify
    # an SLT module. Connector/special/passive families need explicit reviewed
    # power-contact authority; never assign SLT rails just from their name.
    if overlay.get("power_contacts"):
        power = overlay["power_contacts"]
    elif widths == {"SINGLE CARD"} and module_is_slt and ordinary_card_kind:
        power = SINGLE_POWER
    elif widths == {"DOUBLE CARD"} and module_is_slt and ordinary_card_kind:
        power = DOUBLE_POWER
    else:
        power = {}
        uncertainties.append({"kind": "module kind lacks one unambiguous ordinary SLT single/double pinout", "observed_widths": sorted(widths), "listing_kinds": sorted(kinds),"circuit_identifiers":sorted(circuit_codes)})
    # Deduplicate exact source bindings while preserving deterministic order.
    bindings = sorted({(b["path"], b["sha256"]): b for b in bindings}.values(), key=lambda b:b["path"])
    return catalog, observations, models, power, bindings, changes, uncertainties

def derive_semantics(card, catalog, observations, models, power, uncertainties):
    portions = defaultdict(list)
    by_page = defaultdict(dict)
    for o in observations:
        portions[o["portion"]].append(o)
        by_page[o["page"]][o["node"]] = o
    contact_ports = defaultdict(lambda: defaultdict(set))
    nodes = {}
    manual_path = ROOT / "notes/Card-ALD/Manual canonical circuit forms.json"
    manual = read(manual_path) if manual_path.is_file() else {"circuits": {}}
    for portion, occurrences in sorted(portions.items()):
        circuits = Counter(str(o.get("circuit_identifier") or "").strip() for o in occurrences)
        readable = {code for code in circuits if re.fullmatch(r"[A-Z]\d\d[A-Z]{2}", code)}
        if len(readable) == 1:
            circuit = next(iter(readable))
        else:
            circuit = "�����"
            uncertainties.append({"kind": "circuit identifier unresolved", "portion": portion, "readings": dict(circuits)})
        canonical = manual.get("circuits", {}).get(circuit, {}).get("canonical_form")
        labels = Counter(primary(o.get("function_label")) for o in occurrences)
        if canonical:
            function = canonical["primary_function"]
            triangles = {"input": bool(canonical.get("all_input_triangles")), "output": bool(canonical.get("all_output_triangles"))}
        else:
            function = next(iter(labels)) if len(labels) == 1 else "�"
            triangles = {}
            uncertainties.append({"kind": "canonical circuit form not established by manual", "portion": portion, "circuit_identifier": circuit, "observed_functions": dict(labels)})
        node = {"portion": portion, "id": portion, "card_type": card, "function": function, "unit": circuit,
                "_inputs": [], "_outputs": [], "observations": [{"page": o["page"], "node": o["node"]} for o in occurrences]}
        node["_canonical_triangles"] = triangles
        node["_observed_pinless_counts"] = {}
        node["_observed_pinless_triangles"] = {}
        for side in ("input", "output"):
            pinless = [[p for p in o.get("pins",[]) if p.get("side")==side and
                        (p.get("pin") is None or re.fullmatch(r"(?:IN|OUT)\d+|[AB]|(?:input|output)\d*",str(p.get("pin")),re.I))]
                       for o in occurrences]
            node["_observed_pinless_counts"][side]=max((len(ps) for ps in pinless),default=0)
            marker_values={bool(p.get("triangle")) for ps in pinless for p in ps}
            if side in triangles:
                node["_observed_pinless_triangles"][side]=triangles[side]
            elif len(marker_values)==1:
                node["_observed_pinless_triangles"][side]=next(iter(marker_values))
            else:
                node["_observed_pinless_triangles"][side]=False
                if marker_values:
                    uncertainties.append({"kind":"pinless decoration lacks one established form","portion":portion,"side":side,"observed_markers":sorted(marker_values)})
            names = defaultdict(list)
            for o in occurrences:
                for p in o.get("pins", []):
                    if p.get("side") != side:
                        continue
                    pin = physical_contact(p.get("pin"))
                    if pin and pin not in power:
                        if set(power) == set(SINGLE_POWER) and pin[0] in "GJ":
                            uncertainties.append({"kind": "double-card contact on single-card occurrence", "page": o["page"], "node": o["node"], "pin": pin})
                            continue
                        names[pin].append((o,p))
                    elif p.get("pin") is not None and pin is None and not re.fullmatch(r"(?:IN|OUT)\d+|[AB]|(?:input|output)\d*", str(p["pin"]), re.I):
                        uncertainties.append({"kind": "unresolved physical/control label", "page": o["page"], "node": o["node"], "portion": portion, "label": p["pin"]})
            for pin, entries in sorted(names.items()):
                wedge = triangles.get(side)
                if wedge is None:
                    readings = {bool(p.get("triangle")) for _,p in entries}
                    wedge = next(iter(readings)) if len(readings) == 1 else False
                    if len(readings) > 1:
                        uncertainties.append({"kind": "noncanonical decoration differs", "portion": portion, "side": side, "pin": pin})
                port = {"pin": pin, "triangle": wedge, "side": side, "row": len(node["_inputs"] if side == "input" else node["_outputs"]),
                        "ref": pin, "evidence": [{"page":o["page"],"node":o["node"],"row":p.get("row")} for o,p in entries]}
                node["_inputs" if side == "input" else "_outputs"].append(port)
                contact_ports[pin][side].add(portion)
        nodes[portion] = node
    edges = defaultdict(list)
    rejected = []
    for page, model in sorted(models.items()):
        records = by_page[page]
        for net in model.get("nets", []):
            drivers = {net.get("driver")} if isinstance(net.get("driver"),str) else set()
            for field in ("declared_physical_output_drivers", "route_owners"):
                drivers.update(x for x in net.get(field, []) or [] if isinstance(x,str))
            for driver in sorted(drivers):
                if "." not in driver:
                    continue
                sid, suffix = driver.split(".",1)
                source = records.get(sid)
                if source is None or not source.get("_instance"):
                    continue
                for target in net.get("targets", []):
                    if not isinstance(target,str) or "." not in target:
                        continue
                    tid, tsuffix = target.split(".",1)
                    sink = records.get(tid)
                    if sink is None or sink.get("_instance") != source["_instance"]:
                        continue
                    s,t = source["portion"],sink["portion"]
                    if s == t:
                        continue
                    outgoing = {p["pin"] for p in nodes[s]["_outputs"] if p["pin"]}
                    incoming = {p["pin"] for p in nodes[t]["_inputs"] if p["pin"]}
                    sp,tp = physical_contact(suffix),physical_contact(tsuffix)
                    # Resolve a missing source label only when the portion's
                    # current evidence gives exactly one physical output.
                    if sp is None and len(outgoing) == 1:
                        sp = next(iter(outgoing))
                    if sp and sp not in outgoing or tp and tp not in incoming:
                        rejected.append({"page":page,"driver":driver,"target":target,"reason":"net suffix not present on corrected physical ports"})
                        continue
                    if sp in power or tp in power:
                        continue
                    if sp and tp and sp != tp:
                        rejected.append({"page":page,"driver":driver,"target":target,"reason":"different physical contacts: installation strap"})
                        continue
                    if sp is None and tp and len(drivers) > 1:
                        rejected.append({"page":page,"driver":driver,"target":target,"reason":"multi-driver page net does not establish this individual internal edge"})
                        continue
                    common = outgoing & incoming
                    if len(common) == 1:
                        sp = tp = next(iter(common))
                    elif tp is None and not any(p.get("side") == "input" and physical_contact(p.get("pin")) is None for p in sink["pins"]):
                        if sp in incoming:
                            tp = sp
                        elif len(incoming) == 1:
                            tp = next(iter(incoming))
                        else:
                            rejected.append({"page":page,"driver":driver,"target":target,"reason":"unmapped target suffix; no uniquely identified physical or pinless input"})
                            continue
                    edges[s,t,sp or "PINLESS",tp or "PINLESS"].append({"page":page,"driver":driver,"target":target,"instance":source["_instance"]})
    for pin,sides in sorted(contact_ports.items()):
        if len(sides["output"]) > 1:
            uncertainties.append({"kind":"multiple portions drive one contact; wired-OR needs review","pin":pin,"portions":sorted(sides["output"])})
        for s in sorted(sides["output"]):
            for t in sorted(sides["input"]):
                if s != t:
                    edges[s,t,pin,pin].append({"basis":"fixed shared physical contact","pin":pin})
    final_edges = [{"source":s,"target":t,"output_ref":o,"input_ref":i,"evidence":e}
                   for (s,t,o,i),e in sorted(edges.items())]
    for portion,node in nodes.items():
        for e in final_edges:
            if e["target"] == portion and e["input_ref"] == "PINLESS":
                node["_inputs"].append({"pin":None,"triangle":node["_observed_pinless_triangles"]["input"],"side":"input","row":len(node["_inputs"]),"ref":e["source"]})
        if any(e["source"] == portion and e["output_ref"] == "PINLESS" for e in final_edges):
            node["_outputs"].append({"pin":None,"triangle":node["_observed_pinless_triangles"]["output"],"side":"output","row":0,"ref":"PINLESS"})
        for side,key in (("input","_inputs"),("output","_outputs")):
            expected=node["_observed_pinless_counts"][side]
            routed=sum(p["pin"] is None for p in node[key])
            # A globally named output can recover an unlabelled occurrence of
            # that single output. Multiple anonymous ports remain unresolved.
            recovered_named=side=="output" and expected==1 and len(node[key])==1 and node[key][0]["pin"] is not None
            if expected>routed and not recovered_named:
                uncertainties.append({"kind":"observed pinless ports have no reconstructed internal edge","portion":portion,"side":side,
                                      "maximum_visible_pinless_ports":expected,"reconstructed_pinless_ports":routed,
                                      "consequence":"Candidate is incomplete; untraceable ports are recorded here rather than assigned invented contacts or wires."})
        if not node["_inputs"] and not node["_outputs"]:
            uncertainties.append({"kind":"portion has no reconstructable routed ports","portion":portion})
    listed = set(catalog.get("listing_portions", []))
    for portion in sorted(listed-set(nodes)):
        uncertainties.append({"kind":"listing portion has no current diagram occurrence","portion":portion})
    possible={f"{letter}{number:02}" for letter in ("BDGJ" if set(power)==set(DOUBLE_POWER) else "BD" if set(power)==set(SINGLE_POWER) else "") for number in range(2,14)}
    return {"schema":"derived-card-data-v1","card_type":card,"observations":len(observations),
            "pages":len(by_page),"portions":nodes,"edges":final_edges,
            "signal_pins":{pin:{side:sorted(ps) for side,ps in sides.items()} for pin,sides in sorted(contact_ports.items())},
            "power_pins":power,"rejected_installation_or_unmapped_edges":rejected,
            "unobserved_contacts":sorted(possible-set(power)-set(contact_ports)),
            "unobserved_contact_interpretation":"No connection observed; electrical disconnection is not established.",
            "listing_portions":sorted(listed),"listing_records":catalog.get("listing_records",[])}, manual_path

def terminal_components(model):
    """Return logical port memberships independently of drawing coordinates."""
    nets = defaultdict(set)
    for portion,node in model["portions"].items():
        for side,key in (("input","_inputs"),("output","_outputs")):
            for p in node[key]:
                if p["pin"]:
                    nets[p["pin"]].add((portion,side,p["pin"]))
    for e in model["edges"]:
        key = e["output_ref"] if e["output_ref"] != "PINLESS" else "INTERNAL:"+e["source"]
        nets[key].add((e["source"],"output",None if e["output_ref"] == "PINLESS" else e["output_ref"]))
        if e["input_ref"] == "PINLESS":
            nets[key].add((e["target"],"input",None))
    return nets

def compact_segments(cells):
    segments,marks = [],[]
    by_row = defaultdict(list)
    for (x,y),(char,arms) in cells.items():
        if char == "─":
            by_row[y].append(x)
        else:
            mark={"x":x,"y":y,"symbol":char}
            if char == "◇":
                mark["arms"]="".join(d for d in "NESW" if d in arms)
            marks.append(mark)
    for y,xs in sorted(by_row.items()):
        start=last=None
        for x in sorted(xs):
            if last is not None and x != last+1:
                segments.append({"x1":start,"x2":last,"y":y})
                start=None
            if start is None:start=x
            last=x
        if start is not None:segments.append({"x1":start,"x2":last,"y":y})
    return {"horizontal_segments":segments,"marks":sorted(marks,key=lambda p:(p["y"],p["x"]))}

def normalize_free_row_scene(spec):
    """Remove scene margins with one uniform body translation; routes stay fixed."""
    if spec["canvas"].get("grid_step",7) != 1:
        return
    header_rows=spec["canvas"]["header_rows"]
    body_rows=[b["top"] for b in spec["boxes"]]
    body_rows += [s["y"] for s in spec["wiring"]["horizontal_segments"]]
    body_rows += [m["y"] for m in spec["wiring"]["marks"]]
    body_rows += [p["row"] for p in spec["exterior_pins"]]
    body_annotations=[a for a in spec["annotations"] if a["row"]>=header_rows]
    body_rows += [a["row"] for a in body_annotations]
    if not body_rows:return
    old_height=spec["canvas"]["height"]
    first=min(body_rows)
    delta=header_rows+1-first
    for box in spec["boxes"]:
        box["top"]+=delta
        for port in box["ports"]:port["row"]+=delta
    for segment in spec["wiring"]["horizontal_segments"]:segment["y"]+=delta
    for mark in spec["wiring"]["marks"]:mark["y"]+=delta
    for pin in spec["exterior_pins"]:pin["row"]+=delta
    for annotation in body_annotations:annotation["row"]+=delta
    last=max([b["top"]+b["height"]-1 for b in spec["boxes"]]+
             [s["y"] for s in spec["wiring"]["horizontal_segments"]]+
             [m["y"] for m in spec["wiring"]["marks"]]+
             [p["row"] for p in spec["exterior_pins"]]+
             [a["row"] for a in spec["annotations"]])
    spec["canvas"]["height"]=last+1
    spec["canvas"]["grid_origin"]=0
    spec["provenance"]["scene_margin_normalization"]={
        "body_row_translation":delta,"first_body_row_before":first,
        "first_body_row_after":first+delta,"height_before":old_height,
        "height_after":last+1,"removed_blank_tail_rows":old_height+delta-last-1,
        "method":"Uniform translation of boxes, semantic port rows, routes, exterior labels and nonheader annotations; headers unchanged, no rerouting."}


def generic_definition(model, provenance, uncertainties, reviewed_overlay=None):
    geometry = render_composite_card.prepare(model)
    boundary_review=None
    if model.get("layout_hints",{}).get("row_step")==1:
        import equivalent_input_order
        geometry,input_order_review=equivalent_input_order.optimize(model,geometry)
        geometry,boundary_review=render_composite_card.optimize_boundary_pins(model,geometry)
        geometry,trunk_review=render_composite_card.optimize_fanout_trunks(model,geometry)
        import vertical_fanout_order
        geometry,vertical_review=vertical_fanout_order.optimize(model,geometry)
    route_validation=render_composite_card.verify(model,geometry)
    positions,ports,exterior,router=geometry
    glyphs={frozenset({0,2}):"─",frozenset({1,3}):"│",frozenset({0,1}):"┌",
            frozenset({1,2}):"┐",frozenset({0,3}):"└",frozenset({2,3}):"┘"}
    cells={}
    for point,nets in router.wires.items():
        if not nets:continue
        if len(nets)>1:char,arms="┼",set("NESW")
        else:
            key,dirs=next(iter(nets.items()))
            dirs=dirs|router.virtual_endpoint_directions[point].get(key,set())
            char="◇" if len(dirs)>=3 else glyphs[frozenset(dirs)]
            arms={DIR_NAMES[d] for d in dirs}
        cells[point]=char,arms
    boxes=[]
    for portion,pos in positions.items():
        node=model["portions"][portion]
        ps=[]
        for (p,side,key),port in sorted(ports.items()):
            if p!=portion:continue
            ps.append({"id":port.get("id") or side+":"+str(port["point"][1]-pos["top"]),"row":port["point"][1],
                       "side":side,"pin":port["pin"],"triangle":port["triangle"]})
        boxes.append({"portion":portion,"x":pos["x"],"top":pos["top"],"height":pos["height"],
                      "function":node["function"],"circuit_identifier":node["unit"],"ports":ps})
    spec={"schema":"reviewed-card-render-definition-v1","card_type":model["card_type"],
          "review_status":"unreviewed private candidate","canvas":{"width":router.width,"height":router.height,"header_rows":7,"grid_origin":0,"grid_step":model.get("layout_hints",{}).get("row_step",7)},
          "power_contacts":model["power_pins"],"canonical_line_ending":"LF","boxes":boxes,
          "wiring":compact_segments(cells),"exterior_pins":[{"pin":pin,"side":p["side"],"x":0 if p["side"]=="input" else router.width-3,"row":p["row"]} for pin,p in sorted(exterior.items())],
          "annotations":[{"x":0,"row":0,"text":"CARD-ALD "+model["card_type"]+"  DRAFT EVIDENCE UNION; REVIEW REQUIRED"},
                         {"x":0,"row":1,"text":f"{model['observations']} OCCURRENCES; {len(model['portions'])} OBSERVED PORTIONS; {len(uncertainties)} REVIEW ITEMS"},
                         {"x":0,"row":3,"text":f"{len(model.get('unobserved_contacts',[]))} CONTACTS WITH NO OBSERVED CONNECTION; SEE EVIDENCE JSON"}],
          "variants":[],"provenance":deepcopy(provenance)}
    spec["layout_validation"]=route_validation
    if boundary_review is not None:
        spec["provenance"]["equivalent_input_ordering"]={"optimizer":binding(Path(equivalent_input_order.__file__)),"review":input_order_review}
        spec["provenance"]["boundary_pin_optimization"]=boundary_review
        spec["provenance"]["fanout_trunk_optimization"]=trunk_review
        spec["provenance"]["vertical_fanout_optimization"]={"optimizer":binding(Path(vertical_fanout_order.__file__)),"review":vertical_review}
    if model["power_pins"]:
        spec["annotations"].append({"x":0,"row":2,"text":"POWER: "+"; ".join(pin+" "+level for pin,level in model["power_pins"].items())})
    if reviewed_overlay:
        old_canvas=reviewed_overlay["layout"]["canvas"]
        annotations=deepcopy(reviewed_overlay["layout"]["annotations"])
        footers=[a for a in annotations if a["row"]>=old_canvas["header_rows"]]
        if footers:
            original_start=min(a["row"] for a in footers)
            diagram_bottom=max([p["top"]+p["height"]-1 for p in positions.values()]+[y for x,y in cells])
            footer_start=diagram_bottom+3
            for annotation in footers:
                annotation["row"]=footer_start+(annotation["row"]-original_start)
            spec["canvas"]["height"]=max(spec["canvas"]["height"],max(a["row"] for a in footers)+1)
        spec["annotations"]=annotations
        spec["variants"]=deepcopy(reviewed_overlay.get("approved_variants",[]))
        spec["canonical_line_ending"]=reviewed_overlay.get("canonical_line_ending","LF")
        spec["review_status"]="reviewed topology and notation; private unreviewed graph placement"
        if "header" in reviewed_overlay:
            spec["header"]=reviewed_header(reviewed_overlay,model)
    normalize_free_row_scene(spec)
    spec["nets"]=generate_card.wiring_graph(spec)
    if reviewed_overlay:
        expected=sorted(sorted(net["terminals"] if isinstance(net,dict) else net) for net in reviewed_overlay["reviewed_nets"])
        assert spec["nets"]==expected,"Relayout changed approved terminal connections"
    generate_card.validate(spec)
    return spec

def reviewed_routing_model(overlay,observed_model):
    """Recover exact reviewed networks while retaining stable semantic port IDs."""
    nodes={}
    by_terminal={}
    signal=defaultdict(lambda:defaultdict(set))
    for portion,fact in overlay["reviewed_portions"].items():
        node={"id":portion,"portion":portion,"card_type":observed_model["card_type"],
              "function":fact["function"],"unit":fact.get("unit",fact.get("circuit_identifier")),"_inputs":[],"_outputs":[]}
        for p in fact["ports"]:
            port={"id":p["id"],"pin":p.get("pin"),"triangle":bool(p["triangle"]),"side":p["side"],"row":0,"ref":p["id"]}
            node["_inputs" if p["side"]=="input" else "_outputs"].append(port)
            by_terminal["PORT:"+portion+":"+p["id"]]=(portion,p["side"],p["id"])
            if p.get("pin"):signal[p["pin"]][p["side"]].add(portion)
        nodes[portion]=node
    networks=[]
    edges=[]
    for index,net in enumerate(overlay["reviewed_nets"],1):
        terminals=net["terminals"] if isinstance(net,dict) else net
        network={"id":net.get("id",f"N{index:03}") if isinstance(net,dict) else f"N{index:03}","inputs":[],"outputs":[],"exterior_pin":None}
        for terminal in terminals:
            if terminal.startswith("PIN:"):
                assert network["exterior_pin"] is None,"Two physical contacts on one reviewed net"
                network["exterior_pin"]=terminal[4:]
            else:
                portion,side,port_id=by_terminal[terminal]
                network[side+"s"].append((portion,port_id))
        for source,sport in network["outputs"]:
            for target,tport in network["inputs"]:
                if source!=target:edges.append({"source":source,"target":target,"output_ref":sport,"input_ref":tport,
                    "evidence":[{"basis":"explicit reviewed terminal partition","net":network["id"]}]})
        networks.append(network)
    return {"schema":"reviewed-card-routing-input-v1","card_type":observed_model["card_type"],"portions":nodes,
            "edges":edges,"networks":networks,"power_pins":deepcopy(overlay["power_contacts"]),
            "signal_pins":{pin:{side:sorted(ps) for side,ps in sides.items()} for pin,sides in signal.items()},
            "observations":observed_model["observations"],"pages":observed_model["pages"]}

def reviewed_header(overlay,model):
    facts=deepcopy(overlay["header"])
    facts["reviewed_occurrences"]=model["observations"]
    facts["reviewed_pages"]=model["pages"]
    return facts


def reviewed_definition(card, overlay, model, provenance, uncertainties):
    """Combine independently derived facts with explicitly reviewed supplements."""
    reviewed=overlay["reviewed_portions"]
    layout=overlay["layout"]
    boxes=[]
    comparisons=[]
    for portion in sorted(set(model["portions"])-set(reviewed)):
        uncertainties.append({"kind":"new current portion outside reviewed layout","portion":portion,"observations":model["portions"][portion]["observations"]})
    for placement in layout["boxes"]:
        portion=placement["portion"]
        fact=reviewed[portion]
        actual=model["portions"].get(portion)
        if actual is None:
            uncertainties.append({"kind":"reviewed portion has no current normalized occurrence","portion":portion})
        else:
            expected_circuit=fact.get("unit",fact.get("circuit_identifier"))
            if actual["unit"] != expected_circuit:
                uncertainties.append({"kind":"current circuit consensus differs from reviewed supplement","portion":portion,"derived":actual["unit"],"reviewed":expected_circuit})
            observed={(p["side"],p["pin"]) for p in actual["_inputs"]+actual["_outputs"] if p["pin"]}
            accepted={(p["side"],p.get("pin")) for p in fact["ports"] if p.get("pin")}
            comparisons.append({"portion":portion,"observed_contact_roles":sorted(observed),"reviewed_contact_roles":sorted(accepted),
                                "new_current_contact_roles":sorted(observed-accepted),"reviewed_supplements_not_currently_drawn":sorted(accepted-observed)})
            if observed-accepted:
                uncertainties.append({"kind":"new contact role outside reviewed layout","portion":portion,"roles":sorted(observed-accepted)})
        rows={p["id"]:p["row"] for p in placement["ports"]}
        ps=[{"id":p["id"],"side":p["side"],"pin":p.get("pin"),"triangle":bool(p["triangle"]),"row":rows[p["id"]]} for p in fact["ports"]]
        assert set(rows)=={p["id"] for p in fact["ports"]}, (card,portion,"Layout port coverage differs")
        boxes.append({"portion":portion,"x":placement["x"],"top":placement["top"],"height":placement["height"],
                      "function":fact["function"],"circuit_identifier":fact.get("unit",fact.get("circuit_identifier")),"ports":ps})
        if "compact_termination" in placement:
            boxes[-1]["compact_termination"]=deepcopy(placement["compact_termination"])
    assert {b["portion"] for b in boxes}==set(reviewed),"Reviewed portion/layout coverage differs"
    nets=[]
    for n in overlay["reviewed_nets"]:
        terminals=n["terminals"] if isinstance(n,dict) else n
        nets.append(sorted(terminals))
    port_side={(portion,p["id"]):p["side"] for portion,fact in reviewed.items() for p in fact["ports"]}
    approved_pairs=set()
    for terminals in nets:
        outs,ins=set(),set()
        for terminal in terminals:
            if not terminal.startswith("PORT:"):continue
            _,portion,port=terminal.split(":",2)
            (outs if port_side[portion,port]=="output" else ins).add(portion)
        approved_pairs.update((s,t) for s in outs for t in ins if s!=t)
    derived_pairs={(e["source"],e["target"]) for e in model["edges"]}
    for source,target in sorted(derived_pairs-approved_pairs):
        uncertainties.append({"kind":"new derived internal connection outside reviewed nets","source":source,"target":target,
                              "evidence":[e for e in model["edges"] if e["source"]==source and e["target"]==target]})
    comparisons.append({"reviewed_internal_pairs_not_currently_reconstructed":[list(pair) for pair in sorted(approved_pairs-derived_pairs)]})
    spec={"schema":"reviewed-card-render-definition-v1","card_type":card,"canvas":deepcopy(layout["canvas"]),
          "power_contacts":deepcopy(overlay["power_contacts"]),"canonical_line_ending":overlay.get("canonical_line_ending","LF"),
          "boxes":boxes,"wiring":deepcopy(layout["wiring"]),"exterior_pins":deepcopy(layout["exterior_pins"]),
          "annotations":deepcopy(layout["annotations"]),"variants":deepcopy(overlay.get("approved_variants",[])),
          "nets":sorted(nets),"provenance":provenance,
          "review_status":"reviewed supplemental layout; current-evidence comparisons retained separately"}
    if "header" in overlay:
        spec["header"]=reviewed_header(overlay,model)
    assert generate_card.wiring_graph(spec)==sorted(nets),"Portable reviewed geometry differs from reviewed terminal nets"
    generate_card.validate(spec)
    return spec,comparisons

def _build(card_type, overrides_path=None, relayout=False):
    if not re.fullmatch(r"\d{4}",card_type):
        raise ValueError("Card type must be exactly four digits")
    path=Path(overrides_path) if overrides_path else ROOT/"json/Card-ALD/build-overrides"/(card_type+".json")
    overlay=read(path) if path.is_file() else {}
    overlay_binding_checks=[]
    rejected_overlay=None
    if overlay:
        assert overlay["schema"]=="reviewed-card-build-overrides-v1"
        assert overlay.get("card_type",card_type)==card_type
        overlay_binding_checks=[verify_binding(item) for item in overlay.get("source_bindings",[])]
        if any(not item["current"] for item in overlay_binding_checks):
            rejected_overlay={"path":str(path),"reason":"reviewed supplement source binding is stale or missing","bindings":overlay_binding_checks}
            overlay={}
    catalog,obs,models,power,bindings,changes,uncertainties=load_evidence(card_type,overlay)
    if rejected_overlay:uncertainties.append({"kind":"reviewed supplement not applied",**rejected_overlay})
    model,manual_path=derive_semantics(card_type,catalog,obs,models,power,uncertainties)
    if manual_path.is_file():bindings.append(binding(manual_path))
    provenance={"schema":"derived-card-data-provenance-v1","builder":binding(Path(__file__)),"source_bindings":bindings,
                "derivation":"Current occurrence catalog, independently hash-bound published source models and socket-listing facts; explicit reviewed supplements remain distinct from fresh observations.",
                "reviewed_supplement":binding(path) if overlay else None,
                "reviewed_source_bindings":deepcopy(overlay.get("source_bindings",[])),"source_corrections_applied":changes}
    provenance["reviewed_source_binding_checks"]=overlay_binding_checks
    report={"schema":"card-data-build-evidence-v1","card_type":card_type,"provenance":provenance,
            "derived_model":model,"uncertainties":uncertainties,"reviewed_supplement_used":bool(overlay)}
    definition=None
    try:
        if overlay:
            definition,comparisons=reviewed_definition(card_type,overlay,model,provenance,uncertainties)
            report["reviewed_fact_comparisons"]=comparisons
        elif not power:
            uncertainties.append({"kind":"definition not routed for unsupported or ambiguous module kind"})
        else:
            definition=generic_definition(model,provenance,uncertainties)
        if relayout and (overlay or power):
            definition=None
            import graph_card_layout
            routing_model=reviewed_routing_model(overlay,model) if overlay else deepcopy(model)
            report["relayout"]={"planner":binding(Path(graph_card_layout.__file__)),
                               "source":"reviewed terminal partitions" if overlay else "unreviewed derived evidence"}
            definition=None
            attempts=[]
            successes=[]
            for row_gap in (0,1):
                routing_model["layout_options"]={"row_step":1,"row_gap":row_gap}
                hints=graph_card_layout.plan(routing_model)
                if overlay:
                    labels=list(overlay["layout"]["annotations"])
                    variant_labels=[x for v in overlay.get("approved_variants",[]) for x in v.get("annotation_overrides",[])]
                    hints["minimum_width"]=max([hints.get("minimum_width",0)]+[x.get("x",0)+len(x["text"]) for x in labels+variant_labels])
                for extra,interval in enumerate(dict.fromkeys([hints.get("bank_interval",36),36,42,48,60])):
                    trial=deepcopy(hints)
                    trial["bank_interval"]=interval
                    trial["first_bank_x"]=hints.get("first_bank_x",18)+extra*4
                    trial["right_margin"]=hints.get("right_margin",18)+extra*4
                    routing_model["layout_hints"]=trial
                    try:
                        candidate=generic_definition(routing_model,provenance,uncertainties,overlay or None)
                        metrics=candidate["layout_validation"]
                        attempts.append({"row_gap":row_gap,"bank_interval":interval,"first_bank_x":trial["first_bank_x"],"right_margin":trial["right_margin"],
                                         "success":True,"routing_metrics":metrics})
                        successes.append((candidate,trial))
                        break
                    except (AssertionError,ValueError,KeyError) as exc:
                        attempts.append({"row_gap":row_gap,"bank_interval":interval,"first_bank_x":trial["first_bank_x"],"right_margin":trial["right_margin"],"success":False,"detail":str(exc)})
            report["relayout"]["routing_attempts"]=attempts
            if not successes:raise ValueError("No valid graph routing found in reviewed spacing trials; see relayout.routing_attempts")
            definition,chosen_hints=min(successes,key=lambda item:(item[0]["layout_validation"]["crossings"],item[0]["canvas"]["width"],item[0]["layout_validation"]["routed_grid_steps"]))
            report["relayout"]["layout_hints"]=chosen_hints
            report["relayout"]["selection_rule"]="Fewest crossings, then smallest width, then shortest routing among the first successful width for each row gap."
            report["relayout"]["terminal_partition_identity_verified"]=bool(overlay)
    except (AssertionError,ValueError,KeyError,RuntimeError,ImportError) as exc:
        uncertainties.append({"kind":"candidate definition requires review before routing","detail":str(exc),"exception":type(exc).__name__})
    report["definition_generated"]=definition is not None
    if definition is not None:
        report["validation"]=generate_card.validate(definition)
    return definition,report

def build(card_type, overrides_path=None, root=None, relayout=False):
    """Build without writes; root= supports portable clones and fixture tests."""
    global ROOT
    previous=ROOT
    try:
        if root is not None:ROOT=Path(root).resolve()
        return _build(card_type,overrides_path,relayout)
    finally:
        ROOT=previous

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card_type")
    parser.add_argument("--output-dir",type=Path,help="Private destination, default tmp/ald-text/ald/card-data/CARD")
    parser.add_argument("--overrides",type=Path,help="Portable reviewed supplement JSON; default checks json/Card-ALD/build-overrides/CARD.json")
    parser.add_argument("--root",type=Path,help="Repository root for portable clones or private evidence fixtures")
    parser.add_argument("--relayout",action="store_true",help="Privately plan/reroute the graph; reviewed cards retain exact approved terminals and port IDs")
    parser.add_argument("--render",action="store_true",help="Also validate/render TXT candidates privately")
    parser.add_argument("--check",action="store_true",help="Read/derive/validate without writing files")
    args=parser.parse_args()
    if not re.fullmatch(r"\d{4}",args.card_type):parser.error("Use a four-digit card type, for example0141")
    try:definition,report=build(args.card_type,args.overrides,args.root,args.relayout)
    except (ValueError,AssertionError,KeyError) as exc:parser.error(str(exc))
    out=args.output_dir or DEFAULT_OUTPUT/args.card_type
    if not args.check:
        out.mkdir(parents=True,exist_ok=True)
        if definition is not None:
            (out/(args.card_type+".json")).write_text(json.dumps(definition,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            if args.render:
                outputs,_=generate_card.build(definition)
                for name,raw in outputs.items():(out/name).write_bytes(raw)
        (out/(args.card_type+" evidence.json")).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"card_type":args.card_type,"definition_generated":definition is not None,
                      "review_items":len(report["uncertainties"]),"reviewed_supplement_used":report["reviewed_supplement_used"],
                      "output_directory":str(out),"check_only":args.check},ensure_ascii=False))

if __name__=="__main__":main()

"""Build evidence-backed composite 4633/4634 card models and candidate drawings.

The union covers all current nonpending catalog occurrences.  A physical
contact is joined wherever it appears on this card type.  Page nets whose
two named contacts differ are installation straps, never internal wiring.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import build_463x_layered as layered
import render_composite_card as renderer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT.parent / "tmp/ald-text/ald/card-universal/463x"
SUPPLY = {"D08": "GROUND", "J08": "GROUND", "D03": "+3V", "J03": "+3V",
          "B06": "-3V", "G06": "-3V", "B11": "+6V", "G11": "+6V"}
PIN = re.compile(r"[BDGJ](?:0[2-9]|1[0-3])\Z")
# These corrections affect this derived candidate only. Canonical ALD source
# changes require the separately reviewed release process.
SOURCE_CORRECTIONS = {
    ("4633", "AP673", "BY"): {"J05": "J02"},
    ("4633", "AP301", "BB"): {"D09": "D04"},
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def contact(raw):
    if raw is None:
        return None
    raw = str(raw).rstrip("✲")
    if PIN.fullmatch(raw):
        return raw
    if len(raw) == 4 and raw[0] in "0123456789BH" and PIN.fullmatch(raw[1:]):
        return raw[1:]
    return None

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def extract(card):
    catalog_path = ROOT / "json/Card types current" / f"{card}.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    observations = []
    corrections_used = []
    minority_audit_path = OUT.parent / "4191/4634-minority-crops/verdicts.json"
    minority_audit = json.loads(minority_audit_path.read_text(encoding="utf-8")) if minority_audit_path.is_file() else {"rows": []}
    for record in catalog["diagram_occurrences"]:
        if not record.get("source_reviewed"):
            continue
        correction = SOURCE_CORRECTIONS.get((card, record["page"], record["node"]), {})
        correction = dict(correction)
        indexed_corrections = {}
        if card == "4634":
            for verdict in minority_audit["rows"]:
                if verdict["page"] == record["page"] and verdict["block"] == record["node"] and verdict["verdict"] == "clear_model_misread":
                    index = verdict["pin_index"]
                    assert record["pins"][index]["row"] == verdict["row"]
                    assert record["pins"][index]["pin"] in (verdict["minority_pin"], verdict["native_reading"])
                    indexed_corrections[index] = verdict["native_reading"]
                    correction[verdict["minority_pin"]] = verdict["native_reading"]
        if correction:
            corrections_used.append({"page": record["page"], "node": record["node"], "pins": correction,
                                     "scope": "derived composite only; source-reviewed correction"})
        pins = []
        for pin_index, p in enumerate(record["pins"]):
            raw = p.get("pin")
            physical = contact(indexed_corrections.get(pin_index, correction.get(raw, raw)))
            pins.append({"physical_pin": physical, "direction": p["side"],
                         "drawn_connected_port": True, "triangle_glyph": bool(p.get("triangle")),
                         "pin_name_readability": "physical name" if physical else "unprinted" if p["pin"] is None or re.fullmatch(r"(?:IN|OUT)\d+|[AB]", str(p["pin"])) else "other terminal/control label",
                         "printed_label_literal": p.get("printed_pin"),
                         "polarity_decoration": {"marker": "triangle" if p.get("triangle") else "none",
                            "glyph_bindings": [{"glyph": "◺" if p.get("triangle") else "│"}]}})
        portion = record["portion"]
        if (card, record["page"], record["node"], portion) == ("4633", "AP271", "AS", "F2"):
            portion = "A2"
            corrections_used.append({"page": "AP271", "node": "AS", "portion": {"F2": "A2"},
                "basis": "B08 OR/U03AI to A3 uniquely matches A2 on all other slices; installed socket listing has A2 and no F2; worn literal retained in source model"})
        observations.append({"portion_literal": portion, "page": record["page"],
            "node_identifier": record["node"], "function_literal": record["function_label"],
            "unit_code_literal": record["circuit_identifier"], "pins": pins,
            "observation_id": record["page"] + ":" + record["node"],
            "physical_instance_key": record["location"], "_pin_correction": correction})
    by_portion = defaultdict(list)
    by_page = defaultdict(dict)
    issues = []
    for o in observations:
        by_portion[o["portion_literal"]].append(o)
        by_page[o["page"]][o["node_identifier"]] = o
    models = {}
    manifest = json.loads((ROOT / "notes/Content data manifest.json").read_text(encoding="utf-8"))
    for f in manifest["files"]:
        if f.get("role") != "Published page content model":
            continue
        path = ROOT / f["path"]
        page = path.stem.split()[0]
        if page in by_page:
            assert sha(path) == f["sha256"], path
            models[page] = (path, json.loads(path.read_text(encoding="utf-8")))
    nodes = {}
    pin_index = defaultdict(lambda: defaultdict(set))
    for portion, obs in sorted(by_portion.items()):
        functions = Counter(layered.primary_function(o["function_literal"]) for o in obs)
        circuits = Counter(o["unit_code_literal"] for o in obs)
        selected = max(obs, key=lambda o: sum(bool(p.get("physical_pin")) for p in o["pins"]))
        node = {"id": portion, "portion": portion, "card_type": card,
                "function": functions.most_common(1)[0][0],
                "unit": circuits.most_common(1)[0][0],
                "row": sorted(by_portion).index(portion) * 7,
                "column": 0, "_page": "COMPOSITE", "_inputs": [], "_outputs": [],
                "function_variants": dict(functions), "circuit_variants": dict(circuits),
                "observation_ids": [o["observation_id"] for o in obs],
                "reference_occurrence": {"page": selected["page"], "block": selected["node_identifier"]}}
        for side in ("input", "output"):
            ports = defaultdict(list)
            for o in obs:
                for p in o["pins"]:
                    if p.get("direction") != side or not p.get("drawn_connected_port"):
                        continue
                    pin = p.get("physical_pin")
                    if pin:
                        if not PIN.fullmatch(pin):
                            issues.append({"kind": "invalid physical pin", "portion": portion, "pin": pin})
                            continue
                        if pin in SUPPLY:
                            issues.append({"kind": "supply tie omitted from signal graph", "portion": portion,
                                           "pin": pin, "observation_id": o["observation_id"]})
                            continue
                        ports[pin].append((o, p))
                    elif p.get("pin_name_readability") not in ("unprinted",):
                        issues.append({"kind": "unresolved nonphysical label", "portion": portion,
                                       "observation_id": o["observation_id"], "port": p})
            for pin, entries in sorted(ports.items()):
                polarity = Counter(p.get("polarity_decoration", {}).get("marker", "none") for _, p in entries)
                matching = [e for e in entries if layered.primary_function(e[0]["function_literal"]) == node["function"]]
                if not matching:
                    matching = entries
                wedges = Counter(bool(p.get("triangle_glyph")) or
                                 p.get("polarity_decoration", {}).get("marker") == "open triangle"
                                 for _, p in matching)
                # The literal border field is authoritative; triangle_glyph
                # may be absent on older records.
                wedge = Counter(any(b.get("glyph") == "◺" for b in
                                    p.get("polarity_decoration", {}).get("glyph_bindings", []))
                                for _, p in matching).most_common(1)[0][0]
                port = {"pin": pin, "raw": pin, "triangle": wedge, "side": side,
                        "row": len(node["_inputs"] if side == "input" else node["_outputs"]),
                        "ref": pin, "evidence": [o["observation_id"] for o, _ in entries],
                        "polarity_variants": dict(polarity)}
                node["_inputs" if side == "input" else "_outputs"].append(port)
                pin_index[pin][side].add(portion)
        nodes[portion] = node
    edges = defaultdict(list)
    rejected = []
    for page, obs in sorted(by_page.items()):
        if page not in models:
            issues.append({"kind": "missing current model", "page": page})
            continue
        path, doc = models[page]
        for net in doc.get("nets", []):
            drivers = [net.get("driver")]
            drivers += net.get("declared_physical_output_drivers", []) or []
            drivers += net.get("route_owners", []) or []
            for driver in set(d for d in drivers if isinstance(d, str)):
                if "." not in driver:
                    continue
                sid, source_ref = driver.split(".", 1)
                source = obs.get(sid)
                if not source:
                    continue
                for target in net.get("targets", []):
                    if not isinstance(target, str) or "." not in target:
                        continue
                    tid, target_ref = target.split(".", 1)
                    sink = obs.get(tid)
                    if not sink or source["physical_instance_key"] != sink["physical_instance_key"]:
                        continue
                    sp, tp = source["portion_literal"], sink["portion_literal"]
                    if sp == tp:
                        continue
                    source_pin = contact(source_ref)
                    target_pin = contact(target_ref)
                    source_pin = source["_pin_correction"].get(source_pin, source_pin)
                    target_pin = sink["_pin_correction"].get(target_pin, target_pin)
                    source_ports = [p for p in source["pins"] if p["direction"] == "output"]
                    target_ports = [p for p in sink["pins"] if p["direction"] == "input"]
                    source_named = {p["physical_pin"] for p in source_ports if p["physical_pin"]}
                    target_named = {p["physical_pin"] for p in target_ports if p["physical_pin"]}
                    # Old net-reference strings can survive a corrected box
                    # label. Never promote such a mismatched suffix into a new
                    # card contact or an extra logical input.
                    if source_pin and source_pin not in source_named or target_pin and target_pin not in target_named:
                        issues.append({"kind": "net suffix differs from current box port", "page": page,
                                       "driver": driver, "target": target,
                                       "source_named_outputs": sorted(source_named),
                                       "target_named_inputs": sorted(target_named)})
                        continue
                    if source_pin is None and not any(p["physical_pin"] is None for p in source_ports) and len(source_named) == 1:
                        source_pin = next(iter(source_named))
                    if target_pin is None and not any(p["physical_pin"] is None for p in target_ports):
                        if source_pin in target_named:
                            target_pin = source_pin
                        elif len(target_named) == 1:
                            target_pin = next(iter(target_named))
                        else:
                            issues.append({"kind": "unmapped unlabelled net target", "page": page, "driver": driver, "target": target})
                            continue
                    if source_pin and target_pin and source_pin != target_pin:
                        rejected.append({"page": page, "driver": driver, "target": target,
                                         "reason": "distinct physical contacts: installation strap"})
                        continue
                    if source_pin in SUPPLY or target_pin in SUPPLY:
                        continue
                    if source_pin is None and target_pin and len({d for d in drivers if isinstance(d, str)}) > 1:
                        rejected.append({"page": page, "driver": driver, "target": target,
                            "reason": "multi-driver installation net does not prove a fixed internal pinless-to-contact edge",
                            "source_join_evidence": net.get("source_join_evidence")})
                        continue
                    # Numbered/synthetic IN/OUT suffixes denote pinless ports.
                    # Nonphysical logical A/B port designators remain pinless.
                    edges[(sp, tp, source_pin or "PINLESS", target_pin or "PINLESS")].append(
                        {"page": page, "driver": driver, "target": target,
                         "source_observation": source["observation_id"], "target_observation": sink["observation_id"]})
    # A fixed physical contact electrically joins its driver to all consumers.
    # This includes consumers that are unused in the reference installation.
    for pin, sides in pin_index.items():
        for source in sides.get("output", set()):
            for target in sides.get("input", set()):
                if source != target:
                    edges[(source, target, pin, pin)].append({"basis": "same physical contact on card type", "pin": pin})
    # A missing port label in one occurrence does not create a second wire.
    # Where the two portions share a named output/input contact, that contact
    # identifies this connection. Otherwise a source with one known output
    # supplies the identity of its unlabelled output occurrence.
    normalized = defaultdict(list)
    for (s, t, out_ref, in_ref), evidence in edges.items():
        outputs = {p["pin"] for p in nodes[s]["_outputs"] if p["pin"]}
        inputs = {p["pin"] for p in nodes[t]["_inputs"] if p["pin"]}
        common = outputs & inputs
        if len(common) == 1:
            out_ref = in_ref = next(iter(common))
        elif out_ref == "PINLESS" and len(outputs) == 1:
            out_ref = next(iter(outputs))
        normalized[(s, t, out_ref, in_ref)].extend(evidence)
    # Add exactly the observed count of internal pinless ports needed by graph.
    for portion, node in nodes.items():
        incoming = [e for e in normalized if e[1] == portion and e[3] == "PINLESS"]
        if incoming:
            variants = [p for o in by_portion[portion] for p in o["pins"]
                        if p.get("direction") == "input" and not p.get("physical_pin")
                        and p.get("drawn_connected_port")]
            for index, edge in enumerate(incoming):
                node["_inputs"].append({"pin": None, "raw": None, "triangle":
                    any(b.get("glyph") == "◺" for p in variants for b in
                        p.get("polarity_decoration", {}).get("glyph_bindings", [])),
                    "side": "input", "row": index, "ref": "PINLESS"})
        if any(e[0] == portion and e[2] == "PINLESS" for e in normalized):
            node["_outputs"].append({"pin": None, "raw": None, "triangle":
                any(any(b.get("glyph") == "◺" for b in p.get("polarity_decoration", {}).get("glyph_bindings", []))
                    for o in by_portion[portion] for p in o["pins"]
                    if p.get("direction") == "output" and not p.get("physical_pin")),
                "side": "output", "row": 0, "ref": "PINLESS"})
    conflicts = []
    for pin, sides in sorted(pin_index.items()):
        if len(sides.get("output", set())) > 1:
            conflicts.append({"kind": "multiple physical output portions", "pin": pin,
                              "portions": sorted(sides["output"])})
    return {"schema": "card-universal-evidence-v1", "card_type": card,
            "catalog_sha256": sha(catalog_path), "observations": len(observations),
            "pages": len(by_page), "portions": nodes,
            "database_portions": sorted((set(catalog["observed_portions"]) | set(catalog["listing_portions"])) - ({"F2"} if card == "4633" else set())),
            "missing_portions": sorted(((set(catalog["observed_portions"]) | set(catalog["listing_portions"])) - ({"F2"} if card == "4633" else set())) - set(nodes)),
            "edges": [{"source": s, "target": t, "output_ref": o, "input_ref": i,
                       "evidence": evidence} for (s, t, o, i), evidence in sorted(normalized.items())],
            "signal_pins": {pin: {side: sorted(ps) for side, ps in sides.items()}
                            for pin, sides in sorted(pin_index.items())},
            "power_pins": SUPPLY, "conflicts": conflicts, "issues": issues,
            "candidate_source_corrections": corrections_used,
            "native_minority_audit": {"path": str(minority_audit_path), "sha256": sha(minority_audit_path)} if minority_audit_path.is_file() else None,
            "excluded_installation_straps": rejected,
            "models": [{"page": page, "path": str(path.relative_to(ROOT)), "sha256": sha(path)}
                       for page, (path, _) in sorted(models.items())]}

def main():
    for card in ("4633", "4634"):
        result = extract(card)
        write(OUT / f"{card} composite.json", result)
        render_candidates(result)
        print(card, "occurrences", result["observations"], "pages", result["pages"],
              "portions", len(result["portions"]), "edges", len(result["edges"]),
              "pins", len(result["signal_pins"]), "conflicts", len(result["conflicts"]))

def render_candidates(model):
    card = model["card_type"]
    dictionary_path = OUT.parent / "Manual canonical circuit forms.json"
    manual = json.loads(dictionary_path.read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "json/Card types current" / f"{card}.json").read_text(encoding="utf-8"))
    canonical = {}
    provisional = []
    for portion, node in model["portions"].items():
        source = manual["circuits"][node["unit"]]
        form = source.get("canonical_form")
        if form:
            canonical[portion] = {"function": form["primary_function"],
                "input_wedge": bool(form["all_input_triangles"]),
                "output_wedge": bool(form["all_output_triangles"])}
        else:
            provisional.append(portion)
            canonical[portion] = {"function": node["function"],
                "input_wedge": Counter(p["triangle"] for p in node["_inputs"]).most_common(1)[0][0] if node["_inputs"] else False,
                "output_wedge": Counter(p["triangle"] for p in node["_outputs"]).most_common(1)[0][0] if node["_outputs"] else False}
    geometry = renderer.prepare(model)
    observed_signal = set(model["signal_pins"])
    unavailable = sorted({f"{a}{n:02}" for a in "BDGJ" for n in range(2,14)} - observed_signal - set(SUPPLY))
    header = [f"CARD-ALD 580{card} DOUBLE CARD  COMPOSITE PINOUT  CANONICAL CIRCUIT FORMS",
              "POWER: GROUND D08 J08; +3V D03 J03; -3V B06 G06; +6V B11 G11",
              f"{model['observations']} REVIEWED OCCURRENCES ON {model['pages']} PAGES; {len(model['portions'])} PORTIONS; {len(model['signal_pins'])} OBSERVED SIGNAL CONTACTS",
              "NO OBSERVED SIGNAL CONNECTION: " + (", ".join(unavailable) if unavailable else "NONE"),
              "PROVISIONAL OBSERVATION-DERIVED CIRCUIT FORM: " + (", ".join(p+" "+model['portions'][p]['unit'] for p in provisional) if provisional else "NONE"),
              "WIRING IS THE UNION OF REVIEWED CARD OCCURRENCES; INSTALLATION STRAPS ARE EXCLUDED.",
              "FUNCTIONS AND WEDGES FOLLOW THE SLT MANUAL DEFINITIONS; NUMBERED FILES RETAIN OBSERVED NOTATION."]
    base = renderer.draw(model, geometry, canonical, header)
    (OUT / f"{card}.txt").write_text(base, encoding="utf-8")
    # One observed installed card can be spread over several sheets. Build
    # complete symbol-pattern variants from those physical-instance groups.
    # Portions unused in that installation keep the canonical symbol.
    installed = defaultdict(dict)
    installed_evidence = defaultdict(list)
    for record in catalog["diagram_occurrences"]:
        portion = record["portion"]
        if (card, record["page"], record["node"], portion) == ("4633", "AP271", "AS", "F2"):
            portion = "A2"
        if portion not in model["portions"]:
            continue
        ins = [bool(p["triangle"]) for p in record["pins"] if p["side"] == "input"]
        outs = [bool(p["triangle"]) for p in record["pins"] if p["side"] == "output"]
        # The observed function convention determines uniform polarity of
        # equivalent inputs; majority resolves a partially omitted marker.
        form = {"function": layered.primary_function(record["function_label"]),
                "input_wedge": Counter(ins).most_common(1)[0][0] if ins else canonical[portion]["input_wedge"],
                "output_wedge": Counter(outs).most_common(1)[0][0] if outs else canonical[portion]["output_wedge"]}
        correction = next((x.get("pins", {}) for x in model["candidate_source_corrections"]
                           if x["page"] == record["page"] and x["node"] == record["node"]), {})
        for side in ("input", "output"):
            explicit = {}
            unknown = []
            for port in record["pins"]:
                if port["side"] != side:
                    continue
                pin = contact(correction.get(port["pin"], port["pin"]))
                if pin:
                    explicit[pin] = bool(port["triangle"])
                else:
                    unknown.append(bool(port["triangle"]))
            if side == "output" and unknown:
                explicit["INTERNAL:" + portion] = unknown[0]
            elif side == "input" and unknown:
                incoming = sorted({(e["output_ref"] if e["output_ref"] != "PINLESS" else "INTERNAL:"+e["source"])
                                   for e in model["edges"] if e["target"] == portion and e["input_ref"] == "PINLESS"})
                if len(unknown) == len(incoming) == 1 or len(set(unknown)) == 1:
                    explicit.update({key: unknown[0] for key in incoming})
                elif unknown:
                    # Preserve the literal row pattern in evidence if its
                    # connection-to-row attribution is not uniquely known.
                    form["unmapped_pinless_markers"] = unknown
            if explicit:
                form[side + "_wedges"] = explicit
        key = record["location"]
        installed[key][portion] = form
        installed_evidence[key].append({"page": record["page"], "node": record["node"], "portion": portion,
                                        "literal_function": record["function_label"],
                                        "input_markers": ins, "output_markers": outs})
    variants = {}
    for instance, observed in installed.items():
        form = deepcopy(canonical)
        form.update(observed)
        signature = json.dumps(form, sort_keys=True)
        if signature == json.dumps(canonical, sort_keys=True):
            continue
        if signature not in variants:
            variants[signature] = {"forms": form, "instances": [], "evidence": []}
        variants[signature]["instances"].append(instance)
        variants[signature]["evidence"].extend(installed_evidence[instance])
    positions, ports, exterior, router = geometry
    mutable = {(x, y) for n in positions.values() for x in range(n["x"]+1,n["x"]+7)
               for y in (n["top"]+1,)}
    mutable |= {(positions[p]["x"] if side == "input" else positions[p]["x"]+7, port["point"][1])
                for (p,side,_),port in ports.items()}
    base_rows = [line.ljust(router.width) for line in base.splitlines()]
    index = []
    for number, variant in enumerate(variants.values(), 1):
        variant_header = list(header)
        variant_header[0] = f"CARD-ALD 580{card} DOUBLE CARD  COMPOSITE PINOUT  OBSERVED NOTATION VARIANT {number:02}"
        variant_header[6] = "SAME PORTIONS, CONTACTS AND WIRE GEOMETRY AS BASE; ONLY FUNCTION LABELS AND WEDGES DIFFER."
        text = renderer.draw(model, geometry, variant["forms"], variant_header)
        rows = [line.ljust(router.width) for line in text.splitlines()]
        assert len(rows) == len(base_rows)
        for y in range(7, len(rows)):
            assert all(a == b or (x,y) in mutable for x,(a,b) in enumerate(zip(base_rows[y], rows[y]))), (card,number,y)
        name = f"{card}-{number:02}.txt"
        (OUT / name).write_text(text, encoding="utf-8")
        index.append({"file": name, "sha256": sha(OUT/name), **variant})
    write(OUT / f"{card} render provenance.json", {
        "schema": "card-composite-render-v1", "card_type": card,
        "base": {"file": f"{card}.txt", "sha256": sha(OUT/f"{card}.txt")},
        "composite_model_sha256": sha(OUT/f"{card} composite.json"),
        "canonical_dictionary": {"path": str(dictionary_path), "sha256": sha(dictionary_path)},
        "canonical_forms": canonical, "provisional_canonical_portions": provisional,
        "unobserved_contacts": unavailable, "variants": index,
        "variant_geometry_identity_verified": True,
        "geometry": {"width": router.width, "height": router.height, "boxes": positions,
                     "ports": [{"portion": p,"side":side,"net":net,**port} for (p,side,net),port in ports.items()],
                     "exterior_contacts": exterior,
                     "net_wire_cells": {net: sorted(cells) for net,cells in router.by_net.items()}}})

if __name__ == "__main__":
    main()

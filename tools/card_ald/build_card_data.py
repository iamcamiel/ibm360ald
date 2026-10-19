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
import sys
import card_source as page_reader
import re
import sys

from card_source import physical_contact, resolve_net_port

import generate_card
import render_composite_card
import component_forms

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


def primary(label):
    text = str(label or "").strip()
    return text.split()[0] if text else "�"

def parse_location(text, listed_locations=None):
    """Resolve abbreviated cabinets from actual socket-listing evidence.

    A missing cabinet number is ambiguous when two listed cabinets match.
    Ordinary 02 aliases retain their existing meaning when no listing matches.
    """
    literal = str(text or "").strip().upper()
    explicit = re.fullmatch(r"(\d{2}[A-Z])-([A-Z]\d)([A-Z]\d)(?:[BT])?", literal)
    if explicit:
        cabinet, board, socket = explicit.groups()
        return cabinet + "-" + board, socket
    abbreviated = re.fullmatch(r"([A-Z])-([A-Z]\d)([A-Z]\d)(?:[BT])?", literal)
    if not abbreviated:
        return None
    frame, board, socket = abbreviated.groups()
    candidates = set()
    for listed_board, listed_socket in listed_locations or ():
        match = re.fullmatch(r"\d{2}([A-Z])-([A-Z]\d)", str(listed_board))
        if match and match.groups() == (frame, board) and listed_socket == socket:
            candidates.add((listed_board, socket))
    if candidates:
        return next(iter(candidates)) if len(candidates) == 1 else None
    if frame in "ABCEKL":
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

def locate_catalog_node(model, occurrence):
    node,pointer,problem=page_reader.exact_source_node(model,occurrence)
    return node, ({'reason':problem,'node_pointer':occurrence.get('node_pointer')} if problem else
                  {'method':'exact node_pointer' if occurrence.get('node_pointer') is not None else 'unique non-null ID','node_pointer':pointer})


def load_evidence(card, overlay, component_authority_path=None):
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
        identity_issue = page_reader.ordinary_slt_identity_issue(original, card)
        if identity_issue:
            uncertainties.append({"kind":"ordinary SLT portion identity unresolved", "page":original.get("page"), "node":original.get("node"), "identity":identity_issue})
            continue
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
    models = {};model_paths={}
    bindings = [binding(catalog_path), binding(manifest_path), binding(Path(page_reader.__file__))]
    bindings.extend(binding(path) for path in page_reader.runtime_paths(ROOT))
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
        models[page] = page_reader.read(path,ROOT)
        model_paths[page]=path.resolve()
        bindings.append(binding(path))
    for page in sorted(pages - set(models)):
        uncertainties.append({"kind": "current source model unavailable", "page": page})
    for proof in overlay.get('reviewed_pinless_controls',[]) if overlay else []:
        page=proof.get('page');model=models.get(page);authority=proof.get('model_binding')
        authority_path=Path(authority.get('path','')) if authority else None
        if authority_path is not None and not authority_path.is_absolute():authority_path=ROOT/authority_path
        if not model or not authority or authority_path.resolve()!=model_paths.get(page) or not verify_binding(authority)['current']:
            uncertainties.append({'kind':'pinless control review has no current source binding','review':proof});continue
        choices=[p for n in model.get('nodes',[]) if n.get('id')==proof.get('node') for p in n.get('pins',[])
                 if p.get('_terminal_id')==proof.get('terminal_id') and p.get('pin')==proof.get('literal') and p.get('side')=='input']
        if proof.get('role')!='anonymous-input-wire-annotation' or len(choices)!=1:
            uncertainties.append({'kind':'pinless control review does not identify one current input','review':proof});continue
        choices[0]['_reviewed_pinless_control']=deepcopy(proof)
        catalog.setdefault('_reviewed_pinless_controls',[]).append(deepcopy(proof))
    for raw in catalog.get("diagram_occurrences", []):
        page=raw.get("page")
        if page not in models:continue
        node, source_lookup = locate_catalog_node(models[page], raw)
        if node is None:
            uncertainties.append({"kind":"catalog node unresolved in current hash-bound model","page":page,"node":raw.get("node"),"source_lookup":source_lookup})
            continue
        portion_issue = page_reader.ordinary_slt_identity_issue(node, card)
        if portion_issue:
            uncertainties.append({"kind":"ordinary SLT portion identity unresolved", "page":page, "node":raw.get("node"), "identity":portion_issue})
            observations[:] = [o for o in observations if not (o.get("page")==page and o.get("node")==raw.get("node") and o.get("node_pointer")==raw.get("node_pointer"))]
            continue
        identity_audit = node.get("_identity_conflict")
        if identity_audit:
            uncertainties.append({"kind":"conflicting raw model card identity aliases", "page":page, "node":raw.get("node"), "identity_adaptation":identity_audit})
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
        else:
            for observed in observations:
                if observed.get('page')==page and observed.get('node_pointer')==raw.get('node_pointer'):
                    page_reader.attach_typed_terminals(observed,node)
                    observed['_model_binding']=binding(model_paths[page])
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
        location = parse_location(o.get("location"), socket_pairs)
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
    profiles,component_binding=component_forms.reviewed_components(ROOT,component_authority_path,observations,widths,kinds,catalog.get("full_part_numbers_observed",[]))
    if profiles:
        authorized_power=next(iter(profiles.values()))["power_contacts"]
        if "power_contacts" in overlay and overlay["power_contacts"]!=authorized_power:
            raise ValueError("Supplement power contacts differ from current component authority")
        power=deepcopy(authorized_power)
        catalog["_reviewed_component_forms"]=profiles
        bindings.append(component_binding)
        uncertainties[:]=[u for u in uncertainties if u.get("kind")!="module kind lacks one unambiguous ordinary SLT single/double pinout"]
    if profiles:
        import component_context
        context=component_context.apply_context(ROOT,catalog,models,
            {page:binding(path)for page,path in model_paths.items()},authority_path=component_authority_path)
        for hold in context.get('holds',[]):
            uncertainties.append({'kind':'component occurrence net-origin context unresolved',**hold})
        for occurrence in observations:
            node,lookup=locate_catalog_node(models.get(occurrence['page'],{}),occurrence)
            if node is not None:page_reader.attach_typed_terminals(occurrence,node)
        if context.get('proofs'):
            catalog['_occurrence_net_origin_context']=deepcopy(context)
            bindings.append(binding(Path(component_context.__file__)))
    # Deduplicate exact source bindings while preserving deterministic order.
    bindings = sorted({(b["path"], b["sha256"]): b for b in bindings}.values(), key=lambda b:b["path"])
    return catalog, observations, models, power, bindings, changes, uncertainties

def annotation_supply_driver(raw_nodes, drivers, power):
    """Recognize only an explicitly reviewed non-card ground service terminal.

    A pin named like a supply rail on a real card is not sufficient evidence.
    Mixed-driver nets and unreadable/unreviewed pseudo-blocks remain unresolved.
    """
    if len(drivers)!=1:return None
    reference=next(iter(drivers))
    if not isinstance(reference,str) or '.' not in reference:return None
    node=raw_nodes.get(reference.split('.',1)[0],{})
    if (node.get('kind')!='service' or node.get('source_reviewed') is not True
        or node.get('card_type') not in (None,'') or node.get('portion') not in (None,'')
        or node.get('unit')!='GND' or not node.get('non_card_evidence')):return None
    port=resolve_net_port(node,reference,'output')
    if port['status']!='numbered' or power.get(port['physical_contact'])!='GROUND':return None
    return {'reference':reference,'power_contact':port['physical_contact'],'level':'GROUND',
            'source_kind':'reviewed non-card ground service terminal'}


def select_notation_baseline(node,occurrences,uncertainties):
    """One joint current source pattern, never independent per-pin votes."""
    mixed_symbols=node.pop('_mixed_symbol_slots',None)
    mixed_triangles=node.pop('_mixed_triangle_slots',None)
    observed_symbols=node.pop('_observed_symbol_slots',None)
    origin_slots=node.pop('_observed_net_origin_slots',None)
    if not mixed_symbols and not mixed_triangles and not observed_symbols and not origin_slots:return
    ports={(p['side'],p['pin']):p for p in node['_inputs']+node['_outputs'] if p.get('pin')}
    required={slot for slot,p in ports.items() if any(any(o.get('pin_symbols',{}).values()) for o in p.get('source_pin_symbol_observations',[]))
              or any(o.get('border_symbol')=='X' for o in p.get('source_edge_decorations',[]))}
    required.update(mixed_triangles or [])
    required.update(origin_slots or [])
    patterns=[]
    for occurrence in occurrences:
        slots={};conflict=False
        for _,terminal in page_reader.logical_terminal_items(occurrence):
            slot=(terminal.get('side'),page_reader.terminal_contact(terminal))
            if slot not in ports:continue
            try:
                symbols=page_reader.terminal_pin_symbols(terminal)
                if symbols is None:continue
                value={'pin_symbols':symbols,'border_symbol':page_reader.terminal_border_symbol(terminal)}
                if page_reader.occurrence_net_role(terminal):value['occurrence_net_role']=page_reader.documentary_occurrence_net_role(terminal)
                if node.get('_reviewed_component'):
                    value['triangle']=page_reader.wedge(terminal)
                    if type(value['triangle'])is not bool:conflict=True;continue
            except ValueError:conflict=True;continue
            if slot in slots and slots[slot]!=value:conflict=True
            slots[slot]=value
        patterns.append({'page':occurrence['page'],'node':occurrence['node'],'node_pointer':occurrence.get('node_pointer'),
            'model_binding':deepcopy(occurrence.get('_model_binding')),
            'ports':[{'side':s,'pin':p,**v} for (s,p),v in sorted(slots.items())],
            'complete_portion_contacts':set(ports)<=set(slots),
            'all_symbol_bearing_contacts_observed':required<=set(slots),'conflicting_source_fields':conflict})
    node['_source_notation_variants']=patterns
    candidates=[p for p in patterns if p['all_symbol_bearing_contacts_observed'] and not p['conflicting_source_fields']]
    if not candidates:
        uncertainties.append({'kind':'source symbol variants lack one joint baseline witness','portion':node['portion']});return
    baseline=min(candidates,key=lambda p:(not p['complete_portion_contacts'],-len(p['ports']),p['page'],str(p['node'])))
    node['_source_notation_baseline_witness']=deepcopy(baseline)
    for observation in baseline['ports']:
        port=ports[observation['side'],observation['pin']]
        for key in ('pin_symbols','border_symbol','triangle'):
            if key not in observation:continue
            if key=='triangle':port[key]=observation[key];continue
            if observation[key] is not None and (key!='pin_symbols' or any(observation[key].values())):port[key]=deepcopy(observation[key])
            else:port.pop(key,None)


def _derive_semantics_base(card, catalog, observations, models, power, uncertainties):
    portions = defaultdict(list)
    by_page = defaultdict(dict)
    for o in observations:
        if page_reader.ordinary_slt_identity_issue(o, card):
            raise ValueError("Unresolved ordinary SLT portion identity cannot enter semantic grouping")
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
        profile=catalog.get("_reviewed_component_forms",{}).get(circuit)
        if profile:
            node["function"]=profile["printed_function"]
            triangles={}
            node["_reviewed_component"]=deepcopy(profile)
            if profile.get("above_block_caption"):node["above_block_caption"]=profile["above_block_caption"]
            uncertainties[:]=[u for u in uncertainties if not (u.get("kind")=="canonical circuit form not established by manual" and u.get("portion")==portion)]
            node["_observed_function_labels"]=sorted({str(o.get("function_label") or "").strip() for o in occurrences})
            node["_source_auxiliary_labels"]=component_forms.source_labels(occurrences,models)
            node["_source_pin_literals"]=sorted([{"side":side,"physical_contact":contact,"literal":literal} for side,contact,literal in {
                (p.get("side"),page_reader.terminal_contact(p),str(p.get("pin"))) for o in occurrences for p in o.get("pins",[]) if page_reader.terminal_contact(p) and str(p.get("pin"))!=page_reader.terminal_contact(p)}],key=lambda p:(p["side"],p["physical_contact"],p["literal"]))
        node["_canonical_triangles"] = triangles
        node["_observed_pinless_counts"] = {}
        node["_observed_pinless_triangles"] = {}
        for side in ("input", "output"):
            pinless = [[p for p in o.get("pins",[]) if p.get("side")==side and
                        page_reader.pinless_terminal(p)]
                       for o in occurrences]
            node["_observed_pinless_counts"][side]=max((len(ps) for ps in pinless),default=0)
            marker_values={page_reader.wedge(p) for ps in pinless for p in ps}
            if None in marker_values:
                uncertainties.append({"kind":"unknown source pinless border polarity","portion":portion,"side":side})
                marker_values.discard(None)
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
                for _,p in page_reader.logical_terminal_items(o):
                    if p.get("side") != side:
                        continue
                    pin = page_reader.terminal_contact(p)
                    if pin and pin not in power:
                        if set(power) == set(SINGLE_POWER) and pin[0] in "GJ":
                            uncertainties.append({"kind": "double-card contact on single-card occurrence", "page": o["page"], "node": o["node"], "pin": pin})
                            continue
                        names[pin].append((o,p))
                    elif p.get("pin") is not None and pin is None and not page_reader.pinless_terminal(p):
                        uncertainties.append({"kind": "unresolved physical/control label", "page": o["page"], "node": o["node"], "portion": portion, "label": p["pin"]})
            for pin, entries in sorted(names.items()):
                roles={page_reader.intrinsic_contact_role(p) for _,p in entries}
                origins=[page_reader.documentary_occurrence_net_role(p)for _,p in entries if page_reader.occurrence_net_role(p)]
                if origins:
                    node.setdefault('_observed_net_origin_slots',[]).append((side,pin))
                    node.setdefault('_source_decoration_variants',[]).append({'side':side,'pin':pin,'occurrence_net_origin_observations':deepcopy(origins),'status':'External page commoning only; canonical physical port and intrinsic nets unchanged.'})
                nonlogical=roles=={'nonlogical_common'}
                if len(roles)>1:
                    uncertainties.append({'kind':'conflicting logical/nonlogical contact role','portion':portion,'side':side,'pin':pin})
                # K has no Boolean gate polarity. Retain its exact source edge
                # instead of applying the circuit's all-output inversion rule.
                wedge = None if nonlogical else triangles.get(side)
                if wedge is None:
                    readings = {page_reader.wedge(p) for _,p in entries}
                    if None in readings:
                        uncertainties.append({"kind":"unknown source border polarity","portion":portion,"side":side,"pin":pin})
                        readings.discard(None)
                    wedge = next(iter(readings)) if len(readings) == 1 else False
                    if len(readings) > 1:
                        if profile:
                            node.setdefault('_mixed_triangle_slots',[]).append((side,pin))
                            node.setdefault('_source_decoration_variants',[]).append({
                                'side':side,'pin':pin,'baseline_triangle':wedge,
                                'status':'Observed source notation variants; no hidden wiring or algebraic equivalence inferred.',
                                'occurrences':[{'page':o['page'],'node':o['node'],'row':p.get('row'),'triangle':page_reader.wedge(p)} for o,p in entries]})
                        else:
                            uncertainties.append({"kind": "noncanonical decoration differs", "portion": portion, "side": side, "pin": pin})
                port = {"pin": pin, "triangle": wedge, "side": side, "row": len(node["_inputs"] if side == "input" else node["_outputs"]),
                        "ref": pin, "evidence": [{"page":o["page"],"node":o["node"],"row":p.get("row")} for o,p in entries]}
                if nonlogical:
                    port.update(contact_role='nonlogical_common',border_control='K')
                    port['source_contact_role_observations']=[{'page':o['page'],'node':o['node'],
                        'terminal_id':p.get('_terminal_id'),'contact_role':page_reader.terminal_contact_role(p),
                        'triangle':page_reader.wedge(p)} for o,p in entries]
                if profile:
                    port["source_triangle_observations"]=[{"page":o["page"],"node":o["node"],"terminal_id":p.get("_terminal_id"),"triangle":page_reader.wedge(p)}for o,p in entries]
                edge_symbols=[]
                for occurrence,terminal in entries:
                    try:symbol=page_reader.terminal_border_symbol(terminal)
                    except ValueError as problem:
                        uncertainties.append({'kind':'conflicting typed border symbols','page':occurrence['page'],
                            'node':occurrence['node'],'portion':portion,'side':side,'pin':pin,'reason':str(problem)})
                        continue
                    edge_symbols.append({'page':occurrence['page'],'node':occurrence['node'],
                        'terminal_id':terminal.get('_terminal_id'),'border_symbol':symbol,
                        'border_decorations':deepcopy(terminal.get('_border_decorations',[])),
                        'pin_symbols':deepcopy(terminal.get('_symbols',{}))})
                if any(item['border_symbol']=='X' for item in edge_symbols):
                    port['source_edge_decorations']=edge_symbols
                    if wedge:
                        uncertainties.append({'kind':'typed border symbol conflicts with canonical triangle','portion':portion,'side':side,'pin':pin})
                    else:port['border_symbol']='X'
                    if any(item['border_symbol'] is None for item in edge_symbols):
                        node.setdefault('_mixed_symbol_slots',[]).append((side,pin))
                        node.setdefault('_source_decoration_variants',[]).append({'side':side,'pin':pin,
                            'baseline_border_symbol':'X','status':'Partial source edge-symbol observations; no unobserved X inferred.',
                            'occurrences':deepcopy(edge_symbols)})
                symbol_observations=[]
                for occurrence,terminal in entries:
                    try:symbols=page_reader.terminal_pin_symbols(terminal)
                    except ValueError as problem:
                        uncertainties.append({'kind':'unresolved typed pin symbol placement','page':occurrence['page'],
                            'node':occurrence['node'],'portion':portion,'side':side,'pin':pin,'reason':str(problem)})
                        continue
                    if symbols is not None:symbol_observations.append({'page':occurrence['page'],'node':occurrence['node'],
                        'terminal_id':terminal.get('_terminal_id'),'pin_symbols':symbols,
                        'source_symbols':deepcopy(terminal.get('_symbols',{}))})
                if any(any(item['source_symbols'].get(side,[]) for side in ('prefix','suffix','unplaced')) for item in symbol_observations):
                    if any(any(item['pin_symbols'].values())for item in symbol_observations):node.setdefault('_observed_symbol_slots',[]).append((side,pin))
                    port['source_pin_symbol_observations']=symbol_observations
                    readings={json.dumps(item['pin_symbols'],sort_keys=True) for item in symbol_observations}
                    if len(readings)==1 and any(symbol_observations[0]['pin_symbols'].values()):port['pin_symbols']=deepcopy(symbol_observations[0]['pin_symbols'])
                    elif len(readings)>1:node.setdefault('_mixed_symbol_slots',[]).append((side,pin))
                node["_inputs" if side == "input" else "_outputs"].append(port)
                contact_ports[pin][side].add(portion)
        select_notation_baseline(node,occurrences,uncertainties)
        nodes[portion] = node
    edges = defaultdict(list)
    input_fanouts = defaultdict(list)
    rejected = []
    endpoint_records = []
    supply_ties = []
    supply_ports = set()
    for page, model in sorted(models.items()):
        records = by_page[page]
        raw_nodes = {n.get("id"): n for n in model.get("nodes", [])}
        for net_index, net in enumerate(model.get("nets", [])):
            drivers = {net.get("driver")} if isinstance(net.get("driver"),str) else set()
            for field in ("declared_physical_output_drivers", "route_owners"):
                drivers.update(x for x in net.get(field, []) or [] if isinstance(x,str))
            resolutions = {}
            for side, references in (("output", sorted(drivers)), ("input", net.get("targets", []))):
                for reference in references:
                    if not isinstance(reference, str) or "." not in reference:
                        continue
                    node_id = reference.split(".", 1)[0]
                    occurrence = records.get(node_id)
                    if occurrence is None:
                        continue
                    # Real models must resolve their actual raw node. Minimal
                    # fixtures without a nodes array can use occurrence ports.
                    raw_node = raw_nodes.get(node_id, occurrence if "nodes" not in model else {})
                    resolution = resolve_net_port(raw_node, reference, side, occurrence.get("pins"))
                    resolutions[side, reference] = resolution
                    if resolution["status"] == "unresolved":
                        uncertainties.append({"kind": "net endpoint identity unresolved", "page": page,
                                              "net_index": net_index, "reference": reference, "side": side,
                                              "resolution": deepcopy(resolution)})
            supply=annotation_supply_driver(raw_nodes,drivers,power)
            if supply:
                for (side,reference),resolution in resolutions.items():
                    if side!='input' or resolution['status']!='pinless':continue
                    occurrence=records[reference.split('.',1)[0]]
                    supply_ports.add((page,occurrence['node'],resolution['port_index']))
                    supply_ties.append({'page':page,'net_index':net_index,'net_id':net.get('id'),
                        'portion':occurrence['portion'],'node':occurrence['node'],'target':reference,
                        'target_port_index':resolution['port_index'],**deepcopy(supply),
                        'interpretation':'Explicit page supply tie, omitted from signal wiring; no internal card edge inferred.'})
            if resolutions:
                endpoint_records.append({"page": page, "net_index": net_index, "net_id": net.get("id"),
                    "declared_driver": deepcopy(net.get("driver")), "declared_targets": deepcopy(net.get("targets", [])),
                    "declared_physical_output_drivers": deepcopy(net.get("declared_physical_output_drivers", [])),
                    "route_owners": deepcopy(net.get("route_owners", [])),
                    "terminals": [{"side": side, "reference": reference, **deepcopy(value)}
                                  for (side, reference), value in sorted(resolutions.items())]})
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
                    source_port = resolutions.get(("output", driver), {"status": "unresolved"})
                    target_port = resolutions.get(("input", target), {"status": "unresolved"})
                    if source_port["status"] == "unresolved" or target_port["status"] == "unresolved":
                        rejected.append({"page":page,"driver":driver,"target":target,
                                         "reason":"unresolved exact side-specific endpoint; no pinless inference",
                                         "source_resolution":deepcopy(source_port),"target_resolution":deepcopy(target_port)})
                        continue
                    sp, tp = source_port["physical_contact"], target_port["physical_contact"]
                    if source_port.get('input_only_alias'):
                        # A repeated AR output is the already existing input
                        # contact. Preserve its fanout without inventing a driver.
                        if sp in power or tp in power:
                            continue
                        if tp and sp != tp:
                            rejected.append({"page":page,"driver":driver,"target":target,
                                "reason":"input-only AR contact joins another numbered contact: installation strap"})
                            continue
                        input_fanouts[sp,t,tp or "PINLESS"].append({"page":page,
                            "source_reference":driver,"target":target,"instance":source["_instance"],
                            "role":"input contact fanout; not a block output"})
                        continue
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
                    # Retain the existing installation/power boundary policy;
                    # exact endpoint resolution does not infer anonymous ports.
                    if sp in power or tp in power:
                        continue
                    if sp and tp and sp != tp:
                        rejected.append({"page":page,"driver":driver,"target":target,"reason":"different physical contacts after endpoint inference: installation strap"})
                        continue
                    edges[s,t,sp or "PINLESS",tp or "PINLESS"].append({"page":page,"driver":driver,"target":target,"instance":source["_instance"]})
    for pin,sides in sorted(contact_ports.items()):
        logical_outputs={s for s in sides['output'] if any(p.get('pin')==pin and page_reader.logical_gate_terminal(p) for p in nodes[s]['_outputs'])}
        if len(logical_outputs) > 1:
            uncertainties.append({"kind":"multiple portions drive one contact; wired-OR needs review","pin":pin,"portions":sorted(sides["output"])})
        for s in sorted(sides["output"]):
            for t in sorted(sides["input"]):
                if s != t:
                    edges[s,t,pin,pin].append({"basis":"fixed shared physical contact","pin":pin})
    final_edges = [{"source":s,"target":t,"output_ref":o,"input_ref":i,"evidence":e}
                   for (s,t,o,i),e in sorted(edges.items())]
    final_input_fanouts=[{"contact":pin,"target":target,"input_ref":ref,"evidence":facts}
                         for (pin,target,ref),facts in sorted(input_fanouts.items())]
    for portion,node in nodes.items():
        for fanout in final_input_fanouts:
            if fanout['target']==portion and fanout['input_ref']=='PINLESS':
                node['_inputs'].append({"pin":None,"triangle":node['_observed_pinless_triangles']['input'],
                    "side":"input","row":len(node['_inputs']),"ref":"INPUT_CONTACT:"+fanout['contact']})
        for e in final_edges:
            if e["target"] == portion and e["input_ref"] == "PINLESS":
                node["_inputs"].append({"pin":None,"triangle":node["_observed_pinless_triangles"]["input"],"side":"input","row":len(node["_inputs"]),"ref":e["source"]})
        if any(e["source"] == portion and e["output_ref"] == "PINLESS" for e in final_edges):
            node["_outputs"].append({"pin":None,"triangle":node["_observed_pinless_triangles"]["output"],"side":"output","row":0,"ref":"PINLESS"})
        for side,key in (("input","_inputs"),("output","_outputs")):
            expected=node["_observed_pinless_counts"][side]
            if side=='input':
                # Remove only those exact anonymous terminals individually proved
                # to be supply ties; a different use still needs normal tracing.
                expected=max((sum(1 for index,port in enumerate(o.get('pins',[]))
                    if port.get('side')=='input' and page_reader.pinless_terminal(port)
                    and (o['page'],o['node'],index) not in supply_ports)
                    for o in portions[portion]),default=0)
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
    if catalog.get("_reviewed_component_forms"):
        possible={f"{letter}{number:02}" for letter in next(iter(catalog["_reviewed_component_forms"].values()))["contact_banks"] for number in range(2,14)}
    return {"schema":"derived-card-data-v1","card_type":card,"observations":len(observations),
            "pages":len(by_page),"portions":nodes,"edges":final_edges,"input_contact_fanouts":final_input_fanouts,
            "signal_pins":{pin:{side:sorted(ps) for side,ps in sides.items()} for pin,sides in sorted(contact_ports.items())},
            "power_pins":power,"source_supply_ties":supply_ties,"rejected_installation_or_unmapped_edges":rejected,
            "source_net_endpoint_resolutions":endpoint_records,
            "unobserved_contacts":sorted(possible-set(power)-set(contact_ports)),
            "unobserved_contact_interpretation":"No connection observed; electrical disconnection is not established.",
            "listing_portions":sorted(listed),"listing_records":catalog.get("listing_records",[])}, manual_path

def derive_semantics(card, catalog, observations, models, power, uncertainties):
    model,manual_path=_derive_semantics_base(card,catalog,observations,models,power,uncertainties)
    if any(n.get('_observed_pinless_counts',{}).get('output',0)>1 for n in model['portions'].values()):
        import anonymous_outputs
        try:
            model=anonymous_outputs.preserve(model,models,page_reader,uncertainties)
        except (ValueError,KeyError,TypeError) as problem:
            uncertainties.append({'kind':'anonymous output joint witness incomplete','holds':[str(problem)]})
    return model,manual_path




def terminal_components(model):
    """Return logical port memberships independently of drawing coordinates."""
    nets = defaultdict(set)
    if model.get('networks') is not None:
        for network in model['networks']:
            for side in ('input','output'):
                for portion,port_id in network[side+'s']:
                    nets[network['id']].add((portion,side,port_id))
        return nets
    for portion,node in model["portions"].items():
        for side,key in (("input","_inputs"),("output","_outputs")):
            for p in node[key]:
                if p["pin"]:
                    nets[p["pin"]].add((portion,side,p["pin"]))
    for fanout in model.get('input_contact_fanouts',[]):
        nets[fanout['contact']].add((fanout['target'],'input',
            None if fanout['input_ref']=='PINLESS' else fanout['input_ref']))
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


def copy_nonlogical_contacts(spec,model,reviewed_overlay=None):
    """Carry only exact current K roles into stable physical drawing slots."""
    for box in spec['boxes']:
        semantic=model['portions'].get(box['portion'],{})
        ports=semantic.get('_inputs',[])+semantic.get('_outputs',[])
        claims=(reviewed_overlay or {}).get('reviewed_portions',{}).get(box['portion'],{}).get('ports',[])
        for port in box['ports']:
            matches=[p for p in ports if p.get('pin') and (p['side'],p['pin'])==(port['side'],port.get('pin'))]
            if len(matches)!=1:continue
            current=matches[0]
            if page_reader.logical_gate_terminal(current):
                if not page_reader.logical_gate_terminal(port):raise ValueError('Nonlogical contact role lacks current source evidence')
                continue
            claim=next((p for p in claims if p['id']==port['id']),None)
            if claim is not None and (claim.get('triangle') is not current['triangle'] or
                claim.get('contact_role')!='nonlogical_common' or claim.get('border_control')!='K'):
                raise ValueError('Reviewed supplement does not preserve the current nonlogical K contact')
            if port['triangle'] is not current['triangle']:
                raise ValueError('Nonlogical K contact lost its source edge polarity')
            port.update(contact_role='nonlogical_common',border_control='K')


def generic_definition(model, provenance, uncertainties, reviewed_overlay=None):
    component_width=component_forms.minimum_heading_width(model,uncertainties)
    if component_width:
        model=deepcopy(model)
        model.setdefault("layout_hints",{})["minimum_width"]=max(component_width,model.get("layout_hints",{}).get("minimum_width",0))
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
    component_forms.decorate_definition(spec,model,reviewed_overlay)
    copy_nonlogical_contacts(spec,model,reviewed_overlay)
    normalize_free_row_scene(spec)
    spec["nets"]=generate_card.wiring_graph(spec)
    if model.get('anonymous_output_preservation'):
        import anonymous_outputs
        anonymous_outputs.attach(spec,model)
    if reviewed_overlay:
        expected=sorted(sorted(net["terminals"] if isinstance(net,dict) else net) for net in reviewed_overlay["reviewed_nets"])
        assert spec["nets"]==expected,"Relayout changed approved terminal connections"
    generate_card.validate(spec)
    return spec

def _reviewed_routing_model_base(overlay,observed_model):
    """Recover exact reviewed networks while retaining stable semantic port IDs."""
    nodes={}
    by_terminal={}
    signal=defaultdict(lambda:defaultdict(set))
    for portion,fact in overlay["reviewed_portions"].items():
        node={"id":portion,"portion":portion,"card_type":observed_model["card_type"],
              "function":fact["function"],"unit":fact.get("unit",fact.get("circuit_identifier")),"_inputs":[],"_outputs":[]}
        observed=observed_model["portions"].get(portion,{})
        for key in ("_reviewed_component","_source_auxiliary_labels","_source_decoration_variants","_source_notation_variants","_source_notation_baseline_witness","above_block_caption"):
            if key in observed:node[key]=deepcopy(observed[key])
        for p in fact["ports"]:
            port={"id":p["id"],"pin":p.get("pin"),"triangle":bool(p["triangle"]),"side":p["side"],"row":0,"ref":p["id"]}
            # Stable geometry may be replayed, but current typed source evidence
            # must survive the same exact physical slot without alias guessing.
            matches=[current for current in observed.get("_inputs",[])+observed.get("_outputs",[])
                     if current.get("pin") and (current["side"],current["pin"])==(p["side"],p.get("pin"))]
            if len(matches)==1:
                for key in ("pin_symbols","border_symbol","source_triangle_observations","source_pin_symbol_observations","source_edge_decorations","contact_role","border_control","source_contact_role_observations"):
                    if key in matches[0]:port[key]=deepcopy(matches[0][key])
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


def _reviewed_definition_base(card, overlay, model, provenance, uncertainties):
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
    if "audit_policy" in overlay:
        spec["audit_policy"]=deepcopy(overlay["audit_policy"])
    component_forms.decorate_definition(spec,model,overlay)
    copy_nonlogical_contacts(spec,model,overlay)
    assert generate_card.wiring_graph(spec)==sorted(nets),"Portable reviewed geometry differs from reviewed terminal nets"
    generate_card.validate(spec)
    return spec,comparisons

def reviewed_routing_model(overlay,observed_model):
    result=_reviewed_routing_model_base(overlay,observed_model)
    if observed_model.get('anonymous_output_preservation'):
        result['anonymous_output_preservation']=deepcopy(observed_model['anonymous_output_preservation'])
    return result


def reviewed_definition(card, overlay, model, provenance, uncertainties):
    spec,comparisons=_reviewed_definition_base(card,overlay,model,provenance,uncertainties)
    if model.get('anonymous_output_preservation'):
        import anonymous_outputs
        anonymous_outputs.attach(spec,model)
    return spec,comparisons


def _old_notation_overlay(overlay):
    if not overlay:return overlay
    result=deepcopy(overlay)
    for variant in result.get('approved_variants',[]):
        variant.pop('circuit_witness',None)
        for change in variant.get('box_overrides',{}).values():change.pop('circuit_identifier',None)
    return result






def _build(card_type, overrides_path=None, relayout=False, component_authority_path=None):
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
            stale=[item for item in overlay_binding_checks if not item["current"]]
            raise ValueError("Reviewed supplement source binding is stale or missing; refusing generic replacement: "+json.dumps(stale,ensure_ascii=False))
    if ('layout' in overlay)!=('reviewed_portions' in overlay):
        raise ValueError('Reviewed geometry requires both layout and reviewed_portions')
    layout_overlay=overlay if 'layout' in overlay else None
    catalog,obs,models,power,bindings,changes,uncertainties=load_evidence(card_type,overlay,component_authority_path)
    import multicircuit_variants as multi
    choices=deepcopy(overlay.get('multicircuit_canonical_choices',{}))
    persisted={b['portion']:deepcopy(b['_multicircuit_preservation']['choice']['choice'])
               for b in overlay.get('layout',{}).get('boxes',[]) if '_multicircuit_preservation' in b}
    if choices and persisted:assert choices==persisted,'Contradictory canonical circuit policies'
    catalog['_explicit_multicircuit_choices']=choices or persisted
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
        if layout_overlay:
            definition,comparisons=reviewed_definition(card_type,layout_overlay,model,provenance,uncertainties)
            report["reviewed_fact_comparisons"]=comparisons
        elif not power and not catalog.get("_reviewed_component_forms"):
            uncertainties.append({"kind":"definition not routed for unsupported or ambiguous module kind"})
        elif not relayout:
            # A requested graph relayout must reach its spacing trials even
            # when the legacy default placement cannot route this card.
            definition=generic_definition(model,provenance,uncertainties)
        if relayout and (layout_overlay or power or catalog.get("_reviewed_component_forms")):
            definition=None
            import graph_card_layout
            routing_model=reviewed_routing_model(layout_overlay,model) if layout_overlay else deepcopy(model)
            report["relayout"]={"planner":binding(Path(graph_card_layout.__file__)),
                               "source":"reviewed terminal partitions" if layout_overlay else "unreviewed derived evidence"}
            definition=None
            attempts=[]
            successes=[]
            for row_gap in (0,1):
                routing_model["layout_options"]={"row_step":1,"row_gap":row_gap}
                hints=graph_card_layout.plan(routing_model)
                if layout_overlay:
                    labels=list(layout_overlay["layout"]["annotations"])
                    variant_labels=[x for v in layout_overlay.get("approved_variants",[]) for x in v.get("annotation_overrides",[])]
                    hints["minimum_width"]=max([hints.get("minimum_width",0)]+[x.get("x",0)+len(x["text"]) for x in labels+variant_labels])
                for extra,interval in enumerate(dict.fromkeys([hints.get("bank_interval",36),36,42,48,60])):
                    trial=deepcopy(hints)
                    trial["bank_interval"]=interval
                    trial["first_bank_x"]=hints.get("first_bank_x",18)+extra*4
                    trial["right_margin"]=hints.get("right_margin",18)+extra*4
                    routing_model["layout_hints"]=trial
                    try:
                        candidate=generic_definition(routing_model,provenance,uncertainties,layout_overlay)
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
            report["relayout"]["terminal_partition_identity_verified"]=bool(layout_overlay)
    except (AssertionError,ValueError,KeyError,RuntimeError,ImportError) as exc:
        uncertainties.append({"kind":"candidate definition requires review before routing","detail":str(exc),"exception":type(exc).__name__})
    report["definition_generated"]=definition is not None
    if definition is not None:
        if catalog.get('_reviewed_pinless_controls'):
            definition['reviewed_pinless_controls']=deepcopy(catalog['_reviewed_pinless_controls'])
        report["validation"]=generate_card.validate(definition)
    return definition,report

def build(card_type, overrides_path=None, root=None, relayout=False, component_authority_path=None):
    """Build without writes; root= supports portable clones and fixture tests."""
    global ROOT
    previous=ROOT
    try:
        if root is not None:ROOT=Path(root).resolve()
        return _build(card_type,overrides_path,relayout,component_authority_path)
    finally:
        ROOT=previous

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card_type")
    parser.add_argument("--output-dir",type=Path,help="Private destination, default tmp/ald-text/ald/card-data/CARD")
    parser.add_argument("--overrides",type=Path,help="Portable reviewed supplement JSON; default checks json/Card-ALD/build-overrides/CARD.json")
    parser.add_argument("--root",type=Path,help="Repository root for portable clones or private evidence fixtures")
    parser.add_argument("--component-authority",type=Path,help="Explicit source-bound component preview authority; no implicit S-family eligibility")
    parser.add_argument("--relayout",action="store_true",help="Privately plan/reroute the graph; reviewed cards retain exact approved terminals and port IDs")
    parser.add_argument("--render",action="store_true",help="Also validate/render TXT candidates privately")
    parser.add_argument("--check",action="store_true",help="Read/derive/validate without writing files")
    args=parser.parse_args()
    if not re.fullmatch(r"\d{4}",args.card_type):parser.error("Use a four-digit card type, for example0141")
    try:definition,report=build(args.card_type,args.overrides,args.root,args.relayout,args.component_authority)
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



_single_circuit_derive_semantics=derive_semantics
def derive_semantics(card, catalog, observations, models, power, uncertainties):
    import multicircuit_variants as multi
    choices=catalog.get('_explicit_multicircuit_choices',{})
    if not choices:return _single_circuit_derive_semantics(card,catalog,observations,models,power,uncertainties)
    plan=multi.make_plan(card,catalog,observations,choices,ROOT)
    if plan is None:return _single_circuit_derive_semantics(card,catalog,observations,models,power,uncertainties)
    canonical_observations=deepcopy(observations)
    for o in canonical_observations:
        if o['portion'] in plan['choices']:
            o['circuit_identifier']=plan['choices'][o['portion']]['choice']['canonical_circuit_identifier']
    model,manual_path=_single_circuit_derive_semantics(card,catalog,canonical_observations,models,power,uncertainties)
    model['multicircuit_preservation']=plan
    return model,manual_path


_single_circuit_generic_definition=generic_definition
def generic_definition(model,provenance,uncertainties,reviewed_overlay=None):
    import multicircuit_variants as multi
    if 'multicircuit_preservation' not in model:
        return _single_circuit_generic_definition(model,provenance,uncertainties,reviewed_overlay)
    result=_single_circuit_generic_definition(model,provenance,uncertainties,_old_notation_overlay(reviewed_overlay))
    result=multi.attach(result,model['multicircuit_preservation'])
    result['provenance']['multicircuit_runtime']=binding(Path(multi.__file__))
    if reviewed_overlay:result['variants']=deepcopy(reviewed_overlay.get('approved_variants',[]))
    generate_card.validate(result)
    return result


_single_circuit_reviewed_definition=reviewed_definition
def reviewed_definition(card,overlay,model,provenance,uncertainties):
    import multicircuit_variants as multi
    if 'multicircuit_preservation' not in model:
        return _single_circuit_reviewed_definition(card,overlay,model,provenance,uncertainties)
    result,comparisons=_single_circuit_reviewed_definition(card,_old_notation_overlay(overlay),model,provenance,uncertainties)
    result=multi.attach(result,model['multicircuit_preservation'])
    result['provenance']['multicircuit_runtime']=binding(Path(multi.__file__))
    result['variants']=deepcopy(overlay.get('approved_variants',[]))
    generate_card.validate(result)
    return result,comparisons


if __name__=="__main__":main()

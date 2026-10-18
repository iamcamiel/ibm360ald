"""Build a source-bound card catalog from the current reviewed ALD snapshot.

This deliberately does not rewrite the historical V15 card database or its
immutable acceptance receipts. It reads only repository files covered by the
current reviewed export and content-data manifests.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from copy import deepcopy
from collections import Counter, defaultdict
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "normalization"))
import read_page as page_reader

from current_card_identity import catalogue_identity


CARD = re.compile(r"[0-9]{4}\Z")
PIN = re.compile(r"([BDGJ])(0[2-9]|1[0-3])\Z")
UNIFORM_DATA = "json/Socket listings uniform/Socket listings.json"
UNIFORM_MANIFEST = "notes/Socket listings uniform/Build manifest.json"
ANNOTATION_FLAGS = ("symbol_only", "annotation_only", "annotation_block")


def relative_path(repo, relative):
    if (not isinstance(relative, str) or "\\" in relative or
            Path(relative).is_absolute() or Path(relative).as_posix() != relative or
            ".." in Path(relative).parts):
        raise ValueError(f"Unsafe repository input: {relative}")
    path = (repo / relative).resolve()
    if not path.is_relative_to(repo):
        raise ValueError(f"Input outside repository: {relative}")
    return path


def accepted_relative(entry):
    # Export history keeps its original checkout path; clones use the ALD suffix.
    parts = str(entry["destination"]).replace("\\", "/").split("/ALD/", 1)
    if len(parts) != 2:
        raise ValueError("Accepted destination has no ALD suffix")
    return "ALD/" + parts[1]


def annotation_flags(node):
    return [key for key in ANNOTATION_FLAGS if node.get(key) is True]


def load_uniform_listings(repo):
    """One source-bound physical record per stable uniform ID; no legacy loops."""
    manifest_path = repo / UNIFORM_MANIFEST
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8-sig"))
    if manifest.get("schema") != "uniform-socket-listing-build-v1":
        raise ValueError("Unsupported uniform socket build")
    files = {item["path"]: item["sha256"] for item in manifest["files"]}
    if len(files) != len(manifest["files"]) or UNIFORM_DATA not in files:
        raise ValueError("Uniform collection is not uniquely inventoried")
    data = read_checked(repo / UNIFORM_DATA, files[UNIFORM_DATA])
    if data.get("schema") != "ibm360-socket-listings-v1":
        raise ValueError("Unsupported uniform socket collection")
    inputs = {}
    for link in manifest["inputs"]:
        path = relative_path(repo, link["path"])
        if link["path"] in inputs or sha(path.read_bytes()) != link["sha256"]:
            raise ValueError("Duplicate or changed uniform input: " + link["path"])
        inputs[link["path"]] = link["sha256"]
    provenance = "notes/Reviewed export provenance.json"
    if provenance not in inputs:
        raise ValueError("Uniform source lacks accepted export provenance")
    by_scan, lines = {}, {}
    for entry in read_checked(repo / provenance, inputs[provenance])["exported"]:
        rel = accepted_relative(entry)
        if rel not in inputs:
            continue
        scan = str(entry["source_scan_id"])
        if scan in by_scan or entry["text_sha256"] != inputs[rel]:
            raise ValueError("Duplicate or stale uniform accepted source")
        by_scan[scan] = rel
        lines[scan] = relative_path(repo, rel).read_text("utf-8-sig").splitlines()
    def span_check(span):
        scan = str(span.get("scan_id")); rows = lines.get(scan)
        row, col, literal = span.get("row"), span.get("column"), span.get("literal")
        if (rows is None or type(row) is not int or type(col) is not int or
                not isinstance(literal, str) or not 0 <= row < len(rows) or col < 0 or
                rows[row][col:col + len(literal)] != literal):
            raise ValueError("Uniform card source span differs from accepted TXT")
    rows = data["records"]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate uniform physical record ID")
    listings, unresolved, selected = defaultdict(list), [], 0
    for index, record in enumerate(rows):
        # This is the uniform builder's card-instance predicate. An unresolved
        # printed width remains a physical card, without inventing single/double.
        if record.get("card_type") is None or "CARD" not in str(record.get("kind_literal")):
            continue
        selected += 1
        for span in [record["header_source"], *record["source_spans"]]:
            span_check(span)
        for reference in record["references"]:
            for span in reference["source_spans"]:
                span_check(span)
        header = record["header_source"]
        source = by_scan[str(header["scan_id"])]
        references = deepcopy(record["references"])
        for reference in references:
            reference["printed_portions"] = deepcopy(reference["portions"])
        listing = {"record_id": record["id"], "page": header["page"],
            "record_pointer": f"/records/{index}", "source_text": source,
            "source_text_sha256": inputs[source], "source_model": UNIFORM_DATA,
            "source_model_sha256": files[UNIFORM_DATA], "board": record["board"],
            "sockets": deepcopy(record["sockets"]),
            "physical_sockets": deepcopy(record["physical_sockets"]),
            "kind": {"single_card": "SINGLE CARD", "double_card": "DOUBLE CARD"}.get(record["kind"]),
            "kind_normalized": record["kind"], "kind_literal": record["kind_literal"],
            "part_number": record["part_number"], "references": references,
            "unused_portions": deepcopy(record["unused_portions"]),
            "header_source": deepcopy(header), "source_spans": deepcopy(record["source_spans"]),
            "source_reviewed": True,
            "source_review_basis": "Current accepted TXT and uniform source spans; no new visual acceptance"}
        card = record["card_type"]
        if not isinstance(card, str) or not CARD.fullmatch(card):
            unresolved.append({"card_type_literal": card, "listing_record": listing})
        else:
            listings[card].append(listing)
    if selected != data["counts"]["card_instances"] or selected != manifest["counts"]["card_instances"]:
        raise ValueError("Uniform physical card coverage differs")
    for rel, expected in inputs.items():
        if sha((repo / rel).read_bytes()) != expected:
            raise ValueError("Uniform source changed during catalogue read: " + rel)
    if sha(manifest_path.read_bytes()) != sha(manifest_raw):
        raise ValueError("Uniform manifest changed during catalogue read")
    return listings, {"manifest": {"path": UNIFORM_MANIFEST, "sha256": sha(manifest_raw)},
        "dataset": {"path": UNIFORM_DATA, "sha256": files[UNIFORM_DATA]},
        "inputs": [{"path": rel, "sha256": expected} for rel, expected in inputs.items()],
        "logical_records": len(rows), "physical_card_records": selected,
        "typed_card_records": sum(map(len, listings.values())),
        "unclassified_card_records": unresolved}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_checked(path: Path, expected: str, page_model=False):
    raw = path.read_bytes()
    actual = sha(raw)
    if actual != expected:
        raise ValueError(f"Changed source: {path}: {actual} != {expected}")
    return page_reader.loads(raw) if page_model else json.loads(raw.decode("utf-8-sig"))


def dump(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def primary_function(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None, None
    label = " ".join(raw.split())
    if "�" in label:
        return None, label
    if label.startswith("R T") or label.startswith("R DR"):
        return "R", label
    return label.split(" ", 1)[0], label


def pin_record(pin):
    label = pin.get("pin")
    printed = pin.get("printed_pin", pin.get("printed_label", label))
    exact = PIN.fullmatch(label) if isinstance(label, str) else None
    decorated = (PIN.fullmatch(label[:-1])
                 if isinstance(label, str) and label.endswith("✲") else None)
    candidate = label if exact else label[:-1] if decorated else None
    parse_status = ("exact" if exact else "asterisk suffix" if decorated
                    else "unlabeled" if label in (None, "") else "unparsed")
    # Preserve the literal pin field. Some accepted source schemas store their
    # physical contact explicitly and their printed spelling separately.
    physical = pin.get("physical_pin")
    if isinstance(physical,str) and PIN.fullmatch(physical):
        printed_contact=(printed[:-1] if isinstance(printed,str) and printed.endswith("✲") else printed)
        if ((candidate is not None and candidate != physical) or
                (isinstance(printed_contact,str) and PIN.fullmatch(printed_contact) and printed_contact != physical)):
            candidate=None;parse_status="conflicting physical contact fields"
        elif candidate is None and "pin" not in pin:
            candidate=physical;parse_status="explicit physical_pin"
    return {
        "side": pin.get("side"),
        "pin": label,
        "printed_pin": printed,
        "physical_pin_candidate": candidate,
        "physical_pin_parse_status": parse_status,
        "valid_physical_pin_syntax": True if candidate else None,
        "triangle": pin.get("triangle"),
        "border_marker": pin.get("border_marker"),
        "row": pin.get("row"),
        "net": pin.get("net"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if output == repo or repo in output.parents and output == repo / "ALD":
        raise ValueError("Output would overwrite canonical ALD pages")

    provenance_path = repo / "notes/Reviewed export provenance.json"
    content_path = repo / "notes/Content data manifest.json"
    provenance_raw, content_raw = provenance_path.read_bytes(), content_path.read_bytes()
    provenance = json.loads(provenance_raw.decode("utf-8-sig"))
    content = json.loads(content_raw.decode("utf-8-sig"))
    accepted = {}
    for entry in provenance["exported"]:
        relative = accepted_relative(entry)
        relative_path(repo, relative)
        if relative in accepted:
            raise ValueError(f"Duplicate accepted page: {relative}")
        accepted[relative] = entry

    cards = defaultdict(lambda: {"occurrences": [], "listings": []})
    source_pages = {}
    unclassified = []
    excluded_annotations = []
    count = Counter()
    for entry in content["files"]:
        if entry["role"] != "Published page content model":
            continue
        model_rel = entry["path"]
        if not model_rel.startswith("json/") or not model_rel.endswith(".json"):
            raise ValueError(f"Unexpected model path: {model_rel}")
        text_rel = "ALD/" + model_rel[5:-5] + ".txt"
        if text_rel not in accepted:
            raise ValueError(f"Model without accepted page: {model_rel}")
        text_entry = accepted[text_rel]
        text_path = repo / text_rel
        if sha(text_path.read_bytes()) != text_entry["text_sha256"]:
            raise ValueError(f"Text changed after acceptance: {text_rel}")
        model = read_checked(relative_path(repo, model_rel), entry["sha256"], page_model=True)
        page_key = text_rel
        source_pages[page_key] = {
            "page": model.get("page", text_entry["page"]),
            "model": model_rel,
            "model_sha256": entry["sha256"],
            "text_sha256": text_entry["text_sha256"],
            "source_scan_id": text_entry.get("source_scan_id"),
            "source_relative": text_entry.get("source_relative"),
        }
        count["models"] += 1
        for index, node in enumerate(model.get("nodes", [])):
            count["diagram_nodes"] += 1
            flags = annotation_flags(node)
            if flags:
                excluded_annotations.append({"page": model.get("page", text_entry["page"]),
                    "node": node.get("id"), "source_text": text_rel,
                    "source_model": model_rel, "source_model_sha256": entry["sha256"],
                    "text_sha256": text_entry["text_sha256"], "node_pointer": f"/nodes/{index}",
                    "card_type_literal": node.get("card_type"), "circuit_identifier": node.get("unit"),
                    "function_literal": node.get("function"), "explicit_flags": flags})
                count["annotation_nodes_excluded"] += 1
                continue
            node, identity_audit = catalogue_identity(node)
            if identity_audit["status"] == "conflict":
                raise ValueError(f"Conflicting source identity: {text_rel} /nodes/{index}")
            card = node.get("card_type")
            if not isinstance(card, str) or not CARD.fullmatch(card):
                count["nodes_without_card_type"] += 1
                if isinstance(card, str) and card:
                    unclassified.append({"page": model.get("page", text_entry["page"]),
                        "node": node.get("id"), "source_text": text_rel,
                        "node_pointer": f"/nodes/{index}", "card_type_literal": card,
                        "printed_card_portion": node.get("printed_card_portion")})
                continue
            portion = node.get("portion")
            if portion is not None:
                portion = str(portion)
            primary, function_label = primary_function(node.get("function"))
            pins = [pin_record(p) for p in node.get("pins", [])]
            inputs = [p for p in pins if p["side"] == "input"]
            outputs = [p for p in pins if p["side"] == "output"]
            shape = {
                "visible_inputs": len(inputs),
                "visible_outputs": len(outputs),
                "input_triangles": sum(p["triangle"] is True for p in inputs),
                "output_triangles": sum(p["triangle"] is True for p in outputs),
                "input_pin_labels": sum(bool(p["pin"]) for p in inputs),
                "output_pin_labels": sum(bool(p["pin"]) for p in outputs),
            }
            cards[card]["occurrences"].append({
                "page": model.get("page", text_entry["page"]),
                "node": node.get("id"),
                "node_pointer": f"/nodes/{index}",
                "source_text": text_rel,
                "portion": portion,
                "printed_card_portion": node.get("printed_card_portion"),
                "function_literal": node.get("function"),
                "function_label": function_label,
                "primary_function": primary,
                "circuit_identifier": node.get("unit"),
                "location": node.get("location"),
                "grid": node.get("grid"),
                "pins": pins,
                "observed_shape": shape,
                "source_reviewed": node.get("source_reviewed", model.get("source_reviewed") is True),
                **({"identity_adaptation": identity_audit} if identity_audit["status"] == "adapted" else {}),
                **({"source_review_basis": "Hash-bound accepted page model and TXT; explicit page source_reviewed true, node review absent"}
                   if "source_reviewed" not in node and model.get("source_reviewed") is True else {}),
            })
            count["card_occurrences"] += 1

    uniform_listings, listing_authority = load_uniform_listings(repo)
    for card, listings in uniform_listings.items():
        cards[card]["listings"].extend(listings)
    count["listing_records"] = listing_authority["typed_card_records"]
    count["physical_card_records"] = listing_authority["physical_card_records"]
    count["unclassified_listing_records"] = len(listing_authority["unclassified_card_records"])

    json_dir = output / "json/Card types current"
    csv_dir = output / "csv/Card types current"
    notes_dir = output / "notes/Card types current"
    for folder in (json_dir, csv_dir, notes_dir):
        folder.mkdir(parents=True, exist_ok=True)
    summary, profiles_csv, occurrences_csv = [], [], []
    pin_width_exceptions = []
    for card, facts in sorted(cards.items()):
        occurrences = sorted(facts["occurrences"], key=lambda x: (x["page"] or "", x["node"] or "", x["source_text"]))
        listings = sorted(facts["listings"], key=lambda x: (x.get("board") or "", str(x.get("sockets")), x.get("source_text", x.get("source_model", ""))))
        profiles = defaultdict(list)
        for obs in occurrences:
            key = (obs["portion"], obs["primary_function"], obs["circuit_identifier"],
                   json.dumps(obs["observed_shape"], sort_keys=True))
            profiles[key].append(obs)
            occurrences_csv.append({"card_type": card, "portion": obs["portion"], "page": obs["page"],
                "node": obs["node"], "function_literal": obs["function_literal"],
                "primary_function": obs["primary_function"], "circuit_identifier": obs["circuit_identifier"],
                "visible_inputs": obs["observed_shape"]["visible_inputs"],
                "visible_outputs": obs["observed_shape"]["visible_outputs"],
                "input_triangles": obs["observed_shape"]["input_triangles"],
                "output_triangles": obs["observed_shape"]["output_triangles"],
                "source_text": obs["source_text"], "node_pointer": obs["node_pointer"]})
        profile_docs = []
        for (portion, function, circuit, shape_json), members in sorted(profiles.items(), key=lambda item: tuple(str(x) for x in item[0])):
            shape = json.loads(shape_json)
            doc = {"portion": portion, "primary_function": function,
                "circuit_identifier": circuit, "observed_shape": shape,
                "occurrences": len(members), "examples": [f"{x['page']} {x['node']}" for x in members[:8]]}
            profile_docs.append(doc)
            profiles_csv.append({"card_type": card, **{k: doc[k] for k in ("portion", "primary_function", "circuit_identifier", "occurrences")},
                **shape, "examples": "; ".join(doc["examples"])})
        parts = sorted({str(x["part_number"]) for x in listings if x.get("part_number")})
        widths = sorted({str(x["kind"]) for x in listings if x.get("kind")})
        physical_widths = sorted(set(widths) & {"SINGLE CARD", "DOUBLE CARD"})
        allowed_letters = ({"B", "D"} if physical_widths == ["SINGLE CARD"]
                           else {"B", "D", "G", "J"} if physical_widths == ["DOUBLE CARD"]
                           else None)
        for occurrence in occurrences:
            for pin in occurrence["pins"]:
                candidate = pin["physical_pin_candidate"]
                if allowed_letters is None or candidate is None:
                    pin["valid_for_observed_card_width"] = None
                else:
                    match = PIN.fullmatch(candidate)
                    pin["valid_for_observed_card_width"] = bool(
                        match and match.group(1) in allowed_letters)
        peers = defaultdict(Counter)
        for occurrence in occurrences:
            for pin in occurrence["pins"]:
                if pin["valid_for_observed_card_width"] is True:
                    peers[(occurrence["portion"], pin["side"])][pin["physical_pin_candidate"]] += 1
        for occurrence in occurrences:
            for pin in occurrence["pins"]:
                if pin["valid_for_observed_card_width"] is False:
                    candidates = peers[(occurrence["portion"], pin["side"])].most_common(5)
                    pin_width_exceptions.append({
                        "card_type": card, "portion": occurrence["portion"],
                        "page": occurrence["page"], "node": occurrence["node"],
                        "source_text": occurrence["source_text"],
                        "node_pointer": occurrence["node_pointer"],
                        "printed_pin_literal": pin["printed_pin"],
                        "modeled_pin_literal": pin["pin"],
                        "physical_pin_candidate": pin["physical_pin_candidate"],
                        "physical_card_widths_observed": physical_widths,
                        "same_portion_side_peer_pins": [
                            {"pin": label, "occurrences": frequency}
                            for label, frequency in candidates],
                        "status": "Derived candidate only; original scan and acceptance required before source correction"})
        docs = {"schema": "current-card-catalog-v1", "card_type": card,
            "full_part_numbers_observed": parts, "listing_kinds_observed": widths,
            "physical_card_widths_observed": physical_widths,
            "observed_portions": sorted({x["portion"] for x in occurrences if x["portion"]}),
            "listing_portions": sorted({str(p) for x in listings for ref in x["references"] for p in ref.get("printed_portions", [])}),
            "listing_records": listings, "portion_profiles": profile_docs, "diagram_occurrences": occurrences,
            "scope": "Observed drawn ports only; unused inputs and complete physical pinout are not inferred"}
        dump(json_dir / f"{card}.json", docs)
        summary.append({"card_type": card, "diagram_occurrences": len(occurrences),
            "listing_records": len(listings), "observed_portions": len(docs["observed_portions"]),
            "profiles": len(profile_docs), "full_part_numbers": "; ".join(parts), "listing_kinds": "; ".join(widths)})

    def write_csv(path, rows, columns):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    write_csv(csv_dir / "Card types.csv", summary,
              ["card_type", "diagram_occurrences", "listing_records", "observed_portions", "profiles", "full_part_numbers", "listing_kinds"])
    write_csv(csv_dir / "Portion profiles.csv", profiles_csv,
              ["card_type", "portion", "primary_function", "circuit_identifier", "occurrences", "visible_inputs", "visible_outputs", "input_triangles", "output_triangles", "input_pin_labels", "output_pin_labels", "examples"])
    write_csv(csv_dir / "Diagram occurrences.csv", occurrences_csv,
              ["card_type", "portion", "page", "node", "function_literal", "primary_function", "circuit_identifier", "visible_inputs", "visible_outputs", "input_triangles", "output_triangles", "source_text", "node_pointer"])
    dump(notes_dir / "Unclassified card identifiers.json", {
        "schema": "current-card-catalog-unclassified-v1", "count": len(unclassified),
        "scope": "Non-numeric diagram card identifiers; includes structural labels and OCR damage. No card type inferred.",
        "observations": sorted(unclassified, key=lambda x: (x["page"] or "", x["node"] or ""))})
    dump(notes_dir / "Physical pin width exceptions.json", {
        "schema": "current-card-catalog-pin-width-exceptions-v1",
        "count": len(pin_width_exceptions),
        "scope": "Only unambiguously parsed physical pins whose letter conflicts with a known single-card width. Peer pins are suggestions, not corrections.",
        "exceptions": sorted(pin_width_exceptions, key=lambda x: (x["card_type"], x["page"], x["node"] or ""))})
    dump(notes_dir / "Excluded annotation nodes.json", {
        "schema": "current-card-catalog-excluded-annotations-v1",
        "count": len(excluded_annotations),
        "policy": "Only explicit true symbol_only, annotation_only or annotation_block flags exclude a node; card type 0000 alone does not.",
        "observations": sorted(excluded_annotations, key=lambda x: (x["source_text"], x["node_pointer"]))})
    (notes_dir / "README.txt").write_text(
        "CURRENT CARD-TYPE CATALOG\n"
        "Rebuild with tools/references/build_current_card_catalog.py from the reviewed export and content-data manifests.\n"
        "Verify with tools/references/verify_current_card_catalog.py.\n\n"
        "All physical card listings come once from the current accepted uniform socket dataset,\n"
        "with stable record IDs and exact source spans. Legacy table shapes are not read again.\n"
        "Continuations retain their source evidence but do not add physical card instances.\n"
        "Unprinted or unreadable card width stays unknown. Explicit annotation nodes are\n"
        "reported separately; a numeric 0000 card is retained unless explicitly annotated.\n\n"
        "json/Card types current/<number>.json contains each observed portion, its exact function label,\n"
        "primary function, circuit identifier, visible pins, polarity triangles, A1 listing facts,\n"
        "and source text/model pointers. csv/Card types current contains searchable summaries.\n"
        "The shape counts describe only visible ports; some inputs are intentionally unused or omitted.\n"
        "A physical pin label is syntactically valid only when it uses B/D (single card) or B/D/G/J\n"
        "(double card) and a number from 02 through 13. Apparent exceptions remain literal in\n"
        "the observations for source review. Labels that cannot be parsed as physical pins are\n"
        "marked unparsed rather than automatically called invalid. Non-numeric card labels,\n"
        "including structural blocks\n"
        "and damaged readings, are listed in Unclassified card identifiers.json.\n\n"
        "This is the current derived catalogue. Superseded research snapshots and\n"
        "intermediate review histories are not retained in the working repository.\n",
        encoding="utf-8")
    files = []
    for branch in (json_dir, csv_dir, notes_dir):
        for path in sorted(branch.iterdir()):
            files.append({"path": path.relative_to(output).as_posix(), "sha256": sha(path.read_bytes())})
    source_inputs = {"notes/Reviewed export provenance.json": sha(provenance_raw),
        "notes/Content data manifest.json": sha(content_raw),
        UNIFORM_MANIFEST: listing_authority["manifest"]["sha256"],
        UNIFORM_DATA: listing_authority["dataset"]["sha256"]}
    for item in listing_authority["inputs"]:
        source_inputs[item["path"]] = item["sha256"]
    for text, binding in source_pages.items():
        source_inputs[text] = binding["text_sha256"]
        source_inputs[binding["model"]] = binding["model_sha256"]
    for name in ("build_current_card_catalog.py", "verify_current_card_catalog.py", "verify_uniform_socket_listings.py", "current_card_identity.py"):
        relative = "tools/references/" + name
        source_inputs[relative] = sha((repo / relative).read_bytes())
    for path in page_reader.runtime_paths(repo):
        source_inputs[path.relative_to(repo).as_posix()] = sha(path.read_bytes())
    for relative, expected in source_inputs.items():
        if sha(relative_path(repo, relative).read_bytes()) != expected:
            raise ValueError("Catalogue source changed during build: " + relative)
    report = {"schema": "current-card-catalog-build-v1", "source_binding": {
        "reviewed_export_provenance_sha256": sha(provenance_raw),
        "content_data_manifest_sha256": sha(content_raw),
        "uniform_manifest_sha256": listing_authority["manifest"]["sha256"],
        "uniform_dataset_sha256": listing_authority["dataset"]["sha256"]},
        "uniform_listing_authority": listing_authority,
        "source_inputs": [{"path": relative, "sha256": expected} for relative, expected in sorted(source_inputs.items())],
        "counts": dict(count), "card_types": len(cards), "portion_profiles": len(profiles_csv),
        "source_pages": source_pages, "files": files,
        "limitations": ["Only accepted pages with a current published content model contribute diagram blocks.",
            "Visible port counts are not full card pinouts; unused inputs can be omitted.",
            "A1 part numbers and card widths are observed facts, not inferred from card-type digits.",
            "Current source references and review status are retained; Git holds version history."]}
    dump(notes_dir / "Build manifest.json", report)
    print(json.dumps({"card_types": len(cards), "counts": dict(count), "profiles": len(profiles_csv),
        "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

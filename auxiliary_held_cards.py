"""Candidate authoritative card-status adapter; never edits production paths.

Historical bytes are opaque evidence, never substituted for current source facts.
All output targets are new files. Upstream source-publication receipt semantics
remain the finite source transaction driver's responsibility, not this adapter's.
"""
import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

from auxiliary_held_contracts import validate

METADATA_BASES = ("json/Card-ALD/build-overrides", "json/Card-ALD/definitions", "notes/Card-ALD/Audits",
                  "notes/Card-ALD/Notation witnesses", "json/Card-ALD", "notes/Card-ALD/Generation")
AUTHORITATIVE_PATH = "notes/Card-ALD/Universal card diagrams publication.json"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes().decode("utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + value)))


def inside(root, path):
    root = Path(root).absolute()
    require(root.resolve() == root, "Root is a filesystem alias")
    path = Path(path)
    path = path.absolute() if path.is_absolute() else root / path
    require(path.is_relative_to(root), "Path escapes repository root")
    require(path.resolve() == path, "Path follows symlink/junction or noncanonical components")
    cursor = path
    while cursor != root:
        require(not cursor.is_symlink() and not getattr(cursor, "is_junction", lambda: False)(), "Symlink/junction rejected")
        cursor = cursor.parent
    return path


def binding(path, root=None):
    require(root is not None, "Portable binding requires explicit repository root")
    path = inside(root, path)
    return {"path": path.relative_to(Path(root).absolute()).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(item, root):
    validate(item, "binding")
    require(PurePosixPath(item["path"]).as_posix() == item["path"], "Noncanonical relative binding")
    path = inside(root, item["path"])
    require(path.is_file() and binding(path, root)["sha256"] == item["sha256"], "Stale/missing binding: " + str(path))
    return path


def write_new(path, value, root):
    path = inside(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(encode(value))
    return binding(path, root)


def runtime(root, area, name):
    directory = str(inside(root, Path(root) / "tools" / area))
    if directory not in sys.path:
        sys.path.insert(0, directory)
    module = importlib.import_module(name)
    require(Path(module.__file__).resolve() == (Path(directory) / (name + ".py")).resolve(),
            "Conflicting imported production runtime: " + name)
    return module


def checkpoint(item, root):
    path = checked(item, root)
    require(path == (Path(root) / "notes/Source status.json").resolve(), "Checkpoint must bind live notes/Source status.json")
    runtime(root, "reviews", "current_checkpoint").load_checkpoint(root)
    return read(path)


def extract_findings(builder, audit):
    result = [{"kind": "builder_uncertainty", "detail": encode(x).decode().strip()}
              for x in builder.get("uncertainties", [])]
    if builder.get("completed") is False and builder.get("error"):
        result.append({"kind": "builder_failure", "detail": str(builder["error"])})
    result += [{"kind": "source_audit", "detail": encode(x).decode().strip()} for x in audit.get("review", [])]
    require(result, "Held audit requires actual nonempty builder/audit findings")
    return result


def verify_audit(doc, root):
    validate(doc, "audit")
    builder = read(checked(doc["builder_evidence"], root))
    audit = read(checked(doc["source_audit"], root))
    require(builder.get("card_type") == audit.get("card_type") == doc["card_type"], "Audit family mismatch")
    require(audit.get("schema") == "card-use-audit-v1" and isinstance(audit.get("source_bindings"), list), "Actual source audit required")
    for item in audit["source_bindings"] + builder.get("provenance", {}).get("source_bindings", []):
        checked({"path": item["path"], "sha256": item["sha256"]}, root)
    require(doc["findings"] == extract_findings(builder, audit), "Findings differ from exact actual audit/builder evidence")
    return doc


def verify_measurements(doc, current, root):
    """Shared measured bytes only; this helper never asserts publication."""
    accepted_sources = {(str((Path(root) / link["path"]).resolve()), link["sha256"])
                        for record in current["records"] for link in record["repository"].values()}
    seen = set()
    for item in doc["source_bindings"]:
        path = checked(item, root)
        key = (str(path), item["sha256"])
        require(key in accepted_sources and key not in seen, "Source not uniquely bound by live checkpoint")
        seen.add(key)
    for item in doc["evidence_bindings"]:
        checked(item, root)
    audit = verify_audit(read(checked(doc["audit_findings"], root)), root)
    require(audit["card_type"] == doc["card_type"], "Event/audit family mismatch")
    source_audit = read(checked(audit["source_audit"], root))
    audit_sources = {(str(checked({"path": x["path"], "sha256": x["sha256"]}, root)), x["sha256"])
                     for x in source_audit["source_bindings"]}
    require(seen <= audit_sources, "Current event source absent from exact audit epoch")
    builder = read(checked(audit["builder_evidence"], root))
    if "provenance" in builder:
        builder_sources = {(str(checked({"path": x["path"], "sha256": x["sha256"]}, root)), x["sha256"])
                           for x in builder["provenance"].get("source_bindings", [])}
        require(seen <= builder_sources, "Current event source absent from exact builder epoch")
    return doc


def verify_event(doc, root):
    validate(doc, "event")
    # Exact upstream envelope semantics belong to AP's finite actual transaction.
    # A measured proposal cannot masquerade as that transaction's receipt.
    receipt = read(checked(doc["source_publication_receipt"], root))
    require(isinstance(receipt, dict) and receipt.get("schema") != "held-derived-card-source-proposal-v1" and
            receipt.get("schema") != "root-private-full-repository-source-counterfactual-v1" and
            receipt.get("proposed") is not True and receipt.get("published") is not False,
            "Measured proposal is not an actual source publication receipt")
    return verify_measurements(doc, checkpoint(doc["current_checkpoint"], root), root)


def verify_proposal(doc, root, expected_source_plan):
    """Validate counterfactual measurements without an installation receipt.

    The coordinator explicitly supplies the exact independently reviewed plan
    binding; no plan or proposed checkpoint is promoted to actual publication.
    """
    validate(doc, "proposal")
    checked(expected_source_plan, root)
    require(doc["source_plan"] == expected_source_plan, "Proposal differs from explicitly admitted source plan")
    plan = read(checked(doc["source_plan"], root))
    require(plan.get("schema") == "ald-reviewed-wiring-source-import-plan-v1" and plan.get("passed") is True,
            "Pre-reviewed source import plan required")
    proposed_checkpoint = checked(doc["proposed_checkpoint"], root)
    runtime(root, "reviews", "current_checkpoint").load_checkpoint(root, path=proposed_checkpoint)
    verify_measurements(doc, read(proposed_checkpoint), root)
    after_images = {row["path"]: row["after_sha256"] for row in plan.get("changes", [])}
    for page in plan.get("pages", []):
        for kind, suffix in [("json", "model"), ("txt", "text")]:
            if kind in page.get("targets", {}) and page.get("after_" + suffix):
                after_images[page["targets"][kind]] = page["after_" + suffix]["sha256"]
    affected = False
    for item in doc["source_bindings"]:
        if item["path"] in after_images:
            require(item["sha256"] == after_images[item["path"]], "Proposed source differs from reviewed plan after-image")
            affected = True
    require(affected, "Proposal has no measured source from the reviewed plan")
    return doc


def verify_historical(history, card, root, active_generation=None):
    validate(history, "historical")
    gp = checked(history["generation"], root)
    dp = checked(history["drawing"], root)
    ap = checked(history["audit"], root)
    checked(history["accepted_review"], root)
    if history["physical_review"] is not None:
        checked(history["physical_review"], root)  # Opaque historical evidence; never physical approval.
    require(not gp.is_relative_to((Path(root) / "notes/Card-ALD/Generation").resolve()), "Historical generation is in active generation namespace")
    require(not dp.is_relative_to((Path(root) / "Card-ALD").resolve()), "Historical drawing is in active drawing namespace")
    require(active_generation is None or gp != Path(active_generation).resolve(), "Historical generation self-binding")
    generation = read(gp)
    require(generation.get("card_type") == card, "Historical family mismatch")
    require(generation.get("schema") == "card-ald-current-publication-v1" and
            generation.get("independent_review", {}).get("passed") is True and
            generation.get("default_builder_reproduced") is True,
            "Historical generation lacks exact accepted current-generation markers")
    require(generation.get("diagram_sha256") == history["drawing"]["sha256"], "Historical drawing differs from generation")
    require(generation.get("source_audit", {}).get("sha256") == history["audit"]["sha256"], "Historical audit differs from generation")
    require(generation.get("independent_review", {}).get("sha256") == history["accepted_review"]["sha256"], "Historical accepted review differs from generation")
    require(not ap.is_relative_to((Path(root) / "notes/Card-ALD/Audits").resolve()), "Historical audit is in active audit namespace")
    verify_files(history["files"], generation, card, root)
    require(generation_files(generation, card).get(generation["canonical"]) == history["drawing"]["sha256"], "Canonical absent from full historical files[]")
    return generation


def verify_files(files, generation, card, root):
    expected = generation_files(generation, card)
    actual = {}
    for row in files:
        validate(row, "historical_file")
        path = checked(row["artifact"], root)
        require(not path.is_relative_to((Path(root) / "Card-ALD").resolve()), "Historical variant is in active drawing namespace")
        require(row["published_path"] not in actual, "Duplicate historical variant")
        actual[row["published_path"]] = row["artifact"]["sha256"]
    require(actual == expected, "Historical variants differ from complete accepted files[]")
    return actual


def generation_files(generation, card):
    rows = generation.get("files")
    require(isinstance(rows, list) and rows, "Accepted generation requires every published files[] record")
    result = {}
    for row in rows:
        validate(row, "binding")
        require(re.fullmatch(r"Card-ALD/" + card + r"(?:-[0-9]+)?\.txt", row["path"]), "Invalid historical variant namespace")
        require(row["path"] not in result, "Duplicate accepted variant")
        result[row["path"]] = row["sha256"]
    require(generation.get("canonical") in result, "Accepted canonical missing from files[]")
    return result


def verify_legacy_history(history, card, root):
    """Direct legacy proof integrity only; never an accepted/current card claim."""
    validate(history, "legacy_historical")
    gp = checked(history["generation"], root)
    require(not gp.is_relative_to(inside(root, "notes/Card-ALD/Generation")), "Legacy generation must be immutable history")
    generation = read(gp)
    require(generation.get("schema") == "card-ald-generation-v1" and generation.get("card_type") == card,
            "Legacy history requires exact legacy generation schema/family")
    require("independent_review" not in generation and "source_audit" not in generation,
            "Legacy history cannot disguise an accepted bundle")
    canonical = checked(history["canonical"], root)
    require(not canonical.is_relative_to(inside(root, "Card-ALD")), "Legacy canonical must be a historical copy")
    require(history["canonical"]["sha256"] == generation["diagram_sha256"], "Legacy canonical identity differs")
    definition = history["definition_provenance"]
    require(definition["declared_binding"] == generation.get("definition"), "Legacy declared definition provenance differs")
    if definition["artifact"] is not None:
        checked(definition["artifact"], root)
        require(definition["artifact"]["sha256"] == definition["declared_binding"]["sha256"], "Legacy exact definition provenance differs")
    if generation.get("source_evidence") is None:
        require(history["source_evidence"] is None and history["source_evidence_status"] == "not-recorded", "Invented legacy source evidence")
    else:
        evidence = read(checked(history["source_evidence"], root))
        require(evidence == generation["source_evidence"] and history["source_evidence_status"] == "embedded-generation-value",
                "Legacy embedded source evidence differs or was omitted")
    if history["physical_review"] is not None:
        checked(history["physical_review"], root)  # Explicit opaque historical evidence, never approval.
    verify_files(history["files"], generation, card, root)
    return generation


def create_legacy_bundle(card, generation, definition, output, root, physical_review=None):
    """Copy old generation/definition/all variants, with honest missing roles."""
    target = inside(root, output)
    require(not target.exists(), "Legacy bundle output must be NEW")
    require(not target.is_relative_to(inside(root, "Card-ALD")) and
            not target.is_relative_to(inside(root, "notes/Card-ALD/Generation")), "Legacy snapshots must be outside active drawing/generation namespaces")
    gp = inside(root, generation)
    dp = inside(root, definition) if definition is not None else None
    old = read(gp)
    require(old.get("schema") == "card-ald-generation-v1" and old.get("card_type") == card and
            "independent_review" not in old and "source_audit" not in old, "Not a separate legacy generation")
    validate(old.get("definition"), "binding")
    if dp is not None:
        require(binding(dp, root)["sha256"] == old["definition"]["sha256"], "Exact old definition provenance required")
    source_files = {rel: checked({"path": rel, "sha256": sha}, root) for rel, sha in generation_files(old, card).items()}
    physical = inside(root, physical_review) if physical_review is not None else None
    guards = {p: p.read_bytes() for p in [gp, *([dp] if dp is not None else []), *source_files.values()] + ([physical] if physical is not None else [])}
    def copy(path, name):
        dest = inside(root, target / name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as stream:
            stream.write(guards[path])
        return binding(dest, root)
    bundle = {"generation": copy(gp, "Generation.json"), "definition_provenance": {"declared_binding": old["definition"],
          "artifact": copy(dp, "Definition provenance.json") if dp is not None else None,
          "status": "recorded-historical-evidence" if dp is not None else "recorded-binding-artifact-unavailable"},
        "files": [{"published_path": rel, "artifact": copy(path, "Drawings/" + Path(rel).name)} for rel, path in source_files.items()],
        "audit": None, "audit_status": "not-recorded", "accepted_review": None, "accepted_review_status": "not-recorded",
        "physical_review": copy(physical, "Physical review.json") if physical is not None else None,
        "physical_review_status": "recorded-historical-evidence" if physical is not None else "not-recorded",
        "current_seal": False}
    bundle["canonical"] = next(row["artifact"] for row in bundle["files"] if row["published_path"] == old["canonical"])
    bundle["source_evidence"] = write_new(target / "Embedded source evidence.json", old["source_evidence"], root) if old.get("source_evidence") is not None else None
    bundle["source_evidence_status"] = "embedded-generation-value" if old.get("source_evidence") is not None else "not-recorded"
    require(all(p.read_bytes() == raw for p, raw in guards.items()), "Legacy input changed during snapshot")
    verify_legacy_history(bundle, card, root)
    write_new(target / "Legacy bundle.json", bundle, root)
    return bundle


def verify_generation(path, root):
    path = inside(root, path)
    doc = validate(read(path), "generation")
    event = verify_event(read(checked(doc["source_event"], root)), root)
    require(event["card_type"] == doc["card_type"] and event["audit_findings"] == doc["audit_findings"],
            "Generation/event audit or family mismatch")
    verify_historical(doc["historical_accepted"], doc["card_type"], root, path)
    predecessor = doc["predecessor_held"]
    if predecessor is None:
        require(doc["sequence"] == 1, "Initial held sequence must be one")
    else:
        pp = checked(predecessor, root)
        require(pp != Path(path).resolve(), "Held predecessor self-binding")
        prior = validate(read(pp), "generation")
        require(prior["card_type"] == doc["card_type"] and prior["sequence"] + 1 == doc["sequence"], "Invalid held successor identity/sequence")
        # Prior event describes history, not live current facts. Never replay its old canonical paths.
        verify_historical(prior["historical_accepted"], prior["card_type"], root, pp)
        require(all(prior["historical_accepted"][key]["sha256"] == doc["historical_accepted"][key]["sha256"]
                    for key in ("generation", "drawing", "audit", "accepted_review")), "Held successor changed historical identity")
        old_physical, new_physical = prior["historical_accepted"]["physical_review"], doc["historical_accepted"]["physical_review"]
        require((None if old_physical is None else old_physical["sha256"]) == (None if new_physical is None else new_physical["sha256"]) and
                prior["historical_accepted"]["physical_review_status"] == doc["historical_accepted"]["physical_review_status"],
                "Held successor changed recorded physical review identity/status")
        require({x["published_path"]: x["artifact"]["sha256"] for x in prior["historical_accepted"]["files"]} ==
                {x["published_path"]: x["artifact"]["sha256"] for x in doc["historical_accepted"]["files"]}, "Held successor changed variant identity")
    return doc


def strict_current(card, generation, root):
    path = checked(generation, root)
    require(path == (Path(root) / f"notes/Card-ALD/Generation/{card}.json").resolve(), "Current generation must be the live generation")
    publisher = runtime(root, "card_ald", "publish_card_candidate")
    result = publisher.verify_current(card, root=root)
    # Preserve the original verifier and add an explicit zero-uncertainty default-build gate.
    spec, evidence = publisher.build_card_data.build(card, root=root)
    require(spec is not None and not evidence["uncertainties"], "Current default builder has unresolved uncertainties")
    outputs, _ = publisher.renderer.build(spec)
    require(all((Path(root) / "Card-ALD" / name).read_bytes() == raw for name, raw in outputs.items()), "Default drawing differs")
    require(result["passed"] is True, "Strict current verification failed")
    return result


def verify_index(path, root, allow_held=False):
    path = inside(root, path)
    require(path == inside(root, AUTHORITATIVE_PATH), "Status index must occupy authoritative Universal publication path")
    doc = validate(read(path), "index")
    if doc["predecessor_index"] is not None:
        previous = checked(doc["predecessor_index"], root)
        require(previous != path, "Index predecessor self-binding")
        validate(read(previous), "index")  # Historical document only, not old live source replay.
    return verify_index_document(doc, root, allow_held)


def verify_index_document(doc, root, allow_held=False):
    validate(doc, "index")
    checkpoint(doc["current_checkpoint"], root)
    base = read(checked(doc["base_inventory"], root))
    require(base.get("schema") == "shared-card-renderer-publication-v1", "Unsupported base inventory")
    base_rows = {row["card_type"]: row for row in base["cards"]}
    require(len(base_rows) == len(base["cards"]), "Duplicate base family")
    rows = {row["card_type"]: row for row in doc["entries"]}
    require(len(rows) == len(doc["entries"]) and set(rows) == set(base_rows), "Family partition must be disjoint and exhaustive")
    counts = {"families": len(rows), "current": 0, "held": 0, "legacy_proof_only": 0}
    for card, row in rows.items():
        status = row["status"]
        counts[status.replace("-", "_")] += 1
        if status == "current":
            strict_current(card, row["generation"], root)
            generation = read(checked(row["generation"], root))
        elif status == "held":
            require(allow_held, "Held card rejected by default: " + card)
            held = verify_generation(checked(row["generation"], root), root)
            require(held["card_type"] == card, "Index/held family mismatch")
            event = read(checked(held["source_event"], root))
            require(event["current_checkpoint"] == doc["current_checkpoint"], "Index/held checkpoint epoch differs")
            generation = read(checked(held["historical_accepted"]["generation"], root))
        else:
            generation = verify_legacy_history(row["historical_legacy"], card, root)
        base_row = base_rows[card]
        require(generation.get("canonical") == base_row["canonical"] and
                generation.get("diagram_sha256") == base_row["diagram_sha256"], "Frozen base inventory/historical relation differs")
        expected_files = {x["path"]: x["sha256"] for x in base["published_files"]
                          if re.fullmatch(r"Card-ALD/" + card + r"(?:-[0-9]+)?\.txt", x["path"])}
        require(generation_files(generation, card) == expected_files, "Frozen base inventory full variant relation differs")
    require(doc["counts"] == counts, "Partition counts differ; held is never current")
    return doc


def verify_current(card, index, root, allow_held=False):
    # Whole inventory validation prevents omission of inconvenient held families.
    doc = verify_index(index, root, allow_held=allow_held)
    row = next((x for x in doc["entries"] if x["card_type"] == card), None)
    require(row is not None, "Family absent from authoritative inventory")
    require(row["status"] != "legacy-proof-only", "Legacy proof is not current")
    return {"card_type": card, "status": row["status"], "current_passed": row["status"] == "current",
            "held_validated": row["status"] == "held", "usable_as_current": row["status"] == "current"}


def publish_current(card, definition, overrides, audit, review, index, root, check_only=True):
    """Guarded consumer adapter. A held family cannot use ordinary publication.

    A future explicit unhold transaction must replace its authoritative partition
    after independent physical/derivation review; this function does not unhold it.
    Other held families remain visible and separately validated in the inventory.
    """
    doc = verify_index(index, root, allow_held=True)
    row = next((x for x in doc["entries"] if x["card_type"] == card), None)
    require(row is not None and row["status"] == "current", "Ordinary publication rejects held/legacy or absent family")
    publisher = runtime(root, "card_ald", "publish_card_candidate")
    spec, evidence = publisher.build_card_data.build(card, root=root)
    require(spec is not None and not evidence["uncertainties"], "Default builder unresolved; publication rejected")
    return publisher.publish(card, definition, overrides, audit, review, root=root, check_only=check_only)


def capture(index, root, allow_held=False):
    doc = verify_index(index, root, allow_held=allow_held)
    result = {"schema": "held-derived-card-capture-v1", "index": binding(index, root),
              "current_checkpoint": doc["current_checkpoint"], "counts": deepcopy(doc["counts"]),
              "current_passed": sorted(x["card_type"] for x in doc["entries"] if x["status"] == "current"),
              "held_validated": sorted(x["card_type"] for x in doc["entries"] if x["status"] == "held"),
              "legacy_proof_only_validated": sorted(x["card_type"] for x in doc["entries"] if x["status"] == "legacy-proof-only"),
              "all_families_current": doc["counts"]["current"] == doc["counts"]["families"]}
    statuses = {x["card_type"]: x["status"] for x in doc["entries"]}
    metadata = []
    namespace = []
    for base in METADATA_BASES:
        for path in sorted((Path(root) / base).glob("[0-9][0-9][0-9][0-9].json")):
            card = path.stem
            require(card in statuses, "Unpartitioned metadata family: " + card)
            namespace.append({"card_type": card, "status": statuses[card], "artifact": binding(path, root)})
            if statuses[card] == "current":
                metadata.append(binding(path, root))
    expected = {(Path(base) / (card + ".json")).as_posix()
                for card, status in statuses.items() if status == "current" for base in METADATA_BASES}
    require({x["path"] for x in metadata} == expected and len(metadata) == 6 * doc["counts"]["current"],
            "Usable current metadata must contain exactly six records per current family")
    base = read(checked(doc["base_inventory"], root))
    expected_drawings = {str((Path(root) / x["path"]).resolve()): x["sha256"] for x in base["published_files"]}
    actual_drawings = {str(p.resolve()): binding(p, root)["sha256"] for p in (Path(root) / "Card-ALD").glob("*.txt")
                       if re.fullmatch(r"[0-9]{4}(?:-[0-9]+)?", p.stem)}
    require(actual_drawings == expected_drawings, "Full numeric drawing namespace differs from frozen inventory")
    for path in actual_drawings:
        card = Path(path).stem[:4]
        require(card in statuses, "Unpartitioned drawing family")
        namespace.append({"card_type": card, "status": statuses[card], "artifact": binding(path, root)})
    result.update(usable_current_metadata=metadata, usable_current_metadata_records=len(metadata), namespace_inventory=namespace)
    return validate(result, "capture")


def verify_capture(path, root, allow_held=False):
    path = inside(root, path)
    doc = validate(read(path), "capture")
    index = checked(doc["index"], root)
    require(doc == capture(index, root, allow_held), "Capture partition, namespace or current epoch differs")
    return doc


def create_generation(card, reason, source_event, historical_generation, drawing, physical_review, accepted_review, historical_audit,
                      output, root, predecessor_held=None):
    output = inside(root, output)
    source_event = inside(root, source_event)
    historical_generation, drawing, accepted_review, historical_audit = [inside(root, x) for x in
        (historical_generation, drawing, accepted_review, historical_audit)]
    physical_review = inside(root, physical_review) if physical_review is not None else None
    require(not output.exists(), "Generation output directory must be new")
    event = verify_event(read(source_event), root)
    require(event["card_type"] == card, "Requested/event family mismatch")
    # Verify historical markers before copying; immutable copies remove active-path coupling.
    originals = {"generation": Path(historical_generation), "drawing": Path(drawing),
                 "accepted_review": Path(accepted_review), "audit": Path(historical_audit)}
    if physical_review is not None:
        originals["physical_review"] = physical_review
    history = {key: binding(path, root) for key, path in originals.items()}
    generation = read(historical_generation)
    require(generation.get("schema") == "card-ald-current-publication-v1" and generation.get("card_type") == card and
            generation.get("independent_review", {}).get("passed") is True and generation.get("default_builder_reproduced") is True,
            "Only an exact previously accepted generation can be preserved as held history")
    require(generation.get("diagram_sha256") == history["drawing"]["sha256"], "Historical drawing mismatch")
    require(generation.get("independent_review", {}).get("sha256") == history["accepted_review"]["sha256"], "Historical review mismatch")
    require(generation.get("source_audit", {}).get("sha256") == history["audit"]["sha256"], "Historical audit mismatch")
    predecessor = binding(predecessor_held, root) if predecessor_held else None
    sequence = 1
    if predecessor:
        prior = validate(read(inside(root, predecessor_held)), "generation")
        sequence = prior["sequence"] + 1
    target = Path(output)
    history = {"current_seal": False, "physical_review": None,
               "physical_review_status": "not-recorded" if physical_review is None else "recorded-historical-evidence"}
    for key, path in originals.items():
        dest = target / "Historical" / (key + path.suffix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as stream:
            stream.write(path.read_bytes())
        history[key] = binding(dest, root)
    history["files"] = []
    prior_files = {x["published_path"]: checked(x["artifact"], root) for x in prior["historical_accepted"]["files"]} if predecessor else {}
    for published_path, sha in generation_files(generation, card).items():
        source = prior_files[published_path] if predecessor else inside(root, published_path)
        require(binding(source, root)["sha256"] == sha, "Historical variant source differs: " + published_path)
        dest = inside(root, target / "Historical/Drawings" / Path(published_path).name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as stream:
            stream.write(source.read_bytes())
        history["files"].append({"published_path": published_path, "artifact": binding(dest, root)})
    doc = {"schema": "held-derived-card-generation-v2", "card_type": card, "status": "held", "current": False,
           "usable_as_current": False, "approval": False, "visible_reason": reason, "source_event": binding(source_event, root),
           "audit_findings": event["audit_findings"], "historical_accepted": history,
           "sequence": sequence, "predecessor_held": predecessor}
    validate(doc, "generation")
    destination = target / "Generation.json"
    write_new(destination, doc, root)
    verify_generation(destination, root)
    return binding(destination, root)


def make_index(base_inventory, current_checkpoint, entries, output, root, predecessor_index=None):
    output = inside(root, output)
    require(output == inside(root, AUTHORITATIVE_PATH), "Status output must replace the authoritative Universal publication path")
    raw = inside(root, base_inventory).read_bytes()
    previous = None
    previous_typed = False
    if output.exists():
        require(predecessor_index is not None and checked(predecessor_index, root) == output, "Existing authoritative index requires exact predecessor guard")
        previous = output.read_bytes()
        if read(output).get("schema") == "shared-card-renderer-publication-v1":
            require(previous == raw, "Initial Universal transition must snapshot exact old authoritative inventory")
        else:
            validate(read(output), "index")
            previous_typed = True
    else:
        require(predecessor_index is None, "Absent index has no predecessor")
    # Snapshot original inventory bytes; old unqualified rows become historical evidence only.
    history_dir = inside(root, output.parent / "Status history")
    history_dir.mkdir(parents=True, exist_ok=True)
    dest = inside(root, history_dir / ("Base-" + hashlib.sha256(raw).hexdigest() + ".json"))
    if not dest.exists():
        with dest.open("xb") as stream:
            stream.write(raw)
    require(dest.read_bytes() == raw, "Historical base collision")
    previous_binding = None
    if previous_typed:
        prior_path = inside(root, history_dir / ("Index-" + hashlib.sha256(previous).hexdigest() + ".json"))
        if not prior_path.exists():
            with prior_path.open("xb") as stream:
                stream.write(previous)
        require(prior_path.read_bytes() == previous, "Historical index collision")
        previous_binding = binding(prior_path, root)
    counts = {"families": len(entries), "current": 0, "held": 0, "legacy_proof_only": 0}
    for row in entries:
        require(row.get("status") in ("current", "held", "legacy-proof-only"), "Unknown partition status")
        counts[row["status"].replace("-", "_")] += 1
    doc = {"schema": "held-derived-card-index-v3", "authoritative": True, "base_inventory": binding(dest, root), "predecessor_index": previous_binding,
           "current_checkpoint": current_checkpoint, "entries": entries, "counts": counts}
    path = output
    validate(doc, "index")
    verify_index_document(doc, root, allow_held=True)
    require((path.read_bytes() if path.exists() else None) == previous, "Authoritative index changed during preparation")
    if previous is None:
        write_new(path, doc, root)
    else:
        staging = path.parent / (".status-" + hashlib.sha256(encode(doc)).hexdigest() + ".new")
        write_new(staging, doc, root)
        require(path.read_bytes() == previous, "Authoritative index changed before replace")
        staging.replace(path)
    verify_index(path, root, allow_held=True)
    return binding(path, root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["generate", "index", "capture", "verify-capture", "verify-current", "verify-proposal"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--request", type=Path, help="Generation arguments or index entries JSON")
    parser.add_argument("--index", type=Path)
    parser.add_argument("--card")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-held", action="store_true")
    parser.add_argument("--expected-source-plan", type=Path, help="Exact portable binding JSON admitted by finite coordinator")
    args = parser.parse_args()
    if args.operation == "generate":
        request = read(args.request)
        require(set(request) in ({"card", "reason", "source_event", "historical_generation", "drawing", "physical_review", "accepted_review", "historical_audit"},
                                  {"card", "reason", "source_event", "historical_generation", "drawing", "physical_review", "accepted_review", "historical_audit", "predecessor_held"}), "Unknown/missing generation request keys")
        result = create_generation(**request, output=args.output, root=args.root)
    elif args.operation == "index":
        request = read(args.request)
        require(set(request) in ({"base_inventory", "current_checkpoint", "entries"}, {"base_inventory", "current_checkpoint", "entries", "predecessor_index"}), "Unknown/missing index request keys")
        result = make_index(**request, output=args.output, root=args.root)
    elif args.operation == "capture":
        result = capture(args.index, args.root, args.allow_held)
        if args.output:
            write_new(args.output, result, args.root)
    elif args.operation == "verify-capture":
        result = verify_capture(args.request, args.root, args.allow_held)
    elif args.operation == "verify-proposal":
        result = verify_proposal(read(args.request), args.root, read(args.expected_source_plan))
    else:
        result = verify_current(args.card, args.index, args.root, args.allow_held)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

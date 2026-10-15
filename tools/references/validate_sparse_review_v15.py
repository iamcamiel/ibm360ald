"""Fail-closed V15 AP041 publication and bounded human shape-review gates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

VERDICT_SHA = "de8bd7edd9ee7762d036db7203f61dad8a263bfeeda233c6d7ffe4131f08be81"
PUBLICATION_SHA = "80afb1f7abc05f17dd2ea04367b37cc9b71ba4f47a6e5b8768bc40482a8df629"
EXPECTED_NODES = {"AS": (11, "OR", "K8", 34, 120),
                  "AU": (13, "A", "K4", 13, 143),
                  "BB": (15, "N", "K6", 13, 166)}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def bound(binding):
    path = Path(binding["path"])
    if sha(path) != binding["sha256"]:
        raise ValueError("V15 source-bound evidence hash changed: " + str(path))
    return load(path)


def validate_ap041(repo, pages, sources, file_sources, publication_path):
    if sha(publication_path) != PUBLICATION_SHA:
        raise ValueError("V15 AP041 publication receipt differs from reviewed receipt")
    publication = load(publication_path)
    stage = bound(publication["stage"])
    audit = bound(publication["independent_acceptance"])
    candidate = bound(stage["source_candidate"])
    for crop in stage["native_crops"]:
        if sha(Path(crop["path"])) != crop["sha256"]:
            raise ValueError("V15 AP041 original-source crop changed")
    if candidate["schema"] != "ap041-three-way-portion-correction-candidate-v1":
        raise ValueError("V15 AP041 candidate identity changed")
    if (publication["schema"] != "ap041-three-way-canonical-publication-v1"
            or stage["schema"] != "ap041-three-way-source-bound-private-stage-v1"
            or audit["schema"] != "ap041-independent-three-way-private-stage-acceptance-v1"
            or audit["status"] != "PASS" or audit["failures"]
            or audit["manifest"] != publication["stage"]):
        raise ValueError("V15 AP041 publication chain is not independently accepted")
    if publication["source_tiff"]["sha256"] != sources[pages["212"]["original_source_id"]]["sha256"]:
        raise ValueError("V15 AP041 original TIFF binding changed")
    if stage["original_tiff"]["sha256"] != publication["source_tiff"]["sha256"]:
        raise ValueError("V15 AP041 stage TIFF binding changed")
    if len(stage["text_edits"]) != 3 or len(stage["model_edits"]) != 9:
        raise ValueError("V15 AP041 requires exactly three printed portions and nine model fields")
    page = pages["212"]
    if page["page"] != "AP041":
        raise ValueError("V15 AP041 scan identity changed")
    text_path = repo / page["text_path"]
    model_rel = "json/AP Parallel Adder/AP041 PARALLEL ADDER BIT 04.json"
    if model_rel not in file_sources:
        raise ValueError("V15 accepted AP041 model missing")
    model_path = repo / model_rel
    expected = {x["artifact"]: x for x in publication["canonical_destinations"]}
    if sha(text_path) != expected["txt"]["sha256"] or sha(model_path) != expected["json"]["sha256"]:
        raise ValueError("V15 AP041 is not yet mirrored into the accepted repository")
    if sources[page["text_source_id"]]["sha256"] != expected["txt"]["sha256"]:
        raise ValueError("V15 AP041 accepted page source identity changed")
    if sources[file_sources[model_rel]]["sha256"] != expected["json"]["sha256"]:
        raise ValueError("V15 AP041 accepted model source identity changed")
    for kind in ("txt", "json", "notes", "preview"):
        if (stage["candidate_quartet"][kind]["sha256"] != expected[kind]["sha256"]
                or stage["before_quartet"][kind]["sha256"] != expected[kind]["before_sha256"]
                or sha(Path(expected[kind]["path"])) != expected[kind]["sha256"]):
            raise ValueError("V15 AP041 staged and published quartet hashes diverged: " + kind)
    model = load(model_path)
    lines = text_path.read_text(encoding="utf-8").splitlines()
    history = model.get(stage["model_history_key"])
    if not isinstance(history, dict) or history.get("candidate", {}).get("sha256") != stage["source_candidate"]["sha256"]:
        raise ValueError("V15 AP041 exact source-bound model history missing")
    if history.get("predecessor_txt_sha256") != expected["txt"]["before_sha256"] or history.get("predecessor_json_sha256") != expected["json"]["before_sha256"]:
        raise ValueError("V15 AP041 model predecessor hashes changed")
    for node_name, (index, function, portion, row, column) in EXPECTED_NODES.items():
        node = model["nodes"][index]
        if (node.get("id") != node_name or node.get("function") != function or node.get("portion") != portion
                or node.get("printed_card_portion") != "4633" + portion
                or node.get("socket_listing_evidence", {}).get("portion") != portion
                or lines[row][column:column + 6] != "4633" + portion):
            raise ValueError("V15 AP041 three-way portion mapping changed: " + node_name)
    return {"publication": publication, "stage": stage, "audit": audit,
            "repo_text_sha256": sha(text_path), "repo_model_sha256": sha(model_path)}


def validate_review(review_path, binding_path):
    if sha(review_path) != VERDICT_SHA:
        raise ValueError("V15 human sparse-shape verdict changed")
    review = load(review_path)
    binding = load(binding_path)
    if sha(Path(binding["v14_build_manifest"]["path"])) != binding["v14_build_manifest"]["sha256"]:
        raise ValueError("V15 frozen V14 exact-observation reference changed")
    if (review["schema_version"] != "ald-sparse-function-shape-human-review-v1"
            or binding["schema"] != "ald-v15-sparse-shape-identity-binding-v1"
            or binding["authority"]["sha256"] != VERDICT_SHA
            or binding["authority"]["path"] != str(review_path)):
        raise ValueError("V15 shape-review authority mismatch")
    if (len(review["interpretation"]["accepted_as_legitimate_different_shape"]) != 16
            or review.get("follow_up_reply") != "0497A2 seems legitimate too now."):
        raise ValueError("V15 human-reviewed case count changed")
    cases = binding["reviewed_legitimate_cases"]
    if (len(cases) != 16 or {c["card_portion"] for c in cases}
            != set(review["interpretation"]["accepted_as_legitimate_different_shape"])):
        raise ValueError("V15 frozen reviewed identities differ from human verdict")
    if binding["corrected_crop_accepted_case"] != "0497A2" or binding["ap041_corrected_case"] != "4633K4":
        raise ValueError("V15 unresolved/resolved shape case scope changed")
    return {c["card_portion"]: c for c in cases}


def annotate_shape_flag(card_portion, flag, cases, source_id, seen):
    case = cases.get(card_portion)
    if case is None or flag["shape_id"] != case["shape_id"]:
        flag["manual_review_required"] = True
        flag["review_status"] = "Open review flag; no direct-human disposition"
        return
    current = [{"page": o["page"], "scan_id": str(o["scan_id"]), "JSON_pointer": o["JSON_pointer"],
                "primary_function": o["primary_function"]} for o in flag["observations"]]
    if (flag["observation_count"] != 2
            or sorted(current, key=lambda o: (o["scan_id"], o["JSON_pointer"]))
            != sorted(case["observations"], key=lambda o: (o["scan_id"], o["JSON_pointer"]))):
        raise ValueError("V15 reviewed shape identity has changed: " + card_portion)
    if card_portion in seen:
        raise ValueError("V15 duplicate reviewed shape: " + card_portion)
    seen.add(card_portion)
    flag["manual_review_required"] = False
    flag["review_status"] = "Direct-human-reviewed legitimate observed variation"
    flag["status"] = "Reviewed legitimate observed variation; retained for traceability"
    flag["review_authority_source_id"] = source_id
    flag["review_authority_JSON_pointer"] = "/interpretation/accepted_as_legitimate_different_shape"
    flag["review_scope"] = "Exact two source observations; no function, pin or wiring correction"


def validate_review_coverage(cases, seen, cards):
    if seen != set(cases):
        raise ValueError("V15 reviewed shape case disappeared or was not annotated: " + str(sorted(set(cases) - seen)))
    k4 = cards["4633"]["portions"]["K4"]
    if any(any(o["page"] == "AP041" for o in flag["observations"]) for flag in k4["shape_review_flags"]):
        raise ValueError("V15 AP041 OR remains incorrectly grouped under 4633K4")


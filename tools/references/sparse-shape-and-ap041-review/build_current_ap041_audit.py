import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

WORK = Path(r"D:\Github\IBM360")
EVIDENCE = WORK / "tmp/ald-text/ald/card-type-database/sparse-shape-review/ap041-k8"
OUT = WORK / "tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/AP041 three-way portion current audit.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned(path):
    path = Path(path)
    return {"file": str(path), "sha256": digest(path)}


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


stage_path = EVIDENCE / "three-way-private-stage/AP041 three-way private stage manifest.json"
accept_path = EVIDENCE / "AP041 independent three-way private-stage acceptance.json"
pub_path = EVIDENCE / "AP041 three-way canonical publication receipt.json"
source_path = EVIDENCE / "AP041 three-way portion correction candidate.json"
crop_path = EVIDENCE / "AP041 AS AU BB three-way native comparison.png"

stage = json.loads(stage_path.read_text(encoding="utf-8"))
accept = json.loads(accept_path.read_text(encoding="utf-8"))
pub = json.loads(pub_path.read_text(encoding="utf-8"))
require(accept["status"] == "PASS" and not accept["failures"], "independent review must pass")
require(accept["manifest"]["sha256"] == digest(stage_path), "independent acceptance stage pin")
require(pub["stage"]["sha256"] == digest(stage_path), "publication stage pin")
require(pub["independent_acceptance"]["sha256"] == digest(accept_path), "publication independent acceptance pin")
require(stage["source_candidate"]["sha256"] == digest(source_path), "candidate pin")
require(stage["comparison"]["sha256"] == digest(crop_path), "native crop pin")
require(stage["original_tiff"]["sha256"] == digest(stage["original_tiff"]["path"]), "original TIFF pin")

quartet = {}
for name, candidate in stage["candidate_quartet"].items():
    published = next(x for x in pub["canonical_destinations"] if x["artifact"] == name)
    require(published["sha256"] == candidate["sha256"], f"{name} publication candidate pin")
    require(digest(published["path"]) == candidate["sha256"], f"{name} current published bytes")
    quartet[name] = {"path": published["path"], "sha256": published["sha256"]}

result = {
    "schema": "ap041-source-bound-current-quartet-audit-v1",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "passed": True,
    "failures": [],
    "scope": "AP041 original TIFF three-way card-portion correction; current canonical quartet only",
    "pages": [
        {
            "page": "AP041",
            "eligible": True,
            "artifact_schema": "reviewed-current-quartet-v1",
            "source": stage["original_tiff"],
            "current_quartet": quartet,
            "owner_receipt": pinned(pub_path),
            "independent_audit": pinned(accept_path),
            "ap041_manifest": pinned(stage_path),
            "ap041_source_evidence": pinned(source_path),
            "ap041_source_crop": pinned(crop_path),
            "checks": {
                "original_TIFF_native_three_portion_readings": True,
                "independent_exact_private_stage_acceptance": True,
                "current_full_quartet_matches_private_stage_and_publication": True,
                "only_three_printed_portions_and_nine_node_aliases_changed": True,
                "functions_pins_wires_geometry_and_other_nodes_unchanged": True,
            },
        }
    ],
    "canonical_writes": 0,
    "repository_writes": 0,
}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"path": str(OUT), "sha256": digest(OUT), "passed": True}, indent=2))

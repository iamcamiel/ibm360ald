"""Publish the four independently reviewed 463x topology/pin repairs.

Preflight binds each staged quartet to the current canonical quartet and
original TIFF before any write. The resulting audit lets the reviewed exporter
select the new current files without accepting a stale earlier version.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path

from release_463x_source_corrections import WORKSPACE, REPO, sha, preview


BASE = WORKSPACE / "tmp/ald-text/ald/card-463x-release"
BATCH = BASE / "463x-topology-stage/manifest.json"
AUDIT = (WORKSPACE / "tmp/ald-text/ald/manual-verification/"
         "contextual-cross-reference-v3/463x topology current audit.json")
REPO_AUDIT = REPO / "notes/Card-ALD/463x topology current audit.json"


def gather():
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    assert batch["schema"] == "card-463x-topology-batch-stage-v1"
    assert set(batch["pages"]) == {"AP071", "AP111", "AP491", "AP551"}
    records = []
    for item in batch["submanifests"]:
        path = Path(item["path"])
        assert sha(path.read_bytes()) == item["sha256"]
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest["schema"] == "card-4634-ap491-topology-stage-v1":
            assert manifest["grid"]["source_output"] == [47, 58]
            assert manifest["grid"]["target_upper_input"] == [52, 72]
            records.append({"page": "AP491", "source": manifest["source"],
                            "prior_quartet": manifest["prior_quartet"],
                            "staged_quartet": manifest["staged_quartet"],
                            "finding": "463439 row 47 feeds 463452 row 52; 463440 feeds row 54"})
        elif manifest["schema"] == "card-4633-a7-pin-stage-v1":
            assert {r["page"] for r in manifest["records"]} == {"AP071", "AP111", "AP551"}
            for record in manifest["records"]:
                assert record["reading"]["new"] == "B13"
                assert record["reading"]["existing_net_target_relabelled"] is True
                records.append({"page": record["page"], "source": record["source"],
                                "prior_quartet": record["prior_quartet"],
                                "staged_quartet": record["staged_quartet"],
                                "finding": "4633A7 upper input reads B13"})
        else:
            raise AssertionError(manifest["schema"])
    assert {r["page"] for r in records} == set(batch["pages"])
    return records


def verify(records):
    source_root = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder").resolve()
    for record in records:
        source = record["source"]
        source_path = Path(source["path"])
        assert source_path.is_file() and source_path.resolve().is_relative_to(source_root)
        assert sha(source_path.read_bytes()) == source["sha256"]
        assert set(record["prior_quartet"]) == set(record["staged_quartet"]) == {
            "txt", "json", "notes", "preview"}
        for kind in record["prior_quartet"]:
            old, new = record["prior_quartet"][kind], record["staged_quartet"][kind]
            assert sha(Path(old["path"]).read_bytes()) == old["sha256"], (record["page"], kind)
            assert sha(Path(new["path"]).read_bytes()) == new["sha256"], (record["page"], kind)
        staged = record["staged_quartet"]
        txt = Path(staged["txt"]["path"]).read_bytes()
        rows = txt.decode("utf-8").splitlines()
        assert len(rows) == 103 and all(len(row) == 245 for row in rows)
        assert sha(preview(txt)) == staged["preview"]["sha256"]
        document = json.loads(Path(staged["json"]["path"]).read_text(encoding="utf-8"))
        if record["page"] == "AP491":
            assert rows[47][58:62] == "───┐" and rows[52][61] == "└"
            assert rows[54][61:73] == "────────────"
            nets = {net["id"]: net for net in document["nets"]}
            assert nets["AC"]["driver"] == "AC.output" and nets["AC"]["targets"] == ["AL.input52"]
            assert nets["AD"]["targets"] == ["AL.input54"]
        else:
            assert rows[31][116:119] == "B13"
            node = next(n for n in document["nodes"] if n["id"] == "AT")
            assert any(pin["side"] == "input" and pin["row"] == 31 and pin["pin"] == "B13"
                       for pin in node["pins"])
    print("Verified", len(records), "source-bound staged pages")


def publish(records):
    verify(records)
    for record in records:
        for kind, old in record["prior_quartet"].items():
            Path(old["path"]).write_bytes(Path(record["staged_quartet"][kind]["path"]).read_bytes())
    audit = {"schema": "card-463x-topology-current-audit-v1",
             "created_utc": datetime.now(timezone.utc).isoformat(),
             "passed": True,
             "reviewer": "Direct physical-page confirmation and independent original-TIFF topology review",
             "stage_manifest": {"path": str(BATCH), "sha256": sha(BATCH.read_bytes())},
             "pages": []}
    for record in records:
        current = {kind: {"path": old["path"], "sha256": record["staged_quartet"][kind]["sha256"]}
                   for kind, old in record["prior_quartet"].items()}
        assert all(sha(Path(item["path"]).read_bytes()) == item["sha256"]
                   for item in current.values())
        audit["pages"].append({"page": record["page"], "eligible": True,
                               "artifact_schema": "reviewed-current-quartet-v1",
                               "source": {k: v for k, v in record["source"].items() if k != "crop"},
                               "prior_quartet": record["prior_quartet"],
                               "current_quartet": current,
                               "checks": {"source_bound": True, "stage_hashes_verified": True,
                                          "grid_json_preview_verified": True,
                                          "human_or_native_review": True},
                               "finding": record["finding"]})
    content = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    AUDIT.write_text(content, encoding="utf-8")
    REPO_AUDIT.write_text(content, encoding="utf-8")
    print("Published", len(records), "reviewed current pages")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("verify", "publish"))
    args = parser.parse_args()
    records = gather()
    verify(records) if args.action == "verify" else publish(records)

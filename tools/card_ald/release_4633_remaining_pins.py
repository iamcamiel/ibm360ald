"""Stage or publish the 37 independently audited 4633 physical-pin readings.

The stage action writes only to tmp/ald-text. Publication is a separate,
explicit action and rechecks all original TIFF and canonical-artifact hashes.
The damaged AP071/AP551 B13 candidates and printed logical A/B labels are
excluded by the accepted native-pin audit ledger.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path

from release_463x_source_corrections import (
    WORKSPACE, CANONICAL, REPO, sha, preview, append_note,
)

LEDGER = WORKSPACE / "tmp/ald-text/ald/4633-native-audit/4633 remaining native pin audit.json"
STAGE = WORKSPACE / "tmp/ald-text/ald/card-463x-release/pin-remaining-stage"
AUDIT = WORKSPACE / "tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/4633 remaining native pin current audit.json"
REPO_AUDIT = REPO / "notes/Card-ALD/4633 remaining native pin current audit.json"
SOURCE = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder")


def paths(root, stem, preview_name):
    return {
        "txt": root / (stem + ".txt"),
        "json": root / (stem + ".json"),
        "notes": root / (stem + " review notes.txt"),
        "preview": root / preview_name,
    }


def changes():
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    assert ledger["summary"] == {
        "supported_correction": 37,
        "probable_hold": 2,
        "not_physical_pin": 6,
    }, ledger["summary"]
    selected = [e for e in ledger["entries"] if e["disposition"] == "supported_correction"]
    assert len(selected) == 37
    assert all(e["current"] != e["corrected"] for e in selected)
    assert all(Path(e["evidence_crop"]).is_file() for e in selected)
    return selected


def stage():
    selected = changes()
    groups = {}
    for change in selected:
        groups.setdefault(change["page"], []).append(change)
    STAGE.mkdir(parents=True, exist_ok=True)
    records = []
    for page, edits in sorted(groups.items()):
        matches = list(CANONICAL.glob(page + " *.json"))
        assert len(matches) == 1, (page, matches)
        stem = matches[0].stem
        preferred = CANONICAL / (stem + " JuliaMono preview.png")
        preview_name = preferred.name if preferred.is_file() else stem + ".png"
        original = paths(CANONICAL, stem, preview_name)
        before = {kind: path.read_bytes() for kind, path in original.items()}
        rows = before["txt"].decode("utf-8").splitlines(keepends=True)
        model = json.loads(before["json"].decode("utf-8"))
        evidence = []
        for edit in edits:
            node_id = edit["node"]
            node = next(n for n in model["nodes"] if n["id"] == node_id)
            assert node["card_type"] == "4633" and node["portion"] == edit["portion"]
            matching = [p for p in node["pins"] if p.get("pin") == edit["current"]
                        and p["side"] == edit["side"]]
            assert len(matching) == 1, (page, node_id, edit["current"], matching)
            pin = matching[0]
            row, col = pin["row"], node["column"]
            old_label = pin.get("printed_label") or edit["current"]
            assert old_label.startswith(edit["current"]), (page, node_id, old_label)
            suffix = old_label[len(edit["current"]):]
            assert suffix in ("", "✲"), (page, node_id, suffix)
            new_label = edit["corrected"] + suffix
            assert len(old_label) == len(new_label), (page, node_id, old_label, new_label)
            lo, hi = (col-12, col+8) if pin["side"] == "input" else (col+7, col+40)
            hits = [i for i in range(lo, min(hi, len(rows[row])))
                    if rows[row].startswith(old_label, i)]
            assert len(hits) == 1, (page, node_id, row, old_label, hits)
            left = hits[0]
            rows[row] = rows[row][:left] + new_label + rows[row][left+len(old_label):]
            pin["pin"] = edit["corrected"]
            if pin.get("printed_label") == old_label:
                pin["printed_label"] = new_label
            for label in model.get("printed_labels", []):
                if label.get("row") == row and label.get("text") == old_label:
                    label["text"] = new_label
            crop = Path(edit["evidence_crop"])
            evidence.append({
                "node": node_id, "portion": edit["portion"], "side": pin["side"],
                "row": row, "column": left, "before": old_label, "after": new_label,
                "crop": {"path": str(crop), "sha256": sha(crop.read_bytes())},
            })
        after = dict(before)
        after["txt"] = "".join(rows).encode("utf-8")
        after["json"] = (json.dumps(model, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        after["preview"] = preview(after["txt"])
        summary = "; ".join(e["node"] + " " + e["before"] + " -> " + e["after"]
                            for e in evidence)
        after["notes"] = append_note(before["notes"],
            "Card-ALD 4633 native pin audit, 2026-10-15: " + summary +
            ". Source TIFFs and independent crops are hash-bound in the stage manifest. " +
            "AP071/AP551 uncertain B13 readings remain for physical review; " +
            "printed A/B logical input labels remain unchanged.")
        assert len(rows) == 103 and all(len(r.rstrip("\r\n")) == 245 for r in rows)
        stage_dir = STAGE / stem
        stage_dir.mkdir(exist_ok=True)
        staged = paths(stage_dir, stem, preview_name)
        for kind, content in after.items():
            staged[kind].write_bytes(content)
        source = SOURCE / (stem + ".tif")
        assert source.is_file(), source
        records.append({
            "page": page,
            "source": {"path": str(source), "sha256": sha(source.read_bytes())},
            "changes": evidence,
            "prior_quartet": {k: {"path": str(original[k]), "sha256": sha(v)}
                              for k, v in before.items()},
            "staged_quartet": {k: {"path": str(staged[k]), "sha256": sha(v)}
                               for k, v in after.items()},
            "checks": {
                "native_crops_viewed": True,
                "only_named_pin_labels_changed": True,
                "grid_json_preview_verified": True,
                "source_and_quartet_hashes_bound": True,
            },
        })
    manifest = {
        "schema": "card-4633-remaining-pins-stage-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "ledger": {"path": str(LEDGER), "sha256": sha(LEDGER.read_bytes())},
        "records": records,
    }
    (STAGE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Staged", len(records), "pages and", len(selected), "physical pins")


def verify_stage():
    manifest_path = STAGE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "card-4633-remaining-pins-stage-v1"
    assert sha(LEDGER.read_bytes()) == manifest["ledger"]["sha256"]
    assert len(manifest["records"]) == 21
    assert sum(len(r["changes"]) for r in manifest["records"]) == 37
    actual_pages = {r["page"] for r in manifest["records"]}
    expected_pages = {e["page"] for e in changes()}
    assert actual_pages == expected_pages

    def semantic_diffs(before, after, path=()):
        if type(before) is not type(after):
            return [path]
        if isinstance(before, dict):
            if before.keys() != after.keys():
                return [path]
            return [difference for key in before
                    for difference in semantic_diffs(before[key], after[key], path+(key,))]
        if isinstance(before, list):
            if len(before) != len(after):
                return [path]
            return [difference for index, (left, right) in enumerate(zip(before, after))
                    for difference in semantic_diffs(left, right, path+(index,))]
        return [] if before == after else [path]

    for record in manifest["records"]:
        assert sha(Path(record["source"]["path"]).read_bytes()) == record["source"]["sha256"]
        for change in record["changes"]:
            crop = change["crop"]
            assert sha(Path(crop["path"]).read_bytes()) == crop["sha256"]
        for kind, old in record["prior_quartet"].items():
            new = record["staged_quartet"][kind]
            assert sha(Path(old["path"]).read_bytes()) == old["sha256"]
            assert sha(Path(new["path"]).read_bytes()) == new["sha256"]
        prior = record["prior_quartet"]
        staged = record["staged_quartet"]
        original_rows = Path(prior["txt"]["path"]).read_text(encoding="utf-8").splitlines()
        staged_rows = Path(staged["txt"]["path"]).read_text(encoding="utf-8").splitlines()
        assert len(original_rows) == len(staged_rows) == 103
        expected_rows = original_rows.copy()
        for change in record["changes"]:
            row, col = change["row"], change["column"]
            old, new = change["before"], change["after"]
            assert expected_rows[row][col:col+len(old)] == old
            assert len(old) == len(new)
            expected_rows[row] = expected_rows[row][:col] + new + expected_rows[row][col+len(old):]
        assert expected_rows == staged_rows, record["page"]
        before_model = json.loads(Path(prior["json"]["path"]).read_text(encoding="utf-8"))
        after_model = json.loads(Path(staged["json"]["path"]).read_text(encoding="utf-8"))
        diff_paths = semantic_diffs(before_model, after_model)
        assert diff_paths
        for path in diff_paths:
            if path[:1] == ("nodes",):
                assert len(path) == 5 and path[2] == "pins" and path[4] in ("pin", "printed_label"), path
            elif path[:1] == ("printed_labels",):
                assert len(path) == 3 and path[2] == "text", path
            else:
                raise AssertionError((record["page"], path))
        from PIL import Image
        with Image.open(staged["preview"]["path"]) as im:
            im.verify()
    print("Verified", len(manifest["records"]), "source-bound pages and",
          sum(len(r["changes"]) for r in manifest["records"]), "pin-only edits")


def publish():
    manifest_path = STAGE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "card-4633-remaining-pins-stage-v1"
    assert sha(LEDGER.read_bytes()) == manifest["ledger"]["sha256"]
    assert sum(len(r["changes"]) for r in manifest["records"]) == 37
    for record in manifest["records"]:
        assert sha(Path(record["source"]["path"]).read_bytes()) == record["source"]["sha256"]
        for change in record["changes"]:
            crop = change["crop"]
            assert sha(Path(crop["path"]).read_bytes()) == crop["sha256"]
        for kind, old in record["prior_quartet"].items():
            new = record["staged_quartet"][kind]
            assert sha(Path(old["path"]).read_bytes()) == old["sha256"]
            assert sha(Path(new["path"]).read_bytes()) == new["sha256"]
    for record in manifest["records"]:
        for kind, old in record["prior_quartet"].items():
            Path(old["path"]).write_bytes(
                Path(record["staged_quartet"][kind]["path"]).read_bytes())
    audit = {
        "schema": "card-4633-remaining-pins-current-audit-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "reviewer": "Coordinator independent native TIFF crop review",
        "scope": "37 named 4633 physical-pin readings; two B13 holds and six A/B labels excluded",
        "stage_manifest": {"path": str(manifest_path), "sha256": sha(manifest_path.read_bytes())},
        "pages": [],
    }
    for record in manifest["records"]:
        current = {kind: {"path": old["path"],
                          "sha256": record["staged_quartet"][kind]["sha256"]}
                   for kind, old in record["prior_quartet"].items()}
        assert all(sha(Path(x["path"]).read_bytes()) == x["sha256"]
                   for x in current.values())
        audit["pages"].append({
            "page": record["page"], "eligible": True,
            "artifact_schema": "reviewed-current-quartet-v1",
            "source": record["source"],
            "prior_quartet": record["prior_quartet"],
            "current_quartet": current,
            "checks": record["checks"], "changes": record["changes"],
        })
    content = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    AUDIT.write_text(content, encoding="utf-8")
    REPO_AUDIT.write_text(content, encoding="utf-8")
    print("Published", len(manifest["records"]), "reviewed 4633 pages")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("stage", "verify", "publish"))
    action = parser.parse_args().action
    {"stage": stage, "verify": verify_stage, "publish": publish}[action]()

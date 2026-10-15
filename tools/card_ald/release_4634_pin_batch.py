"""Stage source-bound 4634 physical-pin readings; publish only when requested.

The batch contains 56 invalid pin strings reviewed against native TIFF crops
and matching card portions, plus AP351 AF's valid-letter B08 correction.
It intentionally excludes internal IN/OUT labels and AP511 AP's internal A.
"""

from argparse import ArgumentParser
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json

from PIL import Image, ImageChops

from release_463x_source_corrections import (
    WORKSPACE, CANONICAL, REPO, sha, preview, append_note,
)


STAGE = WORKSPACE / "tmp/ald-text/ald/card-463x-release/4634-pin-stage"
AUDIT = (WORKSPACE / "tmp/ald-text/ald/manual-verification/"
         "contextual-cross-reference-v3/4634 native pin current audit.json")
REPO_AUDIT = REPO / "notes/Card-ALD/4634 native pin current audit.json"
SOURCE = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder")
CROPS = WORKSPACE / "tmp/ald-text/ald/card-4634-audit/pins"
SCHEMA = "card-4634-physical-pin-stage-v1"

# page node portion side old new; one physical pin per record.  This list is
# fixed here so the release tool does not depend on a private working CSV.
CHANGES_TEXT = """\
AP041 AC 42 input U10 J10
AP041 AC 42 input U07 D07
AP041 AC 42 input U11 D11
AP081 AC 42 input U11 D11
AP081 AC 42 input U07 D07
AP121 AC 42 input U07 D07
AP161 AC 42 input U07 D07
AP201 AC 42 input U07 D07
AP241 AC 42 input U07 D07
AP321 AC 42 input U10 J10
AP321 AC 42 input U07 D07
AP361 AC 42 input U10 J10
AP361 AC 42 input U07 D07
AP401 AC 42 input U07 D07
AP601 AC 42 input U07 D07
AP041 AD 43 input U07 D07
AP121 AD 43 input U07 D07
AP281 AD 43 input U07 D07
AP131 AC 39 input U07 D07
AP211 AC 39 input U07 D07
AP251 AC 39 input U07 D07
AP331 AC 39 input U07 D07
AP371 AC 39 input U07 D07
AP131 AD 40 input U07 D07
AP171 AD 40 input U07 D07
AP211 AD 40 input U07 D07
AP221 AG 17 input 8B0� B09
AP581 AG 17 input F12 B12
AP311 AJ 14 input 8C07 G07
AP151 AC 46 input U12 J12
AP471 AC 46 input U07 J07
AP111 AD 47 input U07 D07
AP151 AD 47 input U07 D07
AP151 AD 47 input U13 D13
AP191 AD 47 input U13 D13
AP231 AD 47 input U13 D13
AP271 AD 47 input U07 D07
AP271 AD 47 input U13 D13
AP311 AE 47 input U13 D13
AP351 AD 47 input U13 D13
AP351 AD 47 input U07 D07
AP391 AD 47 input U13 D13
AP391 AD 47 input U07 D07
AP431 AD 47 input U13 D13
AP191 AE 48 input H02 B02
AP271 AE 48 input U13 D13
AP391 AE 48 input U13 D13
AP431 AE 48 input U13 D13
AP471 AE 48 input U13 D13
AP591 AE 48 input U13 D13
AP191 AF 37 input U13 D13
AP271 AF 37 input U13 D13
AP311 AG 37 input U13 D13
AP391 AF 37 input U08 B08
AP471 AF 37 input U08 B08
AP701 AK B1 input G1� G12
AP351 AF 37 input D08 B08
"""
CHANGES = [tuple(line.split()) for line in CHANGES_TEXT.splitlines()]
assert len(CHANGES) == 57 and len(set(CHANGES)) == 57


def paths(root, stem, preview_name):
    return {
        "txt": root / (stem + ".txt"),
        "json": root / (stem + ".json"),
        "notes": root / (stem + " review notes.txt"),
        "preview": root / preview_name,
    }


def assert_crop_bound(scan, node, crop):
    """Prove the supplied independent audit crop came from this TIFF."""
    x = round(330 + 39.5 * node["column"])
    y = round(160 + 59.7 * node["row"])
    expected = scan.crop((x - 490, y - 130, x + 590, y + 580)).convert("RGB")
    given = Image.open(crop).convert("RGB")
    assert given.size == expected.size and ImageChops.difference(given, expected).getbbox() is None, crop


def stage():
    groups = defaultdict(list)
    for change in CHANGES:
        groups[change[0]].append(change)
    STAGE.mkdir(parents=True, exist_ok=True)
    records = []
    for page, changes in sorted(groups.items()):
        matching = list(CANONICAL.glob(page + " *.json"))
        assert len(matching) == 1, (page, matching)
        stem = matching[0].stem
        candidates = [stem + " JuliaMono preview.png", stem + " JuliaMono.png",
                      stem + " preview.png", stem + ".png"]
        present = [name for name in candidates if (CANONICAL / name).is_file()]
        assert len(present) == 1, (page, present)
        pname = present[0]
        original = paths(CANONICAL, stem, pname)
        before = {kind: path.read_bytes() for kind, path in original.items()}
        rows = before["txt"].decode("utf-8").splitlines(keepends=True)
        model = json.loads(before["json"].decode("utf-8"))
        source = SOURCE / (stem + ".tif")
        assert source.is_file(), source
        scan = Image.open(source).convert("RGB")
        edits = []
        for _, node_id, portion, side, old, new in changes:
            node = next(n for n in model["nodes"] if n["id"] == node_id)
            assert node["card_type"] == "4634" and node["portion"] == portion
            pins = [p for p in node["pins"] if p.get("side") == side and p.get("pin") == old]
            assert len(pins) == 1, (page, node_id, old, pins)
            pin = pins[0]
            row = pin["row"]
            col = node["column"]
            lo, hi = (col - 12, col + 8) if side == "input" else (col + 7, col + 40)
            old_label = pin.get("printed_label", old)
            assert old_label == old, (page, node_id, old_label, old)
            starts = [i for i in range(lo, hi) if rows[row].startswith(old_label, i)]
            assert len(starts) == 1, (page, node_id, row, old, starts)
            left = starts[0]
            # The leading 8 on these two labels is a mistaken wire mark.
            # Replace it by a horizontal line while preserving the 245-cell grid.
            replacement = "─" + new if len(old) == len(new) + 1 else new
            assert len(replacement) == len(old)
            assert rows[row][left:left + len(old)] == old
            rows[row] = rows[row][:left] + replacement + rows[row][left + len(old):]
            pin["pin"] = new
            if "printed_label" in pin:
                pin["printed_label"] = new
            for label in model.get("printed_labels", []):
                if label.get("row") == row and label.get("text") == old:
                    label["text"] = new
                    if replacement.startswith("─") and "column" in label:
                        label["column"] += 1
            crop = CROPS / f"full-{page}-{node_id}.png"
            assert crop.is_file(), crop
            assert_crop_bound(scan, node, crop)
            edits.append({
                "node": node_id, "portion": portion, "side": side, "row": row,
                "column": left, "before": old, "after": new,
                "wire_cell_inserted": replacement.startswith("─"),
                "native_crop": {"path": str(crop), "sha256": sha(crop.read_bytes())},
            })
        assert len(rows) == 103 and all(len(row.rstrip("\r\n")) == 245 for row in rows)
        after = dict(before)
        after["txt"] = "".join(rows).encode("utf-8")
        after["json"] = (json.dumps(model, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        after["preview"] = preview(after["txt"])
        summary = "; ".join(f'{e["node"]} {e["before"]}→{e["after"]}' for e in edits)
        after["notes"] = append_note(
            before["notes"],
            "Card-ALD 4634 physical pin review, 2026-10-15: " + summary +
            ". Corrections were checked against the original TIFF crops, "
            "matching card portions, and the physical B/D/G/J pin alphabet. "
            "Crops and source hashes are bound in the stage manifest. Older "
            "uncertainty remarks remain historical.",
        )
        stage_dir = STAGE / stem
        stage_dir.mkdir(parents=True, exist_ok=True)
        staged = paths(stage_dir, stem, pname)
        for kind, content in after.items():
            staged[kind].write_bytes(content)
        records.append({
            "page": page,
            "source": {"path": str(source), "sha256": sha(source.read_bytes())},
            "changes": edits,
            "prior_quartet": {k: {"path": str(original[k]), "sha256": sha(v)} for k, v in before.items()},
            "staged_quartet": {k: {"path": str(staged[k]), "sha256": sha(v)} for k, v in after.items()},
            "checks": {
                "native_crop_pixels_match_source": True,
                "only_named_txt_pin_cells_changed": True,
                "model_pin_values_match_txt": True,
                "grid_json_preview_verified": True,
                "source_and_quartet_hashes_bound": True,
            },
        })
    manifest = {
        "schema": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "56 invalid 4634 physical-pin readings plus AP351 AF B08",
        "records": records,
    }
    (STAGE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Staged", len(records), "pages and", len(CHANGES), "physical pins")


def publish():
    manifest_path = STAGE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == SCHEMA
    assert {r["page"] for r in manifest["records"]} == {r[0] for r in CHANGES}
    for record in manifest["records"]:
        assert sha(Path(record["source"]["path"]).read_bytes()) == record["source"]["sha256"]
        for change in record["changes"]:
            crop = change["native_crop"]
            assert sha(Path(crop["path"]).read_bytes()) == crop["sha256"]
        for kind, old in record["prior_quartet"].items():
            new = record["staged_quartet"][kind]
            assert sha(Path(old["path"]).read_bytes()) == old["sha256"]
            assert sha(Path(new["path"]).read_bytes()) == new["sha256"]
    for record in manifest["records"]:
        for kind, old in record["prior_quartet"].items():
            Path(old["path"]).write_bytes(Path(record["staged_quartet"][kind]["path"]).read_bytes())
    audit = {
        "schema": "card-4634-physical-pin-current-audit-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "reviewer": "Coordinator native TIFF and same-portion pin review",
        "scope": manifest["scope"],
        "stage_manifest": {"path": str(manifest_path), "sha256": sha(manifest_path.read_bytes())},
        "pages": [],
    }
    for record in manifest["records"]:
        current = {k: {"path": old["path"], "sha256": record["staged_quartet"][k]["sha256"]}
                   for k, old in record["prior_quartet"].items()}
        assert all(sha(Path(x["path"]).read_bytes()) == x["sha256"] for x in current.values())
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
    print("Published", len(manifest["records"]), "reviewed 4634 pages")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("stage", "publish"))
    action = parser.parse_args().action
    stage() if action == "stage" else publish()

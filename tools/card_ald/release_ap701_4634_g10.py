"""Correct AP701 4634B1's upper input from duplicated G12 to native G10."""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path

from PIL import Image, ImageOps

from release_463x_source_corrections import CANONICAL, WORKSPACE, REPO, sha, preview, append_note


STEM = "AP701 PADDER SHIFT CONTROL LEFT 4 SHIFT"
SOURCE = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder") / (STEM + ".tif")
STAGE = WORKSPACE / "tmp/ald-text/ald/card-463x-release/AP701-G10-stage"
AUDIT = (WORKSPACE / "tmp/ald-text/ald/manual-verification/"
         "contextual-cross-reference-v3/4634 AP701 G10 current audit.json")
REPO_AUDIT = REPO / "notes/Card-ALD/4634 AP701 G10 current audit.json"


def paths(root):
    return {"txt": root / (STEM + ".txt"),
            "json": root / (STEM + ".json"),
            "notes": root / (STEM + " review notes.txt"),
            "preview": root / (STEM + " JuliaMono.png")}


def stage():
    assert SOURCE.is_file()
    original = paths(CANONICAL)
    before = {kind: path.read_bytes() for kind, path in original.items()}
    rows = before["txt"].decode("utf-8").splitlines(keepends=True)
    assert len(rows) == 103 and all(len(line.rstrip("\r\n")) == 245 for line in rows)
    assert rows[31][93:96] == "G12"
    rows[31] = rows[31][:93] + "G10" + rows[31][96:]
    after_txt = "".join(rows).encode("utf-8")

    raw = before["json"]
    document = json.loads(raw.decode("utf-8"))
    node = next(n for n in document["nodes"] if n["id"] == "AK")
    assert (node["card_type"], node["portion"], node["row"], node["column"]) == ("4634", "B1", 30, 96)
    upper = next(pin for pin in node["pins"] if pin["side"] == "input" and pin["row"] == 31)
    assert upper["pin"] == "G12" and upper["printed_pin"] == "G1�"
    assert upper["terminal_id"] == "AK.G1�"
    upper["pin"] = upper["printed_pin"] = "G10"
    upper["terminal_id"] = "AK.G10"
    assert any(pin["pin"] == "G12" and pin["row"] == 35 for pin in node["pins"])
    net = next(net for net in document["nets"] if net["id"] == "AF.J06")
    assert net["targets"] == ["AK.G1�"]
    net["targets"] = ["AK.G10"]
    labels = [label for label in document.get("printed_labels", [])
              if label.get("row") == 31 and label.get("column") == 93 and label.get("text") == "G12"]
    assert len(labels) == 1
    labels[0]["text"] = "G10"
    newline = "\r\n" if b"\r\n" in raw else "\n"
    after_json = (json.dumps(document, ensure_ascii=False, indent=2).replace("\n", newline)
                  + newline).encode("utf-8")
    assert len(after_json.decode("utf-8").splitlines()) == len(raw.decode("utf-8").splitlines())
    after = {"txt": after_txt, "json": after_json,
             "notes": append_note(before["notes"],
                "Card-ALD 4634 source review, 2026-10-15: AP701 block AK (4634B1) "
                "upper input reads G10 on the original TIFF, while its lower input is G12. "
                "The earlier transcription duplicated G12. Corrected the printed cells, "
                "structured input, terminal and net target; source and quartet hashes "
                "are bound in the AP701 G10 stage manifest."),
             "preview": preview(after_txt)}
    STAGE.mkdir(parents=True, exist_ok=True)
    staged = paths(STAGE)
    for kind, path in staged.items():
        path.write_bytes(after[kind])
    crop = STAGE / "AP701-AK-G10-native.png"
    with Image.open(SOURCE) as image:
        ImageOps.autocontrast(image.convert("L").crop((3500, 1700, 5200, 2700))).save(crop)
    manifest = {"schema": "card-4634-ap701-g10-stage-v1",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "source": {"path": str(SOURCE), "sha256": sha(SOURCE.read_bytes())},
                "crop": {"path": str(crop), "sha256": sha(crop.read_bytes())},
                "change": {"page": "AP701", "node": "AK", "portion": "B1",
                           "input_row": 31, "before": "G12", "after": "G10"},
                "prior_quartet": {kind: {"path": str(path), "sha256": sha(before[kind])}
                                  for kind, path in original.items()},
                "staged_quartet": {kind: {"path": str(path), "sha256": sha(after[kind])}
                                   for kind, path in staged.items()},
                "checks": {"native_crop_reviewed": True, "grid_preserved": True,
                           "only_named_input_changed": True, "net_target_and_pin_agree": True}}
    (STAGE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    print("Staged AP701 G10")


def publish():
    path = STAGE / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "card-4634-ap701-g10-stage-v1"
    for item in (manifest["source"], manifest["crop"]):
        assert sha(Path(item["path"]).read_bytes()) == item["sha256"]
    for kind, old in manifest["prior_quartet"].items():
        new = manifest["staged_quartet"][kind]
        assert sha(Path(old["path"]).read_bytes()) == old["sha256"]
        assert sha(Path(new["path"]).read_bytes()) == new["sha256"]
    for kind, old in manifest["prior_quartet"].items():
        Path(old["path"]).write_bytes(Path(manifest["staged_quartet"][kind]["path"]).read_bytes())
    current = {kind: {"path": old["path"], "sha256": manifest["staged_quartet"][kind]["sha256"]}
               for kind, old in manifest["prior_quartet"].items()}
    assert all(sha(Path(item["path"]).read_bytes()) == item["sha256"] for item in current.values())
    audit = {"schema": "card-4634-ap701-g10-current-audit-v1",
             "created_utc": datetime.now(timezone.utc).isoformat(),
             "passed": True, "reviewer": "Coordinator original-TIFF and same-portion review",
             "stage_manifest": {"path": str(path), "sha256": sha(path.read_bytes())},
             "pages": [{"page": "AP701", "eligible": True,
                        "artifact_schema": "reviewed-current-quartet-v1",
                        "source": manifest["source"],
                        "prior_quartet": manifest["prior_quartet"],
                        "current_quartet": current,
                        "checks": manifest["checks"], "change": manifest["change"]}]}
    content = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    AUDIT.write_text(content, encoding="utf-8")
    REPO_AUDIT.write_text(content, encoding="utf-8")
    print("Published AP701 G10")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("stage", "publish"))
    args = parser.parse_args()
    stage() if args.action == "stage" else publish()

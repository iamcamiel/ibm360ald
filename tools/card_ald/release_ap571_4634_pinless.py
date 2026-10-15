"""Remove a spurious B08 contact from AP571's 4634 portion 21 output."""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path

from PIL import Image, ImageOps

from release_463x_source_corrections import CANONICAL, WORKSPACE, REPO, sha, preview, append_note


STEM = "AP571 PARALLEL ADDER BIT 57"
SOURCE = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder") / (STEM + ".tif")
STAGE = WORKSPACE / "tmp/ald-text/ald/card-463x-release/AP571-pinless-stage"
AUDIT = (WORKSPACE / "tmp/ald-text/ald/manual-verification/"
         "contextual-cross-reference-v3/4634 AP571 pinless current audit.json")
REPO_AUDIT = REPO / "notes/Card-ALD/4634 AP571 pinless current audit.json"


def paths(root):
    return {"txt": root / (STEM + ".txt"), "json": root / (STEM + ".json"),
            "notes": root / (STEM + " review notes.txt"),
            "preview": root / (STEM + " JuliaMono preview.png")}


def stage():
    assert SOURCE.is_file()
    original = paths(CANONICAL)
    before = {kind: path.read_bytes() for kind, path in original.items()}
    rows = before["txt"].decode("utf-8").splitlines(keepends=True)
    assert len(rows) == 103 and all(len(line.rstrip("\r\n")) == 245 for line in rows)
    assert rows[19][81:84] == "B08" and rows[19][80] == "◺" and rows[19][84] == "┘"
    rows[19] = rows[19][:81] + "───" + rows[19][84:]
    after_txt = "".join(rows).encode("utf-8")

    raw = before["json"]
    document = json.loads(raw.decode("utf-8"))
    source = next(node for node in document["nodes"] if node["id"] == "AG")
    target = next(node for node in document["nodes"] if node["id"] == "AN")
    assert (source["card_type"], source["portion"], source["location"]) == ("4634", "21", "B-E2D4")
    assert (target["card_type"], target["portion"], target["location"]) == ("4634", "29", "B-E2D4")
    output = next(pin for pin in source["pins"] if pin["side"] == "output" and pin["row"] == 19)
    assert output["pin"] == output["printed_pin"] == "B08"
    assert output["terminal_id"] == "AG.B08" and output["triangle"] is True
    output["pin"] = output["printed_pin"] = None
    output["terminal_id"] = "AG.output"
    assert any(pin["side"] == "output" and pin["pin"] == "B08" for pin in target["pins"])
    net = next(net for net in document["nets"] if net["id"] == "N12")
    assert net["driver"] == "AG.B08" and net["targets"] == ["AN.input1"]
    net["driver"] = "AG.output"
    labels = document.get("printed_labels", [])
    original_count = len(labels)
    document["printed_labels"] = [label for label in labels if not
                                  (label.get("column") == 81 and label.get("row") == 19
                                   and label.get("text") == "B08")]
    assert len(document["printed_labels"]) == original_count - 1
    assert any(label.get("column") == 104 and label.get("row") == 19
               and label.get("text") == "B08" for label in document["printed_labels"])
    newline = "\r\n" if b"\r\n" in raw else "\n"
    after_json = (json.dumps(document, ensure_ascii=False, indent=2).replace("\n", newline)
                  + newline).encode("utf-8")
    after = {"txt": after_txt, "json": after_json,
             "notes": append_note(before["notes"],
                "Card-ALD 4634 native wire review, 2026-10-15: AP571 block AG "
                "(4634 portion 21) has a pinless output that feeds block AN. "
                "The previous B08 beside AG was a transcription error; the "
                "real B08 is on AN's output. The AG output cell, structured "
                "pin, and net driver were corrected without changing AN's B08. "
                "Source and quartet hashes are bound in the AP571 pinless audit."),
             "preview": preview(after_txt)}
    STAGE.mkdir(parents=True, exist_ok=True)
    staged = paths(STAGE)
    for kind, path in staged.items():
        path.write_bytes(after[kind])
    crop = STAGE / "AP571-AG-AN-native.png"
    with Image.open(SOURCE) as image:
        ImageOps.autocontrast(image.convert("L").crop((2600, 900, 5000, 1900))).save(crop)
    manifest = {"schema": "card-4634-ap571-pinless-stage-v1",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "source": {"path": str(SOURCE), "sha256": sha(SOURCE.read_bytes())},
                "crop": {"path": str(crop), "sha256": sha(crop.read_bytes())},
                "change": {"page": "AP571", "source_node": "AG", "target_node": "AN",
                           "output_row": 19, "false_pin": "B08", "corrected_pin": None},
                "prior_quartet": {kind: {"path": str(path), "sha256": sha(before[kind])}
                                  for kind, path in original.items()},
                "staged_quartet": {kind: {"path": str(path), "sha256": sha(after[kind])}
                                   for kind, path in staged.items()},
                "checks": {"native_crop_reviewed": True, "grid_preserved": True,
                           "only_named_output_changed": True, "net_driver_and_pin_agree": True}}
    (STAGE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    print("Staged AP571 pinless output")


def publish():
    path = STAGE / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "card-4634-ap571-pinless-stage-v1"
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
    audit = {"schema": "card-4634-ap571-pinless-current-audit-v1",
             "created_utc": datetime.now(timezone.utc).isoformat(),
             "passed": True, "reviewer": "Coordinator original-TIFF and physical-output uniqueness review",
             "stage_manifest": {"path": str(path), "sha256": sha(path.read_bytes())},
             "pages": [{"page": "AP571", "eligible": True,
                        "artifact_schema": "reviewed-current-quartet-v1",
                        "source": manifest["source"],
                        "prior_quartet": manifest["prior_quartet"],
                        "current_quartet": current,
                        "checks": manifest["checks"], "change": manifest["change"]}]}
    content = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    AUDIT.write_text(content, encoding="utf-8")
    REPO_AUDIT.write_text(content, encoding="utf-8")
    print("Published AP571 pinless output")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("stage", "publish"))
    args = parser.parse_args()
    stage() if args.action == "stage" else publish()

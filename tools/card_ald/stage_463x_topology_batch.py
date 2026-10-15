"""Stage four source-bound 4633/4634 topology repairs without publishing.

The AP491 net repair is staged by stage_ap491_topology.  AP071 and AP551
pin readings were confirmed on the physical sheets by the user; AP111 was
independently read from its native TIFF.  This tool writes only temporary
candidate quartets and manifests, never canonical owner files.
"""

from datetime import datetime, timezone
import json
from pathlib import Path

from PIL import Image, ImageOps

from release_463x_source_corrections import (
    CANONICAL, WORKSPACE, append_note, preview, sha,
)
from stage_ap491_topology import STAGE as AP491_STAGE, stage as stage_ap491


BASE = WORKSPACE / "tmp/ald-text/ald/card-463x-release"
STAGE = BASE / "4633-a7-pin-stage"
BATCH = BASE / "463x-topology-stage"
SOURCE_DIR = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder")
READINGS = {
    "AP071": {"stem": "AP071 PARALLEL ADDER BIT 07", "old": "B14",
              "cells": {118: ("4", "3")}, "basis": "user confirmed from physical sheet"},
    "AP111": {"stem": "AP111 PARALLEL ADDER BIT 11", "old": "B11",
              "cells": {118: ("1", "3")}, "basis": "original TIFF and independent source review"},
    "AP551": {"stem": "AP551 PARALLEL ADDER BIT 55", "old": "B9",
              "cells": {116: ("─", "B"), 117: ("B", "1"), 118: ("9", "3")},
              "basis": "user confirmed from physical sheet"},
}


def stage_pin_pages():
    STAGE.mkdir(parents=True, exist_ok=True)
    records = []
    for page, spec in READINGS.items():
        stem = spec["stem"]
        paths = {
            "txt": CANONICAL / (stem + ".txt"),
            "json": CANONICAL / (stem + ".json"),
            "notes": CANONICAL / (stem + " review notes.txt"),
            "preview": (CANONICAL / (stem + " JuliaMono preview.png")
                        if (CANONICAL / (stem + " JuliaMono preview.png")).is_file()
                        else CANONICAL / (stem + ".png")),
        }
        before = {kind: path.read_bytes() for kind, path in paths.items()}
        assert sha(preview(before["txt"])) == sha(before["preview"]), page
        original = before["txt"].decode("utf-8")
        assert original.count("\r\n") == 103, page
        lines = original.splitlines()
        assert len(lines) == 103 and all(len(line) == 245 for line in lines), page
        assert lines[31][119] == "◺" and lines[31][120:122] == "OR", page
        for x, (old, new) in spec["cells"].items():
            assert lines[31][x] == old, (page, x, old, lines[31][x])
            lines[31] = lines[31][:x] + new + lines[31][x + 1:]
        assert lines[31][116:119] == "B13", page
        after_txt = ("\r\n".join(lines) + "\r\n").encode("utf-8")

        document = json.loads(before["json"].decode("utf-8"))
        json_newline = "\r\n" if b"\r\n" in before["json"] else "\n"
        def encode_json(value):
            return (json.dumps(value, ensure_ascii=False, indent=2).replace("\n", json_newline)
                    + json_newline).encode("utf-8")
        assert encode_json(document) == before["json"], page
        node = next(n for n in document["nodes"] if n["id"] == "AT")
        assert (node["card_type"], str(node["portion"]), node["row"], node["column"]) == ("4633", "A7", 30, 119), page
        pin = next(p for p in node["pins"] if p["side"] == "input" and p["row"] == 31)
        assert pin["pin"] == spec["old"], page
        pin["pin"] = "B13"
        if "printed_pin" in pin:
            assert pin["printed_pin"] == spec["old"], page
            pin["printed_pin"] = "B13"
        if "terminal_id" in pin:
            assert pin["terminal_id"] == "AT." + spec["old"], page
            pin["terminal_id"] = "AT.B13"
        changed_targets = 0
        for net in document["nets"]:
            targets = net.get("targets", [])
            if "AT." + spec["old"] in targets:
                net["targets"] = ["AT.B13" if target == "AT." + spec["old"] else target
                                  for target in targets]
                changed_targets += 1
        assert changed_targets == 1, (page, changed_targets)
        after_json = encode_json(document)
        basis = spec["basis"]
        note = (f"Card-ALD source-bound pin review, 2026-10-15: {page} block AT "
                f"(4633A7) upper-left input at row 31, columns 116-118, reads B13 "
                f"rather than {spec['old']} ({basis}). The input pin and its existing "
                "net target were relabeled without changing net ownership or adding "
                "a wire. The four-file candidate is staged only; current source and "
                "quartet hashes are in the 463x topology stage manifest.")
        after = {"txt": after_txt, "json": after_json,
                 "notes": append_note(before["notes"], note),
                 "preview": preview(after_txt)}
        folder = STAGE / stem
        folder.mkdir(exist_ok=True)
        for kind, path in paths.items():
            (folder / path.name).write_bytes(after[kind])
        source = SOURCE_DIR / (stem + ".tif")
        assert source.is_file(), source
        crop_path = folder / (page + "-A7-native-crop.png")
        with Image.open(source) as image:
            ImageOps.autocontrast(image.convert("L").crop((4750, 500, 7650, 2950))).save(crop_path)
        assert all(sha(path.read_bytes()) == sha(before[kind]) for kind, path in paths.items()), page
        records.append({
            "page": page,
            "reading": {"old": spec["old"], "new": "B13", "basis": basis,
                        "text_row": 31, "text_columns": [116, 117, 118],
                        "json_node": "AT", "json_pin_row": 31,
                        "existing_net_target_relabelled": True},
            "source": {"path": str(source), "sha256": sha(source.read_bytes()),
                       "crop": str(crop_path)},
            "prior_quartet": {kind: {"path": str(paths[kind]), "sha256": sha(data)}
                              for kind, data in before.items()},
            "staged_quartet": {kind: {"path": str(folder / paths[kind].name),
                                     "sha256": sha(data)} for kind, data in after.items()},
            "checks": {"current_preview_reproduced": True, "utf8_grid_245x103": True,
                       "json_pin_and_target_agree": True,
                       "canonical_unchanged": True},
        })
    manifest = {"schema": "card-4633-a7-pin-stage-v1",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "status": "staged only; canonical pages unchanged", "records": records}
    (STAGE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return STAGE / "manifest.json"


def stage():
    stage_ap491()
    pin_manifest = stage_pin_pages()
    BATCH.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "card-463x-topology-batch-stage-v1",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "status": "staged only; no canonical or published repository page changed",
                "pages": ["AP071", "AP111", "AP491", "AP551"],
                "submanifests": [
                    {"path": str(AP491_STAGE / "manifest.json"),
                     "sha256": sha((AP491_STAGE / "manifest.json").read_bytes())},
                    {"path": str(pin_manifest), "sha256": sha(pin_manifest.read_bytes())},
                ],
                "AP511": "No correction: the current multi-driver net already records AV.B07 joined with AQ.OUT40 and targeting BC.B07/AU.B07.",
                "AP391": "No correction: original scan routes portion 46 to another gate; portion 54 uses other inputs.",
               }
    (BATCH / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(BATCH / "manifest.json")


if __name__ == "__main__":
    stage()

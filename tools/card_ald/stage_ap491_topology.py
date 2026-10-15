"""Stage, without publishing, the native-verified AP491 4634 topology repair.

The TIFF shows 463439's pinless output at grid row 47 feeding the upper
input of 463452 at row 52.  463440 independently feeds its middle input at
row 54.  The current transcription instead routes 463440 to row 52 and omits
463439's output altogether.
"""

from datetime import datetime, timezone
import json
from pathlib import Path

from PIL import Image, ImageOps

from release_463x_source_corrections import (
    CANONICAL, WORKSPACE, append_note, preview, sha,
)


STEM = "AP491 PARALLEL ADDER BIT 49"
SOURCE = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder") / (STEM + ".tif")
STAGE = WORKSPACE / "tmp/ald-text/ald/card-463x-release/AP491-topology-stage"
FILES = {
    "txt": CANONICAL / (STEM + ".txt"),
    "json": CANONICAL / (STEM + ".json"),
    "notes": CANONICAL / (STEM + " review notes.txt"),
    "preview": CANONICAL / (STEM + " JuliaMono preview.png"),
}


def set_cell(rows, y, x, old, new):
    row = rows[y]
    assert row[x] == old, (y, x, old, row[x])
    rows[y] = row[:x] + new + row[x + 1:]


def stage():
    STAGE.mkdir(parents=True, exist_ok=True)
    before = {kind: path.read_bytes() for kind, path in FILES.items()}
    assert sha(preview(before["txt"])) == sha(before["preview"]), "Current preview is not the accepted text rendering"
    original = before["txt"].decode("utf-8")
    assert original.count("\r\n") == 103
    rows = original.splitlines()
    assert len(rows) == 103 and all(len(row) == 245 for row in rows)

    # 463439 (AC) output: row 47, box edge 57, line 58-60, corner 61.
    for x in range(58, 61):
        set_cell(rows, 47, x, " ", "─")
    set_cell(rows, 47, 61, " ", "┐")
    for y in range(48, 52):
        set_cell(rows, y, 61, " ", "│")
    # Upper 463452 (AL) input, row 52, keeps its horizontal line to box edge 73.
    set_cell(rows, 52, 61, "┌", "└")
    # 463440 (AD) actually runs straight into AL's middle input on row 54.
    set_cell(rows, 53, 61, "│", " ")
    set_cell(rows, 54, 61, "┘", "─")
    for x in range(62, 73):
        set_cell(rows, 54, x, " ", "─")
    assert all(len(row) == 245 for row in rows)
    after_txt = ("\r\n".join(rows) + "\r\n").encode("utf-8")

    document = json.loads(before["json"].decode("utf-8"))
    assert (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8") == before["json"]
    nodes = {node["id"]: node for node in document["nodes"]}
    ac, ad, al = (nodes[key] for key in ("AC", "AD", "AL"))
    assert (ac["card_type"], ac["portion"], ac["row"], ac["column"]) == ("4634", "39", 44, 50)
    assert (ad["card_type"], ad["portion"]) == ("4634", "40")
    assert (al["card_type"], al["portion"], al["row"], al["column"]) == ("4634", "52", 51, 73)
    assert not [pin for pin in ac["pins"] if pin["side"] == "output"]
    assert sorted(pin["row"] for pin in al["pins"] if pin["side"] == "input") == [52, 56]
    ac["pins"].append({"pin": None, "printed_label": "", "row": 47,
                       "side": "output", "triangle": False,
                       "source_reviewed": True, "column": 58})
    al["pins"].append({"pin": None, "printed_label": "", "row": 54,
                       "side": "input", "triangle": False,
                       "source_reviewed": True, "column": 72})
    ad_net = next(net for net in document["nets"] if net["id"] == "AD")
    assert ad_net["driver"] == "AD.output" and ad_net["targets"] == ["AL.input52"]
    ad_net["targets"] = ["AL.input54"]
    assert all(net["id"] != "AC" for net in document["nets"])
    document["nets"].insert(document["nets"].index(ad_net), {
        "id": "AC", "driver": "AC.output", "targets": ["AL.input52"],
        "external": None, "source_reviewed": True,
    })
    after_json = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    assert any(net["driver"] == "AC.output" and net["targets"] == ["AL.input52"]
               for net in document["nets"])

    explanation = (
        "Card-ALD native topology review, 2026-10-15: AP491 block AC "
        "(463439, B-E2F3) has a pinless output at row 47. Its wire turns "
        "at column 61 and enters block AL (463452) at row 52. Block AD "
        "(463440) runs straight into AL at row 54; AL's third input remains "
        "at row 56. Original TIFF crop and quartet hashes are recorded in "
        "the AP491 topology stage manifest. This stage has not been published."
    )
    after = {
        "txt": after_txt,
        "json": after_json,
        "notes": append_note(before["notes"], explanation),
        "preview": preview(after_txt),
    }
    for kind, path in FILES.items():
        (STAGE / path.name).write_bytes(after[kind])
    with Image.open(SOURCE) as scan:
        crop = ImageOps.autocontrast(scan.convert("L").crop((2350, 2800, 3900, 3700)))
        crop.save(STAGE / "AP491-39-52-native-crop.png")
    manifest = {
        "schema": "card-4634-ap491-topology-stage-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "staged only; no canonical owner or repository page changed",
        "source": {"path": str(SOURCE), "sha256": sha(SOURCE.read_bytes()),
                   "crop": str(STAGE / "AP491-39-52-native-crop.png")},
        "grid": {"source_box": "AC/463439", "source_output": [47, 58],
                 "route_turn": [47, 61], "target_box": "AL/463452",
                 "target_upper_input": [52, 72], "target_middle_input": [54, 72]},
        "prior_quartet": {kind: {"path": str(FILES[kind]), "sha256": sha(data)}
                          for kind, data in before.items()},
        "staged_quartet": {kind: {"path": str(STAGE / FILES[kind].name), "sha256": sha(data)}
                           for kind, data in after.items()},
        "checks": {"current_preview_reproduced": True, "utf8_grid_245x103": True,
                   "json_pin_rows_and_nets_checked": True,
                   "staged_preview_exactly_renders_staged_txt": sha(preview(after_txt)) == sha(after["preview"]),
                   "canonical_unchanged": all(sha(path.read_bytes()) == sha(before[kind])
                                              for kind, path in FILES.items())},
    }
    (STAGE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(STAGE / "manifest.json")


if __name__ == "__main__":
    stage()

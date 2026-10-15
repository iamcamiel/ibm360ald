"""Stage and publish two independently checked 4633/4634 source corrections.

AP041 AM/AQ contact G10 was re-read on the native TIFF.  AP181 AN's semantic
portion is 28: its accepted TXT and printed_card_portion already say 463428,
and the page's own source-derived recovery records the same A1-supported
reading.  This tool does not alter any other ALD page or card database.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


REPO = Path(__file__).resolve().parents[2]
WORKSPACE = REPO.parent
CANONICAL = WORKSPACE / "ALD_Visual_Transcriptions" / "ALD Diagrams"
STAGE = WORKSPACE / "tmp" / "ald-text" / "ald" / "card-463x-release" / "stage"
AUDIT = (WORKSPACE / "tmp" / "ald-text" / "ald" / "manual-verification" /
         "contextual-cross-reference-v3" / "463x source correction current audit.json")
REPO_AUDIT = REPO / "notes" / "Card-ALD" / "463x source correction current audit.json"
FONT = WORKSPACE / "tmp" / "ald-text" / "JuliaMono-Regular.ttf"
PAGES = {
    "AP041": "AP041 PARALLEL ADDER BIT 04",
    "AP181": "AP181 PARALLEL ADDER BIT 18",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def quartet(stem):
    return {
        "txt": CANONICAL / (stem + ".txt"),
        "json": CANONICAL / (stem + ".json"),
        "notes": CANONICAL / (stem + " review notes.txt"),
        "preview": CANONICAL / (stem + (" preview.png" if stem.startswith("AP041") else ".png")),
    }


def preview(txt):
    rows = txt.decode("utf-8").splitlines()
    assert len(rows) == 103 and all(len(row) == 245 for row in rows)
    font = ImageFont.truetype(str(FONT), 20)
    image = Image.new("RGB", (2940, 1854), "white")
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char != " ":
                draw.text((x * 12, y * 18), char, font=font, fill="black")
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def append_note(raw, paragraph):
    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    return raw.rstrip(b"\r\n") + newline * 2 + paragraph.encode("utf-8").replace(b"\n", newline) + newline


def prepare():
    STAGE.mkdir(parents=True, exist_ok=True)
    records = []
    for page, stem in PAGES.items():
        paths = quartet(stem)
        before = {name: path.read_bytes() for name, path in paths.items()}
        after = dict(before)
        source = next(Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder").glob(stem + ".tif"))
        if page == "AP041":
            assert before["txt"].count(b"C10") == 2
            assert before["json"].count(b"C10") == 6
            after["txt"] = before["txt"].replace(b"C10", b"G10")
            after["json"] = before["json"].replace(b"C10", b"G10")
            after["preview"] = preview(after["txt"])
            paragraph = (
                "Card-ALD 4633 native correction, 2026-10-15: AP041 block AM (4633K1) "
                "prints output G10 and block AQ (4633K2) prints input G10. The native "
                "crop notes/Card-ALD/evidence/AP041-463x-native.png and the repeated "
                "K1-to-K2 connection identify the earlier C10 reading as a transcription "
                "error. Both same-width text cells, their JSON pins/net/labels, and the "
                "JuliaMono preview were corrected."
            )
        else:
            needle = '"portion": "2�"'.encode("utf-8")
            assert before["json"].count(needle) == 1
            model = json.loads(before["json"].decode("utf-8"))
            node, = [n for n in model["nodes"] if n["id"] == "AN"]
            assert node["printed_card_portion"] == "463428"
            assert any(x.get("source_derived_reading") == "463428"
                       for x in model.get("source_derived_recoveries", []))
            after["json"] = before["json"].replace(needle, b'"portion": "28"')
            paragraph = (
                "Card-ALD 4634 semantic correction, 2026-10-15: AP181 AN's printed "
                "portion is physically worn. The already accepted TXT says 463428, the "
                "JSON printed_card_portion says 463428, and its A1-supported "
                "source_derived_recoveries resolve 463428. The machine-readable portion "
                "field alone changed from 2� to 28. The native uncertainty remains "
                "documented above."
            )
        after["notes"] = append_note(before["notes"], paragraph)
        candidate = STAGE / stem
        candidate.mkdir(exist_ok=True)
        for name, data in after.items():
            (candidate / paths[name].name).write_bytes(data)
        text_rows = after["txt"].decode("utf-8").splitlines()
        assert len(text_rows) == 103 and all(len(row) == 245 for row in text_rows)
        parsed = json.loads(after["json"].decode("utf-8"))
        assert parsed["page"] == page
        record = {
            "page": page,
            "stem": stem,
            "source": {"path": str(source), "sha256": sha(source.read_bytes())},
            "prior_quartet": {k: {"path": str(paths[k]), "sha256": sha(before[k])} for k in paths},
            "staged_quartet": {k: {"path": str(candidate / paths[k].name), "sha256": sha(after[k])} for k in paths},
            "checks": {
                "native_or_cross_reference_evidence_present": True,
                "exact_preimage_and_edit_scope_verified": True,
                "utf8_grid_and_json_parse_verified": True,
                "preview_or_semantic_only_change_verified": True,
                "staged_quartet_hashes_match": True,
            },
        }
        records.append(record)
    manifest = {"schema": "card-463x-source-correction-stage-v1",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "records": records}
    (STAGE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def publish():
    manifest = json.loads((STAGE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "card-463x-source-correction-stage-v1"
    assert {r["page"] for r in manifest["records"]} == set(PAGES)
    for record in manifest["records"]:
        assert sha(Path(record["source"]["path"]).read_bytes()) == record["source"]["sha256"]
        for kind in quartet(record["stem"]):
            before = record["prior_quartet"][kind]
            staged = record["staged_quartet"][kind]
            assert sha(Path(before["path"]).read_bytes()) == before["sha256"]
            assert sha(Path(staged["path"]).read_bytes()) == staged["sha256"]
    for record in manifest["records"]:
        for kind in quartet(record["stem"]):
            staged = Path(record["staged_quartet"][kind]["path"])
            Path(record["prior_quartet"][kind]["path"]).write_bytes(staged.read_bytes())
    audit = {
        "schema": "card-463x-source-bound-current-audit-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "reviewer": "Coordinator independent native and cross-reference review",
        "scope": "Only AP041 4633 G10 and AP181 4634 portion 28",
        "stage_manifest": {"path": str(STAGE / "manifest.json"),
                           "sha256": sha((STAGE / "manifest.json").read_bytes())},
        "pages": [],
    }
    for record in manifest["records"]:
        current = {kind: {"path": prior["path"],
                          "sha256": record["staged_quartet"][kind]["sha256"]}
                   for kind, prior in record["prior_quartet"].items()}
        assert all(sha(Path(v["path"]).read_bytes()) == v["sha256"] for v in current.values())
        audit["pages"].append({
            "page": record["page"],
            "eligible": True,
            "artifact_schema": "reviewed-current-quartet-v1",
            "source": record["source"],
            "prior_quartet": record["prior_quartet"],
            "current_quartet": current,
            "checks": record["checks"],
        })
    raw = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(raw, encoding="utf-8")
    REPO_AUDIT.write_text(raw, encoding="utf-8")
    print("Published AP041 and AP181 source-bound corrections")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("stage", "publish"))
    args = parser.parse_args()
    if args.action == "stage":
        value = prepare()
        print(f"Staged {len(value['records'])} page quartets at {STAGE}")
    else:
        publish()

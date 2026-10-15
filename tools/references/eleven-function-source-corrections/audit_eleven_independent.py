"""Independent, fail-closed review of the private eleven-page function stage.

This reads the original scans and current accepted files; it writes only its own
private audit receipt. It never publishes the staged files.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont


ROOT = Path("D:/Github/IBM360")
HERE = Path(__file__).resolve().parent
CANONICAL = ROOT / "ALD_Visual_Transcriptions"
REPO = ROOT / "ibm360ald"
TIFFS = Path("D:/Reference Materials/IBM 360/IBM_360_ALD")
STAGE = HERE / "eleven-page-private-stage"
MANIFEST = STAGE / "Eleven native and human function correction manifest.json"
NATIVE = HERE / "V13 seven source-bound function correction candidates.json"
HUMAN = HERE / "V13 four direct-human function corrections and DT001 comparison.json"
AUDIT = HERE / "Independent eleven native and human function corrections acceptance.json"
FONT = ROOT / "tmp/ald-text/JuliaMono-Regular.ttf"
MANIFEST_SHA = "9bdeb975f0a457bdbd98e37d6bb162bba754f12074dc820d09b858be8f6c028f"
NATIVE_SHA = "7f12522b6e83348a529646ff01c5f683a633b59c2f53af35e008c46c0ba42d52"
HUMAN_SHA = "f7ac879f867147fd9553587e8ca99db293c5a3f3eb8ea00813cd1f2a4f41014f"
HISTORY = "source_eleven_function_corrections_v1"

# Frozen independently from the two authority records and the original scans.
EXPECTED = {
    "AP737": ("325", "native", (31, 97, "R", "A"), [("/nodes/9/function", "R", "A")], "0143A1"),
    "AP181": ("233", "native", (52, 143, "R", "A"), [("/nodes/19/function", "R", "A")], "419119"),
    "RQ683": ("1893", "native", (38, 51, "OR", "AR"), [("/nodes/6/function", "OR", "AR")], "0494B1"),
    "KU601": ("1108", "native", (10, 51, "OR", "AR"), [("/nodes/1/function", "OR", "AR")], "0514B1"),
    "RQ781": ("1901", "native", (3, 51, "OR", "AR"), [("/nodes/0/function", "OR", "AR")], "3311A4"),
    "MC371": ("1424", "native", (66, 51, "OR", "AR"), [("/nodes/15/function", "OR", "AR")], "4060H1"),
    "AP441": ("274", "native", (17, 97, "A ", "✲A"), [("/nodes/12/function", "A", "✲A")], "463430"),
    "AP531": ("289", "direct-human", (17, 97, "✲O", "✲A"), [("/nodes/12/function", "✲O", "✲A")], "463429"),
    "XM181": ("2185", "direct-human", (59, 120, "F", "A"), [("/nodes/11/function", "F", "A")], "0479A1"),
    "AS201": ("391", "direct-human", (38, 74, "TC", "TD"), [("/nodes/16/function", "TC", "TD")], "3360E1"),
    "AP313": ("252", "direct-human", (45, 190, "N", "A"),
              [("/nodes/18/function", "N", "A"),
               ("/nodes/18/function_layout/semantic_function", "N", "A")], "8008AN"),
}


class AuditError(RuntimeError):
    pass


checks = 0


def ck(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        raise AuditError(message)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binding(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def bound(item: dict) -> Path:
    path = Path(item["path"]).resolve()
    ck(path.is_file() and sha(path) == item["sha256"], "Missing/changed binding: " + str(path))
    return path


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def pointer(model: dict, key: str):
    cursor = model
    parts = key.strip("/").split("/")
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    last = int(parts[-1]) if isinstance(cursor, list) else parts[-1]
    return cursor, last


def render(lines: list[str], config: dict) -> Image.Image:
    image = Image.new("RGB", tuple(config["size"]), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT), config["font_size"])
    kwargs = {"anchor": config["anchor"]} if config.get("anchor") else {}
    for row, line in enumerate(lines):
        draw.text((config["x"], config["y"] + row * config["row_height"]),
                  line, font=font, fill="black", **kwargs)
    return image


def verify_exact_text(before: bytes, after: bytes, edit: dict):
    a = before.decode("utf-8").splitlines(keepends=True)
    z = after.decode("utf-8").splitlines(keepends=True)
    ck(len(a) == len(z) == 103 and all(len(row.rstrip("\r\n")) <= 245 for row in a + z),
       "Text grid dimensions changed")
    row, column = edit["row"], edit["column"]
    ck(a[row][column:column + len(edit["before"])] == edit["before"],
       "Expected predecessor text span missing")
    expected = a[:]
    expected[row] = a[row][:column] + edit["after"] + a[row][column + len(edit["before"]):]
    ck("".join(expected).encode("utf-8") == after, "Unrelated text byte/line/spacing edit")
    ck(all(len(x.rstrip("\r\n")) == len(y.rstrip("\r\n")) for x, y in zip(a, z)),
       "Text grid columns shifted")


def check_no_change(manifest: dict, human: dict) -> dict:
    no_change = manifest["confirmed_no_change"]
    ck(no_change == human["confirmed_no_change"], "DT001 no-change record differs")
    ck(no_change["page"] == "DT001" and no_change["current_function"] == "A" and
       no_change["output_triangle_pin"] == "D02" and no_change["status"] == "no function edit",
       "DT001 no-change identity differs")
    ck(not (STAGE / "DT001").exists(), "DT001 unexpectedly staged")
    scan = bound(no_change["source_tiff"])
    crop = bound(no_change["source_crop"])
    broad = bound(no_change["broad_context_crop"])
    ck(scan.is_relative_to(TIFFS.resolve()) and crop.is_file(), "DT001 source location invalid")
    with Image.open(scan) as original, Image.open(broad) as context:
        expect = original.convert("RGB").crop(tuple(no_change["broad_context_source_pixel_bounds"]))
        ck(ImageChops.difference(expect, context.convert("RGB")).getbbox() is None,
           "DT001 broad crop not exact original TIFF pixels")
    for item in no_change["accepted_canonical_quartet"].values():
        ck(bound(item).is_relative_to(CANONICAL.resolve()), "DT001 current canonical binding invalid")
    ck(bound(no_change["accepted_text"]).is_relative_to(REPO.resolve()) and
       bound(no_change["accepted_model"]).is_relative_to(REPO.resolve()),
       "DT001 current repository binding invalid")
    ck(read(Path(no_change["accepted_model"]["path"]))["nodes"][13]["function"] == "A",
       "DT001 model function changed")
    return {"page": "DT001", "status": "confirmed no change", "source": no_change["source_tiff"],
            "current_text_sha256": no_change["accepted_text"]["sha256"],
            "current_model_sha256": no_change["accepted_model"]["sha256"]}


def run() -> dict:
    ck(sha(MANIFEST) == MANIFEST_SHA, "Stage manifest changed")
    ck(sha(NATIVE) == NATIVE_SHA and sha(HUMAN) == HUMAN_SHA, "Authority record changed")
    ck(FONT.is_file(), "JuliaMono font absent")
    manifest, native, human = read(MANIFEST), read(NATIVE), read(HUMAN)
    ck(manifest["schema"] == "source-native-and-human-eleven-function-private-stage-v1" and
       manifest["history_key"] == HISTORY, "Unexpected stage schema/history")
    ck(manifest["native_candidate_record"] == binding(NATIVE) and
       manifest["human_candidate_record"] == binding(HUMAN), "Stage authority bindings differ")
    ck(manifest["direct_human_authority"] == human["direct_human_authority"] and
       "AP531 is `✲A`" in human["direct_human_authority"]["text"] and
       "XM181 is A" in human["direct_human_authority"]["text"] and
       "AS201 is TD" in human["direct_human_authority"]["text"] and
       "AP313 is A" in human["direct_human_authority"]["text"],
       "Direct-human authority wording/binding differs")
    bound(manifest["stage_script"])
    bound(manifest["shared_renderer"])
    native_by_page = {p["page"]: p for p in native["proposed_corrections"]}
    human_by_page = {p["page"]: p for p in human["proposed_corrections"]}
    staged = {p["page"]: p for p in manifest["pages"]}
    ck(len(manifest["pages"]) == 11 and set(staged) == set(EXPECTED) and
       set(native_by_page) == {p for p, x in EXPECTED.items() if x[1] == "native"} and
       set(human_by_page) == {p for p, x in EXPECTED.items() if x[1] == "direct-human"},
       "Eleven page set/authority partition differs")
    no_change = check_no_change(manifest, human)
    reviewed = []
    for page, sheet in staged.items():
        scan_id, authority_kind, span, changes, card_portion = EXPECTED[page]
        record = native_by_page[page] if authority_kind == "native" else human_by_page[page]
        authority_binding = binding(NATIVE if authority_kind == "native" else HUMAN)
        expected_edit = {"row": span[0], "column": span[1], "before": span[2], "after": span[3]}
        expected_changes = [{"pointer": p, "before": a, "after": z} for p, a, z in changes]
        ck(sheet["scan_id"] == record["scan_id"] == scan_id and
           sheet["authority_kind"] == authority_kind and
           sheet["authority_record"] == authority_binding and
           sheet["text_edit"] == record["text_edit_span"] == expected_edit and
           sheet["active_model_changes"] == record["active_model_changes"] == expected_changes,
           "Source identity or exact edit differs: " + page)
        if card_portion:
            ck(record["printed_card_portion"] == card_portion, "Card portion differs: " + page)
        scan = bound(sheet["source"])
        crop = bound(sheet["source_crop"])
        broad = bound(sheet["broad_context_crop"])
        ck(sheet["source"] == record["source_tiff"] and
           sheet["source_crop"] == record["source_crop"] and
           sheet["broad_context_crop"] == record["broad_context_crop"] and
           scan.is_relative_to(TIFFS.resolve()), "Original TIFF/crop binding differs: " + page)
        with Image.open(scan) as original, Image.open(broad) as context:
            expected_broad = original.convert("RGB").crop(tuple(record["broad_context_source_pixel_bounds"]))
            ck(ImageChops.difference(expected_broad, context.convert("RGB")).getbbox() is None,
               "Broad crop not pixel-exact from TIFF: " + page)
        with Image.open(crop) as focused:
            ck(focused.width > 0 and focused.height > 0, "Focused source crop invalid: " + page)
        quartet, frozen, candidate = (sheet[k] for k in
                                       ("canonical_quartet", "before_quartet", "candidate_quartet"))
        for kind in ("txt", "json", "notes", "preview"):
            current = bound(quartet[kind])
            before = bound(frozen[kind])
            after = bound(candidate[kind])
            ck(current.is_relative_to(CANONICAL.resolve()) and
               before.is_relative_to(STAGE.resolve()) and
               after.is_relative_to(STAGE.resolve()) and
               current.name == before.name == after.name and sha(current) == sha(before),
               "Current canonical/predecessor/stage quartet mismatch: " + page + " " + kind)
        ck(bound(record["accepted_text"]).is_relative_to(REPO.resolve()) and
           bound(record["accepted_model"]).is_relative_to(REPO.resolve()) and
           record["accepted_text"]["sha256"] == frozen["txt"]["sha256"] and
           record["accepted_model"]["sha256"] == frozen["json"]["sha256"],
           "Repository accepted text/model no longer match: " + page)
        before_text = Path(frozen["txt"]["path"]).read_bytes()
        after_text = Path(candidate["txt"]["path"]).read_bytes()
        verify_exact_text(before_text, after_text, expected_edit)
        old_model, new_model = read(Path(frozen["json"]["path"])), read(Path(candidate["json"]["path"]))
        ck(HISTORY not in old_model and new_model[HISTORY] == sheet["history"],
           "Additive source history differs: " + page)
        history = sheet["history"]
        ck(history["authority_kind"] == authority_kind and
           history["source_candidate_record"] == authority_binding and
           history["original_tiff"] == sheet["source"] and
           history["scan_id"] == scan_id and
           history["text_span"] == expected_edit and
           history["active_model_changes"] == expected_changes and
           history["predecessor_text_sha256"] == frozen["txt"]["sha256"] and
           history["predecessor_model_sha256"] == frozen["json"]["sha256"],
           "History authority/source/edit binding differs: " + page)
        ck(("direct_human_authority" in history) == (authority_kind == "direct-human"),
           "Human/native provenance classification confused: " + page)
        if authority_kind == "direct-human":
            ck(history["direct_human_authority"] == manifest["direct_human_authority"],
               "Human authorization not verbatim: " + page)
        reverse = copy.deepcopy(new_model)
        reverse.pop(HISTORY)
        for key, old, new in changes:
            cursor, field = pointer(reverse, key)
            ck(cursor[field] == new, "Candidate active model literal differs: " + page + " " + key)
            cursor[field] = old
        ck(reverse == old_model,
           "Unrelated model node/pin/wire/geometry/raw-history change: " + page)
        if page == "AP313":
            ck(old_model["nodes"][18].get("original_function_literal") ==
               new_model["nodes"][18].get("original_function_literal"),
               "AP313 historical literal was modified")
        old_notes = Path(frozen["notes"]["path"]).read_bytes()
        new_notes = Path(candidate["notes"]["path"]).read_bytes()
        ck(new_notes.startswith(old_notes) and len(new_notes) > len(old_notes) and
           scan_id.encode("ascii") in new_notes[len(old_notes):] and
           sheet["source"]["sha256"].encode("ascii") in new_notes[len(old_notes):],
           "Review notes overwritten or lacking source hash: " + page)
        old_render = render(before_text.decode("utf-8").splitlines(), sheet["render_config"])
        new_render = render(after_text.decode("utf-8").splitlines(), sheet["render_config"])
        with Image.open(frozen["preview"]["path"]) as old_preview, Image.open(candidate["preview"]["path"]) as new_preview:
            ck(ImageChops.difference(old_render, old_preview.convert("RGB")).getbbox() is None and
               ImageChops.difference(new_render, new_preview.convert("RGB")).getbbox() is None,
               "Preview differs from exact JuliaMono rendering: " + page)
        reviewed.append({"page": page, "scan_id": scan_id, "authority_kind": authority_kind,
                         "source": sheet["source"], "source_crop": sheet["source_crop"],
                         "broad_crop_pixel_exact": True, "text_edit": expected_edit,
                         "active_model_changes": expected_changes,
                         "before_text_sha256": frozen["txt"]["sha256"],
                         "candidate_text_sha256": candidate["txt"]["sha256"],
                         "before_model_sha256": frozen["json"]["sha256"],
                         "candidate_model_sha256": candidate["json"]["sha256"]})
    return {"schema": "Independent eleven native and human function corrections acceptance v1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "reviewer": "/root/px311_native", "passed": True, "failures": [],
            "visual_review_pending": False,
            "manifest": binding(MANIFEST), "native_candidate_record": binding(NATIVE),
            "human_candidate_record": binding(HUMAN), "reviewed_pages": reviewed,
            "confirmed_no_change": no_change,
            "counts": {"pages": 11, "native_scan_readings": 7, "direct_human_confirmations": 4,
                       "function_label_edits": 11, "changed_text_cells": 12,
                       "active_model_field_changes": 12, "quartet_files_reviewed": 44,
                       "other_model_fields_changed": 0, "wire_or_pin_geometry_changes": 0,
                       "DT001_changed": 0},
            "check_count": checks, "canonical_writes": 0, "repository_writes": 0,
            "original_scan_writes": 0, "audit_script": binding(Path(__file__))}


def main():
    if AUDIT.exists():
        raise SystemExit("Independent audit already exists; refusing overwrite")
    try:
        report = run()
    except Exception as error:
        report = {"schema": "Independent eleven native and human function corrections acceptance v1",
                  "created_utc": datetime.now(timezone.utc).isoformat(),
                  "reviewer": "/root/px311_native", "passed": False,
                  "failures": [str(error)], "check_count": checks,
                  "manifest": binding(MANIFEST),
                  "native_candidate_record": binding(NATIVE),
                  "human_candidate_record": binding(HUMAN),
                  "canonical_writes": 0, "repository_writes": 0,
                  "original_scan_writes": 0, "audit_script": binding(Path(__file__))}
    AUDIT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "failures": report["failures"],
                      "check_count": report["check_count"], "audit": binding(AUDIT)},
                     ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

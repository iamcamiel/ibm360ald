import copy
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops


MANIFEST = Path(r"D:/Github/IBM360/tmp/ald-text/ald/card-type-database/native-three-review/unified-stage/Unified native three correction manifest.json")
REPORT = Path(r"D:/Github/IBM360/tmp/ald-text/ald/card-type-database/native-three-review/independent-review/Independent three native corrections acceptance.json")
EXPECTED = {
    "PX311": {"scan": "f26cea27ccfc1da055b420098957226d243dcc7d138495b1302196b72b92ad8f", "edit": (7, 96, "│", "◺"), "changes": {"/nodes/11/pins/1/triangle": (False, True), "/printed_labels/27/text": ("B09", "B09◺")}},
    "KU641": {"scan": "3b70660af0475f77bc48db432271d35446c7a2558dff073d01be8ac5d3710a7d", "edit": (54, 149, "◺", "│"), "changes": {"/nodes/35/pins/2/triangle": (True, False)}},
    "AP743": {"scan": "63a9ac9c812db1a4b61ad8171eeebe3381535c00137738cffee7266b8447bd7c", "edit": (17, 120, "O", "A"), "changes": {"/nodes/20/function": ("OR", "AR")}},
}
CROP = {
    "PX311": (Path(r"D:/Github/IBM360/tmp/ald-text/ald/card-type-database/native-source-findings-px311/PX311 AG B09 independently recropped.png"), "faf7c7606e4c55062e80777c731b3cbe5e77e83a7da391a6c4b30b0ae48f33f2"),
    "KU641": (Path(r"D:/Github/IBM360/tmp/ald-text/ald/card-type-database/native-three-review/KU641 BX B10 independent native crop.png"), "55900757deeaf6d233db466f6ec63a1c4b1f68e0fadd020203265b437da9f176"),
    "AP743": (Path(r"D:/Github/IBM360/tmp/ald-text/ald/card-type-database/OH-OK-native-review/AP743 4C OR-AR native.png"), "1709b97a2c2916c07276ed1fc67e04cb69bf18e56fd880926dd3bae89a8b14b5"),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def at_pointer(obj, pointer):
    for p in pointer.split("/")[1:]:
        obj = obj[int(p)] if isinstance(obj, list) else obj[p]
    return obj


def replace_pointer(obj, pointer, value):
    parts = pointer.split("/")[1:]
    for p in parts[:-1]:
        obj = obj[int(p)] if isinstance(obj, list) else obj[p]
    p = parts[-1]
    if isinstance(obj, list):
        obj[int(p)] = value
    else:
        obj[p] = value


def load_lines(path):
    return Path(path).read_text(encoding="utf-8").splitlines()


def main():
    failures = []
    checks = []
    manifest_sha = digest(MANIFEST)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest_sha != "726a8926ab81dc7d1ea1f0fde9272b82198e47a1c94a5fc938273138e267bf5b":
        failures.append("unexpected manifest hash")
    if set(p["page"] for p in manifest["pages"]) != set(EXPECTED):
        failures.append("unexpected page set")
    if manifest["history_key"] != "source_native_three_corrections_v1":
        failures.append("unexpected history key")
    for p in manifest["pages"]:
        page = p["page"]
        e = EXPECTED[page]
        if digest(p["source"]["path"]) != e["scan"] or p["source"]["sha256"] != e["scan"]:
            failures.append(page + ": TIFF hash")
        crop_path, crop_hash = CROP[page]
        if digest(crop_path) != crop_hash:
            failures.append(page + ": native crop hash")
        if digest(p["evidence"]["path"]) != p["evidence"]["sha256"]:
            failures.append(page + ": source evidence hash")
        for qkey in ("txt", "json", "notes", "preview"):
            for variant in ("canonical_quartet", "before_quartet", "candidate_quartet"):
                q = p[variant][qkey]
                if digest(q["path"]) != q["sha256"]:
                    failures.append(f"{page}: {variant} {qkey} hash")
            if p["canonical_quartet"][qkey]["sha256"] != p["before_quartet"][qkey]["sha256"]:
                failures.append(f"{page}: canonical/before {qkey} mismatch")
        row, col, old, new = e["edit"]
        if p["text_edit"] != {"row": row, "column": col, "before": old, "after": new}:
            failures.append(page + ": manifest edit mismatch")
        old_lines = load_lines(p["before_quartet"]["txt"]["path"])
        new_lines = load_lines(p["candidate_quartet"]["txt"]["path"])
        if len(old_lines) != len(new_lines) or any(len(a) != len(b) for a, b in zip(old_lines, new_lines)):
            failures.append(page + ": line dimensions changed")
        diffs = [(i, j, a, b) for i, (al, bl) in enumerate(zip(old_lines, new_lines)) for j, (a, b) in enumerate(zip(al, bl)) if a != b]
        if diffs != [(row, col, old, new)]:
            failures.append(page + ": TXT changed beyond intended cell: " + repr(diffs[:5]))
        old_model = json.loads(Path(p["before_quartet"]["json"]["path"]).read_text(encoding="utf-8"))
        new_model = json.loads(Path(p["candidate_quartet"]["json"]["path"]).read_text(encoding="utf-8"))
        expected_model = copy.deepcopy(old_model)
        for pointer, (before, after) in e["changes"].items():
            if at_pointer(old_model, pointer) != before or at_pointer(new_model, pointer) != after:
                failures.append(page + ": model pointer mismatch " + pointer)
            replace_pointer(expected_model, pointer, after)
        history = new_model.pop("source_native_three_corrections_v1", None)
        if history is None:
            failures.append(page + ": missing additive history")
        else:
            if isinstance(history, list):
                new_entry = history[-1]
            else:
                new_entry = history
            if new_entry.get("scan_id") != p["scan_id"] or new_entry.get("predecessor_text_sha256") != p["before_quartet"]["txt"]["sha256"]:
                failures.append(page + ": history source binding")
            if new_entry.get("stage_status_at_creation") != "private candidate awaiting independent acceptance":
                failures.append(page + ": history status")
        expected_model.pop("source_native_three_corrections_v1", None)
        if new_model != expected_model:
            failures.append(page + ": model changed beyond active pointers/history")
        notes_before = Path(p["before_quartet"]["notes"]["path"]).read_text(encoding="utf-8")
        notes_after = Path(p["candidate_quartet"]["notes"]["path"]).read_text(encoding="utf-8")
        if not notes_after.startswith(notes_before) or len(notes_after) <= len(notes_before):
            failures.append(page + ": notes not append-only")
        im0 = Image.open(p["before_quartet"]["preview"]["path"]).convert("RGB")
        im1 = Image.open(p["candidate_quartet"]["preview"]["path"]).convert("RGB")
        if im0.size != im1.size or im0.size != tuple(p["render_config"]["size"]):
            failures.append(page + ": preview size changed")
        bbox = ImageChops.difference(im0, im1).getbbox()
        if bbox is None:
            failures.append(page + ": preview unchanged")
        checks.append({"page": page, "text_differences": len(diffs), "active_model_changes": len(e["changes"]), "preview_changed_bbox": bbox, "candidate_hashes": {k: v["sha256"] for k, v in p["candidate_quartet"].items()}})
    visual_contact = REPORT.parent / "Three page preview before-after contact.png"
    expected_contact_hash = "f65dd984de3dbc42f8d4009825d6aa91bf5df808ea7373ee8751ea9cc08e5753"
    if digest(visual_contact) != expected_contact_hash:
        failures.append("independently viewed preview contact hash changed")
    result = {"passed": not failures, "failures": failures, "manifest": {"path": str(MANIFEST), "sha256": manifest_sha}, "independent_checks": checks, "native_visual_readings": {"PX311": "B09 has open triangle at the left block border", "KU641": "B10 has a plain right block border", "AP743": "AQ/4C function reads AR"}, "preview_contact": {"path": str(visual_contact), "sha256": expected_contact_hash, "reviewer_viewed": True, "finding": "Each candidate visually changes only the source-supported cell; nearby wires, pins, box placement, and labels match predecessor."}, "manual_photo_needed": False, "canonical_or_repository_files_edited": False}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "failures": failures, "report": str(REPORT), "sha256": digest(REPORT), "checks": checks}, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

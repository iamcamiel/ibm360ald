"""Private stage and guarded publisher for three independently source-read ALD fixes.

--stage creates candidates only. --preflight rechecks every frozen binding.
--publish requires an independent audit binding and coordinator release.
No repository or original scan is written by this tool.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import ImageChops

sys.dont_write_bytecode = True
ROOT = Path("D:/Github/IBM360")
HERE = Path(__file__).resolve().parent
STAGE = HERE / "unified-stage"
CANONICAL = ROOT / "ALD_Visual_Transcriptions"
REPO = ROOT / "ibm360ald"
SOURCE = Path("D:/Reference Materials/IBM 360/IBM_360_ALD")
HISTORY = "source_native_three_corrections_v1"

SHARED = ROOT / "tmp/ald-text/ald/card-type-database/prepare_non_ap_OR_corrections.py"
spec = importlib.util.spec_from_file_location("native_three_shared", SHARED)
u = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(u)

PAGES = [
    {
        "page": "PX311", "scan_id": "1555",
        "stem": "PX311 SC CE SELECT AND MANUAL CONTROL GATING",
        "folder": "ALD Diagrams", "repository_folder": "PX System Console",
        "source": "PX System Console/PX311 SC CE Select and Manual Control Gating.tif",
        "source_sha256": "f26cea27ccfc1da055b420098957226d243dcc7d138495b1302196b72b92ad8f",
        "text_sha256": "496ffb284be33a68061034ded7a8dff92f4859154b44a4d4adb02e8bde6f84ba",
        "model_sha256": "68648cf0c34806aaeaae52996f0659312a87666deeda4a419ac787f1cec59310",
        "evidence": ROOT / "tmp/ald-text/ald/card-type-database/native-source-findings-px311/PX311 AG B09 private native correction proposal.json",
        "edit": {"row": 7, "column": 96, "before": "│", "after": "◺"},
        "changes": [
            {"pointer": "/nodes/11/pins/1/triangle", "before": False, "after": True},
            {"pointer": "/printed_labels/27/text", "before": "B09", "after": "B09◺"},
        ],
        "note": "AG.B09 input border is printed with an open triangle on the original TIFF.",
    },
    {
        "page": "KU641", "scan_id": "1113",
        "stem": "KU641 STORAGE LOGOUT SE STOPPED GATING",
        "folder": "KU MCW, Scan, Logout", "repository_folder": "KU MCW, Scan, Logout",
        "source": "KU MCW, Scan, Logout/KU641 STORAGE LOGOUT SE STOPPED GATING.tif",
        "source_sha256": "3b70660af0475f77bc48db432271d35446c7a2558dff073d01be8ac5d3710a7d",
        "text_sha256": "fc7182e3cad6fe5d21d4871ccb792d29ff930dbff4aee58228fdc87fa8bf961c",
        "model_sha256": "046c67dc3fc56f4a32c7d55acbebcd93c1a3291762c6efd22db87933c165af4c",
        "evidence": ROOT / "tmp/ald-text/ald/card-type-database/native-three-review/KU641 BX B10 independent correction proposal.json",
        "edit": {"row": 54, "column": 149, "before": "◺", "after": "│"},
        "changes": [{"pointer": "/nodes/35/pins/2/triangle", "before": True, "after": False}],
        "note": "BX.B10 output border is straight, with no triangle, on the original TIFF.",
    },
    {
        "page": "AP743", "scan_id": "327",
        "stem": "AP743 ROS BIT 91 DATA REG POSITION ROS BITS 76-81 AND 82-84",
        "folder": "ALD Diagrams", "repository_folder": "AP Parallel Adder",
        "source": "AP Parallel Adder/AP743 ROS BIT 91 DATA REG POSITION ROS BITS 76-81 AND 82-84.tif",
        "source_sha256": "63a9ac9c812db1a4b61ad8171eeebe3381535c00137738cffee7266b8447bd7c",
        "text_sha256": "07e4ec7cef60c8eaa9844f97c82810f92689967b9be3ec67d12373fe64763573",
        "model_sha256": "509da8a2f1ad030e49fcd239c9729ceac42e1e69189456a1d9e516dd0dd6d889",
        "evidence": ROOT / "tmp/ald-text/ald/card-type-database/AP743-native-followup/AP743 4C AQ proposed correction.json",
        "edit": {"row": 17, "column": 120, "before": "O", "after": "A"},
        "changes": [{"pointer": "/nodes/20/function", "before": "OR", "after": "AR"}],
        "note": "AQ/4C function reads AR rather than OR on the original TIFF.",
    },
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(bound: dict) -> Path:
    path = Path(bound["path"]).resolve()
    require(path.is_file() and sha(path) == bound["sha256"], "Changed or missing binding: " + str(path))
    return path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def at_pointer(model: dict, pointer: str):
    cursor = model
    parts = pointer.strip("/").split("/")
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    last = int(parts[-1]) if isinstance(cursor, list) else parts[-1]
    return cursor, last


def model_bytes(model: dict) -> bytes:
    return (json.dumps(model, indent=2, ensure_ascii=False).replace("\n", "\r\n") + "\r\n").encode("utf-8")


def line_replace(raw: bytes, edit: dict) -> bytes:
    text = raw.decode("utf-8")
    rows = text.splitlines(keepends=True)
    require(len(rows) == 103 and all(len(x.rstrip("\r\n")) <= 245 for x in rows), "Not a bounded 103-row grid")
    r, c = edit["row"], edit["column"]
    require(rows[r][c] == edit["before"] and len(edit["before"]) == len(edit["after"]) == 1, "Wrong exact text cell")
    rows[r] = rows[r][:c] + edit["after"] + rows[r][c + 1:]
    result = "".join(rows).encode("utf-8")
    reverse = result.decode("utf-8").splitlines(keepends=True)
    reverse[r] = reverse[r][:c] + edit["before"] + reverse[r][c + 1:]
    require("".join(reverse).encode("utf-8") == raw, "Unrelated text changed")
    return result


def render_config(text_path: Path, lines: list[str]) -> tuple[Path, dict]:
    from PIL import Image
    options = [
        text_path.with_name(text_path.stem + " preview.png"),
        text_path.with_suffix(".png"),
        text_path.with_name(text_path.stem + " JuliaMono preview.png"),
        text_path.with_name(text_path.stem + " JuliaMono.png"),
    ]
    matches = []
    for candidate in options:
        if not candidate.exists():
            continue
        with Image.open(candidate) as image:
            config = {"size": list(image.size), "font_size": 20, "row_height": 18,
                      "x": (image.width - 2940) // 2, "y": (image.height - 1854) // 2}
            if list(image.size) == [2956, 1870]:
                config["anchor"] = "lt"
            if ImageChops.difference(image.convert("RGB"), u.render(lines, config)).getbbox() is None:
                matches.append((candidate, config))
    require(len(matches) == 1, "Accepted preview does not exactly reproduce text: " + str(text_path))
    return matches[0]


def paths(page: dict) -> dict:
    stem = page["stem"]
    folder = CANONICAL / page["folder"]
    text = folder / (stem + ".txt")
    preview, config = render_config(text, text.read_text(encoding="utf-8").splitlines())
    return {"txt": text, "json": folder / (stem + ".json"),
            "notes": folder / (stem + " review notes.txt"), "preview": preview,
            "render_config": config}


def stage() -> dict:
    require(not STAGE.exists(), "Stage already exists; refusing overwrite")
    require(sha(SHARED) == "6e78281de9aa1714156810fb4ebbe5b14a82fa843cb2f02c2fcb37ac3f884885", "Changed shared renderer")
    STAGE.mkdir(parents=True)
    manifest = {"schema": "source-native-three-page-correction-stage-v1",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "status": "PRIVATE; requires independent audit and coordinator release before publication",
                "history_key": HISTORY, "stage_script": binding(Path(__file__)),
                "shared_renderer": binding(SHARED), "pages": []}
    for p in PAGES:
        src = SOURCE / p["source"]
        require(src.is_file() and sha(src) == p["source_sha256"], "Original TIFF changed: " + p["page"])
        evidence = p["evidence"]
        require(evidence.is_file(), "Missing independent evidence: " + p["page"])
        files = paths(p)
        require(sha(files["txt"]) == p["text_sha256"] and sha(files["json"]) == p["model_sha256"],
                "Current accepted text/model changed: " + p["page"])
        for kind in ("txt", "json"):
            repo = REPO / ("ALD" if kind == "txt" else "json") / p["repository_folder"] / (p["stem"] + "." + kind)
            require(repo.is_file() and sha(repo) == sha(files[kind]), "Repository/canonical epoch mismatch: " + p["page"])
        folder = STAGE / p["page"]
        before = folder / "before"
        candidate = folder / "candidate"
        before.mkdir(parents=True)
        candidate.mkdir(parents=True)
        bounds, targets = {}, {}
        for kind in ("txt", "json", "notes", "preview"):
            source_file = files[kind]
            frozen = before / source_file.name
            shutil.copy2(source_file, frozen)
            bounds[kind] = binding(frozen)
            targets[kind] = candidate / source_file.name
        raw = files["txt"].read_bytes()
        lines = raw.decode("utf-8").splitlines()
        text_after = line_replace(raw, p["edit"])
        targets["txt"].write_bytes(text_after)
        model_raw = files["json"].read_bytes()
        model = json.loads(model_raw.decode("utf-8"))
        require(model_bytes(model) == model_raw, "Unexpected model serialization: " + p["page"])
        updated = copy.deepcopy(model)
        require(HISTORY not in updated, "Correction already applied: " + p["page"])
        for change in p["changes"]:
            cursor, key = at_pointer(updated, change["pointer"])
            require(cursor[key] == change["before"], "Changed model pointer: " + change["pointer"])
            cursor[key] = change["after"]
        updated[HISTORY] = {
            "scope": "Exact native TIFF reread; not inferred from card database",
            "scan_id": p["scan_id"], "original_tiff": binding(src),
            "source_evidence": binding(evidence),
            "predecessor_text_sha256": sha(files["txt"]),
            "predecessor_model_sha256": sha(files["json"]),
            "text_cell": p["edit"], "active_model_changes": p["changes"],
            "stage_status_at_creation": "private candidate awaiting independent acceptance",
        }
        targets["json"].write_bytes(model_bytes(updated))
        require(u.diff(model, updated) == [
            *[dict(json_pointer=x["pointer"], before=x["before"], after=x["after"]) for x in p["changes"]],
            {"json_pointer": "/" + HISTORY, "added": updated[HISTORY]},
        ] or sorted(x["json_pointer"] for x in u.diff(model, updated)) ==
                sorted([x["pointer"] for x in p["changes"]] + ["/" + HISTORY]), "Unexpected model delta")
        note_raw = files["notes"].read_bytes()
        newline = b"\r\n" if b"\r\n" in note_raw else b"\n"
        entry = ("Native source correction " + p["page"] + " (scan " + p["scan_id"] + "): " +
                 p["note"] + " TIFF SHA-256 " + p["source_sha256"] + ".")
        targets["notes"].write_bytes(note_raw + (b"" if note_raw.endswith(newline) else newline) + entry.encode("utf-8") + newline)
        image = u.render(text_after.decode("utf-8").splitlines(), files["render_config"])
        image.save(targets["preview"])
        require(ImageChops.difference(image, u.render(text_after.decode("utf-8").splitlines(), files["render_config"])).getbbox() is None,
                "New preview does not match text")
        manifest["pages"].append({
            "page": p["page"], "scan_id": p["scan_id"], "source": binding(src),
            "evidence": binding(evidence), "canonical_quartet": {k: binding(files[k]) for k in bounds},
            "before_quartet": bounds, "candidate_quartet": {k: binding(targets[k]) for k in bounds},
            "render_config": files["render_config"], "text_edit": p["edit"],
            "active_model_changes": p["changes"], "history": updated[HISTORY],
        })
    path = STAGE / "Unified native three correction manifest.json"
    save(path, manifest)
    return {"manifest": binding(path), "pages": len(manifest["pages"]), "canonical_writes": 0,
            "repository_writes": 0, "original_scan_writes": 0}


def preflight(manifest_path: Path, expected_sha: str, audit: Path | None, audit_sha: str | None) -> tuple[dict, dict]:
    require(manifest_path.resolve() == (STAGE / "Unified native three correction manifest.json").resolve(), "Wrong stage manifest")
    require(sha(manifest_path) == expected_sha, "Manifest has changed")
    manifest = load(manifest_path)
    require(manifest["history_key"] == HISTORY and len(manifest["pages"]) == 3, "Wrong staged scope")
    checked(manifest["stage_script"])
    checked(manifest["shared_renderer"])
    if audit is not None:
        require(audit_sha is not None and sha(audit) == audit_sha, "Independent audit changed")
        reviewed = load(audit)
        require(reviewed.get("passed") is True and not reviewed.get("failures"), "Independent audit did not pass")
        require(reviewed.get("manifest", {}).get("sha256") == expected_sha, "Audit covers another stage")
    pages_seen = set()
    for page in manifest["pages"]:
        page_id = page["page"]
        require(page_id in {p["page"] for p in PAGES} and page_id not in pages_seen, "Wrong/duplicate page")
        pages_seen.add(page_id)
        source = checked(page["source"])
        require(source.is_relative_to(SOURCE.resolve()), "Source outside original archive")
        checked(page["evidence"])
        for kind in ("txt", "json", "notes", "preview"):
            current = checked(page["canonical_quartet"][kind])
            before = checked(page["before_quartet"][kind])
            candidate = checked(page["candidate_quartet"][kind])
            require(current.is_relative_to(CANONICAL.resolve()) and before.is_relative_to(STAGE.resolve()) and
                    candidate.is_relative_to(STAGE.resolve()) and current.name == before.name == candidate.name,
                    "Quartet path escaped stage/canonical")
            require(sha(current) == sha(before), "Current predecessor epoch changed")
        old_text = checked(page["before_quartet"]["txt"]).read_bytes()
        new_text = checked(page["candidate_quartet"]["txt"]).read_bytes()
        require(line_replace(old_text, page["text_edit"]) == new_text, "Unexpected text candidate bytes")
        old_model = load(checked(page["before_quartet"]["json"]))
        new_model = load(checked(page["candidate_quartet"]["json"]))
        require(page["history"] == new_model[HISTORY] and HISTORY not in old_model, "Wrong additive history")
        restored = copy.deepcopy(new_model)
        del restored[HISTORY]
        for change in page["active_model_changes"]:
            cursor, key = at_pointer(restored, change["pointer"])
            require(cursor[key] == change["after"], "Wrong active candidate pointer")
            cursor[key] = change["before"]
        require(restored == old_model, "Unrelated node/pin/wire/geometry/raw history changed")
        require(model_bytes(new_model) == checked(page["candidate_quartet"]["json"]).read_bytes(), "Model bytes noncanonical")
        old_notes = checked(page["before_quartet"]["notes"]).read_bytes()
        new_notes = checked(page["candidate_quartet"]["notes"]).read_bytes()
        require(new_notes.startswith(old_notes), "Review notes predecessor not preserved")
        after_lines = new_text.decode("utf-8").splitlines()
        rendered = u.render(after_lines, page["render_config"])
        from PIL import Image
        with Image.open(checked(page["candidate_quartet"]["preview"])) as image:
            require(ImageChops.difference(rendered, image.convert("RGB")).getbbox() is None,
                    "Candidate preview differs from text")
    require(pages_seen == {"PX311", "KU641", "AP743"}, "Missing staged page")
    return manifest, {"passed": True, "pages": 3, "changed_text_cells": 3,
                      "active_model_changes": 4, "candidate_quartet_files": 12,
                      "original_scans_checked": 3, "canonical_writes": 0,
                      "repository_writes": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--independent-audit", type=Path)
    parser.add_argument("--independent-audit-sha256")
    args = parser.parse_args()
    require(sum((args.stage, args.preflight, args.publish)) == 1, "Choose one mode")
    if args.stage:
        print(json.dumps(stage()))
        return
    require(args.manifest_sha256 is not None, "Manifest SHA-256 required")
    path = STAGE / "Unified native three correction manifest.json"
    manifest, result = preflight(path, args.manifest_sha256, args.independent_audit,
                                 args.independent_audit_sha256)
    if args.preflight:
        print(json.dumps(result))
        return
    require(args.independent_audit is not None and args.independent_audit_sha256 is not None,
            "Independent audit binding required to publish")
    receipt = STAGE / "Unified native three publication receipt.json"
    require(not receipt.exists(), "Already published")
    staged = []
    try:
        for page in manifest["pages"]:
            for kind in ("txt", "json", "notes", "preview"):
                dest = checked(page["canonical_quartet"][kind])
                candidate = checked(page["candidate_quartet"][kind])
                temp = dest.with_name(dest.name + ".native-three.tmp")
                require(not temp.exists(), "Publishing temporary file already exists")
                shutil.copyfile(candidate, temp)
                require(sha(temp) == sha(candidate), "Temporary candidate changed")
                staged.append((dest, temp, page["canonical_quartet"][kind]["sha256"],
                               page["candidate_quartet"][kind]["sha256"]))
        for dest, temp, old_sha, next_sha in staged:
            require(sha(dest) == old_sha and sha(temp) == next_sha, "Publication race or corrupted stage")
        for page in manifest["pages"]:
            checked(page["source"])
        for dest, temp, old_sha, next_sha in staged:
            temp.replace(dest)
    finally:
        for _, temp, _, _ in staged:
            if temp.exists():
                temp.unlink()
    for dest, _, _, next_sha in staged:
        require(sha(dest) == next_sha, "Published file differs")
    save(receipt, {"published_utc": datetime.now(timezone.utc).isoformat(),
                   "manifest": binding(path), "independent_audit": binding(args.independent_audit),
                   "pages": 3, "quartet_files": 12,
                   "canonical_destinations": [binding(dest) for dest, _, _, _ in staged],
                   "repository_writes": 0, "original_scan_writes": 0})
    print(json.dumps({"published": True, "receipt": binding(receipt), "pages": 3}))


if __name__ == "__main__":
    main()

"""Create and verify private, source-bound seven-page ALD function corrections.

This tool writes only beneath seven-page-private-stage. Publication is deliberately
outside its scope, pending an independent review and coordinator release.
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
SOURCE = HERE / "V13 seven source-bound function correction candidates.json"
SOURCE_SHA = "7f12522b6e83348a529646ff01c5f683a633b59c2f53af35e008c46c0ba42d52"
STAGE = HERE / "seven-page-private-stage"
MANIFEST = STAGE / "Seven native function correction manifest.json"
CANONICAL = ROOT / "ALD_Visual_Transcriptions"
REPO = ROOT / "ibm360ald"
HISTORY = "source_native_seven_function_corrections_v1"
SHARED = ROOT / "tmp/ald-text/ald/card-type-database/prepare_non_ap_OR_corrections.py"
SHARED_SHA = "6e78281de9aa1714156810fb4ebbe5b14a82fa843cb2f02c2fcb37ac3f884885"
PRIOR = ROOT / "tmp/ald-text/ald/card-type-database/native-three-review/unified_native_three.py"

spec = importlib.util.spec_from_file_location("seven_native_prior", PRIOR)
prior = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(prior)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bound(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def verify_bound(record: dict) -> Path:
    path = Path(record["path"]).resolve()
    require(path.is_file() and sha(path) == record["sha256"], "Changed binding: " + str(path))
    return path


def same_repo_and_canonical(record: dict, kind: str) -> Path:
    repo = verify_bound(record["accepted_text" if kind == "txt" else "accepted_model"])
    matches = list(CANONICAL.rglob(repo.name))
    require(len(matches) == 1 and sha(matches[0]) == sha(repo),
            "Canonical/repository epoch mismatch: " + record["page"] + " " + kind)
    return matches[0]


def replace_span(raw: bytes, edit: dict) -> bytes:
    require(len(edit["before"]) == len(edit["after"]), "Text edit changes column width")
    rows = raw.decode("utf-8").splitlines(keepends=True)
    require(len(rows) == 103 and all(len(x.rstrip("\r\n")) <= 245 for x in rows), "Wrong page grid")
    row, col, before, after = edit["row"], edit["column"], edit["before"], edit["after"]
    require(rows[row][col:col + len(before)] == before, "Text predecessor changed")
    rows[row] = rows[row][:col] + after + rows[row][col + len(before):]
    result = "".join(rows).encode("utf-8")
    back = result.decode("utf-8").splitlines(keepends=True)
    back[row] = back[row][:col] + before + back[row][col + len(after):]
    require("".join(back).encode("utf-8") == raw, "Text edit altered other cells")
    return result


def stage() -> dict:
    require(not STAGE.exists(), "Private stage already exists; refusing overwrite")
    require(sha(SOURCE) == SOURCE_SHA, "Candidate source record changed")
    require(sha(SHARED) == SHARED_SHA, "Shared renderer changed")
    record = json.loads(SOURCE.read_text(encoding="utf-8"))
    proposals = record["proposed_corrections"]
    require(len(proposals) == 7 and {x["page"] for x in proposals} ==
            {"AP737", "AP181", "RQ683", "KU601", "RQ781", "MC371", "AP441"}, "Wrong proposal set")
    STAGE.mkdir(parents=True)
    manifest = {
        "schema": "source-native-seven-function-private-stage-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PRIVATE; requires independent audit and coordinator release before publication",
        "candidate_record": bound(SOURCE), "stage_script": bound(Path(__file__)),
        "shared_renderer": bound(SHARED), "history_key": HISTORY, "pages": [],
    }
    for p in proposals:
        page = p["page"]
        source = verify_bound(p["source_tiff"])
        crop = verify_bound(p["source_crop"])
        context = verify_bound(p["broad_context_crop"])
        txt = same_repo_and_canonical(p, "txt")
        model_path = same_repo_and_canonical(p, "json")
        notes = txt.with_name(txt.stem + " review notes.txt")
        require(notes.is_file(), "Missing notes: " + page)
        preview, config = prior.render_config(txt, txt.read_text(encoding="utf-8").splitlines())
        files = {"txt": txt, "json": model_path, "notes": notes, "preview": preview}
        page_root = STAGE / page
        before, candidate = page_root / "before", page_root / "candidate"
        before.mkdir(parents=True)
        candidate.mkdir()
        before_bound, candidate_files = {}, {}
        for kind, path in files.items():
            frozen = before / path.name
            shutil.copy2(path, frozen)
            before_bound[kind] = bound(frozen)
            candidate_files[kind] = candidate / path.name

        edit = p["text_edit_span"]
        require((edit["row"], edit["column"]) ==
                (p["function_cell_zero_based"]["row"], p["function_cell_zero_based"]["column"]),
                "Function cell disagrees with proposed edit: " + page)
        raw = txt.read_bytes()
        new_text = replace_span(raw, edit)
        candidate_files["txt"].write_bytes(new_text)

        original_model_bytes = model_path.read_bytes()
        original_model = json.loads(original_model_bytes.decode("utf-8"))
        require(prior.model_bytes(original_model) == original_model_bytes, "Unexpected model serialization: " + page)
        updated = copy.deepcopy(original_model)
        require(HISTORY not in updated, "Correction already staged: " + page)
        changes = p["active_model_changes"]
        require(len(changes) == 1 and changes[0]["pointer"] == p["active_model_function_pointer"],
                "Unexpected active model changes: " + page)
        for change in changes:
            cursor, key = prior.at_pointer(updated, change["pointer"])
            require(cursor[key] == change["before"], "Changed model predecessor: " + page)
            cursor[key] = change["after"]
        history = {
            "scope": "Exact native TIFF reread; function change is not inferred from card database",
            "scan_id": p["scan_id"], "original_tiff": bound(source),
            "source_crop": bound(crop), "broad_context_crop": bound(context),
            "source_candidate_record": bound(SOURCE),
            "predecessor_text_sha256": sha(txt), "predecessor_model_sha256": sha(model_path),
            "text_span": edit, "active_model_changes": changes,
            "stage_status_at_creation": "private candidate awaiting independent acceptance",
        }
        updated[HISTORY] = history
        candidate_files["json"].write_bytes(prior.model_bytes(updated))
        diffs = prior.u.diff(original_model, updated)
        require(sorted(x["json_pointer"] for x in diffs) == sorted([changes[0]["pointer"], "/" + HISTORY]),
                "Extra active model changes: " + page)

        note_raw = notes.read_bytes()
        newline = b"\r\n" if b"\r\n" in note_raw else b"\n"
        entry = ("Native source correction " + page + " (scan " + p["scan_id"] + "): " +
                 p["node_id"] + "/" + str(p["grid"] or "ungridded") + " function " +
                 changes[0]["before"] + " -> " + changes[0]["after"] +
                 "; original TIFF SHA-256 " + sha(source) + ".")
        candidate_files["notes"].write_bytes(note_raw + (b"" if note_raw.endswith(newline) else newline) +
                                             entry.encode("utf-8") + newline)
        image = prior.u.render(new_text.decode("utf-8").splitlines(), config)
        image.save(candidate_files["preview"])
        # The same renderer/configuration reproduced the accepted preview exactly above.
        require(ImageChops.difference(image, prior.u.render(new_text.decode("utf-8").splitlines(), config)).getbbox() is None,
                "Candidate preview mismatch: " + page)
        manifest["pages"].append({
            "page": page, "scan_id": p["scan_id"], "source": bound(source),
            "source_crop": bound(crop), "broad_context_crop": bound(context),
            "canonical_quartet": {k: bound(v) for k, v in files.items()},
            "before_quartet": before_bound,
            "candidate_quartet": {k: bound(v) for k, v in candidate_files.items()},
            "render_config": config, "text_edit": edit,
            "active_model_changes": changes, "history": history,
        })
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"manifest": bound(MANIFEST), "pages": 7, "canonical_writes": 0, "repository_writes": 0}


def preflight(expected_sha: str) -> dict:
    require(sha(MANIFEST) == expected_sha, "Stage manifest changed")
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(m["history_key"] == HISTORY and len(m["pages"]) == 7, "Wrong stage scope")
    for key in ("candidate_record", "stage_script", "shared_renderer"):
        verify_bound(m[key])
    for p in m["pages"]:
        for key in ("source", "source_crop", "broad_context_crop"):
            verify_bound(p[key])
        for kind in ("txt", "json", "notes", "preview"):
            current = verify_bound(p["canonical_quartet"][kind])
            before = verify_bound(p["before_quartet"][kind])
            candidate = verify_bound(p["candidate_quartet"][kind])
            require(current.is_relative_to(CANONICAL.resolve()) and
                    before.is_relative_to(STAGE.resolve()) and candidate.is_relative_to(STAGE.resolve()) and
                    current.name == before.name == candidate.name and sha(current) == sha(before),
                    "Changed predecessor quartet: " + p["page"] + " " + kind)
        before_txt = Path(p["before_quartet"]["txt"]["path"]).read_bytes()
        candidate_txt = Path(p["candidate_quartet"]["txt"]["path"]).read_bytes()
        require(replace_span(before_txt, p["text_edit"]) == candidate_txt,
                "Non-exact candidate text edit: " + p["page"])
        old = json.loads(Path(p["before_quartet"]["json"]["path"]).read_text(encoding="utf-8"))
        new = json.loads(Path(p["candidate_quartet"]["json"]["path"]).read_text(encoding="utf-8"))
        require(new[HISTORY] == p["history"], "History changed: " + p["page"])
        require(sorted(x["json_pointer"] for x in prior.u.diff(old, new)) ==
                sorted([p["active_model_changes"][0]["pointer"], "/" + HISTORY]),
                "Extra model change: " + p["page"])
        from PIL import Image
        with Image.open(p["candidate_quartet"]["preview"]["path"]) as image:
            rendered = prior.u.render(candidate_txt.decode("utf-8").splitlines(), p["render_config"])
            require(ImageChops.difference(image.convert("RGB"), rendered).getbbox() is None,
                    "Candidate preview mismatch: " + p["page"])
    return {"manifest": bound(MANIFEST), "pages": 7, "preflight": "PASS", "canonical_writes": 0,
            "repository_writes": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--preflight", metavar="MANIFEST_SHA256")
    args = parser.parse_args()
    require(args.stage != bool(args.preflight), "Choose exactly one of --stage or --preflight")
    print(json.dumps(stage() if args.stage else preflight(args.preflight), indent=2))

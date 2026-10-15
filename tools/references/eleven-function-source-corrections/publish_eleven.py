"""Guarded canonical-only publisher for the independently accepted 11 ALD pages.

Run --preflight first. --publish changes exactly 44 canonical quartet files and
requires the immutable stage manifest and independent audit hashes below.
It never writes the repository, original TIFFs, or source evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STAGE_SCRIPT = HERE / "stage_eleven.py"
MANIFEST = HERE / "eleven-page-private-stage/Eleven native and human function correction manifest.json"
MANIFEST_SHA = "9bdeb975f0a457bdbd98e37d6bb162bba754f12074dc820d09b858be8f6c028f"
AUDIT = HERE / "Independent eleven native and human function corrections acceptance.json"
AUDIT_SHA = "aa8d69862b3e6a86179a2df96b7971d99faeb43b56ae3c2137607cb70628f81a"
RECEIPT = HERE / "eleven-page-private-stage/Eleven canonical publication receipt.json"
CANONICAL = Path("D:/Github/IBM360/ALD_Visual_Transcriptions").resolve()
SOURCE_ARCHIVE = Path("D:/Reference Materials/IBM 360/IBM_360_ALD").resolve()

spec = importlib.util.spec_from_file_location("eleven_stage", STAGE_SCRIPT)
stage = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(stage)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def preflight() -> tuple[dict, dict]:
    require(not RECEIPT.exists(), "Publication receipt already exists")
    require(sha(MANIFEST) == MANIFEST_SHA, "Stage manifest changed")
    require(sha(AUDIT) == AUDIT_SHA, "Independent audit changed")
    stage_result = stage.preflight(MANIFEST_SHA)
    require(stage_result["preflight"] == "PASS", "Stage preflight failed")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    require(audit.get("passed") is True and audit.get("failures") == [] and
            audit.get("visual_review_pending") is False, "Independent audit incomplete")
    require(audit.get("manifest") == binding(MANIFEST), "Audit is bound to another manifest")
    require(audit.get("native_candidate_record") == manifest["native_candidate_record"] and
            audit.get("human_candidate_record") == manifest["human_candidate_record"],
            "Audit source authority binding differs")
    review = audit.get("reviewed_pages")
    require(isinstance(review, list) and len(review) == 11, "Wrong audit page count")
    audited = {x["page"]: x for x in review}
    pages = {x["page"]: x for x in manifest["pages"]}
    require(len(audited) == len(pages) == 11 and audited.keys() == pages.keys(),
            "Audit and stage page sets differ")
    for page_id, page in pages.items():
        a = audited[page_id]
        require(a["authority_kind"] == page["authority_kind"] and a["source"] == page["source"] and
                a["source_crop"] == page["source_crop"] and a["text_edit"] == page["text_edit"] and
                a["active_model_changes"] == page["active_model_changes"] and
                a["broad_crop_pixel_exact"] is True, "Audit disagrees on page " + page_id)
        require(Path(page["source"]["path"]).resolve().is_relative_to(SOURCE_ARCHIVE),
                "Source outside original archive")
        for kind in ("txt", "json", "notes", "preview"):
            current = Path(page["canonical_quartet"][kind]["path"]).resolve()
            require(current.is_relative_to(CANONICAL) and sha(current) ==
                    page["canonical_quartet"][kind]["sha256"], "Current predecessor changed")
    require({x["page"] for x in manifest["pages"] if x["authority_kind"] == "native"} ==
            {"AP737", "AP181", "RQ683", "KU601", "RQ781", "MC371", "AP441"},
            "Native page scope changed")
    require({x["page"] for x in manifest["pages"] if x["authority_kind"] == "direct-human"} ==
            {"AP531", "XM181", "AS201", "AP313"}, "Human page scope changed")
    require(manifest["confirmed_no_change"]["page"] == "DT001" and
            manifest["confirmed_no_change"]["current_function"] == "A", "DT001 should remain unchanged")
    return manifest, {"preflight": "PASS", "pages": 11, "canonical_quartet_files": 44,
                      "manifest": binding(MANIFEST), "independent_audit": binding(AUDIT),
                      "repository_writes": 0, "original_scan_writes": 0}


def publish() -> dict:
    manifest, report = preflight()
    staged = []
    replaced = []
    try:
        for page in manifest["pages"]:
            for kind in ("txt", "json", "notes", "preview"):
                current = Path(page["canonical_quartet"][kind]["path"]).resolve()
                candidate = Path(page["candidate_quartet"][kind]["path"]).resolve()
                predecessor = Path(page["before_quartet"][kind]["path"]).resolve()
                require(candidate.is_relative_to(stage.STAGE.resolve()) and
                        predecessor.is_relative_to(stage.STAGE.resolve()), "Candidate path escaped private stage")
                require(sha(candidate) == page["candidate_quartet"][kind]["sha256"] and
                        sha(predecessor) == page["before_quartet"][kind]["sha256"],
                        "Candidate or predecessor changed")
                temp = current.with_name(current.name + ".eleven-function.tmp")
                require(not temp.exists(), "Publication temporary file already exists: " + str(temp))
                shutil.copyfile(candidate, temp)
                require(sha(temp) == sha(candidate), "Temporary candidate copy differs")
                staged.append((current, temp, predecessor, page["canonical_quartet"][kind]["sha256"],
                               page["candidate_quartet"][kind]["sha256"]))
        for current, temp, _, old_sha, next_sha in staged:
            require(sha(current) == old_sha and sha(temp) == next_sha, "Publication race or damaged temporary copy")
        for current, temp, predecessor, _, _ in staged:
            temp.replace(current)
            replaced.append((current, predecessor))
        for current, _, _, _, next_sha in staged:
            require(sha(current) == next_sha, "Published file differs from candidate")
    except Exception:
        # Best-effort rollback uses the exact frozen predecessor bytes. Any failed
        # rollback is reported rather than silently leaving a mixed publication.
        failures = []
        for current, predecessor in reversed(replaced):
            try:
                shutil.copyfile(predecessor, current)
            except Exception as exc:
                failures.append(str(current) + ": " + str(exc))
        if failures:
            raise RuntimeError("Publication failed and rollback was incomplete: " + "; ".join(failures))
        raise
    finally:
        for _, temp, _, _, _ in staged:
            if temp.exists():
                temp.unlink()
    receipt = {"published_utc": datetime.now(timezone.utc).isoformat(),
               "manifest": binding(MANIFEST), "independent_audit": binding(AUDIT),
               "pages": 11, "canonical_quartet_files": 44,
               "canonical_destinations": [binding(current) for current, _, _, _, _ in staged],
               "repository_writes": 0, "original_scan_writes": 0}
    RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"published": True, "receipt": binding(RECEIPT), **report}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    print(json.dumps(preflight()[1] if args.preflight else publish(), indent=2))

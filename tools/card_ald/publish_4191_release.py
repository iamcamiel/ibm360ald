"""Publish the audited 4191 quartet corrections to the working collection.

The established reviewed export/import tools mirror these to the repository.
This script guards every predecessor and source hash, keeps recovery copies,
and writes a current-quartet acceptance for the export selector.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


REPO = Path(__file__).resolve().parents[2]
WORKSPACE = REPO.parent
STAGE = WORKSPACE / "tmp/ald-text/ald/card-4191-release"
MANIFEST = STAGE / "manifest.json"
OVERLAY = REPO / "notes/Card-ALD/4191 release overlay audit.json"
AUDIT = WORKSPACE / "tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/4191 source correction current audit.json"
RECEIPT = STAGE / "4191 canonical publication receipt.json"
BACKUP = STAGE / "before-publication"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def artifact(path):
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def main():
    manifest = read(MANIFEST)
    overlay = read(OVERLAY)
    assert manifest["schema"] == "card-4191-scoped-source-correction-release-v1"
    assert manifest["status"] == "independently audited private release; not yet published"
    assert overlay["stage_manifest_sha256"] == digest(MANIFEST.read_bytes())
    assert overlay["pages"] == 68 and overlay["blocks"] == 644
    assert overlay["corrected_pages"] == len(manifest["records"]) == 45
    assert overlay["adder_slices"] == overlay["five_driver_slices"] == 60
    assert not overlay["flags"] and not overlay["topology_anomalies"]
    assert not AUDIT.exists() and not RECEIPT.exists() and not BACKUP.exists(), \
        "Prior 4191 publication exists; inspect it before rerunning"
    writes = []
    page_records = []
    for record in manifest["records"]:
        page = record["page"]
        folder = STAGE / page
        quartet = {}
        for key, before_key, after_key in (
            ("txt", "text_before_sha256", "release_text_sha256"),
            ("json", "json_before_sha256", "release_json_sha256"),
            ("notes", "notes_before_sha256", "release_notes_sha256"),
            ("preview", "preview_before_sha256", "release_preview_sha256"),
        ):
            source_key = {"txt": "owner_text", "json": "owner_json",
                          "notes": "owner_notes", "preview": "owner_preview"}[key]
            target = Path(record[source_key])
            candidate = folder / target.name
            assert target.is_file() and candidate.is_file()
            assert target.resolve().is_relative_to(
                (WORKSPACE / "ALD_Visual_Transcriptions/ALD Diagrams").resolve())
            assert digest(target.read_bytes()) == record[before_key], (page, key)
            assert digest(candidate.read_bytes()) == record[after_key], (page, key)
            writes.append((page, key, target, candidate, record[before_key]))
            quartet[key] = {"path": str(target), "sha256": record[after_key]}
        assert digest(Path(record["scan"]).read_bytes()) == record["scan_sha256"]
        assert digest(Path(record["text"]).read_bytes()) == record["text_before_sha256"]
        assert digest(Path(record["json"]).read_bytes()) == record["json_before_sha256"]
        page_records.append({
            "page": page,
            "eligible": True,
            "artifact_schema": "reviewed-current-quartet-v1",
            "source": {"path": record["scan"], "sha256": record["scan_sha256"]},
            "current_quartet": quartet,
            "before_text_sha256": record["text_before_sha256"],
            "before_json_sha256": record["json_before_sha256"],
            "field_edits": record["field_edit_count"],
            "wiring_edited": record["wiring_edits"],
            "checks": {
                "source_scan_bound": True,
                "accepted_predecessor_exact": True,
                "all_field_cells_exact": True,
                "inferred_contacts_supported_by_peer_portions": True,
                "wiring_matches_human_and_native_review": True,
                "complete_4191_corpus_topology_passed": True,
                "preview_reproduced_pixel_exact": True,
                "current_quartet_hashes_match": True,
            },
        })
    assert len(writes) == 45 * 4
    audit = {
        "schema": "4191-scoped-source-correction-current-quartet-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "reviewer": "coordinator independent scoped audit",
        "scope": "Exact 4191 field and wiring corrections on prior accepted AP pages; not a fresh whole-page transcription",
        "release_manifest": {"path": str(MANIFEST), "sha256": digest(MANIFEST.read_bytes())},
        "overlay_audit": {"path": str(OVERLAY), "sha256": digest(OVERLAY.read_bytes())},
        "pages": page_records,
    }
    backup_files = []
    try:
        for page, key, target, _, before in writes:
            saved = BACKUP / page / target.name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
            assert digest(saved.read_bytes()) == before
            backup_files.append((target, saved))
        for _, _, target, candidate, _ in writes:
            target.write_bytes(candidate.read_bytes())
        for page in page_records:
            for entry in page["current_quartet"].values():
                assert digest(Path(entry["path"]).read_bytes()) == entry["sha256"], page["page"]
        AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        receipt = {
            "schema": "4191-guarded-canonical-publication-v1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "passed": True,
            "page_count": 45,
            "current_audit": artifact(AUDIT),
            "release_manifest": artifact(MANIFEST),
            "backup_root": str(BACKUP),
            "pages": [{"page": page["page"], "source": page["source"],
                       "current_quartet": page["current_quartet"]}
                      for page in page_records],
        }
        RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    except Exception:
        AUDIT.unlink(missing_ok=True)
        RECEIPT.unlink(missing_ok=True)
        for target, saved in backup_files:
            shutil.copy2(saved, target)
        raise
    print(f"Published and independently hash-verified {len(page_records)} working quartets; "
          f"current audit: {AUDIT}")


if __name__ == "__main__":
    main()

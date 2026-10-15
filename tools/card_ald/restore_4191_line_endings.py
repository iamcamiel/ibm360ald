"""Preserve the original CRLF style after the accepted 4191 correction.

This changes bytes only. It verifies normalized UTF-8 text and parsed JSON
are identical, preserves before-files, and records a fresh accepted quartet.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


REPO = Path(__file__).resolve().parents[2]
WORKSPACE = REPO.parent
STAGE = WORKSPACE / "tmp/ald-text/ald/card-4191-release"
BASE = STAGE / "manifest.json"
OLD_AUDIT = WORKSPACE / "tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/4191 source correction current audit.json"
AUDIT = OLD_AUDIT.with_name("4191 line ending preservation current audit.json")
MANIFEST = STAGE / "4191 CRLF preservation manifest.json"
RECEIPT = STAGE / "4191 CRLF preservation publication receipt.json"
BACKUP = STAGE / "before-crlf-preservation"
ORIGINAL = STAGE / "before-publication"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(raw):
    return raw.replace(b"\r\n", b"\n")


def main():
    base = load(BASE)
    predecessor = load(OLD_AUDIT)
    assert predecessor["passed"] is True and len(predecessor["pages"]) == 45
    assert not AUDIT.exists() and not MANIFEST.exists() and not RECEIPT.exists() and not BACKUP.exists()
    by_page = {page["page"]: page for page in predecessor["pages"]}
    records = []
    writes = []
    for record in base["records"]:
        page = record["page"]
        old_page = by_page[page]
        quartet = {}
        for kind, target_key in (("txt", "owner_text"), ("json", "owner_json"),
                                 ("notes", "owner_notes"), ("preview", "owner_preview")):
            target = Path(record[target_key])
            raw = target.read_bytes()
            assert sha(raw) == old_page["current_quartet"][kind]["sha256"]
            original = ORIGINAL / page / target.name
            if kind != "preview":
                before = original.read_bytes()
                assert before.count(b"\r\n") == before.count(b"\n") > 0
                after = normalize(raw).replace(b"\n", b"\r\n")
                assert normalize(after) == normalize(raw)
                assert after.count(b"\r\n") == after.count(b"\n")
                if kind == "json":
                    assert json.loads(after) == json.loads(raw)
                else:
                    assert after.decode("utf-8").replace("\r\n", "\n") == raw.decode("utf-8").replace("\r\n", "\n")
            else:
                after = raw
            writes.append((page, kind, target, raw, after))
            quartet[kind] = {"path": str(target), "sha256": sha(after)}
        assert sha(Path(record["scan"]).read_bytes()) == record["scan_sha256"]
        records.append({
            "page": page, "eligible": True,
            "artifact_schema": "reviewed-current-quartet-v1",
            "source": {"path": record["scan"], "sha256": record["scan_sha256"]},
            "current_quartet": quartet,
            "prior_quartet": old_page["current_quartet"],
            "checks": {
                "original_crlf_style_restored": True,
                "utf8_glyphs_and_grid_unchanged": True,
                "json_structure_unchanged": True,
                "source_scan_and_prior_acceptance_bound": True,
                "pixel_preview_unchanged": True,
                "current_quartet_hashes_match": True,
            },
        })
    assert len(writes) == 180
    audit = {
        "schema": "4191-crlf-preservation-current-quartet-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "reviewer": "coordinator byte-equivalence audit",
        "scope": "Only restore original CRLF line endings; source-accepted 4191 glyphs, JSON structure and preview pixels unchanged",
        "predecessor_audit": {"path": str(OLD_AUDIT), "sha256": sha(OLD_AUDIT.read_bytes())},
        "pages": records,
    }
    try:
        for page, _, target, raw, _ in writes:
            saved = BACKUP / page / target.name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
            assert saved.read_bytes() == raw
        for _, _, target, _, after in writes:
            if target.read_bytes() != after:
                target.write_bytes(after)
        for page in records:
            for item in page["current_quartet"].values():
                assert sha(Path(item["path"]).read_bytes()) == item["sha256"]
        manifest = {
            "schema": "4191-crlf-byte-only-preservation-v1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "prior_release_manifest": {"path": str(BASE), "sha256": sha(BASE.read_bytes())},
            "pages": [{"page": record["page"], "source": record["source"],
                       "before": record["prior_quartet"], "after": record["current_quartet"]}
                      for record in records],
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
        receipt = {
            "schema": "4191-crlf-preservation-publication-v1",
            "passed": True,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "page_count": 45,
            "manifest": {"path": str(MANIFEST), "sha256": sha(MANIFEST.read_bytes())},
            "current_audit": {"path": str(AUDIT), "sha256": sha(AUDIT.read_bytes())},
            "backup_root": str(BACKUP),
        }
        RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    except Exception:
        for _, _, target, raw, _ in writes:
            target.write_bytes(raw)
        for path in (AUDIT, MANIFEST, RECEIPT):
            path.unlink(missing_ok=True)
        raise
    print(f"Restored original CRLF style on 45 accepted working quartets: {AUDIT}")


if __name__ == "__main__":
    main()

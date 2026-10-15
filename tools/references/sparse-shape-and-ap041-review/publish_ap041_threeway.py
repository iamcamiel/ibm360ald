"""Publish independently accepted AP041 native portion labels to canonical files."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "three-way-private-stage/AP041 three-way private stage manifest.json"
AUDIT = ROOT / "AP041 independent three-way private-stage acceptance.json"
RECEIPT = ROOT / "AP041 three-way canonical publication receipt.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    stage = json.loads(STAGE.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "PASS" and not audit["failures"] and audit["checks"] >= 90
    assert Path(audit["manifest"]["path"]).resolve() == STAGE.resolve()
    assert sha(STAGE) == audit["manifest"]["sha256"]
    assert sha(Path(stage["original_tiff"]["path"])) == stage["original_tiff"]["sha256"]
    assert sha(Path(stage["source_candidate"]["path"])) == stage["source_candidate"]["sha256"]
    old, new, destinations = {}, {}, {}
    for key in ("txt", "json", "notes", "preview"):
        before = stage["before_quartet"][key]
        after = stage["candidate_quartet"][key]
        target = stage["canonical_before_quartet"][key]
        source = Path(after["path"])
        destination = Path(target["path"])
        assert source.is_file() and sha(source) == after["sha256"]
        assert destination.is_file() and sha(destination) == before["sha256"] == target["sha256"]
        assert destination.resolve().is_relative_to((Path("D:/Github/IBM360/ALD_Visual_Transcriptions") / "ALD Diagrams").resolve())
        old[key], new[key], destinations[key] = destination.read_bytes(), source.read_bytes(), destination
    assert not RECEIPT.exists(), "Existing publication receipt requires a separate audit"
    written = []
    try:
        for key in ("txt", "json", "notes", "preview"):
            destinations[key].write_bytes(new[key])
            assert sha(destinations[key]) == stage["candidate_quartet"][key]["sha256"]
            written.append(key)
    except BaseException:
        for key in reversed(written):
            destinations[key].write_bytes(old[key])
        raise
    receipt = {
        "schema": "ap041-three-way-canonical-publication-v1",
        "published_utc": datetime.now(timezone.utc).isoformat(),
        "stage": {"path": str(STAGE), "sha256": sha(STAGE)},
        "independent_acceptance": {"path": str(AUDIT), "sha256": sha(AUDIT)},
        "source_tiff": stage["original_tiff"],
        "canonical_destinations": [
            {"artifact": key, "path": str(destinations[key]), "before_sha256": stage["before_quartet"][key]["sha256"], "sha256": sha(destinations[key])}
            for key in ("txt", "json", "notes", "preview")
        ],
    }
    RECEIPT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"published": len(written), "receipt": str(RECEIPT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

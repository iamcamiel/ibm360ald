"""Compile native-scan verdicts for the SLT supply-contact review queue.

The three reviewer ledgers are intentionally kept outside the repository while
native crops are being checked.  This tool refuses incomplete or stale ledgers,
then records their source bindings and the remaining manual-review cases.
"""

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import csv
import json


ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / "csv/Pin validation/SLT supply-pin review queue.csv"
EVIDENCE = ROOT.parent / "tmp/ald-text/ald/slt-supply-visual"
REPORT = ROOT / "notes/Pin validation/SLT supply-pin visual review.json"
CSV = ROOT / "csv/Pin validation/SLT supply-pin visual review.csv"
UNRESOLVED = ROOT / "csv/Pin validation/SLT supply-pin questions.csv"
OVERRIDES = ROOT / "notes/Pin validation/SLT supply-pin coordinator visual overrides.json"
VERDICTS = {"clear_misread", "genuine_supply_tie", "other_genuine_print", "unresolved"}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    with QUEUE.open(encoding="utf-8-sig", newline="") as stream:
        queue = list(csv.DictReader(stream))
    records = {}
    ledgers = []
    for owner in "abc":
        path = EVIDENCE / owner / "verdicts.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["rows"]
        ledgers.append({"path": str(path), "sha256": digest(path), "rows": len(rows)})
        for row in rows:
            index = int(row["queue_index"])
            assert index not in records, f"duplicate queue index {index}"
            assert 0 <= index < len(queue), f"out-of-range queue index {index}"
            original = queue[index]
            for key in ("page", "block"):
                assert str(row[key]) == str(original[key]), (index, key)
            # Some reviewers retain the printed numeric bank qualifier (6B06),
            # whereas the queue's contact field contains its bare SLT contact.
            assert row["contact"] in (original["contact"], original["printed_pin"]), (index, "contact")
            assert int(row["pin_index"]) == int(original["pin_index"]), index
            assert row["verdict"] in VERDICTS, index
            crop = Path(row["crop_path"])
            scan = Path(row["scan_path"])
            assert crop.is_file() and scan.is_file(), index
            assert digest(crop) == row["crop_sha256"], (index, "crop hash")
            assert digest(scan) == row["scan_sha256"], (index, "scan hash")
            assert len(row["crop_rect"]) == 4, index
            if row["verdict"] == "clear_misread":
                assert row.get("proposed_pin"), index
            records[index] = row
    assert set(records) == set(range(len(queue))), sorted(set(range(len(queue))) - set(records))
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    for update in overrides["rows"]:
        index = update["queue_index"]
        old = records[index]
        bound = sha256(json.dumps(old, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        assert bound == update["reviewer_row_sha256"], (index, "stale coordinator override")
        records[index] = {**old, **update["replace"], "coordinator_review": True}
        crop = Path(records[index]["crop_path"])
        assert digest(crop) == records[index]["crop_sha256"], (index, "coordinator crop")

    fields = ["queue_index", "page", "folder", "block", "card_type", "portion",
              "location", "modeled_pin", "native_reading", "verdict", "proposed_pin",
              "rationale", "scan_path", "scan_sha256", "crop_path", "crop_sha256",
              "crop_rect", "question", "best_guess", "answer"]
    combined = []
    for index, original in enumerate(queue):
        reviewed = records[index]
        combined.append({
            "queue_index": index,
            "page": original["page"], "folder": original["folder"],
            "block": original["block"], "card_type": original["card_type"],
            "portion": original["portion"], "location": original["location"],
            "modeled_pin": original["printed_pin"],
            "native_reading": reviewed.get("native_reading"),
            "verdict": reviewed["verdict"],
            "proposed_pin": reviewed.get("proposed_pin"),
            "rationale": reviewed["rationale"],
            "scan_path": reviewed["scan_path"],
            "scan_sha256": reviewed["scan_sha256"],
            "crop_path": reviewed["crop_path"],
            "crop_sha256": reviewed["crop_sha256"],
            "crop_rect": reviewed["crop_rect"],
            "question": reviewed.get("question", ""),
            "best_guess": reviewed.get("best_guess", ""),
            "answer": "",
        })
    CSV.parent.mkdir(parents=True, exist_ok=True)
    for path, rows in ((CSV, combined), (UNRESOLVED, [r for r in combined if r["verdict"] == "unresolved"])):
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in sorted(rows, key=lambda r: (r["page"], r["block"], r["queue_index"])):
                writer.writerow({**row, "crop_rect": json.dumps(row["crop_rect"])})
    report = {
        "schema": "slt-supply-pin-native-visual-review-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "queue": {"path": str(QUEUE.relative_to(ROOT)), "sha256": digest(QUEUE), "rows": len(queue)},
        "reviewer_ledgers": ledgers,
        "coordinator_review": {"path": str(OVERRIDES.relative_to(ROOT)), "sha256": digest(OVERRIDES)},
        "counts": dict(Counter(row["verdict"] for row in combined)),
        "literal_outcomes": dict(Counter("misread" if row["verdict"] == "clear_misread" else "needs_physical_check" if row["verdict"] == "unresolved" else "matches_scan" for row in combined)),
        "rows": combined,
        "review_csv": {"path": str(CSV.relative_to(ROOT)), "sha256": digest(CSV)},
        "questions_csv": {"path": str(UNRESOLVED.relative_to(ROOT)), "sha256": digest(UNRESOLVED)},
        "interpretation": "This is a literal native-scan inspection. Local-tie classifications are topology candidates, not proof of a supply connection. Legible printed contacts are preserved; electrical interpretation of apparent rule exceptions requires a separate card-level review. Clear misreads are recorded for source-bound correction; this report does not change ALD text or page models.",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"queue": len(queue), "counts": report["counts"], "questions": sum(r["verdict"] == "unresolved" for r in combined)}, indent=2))


if __name__ == "__main__":
    main()

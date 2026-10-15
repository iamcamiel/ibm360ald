"""Compare the complete 4191 corpus with private corrected TXT/JSON candidates.

This is an assessment only: published ALD and JSON files are never changed.
"""

from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import audit_4191_occurrences as audit


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
STAGE = WORKSPACE / "tmp/ald-text/ald/card-4191-combined-stage"
REPORT = ROOT / "notes/Card-ALD/4191 corrected overlay audit.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true",
                        help="audit metadata-refreshed release rather than the private candidate")
    args = parser.parse_args()
    stage = STAGE if not args.release else WORKSPACE / "tmp/ald-text/ald/card-4191-release"
    report = REPORT if not args.release else ROOT / "notes/Card-ALD/4191 release overlay audit.json"
    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="audit-4191-", dir=WORKSPACE / "tmp") as scratch:
        overlay = Path(scratch)
        models = overlay / "json"
        texts = overlay / "txt"
        models.mkdir()
        texts.mkdir()
        for source in audit.MODEL_DIR.glob("*.json"):
            shutil.copy2(source, models / source.name)
        for source in audit.TEXT_DIR.glob("*.txt"):
            shutil.copy2(source, texts / source.name)
        for record in manifest["records"]:
            folder = stage / record["page"]
            for key, destination in (("json", models), ("text", texts)):
                filename = Path(record[key]).name
                shutil.copy2(folder / filename, destination / filename)
        audit.MODEL_DIR = models
        audit.TEXT_DIR = texts
        audit.ROOT = WORKSPACE
        rows, pages, topology = audit.scan()

    flags = Counter(flag for row in rows for flag in row["flags"].split(";") if flag)
    remaining = [{key: row[key] for key in (
        "page", "block", "portion", "function", "expected_primary_function",
        "circuit_identifier", "expected_circuit_identifier", "pins",
        "invalid_pinlike_labels", "unexpected_pins", "flags")}
        for row in rows if row["flags"]]
    anomalies = [row for row in topology if
                 row["published_JSON_linked_A_driver_labels"] != 5 or
                 row["published_JSON_combined_driver_nets"] or
                 row["pin_pair_disagreements"]]
    result = {
        "scope": "Published AP pages overlaid with audited 4191 release" if args.release
                 else "Published AP pages overlaid with private combined 4191 candidates",
        "candidate_status": manifest["status"],
        "stage_manifest_sha256": hashlib.sha256((stage / "manifest.json").read_bytes()).hexdigest(),
        "pages": len(pages),
        "corrected_pages": len(manifest["records"]),
        "blocks": len(rows),
        "portions": len({row["portion"] for row in rows}),
        "adder_slices": len(topology),
        "flags": dict(sorted(flags.items())),
        "flagged_blocks": remaining,
        "five_driver_slices": sum(
            row["published_JSON_linked_A_driver_labels"] == 5 for row in topology),
        "combined_driver_slices": sum(
            bool(row["published_JSON_combined_driver_nets"]) for row in topology),
        "topology_anomalies": anomalies,
    }
    report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in {"flagged_blocks", "topology_anomalies"}},
                     indent=2))
    print("Flagged blocks:", len(remaining), "Topology anomalies:", len(anomalies))
    print("Report:", report)


if __name__ == "__main__":
    main()

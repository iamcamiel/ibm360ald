"""Stage and publish the human-confirmed AP411 4633J4 unit reading."""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path

from release_463x_source_corrections import (
    WORKSPACE, CANONICAL, REPO, sha, preview, append_note,
)


STEM = "AP411 PARALLEL ADDER BIT 41"
STAGE = WORKSPACE / "tmp/ald-text/ald/card-463x-release/ap411-human-stage"
AUDIT = WORKSPACE / "tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/4633 AP411 human unit current audit.json"
REPO_AUDIT = REPO / "notes/Card-ALD/4633 AP411 human unit current audit.json"
SOURCE = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder") / f"{STEM}.tif"


def files(root):
    return {
        "txt": root / f"{STEM}.txt",
        "json": root / f"{STEM}.json",
        "notes": root / f"{STEM} review notes.txt",
        "preview": root / f"{STEM} JuliaMono preview.png",
    }


def stage():
    current = files(CANONICAL)
    prior = {kind: path.read_bytes() for kind, path in current.items()}
    after = dict(prior)
    rows = prior["txt"].decode("utf-8").splitlines(keepends=True)
    assert len(rows) == 103 and all(len(row.rstrip("\r\n")) == 245 for row in rows)
    assert rows[40].count("U03A1") == 1
    rows[40] = rows[40].replace("U03A1", "U03AM")
    after["txt"] = "".join(rows).encode("utf-8")

    model = json.loads(prior["json"].decode("utf-8"))
    node = next(n for n in model["nodes"] if n["id"] == "AP")
    assert node["card_type"] == "4633" and node["portion"] == "J4" and node["unit"] == "U03A1"
    raw = prior["json"]
    assert raw.count(b'"unit": "U03A1"') == 1
    raw = raw.replace(b'"unit": "U03A1"', b'"unit": "U03AM"')
    old_literal = b'"literal": "U03A1"'
    assert raw.count(old_literal) == 1
    raw = raw.replace(old_literal, b'"literal": "U03AM"')
    old_kind = b'"kind": "native literal unit"'
    assert raw.count(old_kind) == 1
    raw = raw.replace(old_kind, b'"kind": "direct human-confirmed unit"')
    old_evidence = b'Original-resolution AP-unit-full-resolution.png shows final numeral1; preserve literal rather than replacing with U03AM.'
    assert raw.count(old_evidence) == 1
    new_evidence = b'Direct human review of the enlarged AP411 crop reads U03AM; AP451 and other 4633J4 blocks independently agree.'
    after["json"] = raw.replace(old_evidence, new_evidence)

    note = prior["notes"].decode("utf-8")
    assert note.count("\"literal\": \"U03A1\"") == 2
    assert note.count("Original-resolution AP-unit-full-resolution.png shows final numeral1; preserve literal rather than replacing with U03AM.") == 2
    note = note.replace('"kind": "native literal unit"', '"kind": "direct human-confirmed unit"')
    note = note.replace('"literal": "U03A1"', '"literal": "U03AM"')
    note = note.replace(
        "Original-resolution AP-unit-full-resolution.png shows final numeral1; preserve literal rather than replacing with U03AM.",
        "Direct human review of the enlarged AP411 crop reads U03AM; AP451 and other 4633J4 blocks independently agree.",
    )
    after["notes"] = append_note(
        note.encode("utf-8"),
        "Card-ALD 4633 direct human correction, 2026-10-15: AP411 block AP (4633J4) circuit identifier is U03AM. "
        "Earlier source review read U03A1; the user re-read the displayed original crop as U03AM.",
    )
    after["preview"] = preview(after["txt"])
    parsed = json.loads(after["json"].decode("utf-8"))
    assert next(n for n in parsed["nodes"] if n["id"] == "AP")["unit"] == "U03AM"
    assert after["txt"].decode("utf-8").splitlines()[40].count("U03AM") == 1
    assert SOURCE.is_file()
    STAGE.mkdir(parents=True, exist_ok=True)
    staged = files(STAGE)
    for kind, content in after.items():
        staged[kind].write_bytes(content)
    manifest = {
        "schema": "card-4633-ap411-human-stage-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "human_quote": "I read that crop as U03AM",
        "page": "AP411",
        "source": {"path": str(SOURCE), "sha256": sha(SOURCE.read_bytes())},
        "prior_quartet": {kind: {"path": str(current[kind]), "sha256": sha(content)} for kind, content in prior.items()},
        "staged_quartet": {kind: {"path": str(staged[kind]), "sha256": sha(content)} for kind, content in after.items()},
        "checks": {
            "direct_human_crop_reading": True,
            "same_portion_cross_check": True,
            "one_unit_label_and_node_corrected": True,
            "source_and_quartet_hashes_bound": True,
            "utf8_grid_json_preview_verified": True,
        },
    }
    (STAGE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Staged AP411 human unit correction")


def publish():
    manifest_path = STAGE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "card-4633-ap411-human-stage-v1"
    assert sha(Path(manifest["source"]["path"]).read_bytes()) == manifest["source"]["sha256"]
    for kind, old in manifest["prior_quartet"].items():
        new = manifest["staged_quartet"][kind]
        assert sha(Path(old["path"]).read_bytes()) == old["sha256"]
        assert sha(Path(new["path"]).read_bytes()) == new["sha256"]
    for kind, old in manifest["prior_quartet"].items():
        Path(old["path"]).write_bytes(Path(manifest["staged_quartet"][kind]["path"]).read_bytes())
    current = {kind: {"path": old["path"], "sha256": manifest["staged_quartet"][kind]["sha256"]}
               for kind, old in manifest["prior_quartet"].items()}
    assert all(sha(Path(x["path"]).read_bytes()) == x["sha256"] for x in current.values())
    audit = {
        "schema": "card-4633-ap411-human-current-audit-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "reviewer": "Direct human reading of original crop, staged and checked by coordinator",
        "scope": "AP411 4633J4 circuit identifier only",
        "stage_manifest": {"path": str(manifest_path), "sha256": sha(manifest_path.read_bytes())},
        "pages": [{
            "page": "AP411", "eligible": True,
            "artifact_schema": "reviewed-current-quartet-v1",
            "source": manifest["source"], "prior_quartet": manifest["prior_quartet"],
            "current_quartet": current, "checks": manifest["checks"],
        }],
    }
    content = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    AUDIT.write_text(content, encoding="utf-8")
    REPO_AUDIT.write_text(content, encoding="utf-8")
    print("Published AP411 human unit correction")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("stage", "publish"))
    stage() if parser.parse_args().action == "stage" else publish()

"""Publish the native-verified AP511 4633A2 function correction."""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path

from release_463x_source_corrections import (
    WORKSPACE, CANONICAL, REPO, sha, preview, append_note,
)


STAGE = WORKSPACE / "tmp/ald-text/ald/card-463x-release/second-stage"
AUDIT = WORKSPACE / "tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/463x second source correction current audit.json"
REPO_AUDIT = REPO / "notes/Card-ALD/463x second source correction current audit.json"
PAGES = {
    "AP511": "AP511 PARALLEL ADDER BIT 51",
}


def paths(stem):
    return {
        "txt": CANONICAL / f"{stem}.txt",
        "json": CANONICAL / f"{stem}.json",
        "notes": CANONICAL / f"{stem} review notes.txt",
        "preview": CANONICAL / f"{stem} JuliaMono preview.png",
    }


def stage():
    records = []
    STAGE.mkdir(parents=True, exist_ok=True)
    for page, stem in PAGES.items():
        quartet = paths(stem)
        before = {kind: file.read_bytes() for kind, file in quartet.items()}
        after = dict(before)
        assert before["txt"].count(b"\xe2\x94\x82AR    \xe2\x94\x82") >= 1
        lines = before["txt"].decode("utf-8").splitlines(keepends=True)
        assert lines[17][119:127] == "│AR    │"
        lines[17] = lines[17][:120] + "OR" + lines[17][122:]
        after["txt"] = "".join(lines).encode("utf-8")
        raw = before["json"]
        begin = raw.index(b'"id": "AS"')
        end = raw.index(b'"id": "AT"', begin)
        block = raw[begin:end]
        assert block.count(b'"function": "AR"') == 1 and b'"portion": "A2"' in block
        after["json"] = raw[:begin] + block.replace(b'"function": "AR"', b'"function": "OR"') + raw[end:]
        finding = "AP511 block AS (4633A2) visibly reads OR, not AR; see notes/Card-ALD/evidence/AP511-463x-variant-native.png. Its function now agrees with thirteen other A2 observations."
        after["preview"] = preview(after["txt"])
        after["notes"] = append_note(before["notes"], "Card-ALD 4633 native correction, 2026-10-15: " + finding)
        rows = after["txt"].decode("utf-8").splitlines()
        assert len(rows) == 103 and all(len(row) == 245 for row in rows)
        model = json.loads(after["json"].decode("utf-8"))
        assert next(n for n in model["nodes"] if n["id"] == "AS")["function"] == "OR"
        target = STAGE / stem
        target.mkdir(exist_ok=True)
        for kind, data in after.items():
            (target / quartet[kind].name).write_bytes(data)
        source = next(Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder").glob(stem + ".tif"))
        records.append({
            "page": page,
            "source": {"path": str(source), "sha256": sha(source.read_bytes())},
            "prior_quartet": {kind: {"path": str(quartet[kind]), "sha256": sha(data)} for kind, data in before.items()},
            "staged_quartet": {kind: {"path": str(target / quartet[kind].name), "sha256": sha(data)} for kind, data in after.items()},
            "checks": {
                "native_crop_independently_read": True,
                "same_portion_cross_check": True,
                "only_named_node_field_changed": True,
                "utf8_grid_json_preview_verified": True,
                "source_and_quartet_hashes_bound": True,
            },
        })
    manifest = {"schema": "card-463x-second-source-stage-v1",
                "created_utc": datetime.now(timezone.utc).isoformat(), "records": records}
    (STAGE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Staged native AP511 correction")


def publish():
    manifest = json.loads((STAGE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "card-463x-second-source-stage-v1"
    assert {r["page"] for r in manifest["records"]} == set(PAGES)
    for record in manifest["records"]:
        assert sha(Path(record["source"]["path"]).read_bytes()) == record["source"]["sha256"]
        for kind, before in record["prior_quartet"].items():
            staged = record["staged_quartet"][kind]
            assert sha(Path(before["path"]).read_bytes()) == before["sha256"]
            assert sha(Path(staged["path"]).read_bytes()) == staged["sha256"]
    for record in manifest["records"]:
        for kind, before in record["prior_quartet"].items():
            Path(before["path"]).write_bytes(Path(record["staged_quartet"][kind]["path"]).read_bytes())
    audit = {"schema": "card-463x-second-source-current-audit-v1",
             "created_utc": datetime.now(timezone.utc).isoformat(),
             "passed": True,
             "reviewer": "Coordinator independent native-source review",
             "scope": "AP511 4633A2 function only",
             "stage_manifest": {"path": str(STAGE / "manifest.json"),
                                "sha256": sha((STAGE / "manifest.json").read_bytes())},
             "pages": []}
    for record in manifest["records"]:
        current = {kind: {"path": before["path"],
                          "sha256": record["staged_quartet"][kind]["sha256"]}
                   for kind, before in record["prior_quartet"].items()}
        assert all(sha(Path(x["path"]).read_bytes()) == x["sha256"] for x in current.values())
        audit["pages"].append({"page": record["page"], "eligible": True,
                               "artifact_schema": "reviewed-current-quartet-v1",
                               "source": record["source"],
                               "prior_quartet": record["prior_quartet"],
                               "current_quartet": current,
                               "checks": record["checks"]})
    raw = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    AUDIT.write_text(raw, encoding="utf-8")
    REPO_AUDIT.write_text(raw, encoding="utf-8")
    print("Published native AP511 correction")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("stage", "publish"))
    action = parser.parse_args().action
    stage() if action == "stage" else publish()

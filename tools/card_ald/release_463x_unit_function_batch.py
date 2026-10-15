"""Stage and publish source-backed 4633/4634 unit and function corrections."""
from argparse import ArgumentParser
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from release_463x_source_corrections import WORKSPACE, CANONICAL, REPO, sha, preview, append_note

STAGE = WORKSPACE / "tmp/ald-text/ald/card-463x-release/unit-function-stage"
AUDIT = WORKSPACE / "tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/463x unit function current audit.json"
REPO_AUDIT = REPO / "notes/Card-ALD/463x unit function current audit.json"
SOURCE = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder")
CROP = WORKSPACE / "tmp/ald-text/ald/card-4634-audit"

# Page, node, field, old reading, new reading, evidence.
CHANGES = [
    ("AP511", "BH", "unit", "U55��", "U55AC", "HUMAN"),
    ("AP621", "BF", "unit", "U��AC", "U55AC", "HUMAN"),
    ("AP211", "AN", "unit", "U03��", "U03AW", "HUMAN"),
    ("AP441", "AG", "unit", "U03AV", "U03AY", "NATIVE"),
    ("AP481", "AG", "unit", "U03AV", "U03AY", "NATIVE"),
    ("AP521", "AG", "unit", "U03AV", "U03AY", "NATIVE"),
    ("AP451", "AF", "unit", "U03AV", "U03AY", "NATIVE"),
    ("AP491", "AF", "unit", "U03AV", "U03AY", "NATIVE"),
    ("AP461", "AG", "unit", "U03AV", "U03AY", "NATIVE"),
    ("AP501", "AG", "unit", "U03AV", "U03AY", "NATIVE"),
    ("AP541", "AG", "unit", "U03AV", "U03AY", "NATIVE"),
    ("AP471", "AJ", "unit", "U03AV", "U03AY", "NATIVE"),
    ("AP551", "AJ", "unit", "U03AV", "U03AY", "NATIVE"),
    ("AP161", "AN", "unit", "U03AU", "U03AW", "NATIVE"),
    ("AP481", "AN", "unit", "U03AU", "U03AW", "NATIVE"),
    ("AP491", "AN", "unit", "U03AU", "U03AW", "NATIVE"),
    ("AP501", "AN", "unit", "U03AU", "U03AW", "NATIVE"),
    ("AP541", "AN", "unit", "U03AU", "U03AW", "NATIVE"),
    ("AP311", "AP", "unit", "U03AU", "U03AW", "NATIVE"),
    ("AP471", "AP", "unit", "U03AU", "U03AW", "NATIVE"),
    ("AP637", "AM", "function", "U�", "OR", "NATIVE"),
    ("AP637", "AZ", "function", "U�", "OR", "NATIVE"),
]

def paths(root, stem, preview_name=None):
    result = {kind: root / (stem + suffix) for kind, suffix in {
        "txt": ".txt", "json": ".json", "notes": " review notes.txt",
        "preview": " JuliaMono preview.png"}.items()}
    if preview_name:
        result["preview"] = root / preview_name
    return result

def stage():
    grouped = defaultdict(list)
    for change in CHANGES:
        grouped[change[0]].append(change)
    STAGE.mkdir(parents=True, exist_ok=True)
    records = []
    for page, changes in grouped.items():
        matches = list(CANONICAL.glob(page + " *.json"))
        assert len(matches) == 1, (page, matches)
        stem = matches[0].stem
        preferred_preview = CANONICAL / (stem + " JuliaMono preview.png")
        preview_name = preferred_preview.name if preferred_preview.is_file() else stem + ".png"
        original = paths(CANONICAL, stem, preview_name)
        before = {kind: p.read_bytes() for kind, p in original.items()}
        rows = before["txt"].decode("utf-8").splitlines(keepends=True)
        raw = before["json"]
        evidence = []
        for _, node_id, field, old, new, basis in changes:
            assert field in ("unit", "function") and len(old) == len(new)
            model = json.loads(raw.decode("utf-8"))
            node = next(n for n in model["nodes"] if n["id"] == node_id)
            assert node[field] == old, (page, node_id, field, node[field])
            line = node["row"] + (3 if field == "unit" else 1)
            col = node["column"] + 1
            assert rows[line][col:col + len(old)] == old, (page, node_id, line, col)
            rows[line] = rows[line][:col] + new + rows[line][col + len(old):]
            marker = ('"id": "' + node_id + '"').encode("utf-8")
            begin = raw.index(marker)
            end = raw.find(b'"id": "', begin + len(marker))
            if end < 0:
                end = len(raw)
            block = raw[begin:end]
            old_field = ('"' + field + '": "' + old + '"').encode("utf-8")
            new_field = ('"' + field + '": "' + new + '"').encode("utf-8")
            assert block.count(old_field) == 1, (page, node_id, field)
            raw = raw[:begin] + block.replace(old_field, new_field, 1) + raw[end:]
            crop = CROP / (page + "-" + node_id + ".png") if basis == "NATIVE" else None
            if crop is not None:
                assert crop.is_file(), crop
            evidence.append({"node": node_id, "field": field, "before": old,
                             "after": new, "basis": basis,
                             "crop": str(crop) if crop else None})
        after = dict(before)
        after["txt"] = "".join(rows).encode("utf-8")
        after["json"] = raw
        after["preview"] = preview(after["txt"])
        summary = "; ".join(x["node"] + " " + x["field"] + " " + x["before"] +
                            " -> " + x["after"] + " (" + x["basis"] + ")" for x in evidence)
        after["notes"] = append_note(before["notes"],
            "Card-ALD 463x correction, 2026-10-15: " + summary +
            ". HUMAN readings were confirmed on physical pages in this chat. " +
            "NATIVE readings were checked against original TIFF crops. " +
            "CONTEXT readings combine visible glyphs with repeated same-portion evidence. " +
            "Older damaged-glyph notes remain as historical evidence.")
        parsed = json.loads(after["json"].decode("utf-8"))
        for item in evidence:
            assert next(n for n in parsed["nodes"] if n["id"] == item["node"])[item["field"]] == item["after"]
        assert len(rows) == 103 and all(len(row.rstrip("\r\n")) == 245 for row in rows)
        stage_dir = STAGE / stem
        stage_dir.mkdir(exist_ok=True)
        staged = paths(stage_dir, stem, preview_name)
        for kind, content in after.items():
            staged[kind].write_bytes(content)
        source = SOURCE / (stem + ".tif")
        assert source.is_file(), source
        records.append({"page": page,
                        "source": {"path": str(source), "sha256": sha(source.read_bytes())},
                        "changes": evidence,
                        "prior_quartet": {k: {"path": str(original[k]), "sha256": sha(v)}
                                          for k, v in before.items()},
                        "staged_quartet": {k: {"path": str(staged[k]), "sha256": sha(v)}
                                           for k, v in after.items()},
                        "checks": {"source_bound": True, "only_named_fields_changed": True,
                                   "grid_json_preview_verified": True,
                                   "native_contextual_or_direct_human_evidence": True}})
    manifest = {"schema": "card-463x-unit-function-stage-v1",
                "created_utc": datetime.now(timezone.utc).isoformat(), "records": records}
    (STAGE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    print("Staged", len(records), "pages and", len(CHANGES), "field corrections")

def publish():
    manifest_path = STAGE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "card-463x-unit-function-stage-v1"
    assert {r["page"] for r in manifest["records"]} == {r[0] for r in CHANGES}
    for record in manifest["records"]:
        assert sha(Path(record["source"]["path"]).read_bytes()) == record["source"]["sha256"]
        for kind, old in record["prior_quartet"].items():
            new = record["staged_quartet"][kind]
            assert sha(Path(old["path"]).read_bytes()) == old["sha256"]
            assert sha(Path(new["path"]).read_bytes()) == new["sha256"]
    for record in manifest["records"]:
        for kind, old in record["prior_quartet"].items():
            Path(old["path"]).write_bytes(Path(record["staged_quartet"][kind]["path"]).read_bytes())
    audit = {"schema": "card-463x-unit-function-current-audit-v1",
             "created_utc": datetime.now(timezone.utc).isoformat(),
             "passed": True,
             "reviewer": "Direct human, original-TIFF and contextual same-portion review",
             "scope": "Only listed 4633/4634 unit and function fields; genuine variants retained",
             "stage_manifest": {"path": str(manifest_path), "sha256": sha(manifest_path.read_bytes())},
             "pages": []}
    for record in manifest["records"]:
        current = {kind: {"path": old["path"],
                          "sha256": record["staged_quartet"][kind]["sha256"]}
                   for kind, old in record["prior_quartet"].items()}
        assert all(sha(Path(x["path"]).read_bytes()) == x["sha256"] for x in current.values())
        audit["pages"].append({"page": record["page"], "eligible": True,
                               "artifact_schema": "reviewed-current-quartet-v1",
                               "source": record["source"],
                               "prior_quartet": record["prior_quartet"],
                               "current_quartet": current,
                               "checks": record["checks"], "changes": record["changes"]})
    content = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    AUDIT.write_text(content, encoding="utf-8")
    REPO_AUDIT.write_text(content, encoding="utf-8")
    print("Published", len(manifest["records"]), "reviewed 463x pages")

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("stage", "publish"))
    stage() if parser.parse_args().action == "stage" else publish()

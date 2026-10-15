"""Publish the physical-page-confirmed AP561 AJ portion 25 reading."""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path

from release_463x_source_corrections import CANONICAL, WORKSPACE, REPO, sha, preview, append_note


STEM = "AP561 PARALLEL ADDER BIT 56"
SOURCE = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder") / (STEM + ".tif")
STAGE = WORKSPACE / "tmp/ald-text/ald/card-463x-release/AP561-portion25-stage"
AUDIT = (WORKSPACE / "tmp/ald-text/ald/manual-verification/"
         "contextual-cross-reference-v3/4634 AP561 portion25 current audit.json")
REPO_AUDIT = REPO / "notes/Card-ALD/4634 AP561 portion25 current audit.json"


def paths(root):
    return {"txt": root / (STEM + ".txt"),
            "json": root / (STEM + ".json"),
            "notes": root / (STEM + " review notes.txt"),
            "preview": root / (STEM + " JuliaMono preview.png")}


def stage():
    assert SOURCE.is_file()
    original = paths(CANONICAL)
    before = {kind: path.read_bytes() for kind, path in original.items()}
    rows = before["txt"].decode("utf-8").splitlines(keepends=True)
    assert len(rows) == 103 and all(len(line.rstrip("\r\n")) == 245 for line in rows)
    assert rows[27][74:80] == "463429"
    assert sum(row.count("463429") for row in rows) == 1
    rows[27] = rows[27][:74] + "463425" + rows[27][80:]
    after_txt = "".join(rows).encode("utf-8")

    raw = before["json"]
    model = json.loads(raw.decode("utf-8"))
    node, = [n for n in model["nodes"] if n["id"] == "AJ"]
    assert (node["card_type"], node["portion"], node["printed_card_portion"],
            node["function"], node["unit"], node["row"], node["column"]) == (
                "4634", "29", "463429", "OR", "U03AU", 23, 73)
    marker = b'"id": "AJ"'
    begin = raw.index(marker)
    end = raw.find(b'"id": "', begin + len(marker))
    if end < 0:
        end = len(raw)
    block = raw[begin:end]
    assert block.count(b'"portion": "29"') == 1
    assert block.count(b'"printed_card_portion": "463429"') == 1
    block = block.replace(b'"portion": "29"', b'"portion": "25"', 1)
    block = block.replace(b'"printed_card_portion": "463429"',
                          b'"printed_card_portion": "463425"', 1)
    after_json = raw[:begin] + block + raw[end:]
    updated = json.loads(after_json.decode("utf-8"))
    changed, = [n for n in updated["nodes"] if n["id"] == "AJ"]
    assert (changed["portion"], changed["printed_card_portion"]) == ("25", "463425")
    assert after_json.count(b'"printed_card_portion": "463425"') == 1

    after = {
        "txt": after_txt,
        "json": after_json,
        "notes": append_note(before["notes"],
            "Card-ALD 4634 physical-copy correction, 2026-10-15: The page owner "
            "confirmed that AP561 block AJ's card/portion line ends 25, not 29. "
            "The true printed reading is 463425. Its OR function, U03AU circuit, "
            "wedged inputs and wedged output are unchanged; fourteen other even-bit "
            "AP pages show the same portion-25 circuit and decorations. Corrected "
            "only the two text cells and the corresponding structured portion fields."),
        "preview": preview(after_txt),
    }
    STAGE.mkdir(parents=True, exist_ok=True)
    staged = paths(STAGE)
    for kind, path in staged.items():
        path.write_bytes(after[kind])
    manifest = {
        "schema": "card-4634-ap561-portion25-stage-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(SOURCE), "sha256": sha(SOURCE.read_bytes())},
        "change": {"page": "AP561", "node": "AJ", "card_type": "4634",
                   "before": "29", "after": "25", "basis": "Direct physical-page confirmation"},
        "prior_quartet": {kind: {"path": str(path), "sha256": sha(before[kind])}
                          for kind, path in original.items()},
        "staged_quartet": {kind: {"path": str(path), "sha256": sha(after[kind])}
                           for kind, path in staged.items()},
        "checks": {"physical_page_confirmed": True, "only_named_portion_changed": True,
                   "grid_preserved": True, "json_and_preview_agree": True},
    }
    (STAGE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    print("Staged AP561 AJ 463425")


def publish():
    manifest_path = STAGE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "card-4634-ap561-portion25-stage-v1"
    assert sha(Path(manifest["source"]["path"]).read_bytes()) == manifest["source"]["sha256"]
    for kind, old in manifest["prior_quartet"].items():
        new = manifest["staged_quartet"][kind]
        assert sha(Path(old["path"]).read_bytes()) == old["sha256"]
        assert sha(Path(new["path"]).read_bytes()) == new["sha256"]
    for kind, old in manifest["prior_quartet"].items():
        Path(old["path"]).write_bytes(Path(manifest["staged_quartet"][kind]["path"]).read_bytes())
    current = {kind: {"path": old["path"], "sha256": manifest["staged_quartet"][kind]["sha256"]}
               for kind, old in manifest["prior_quartet"].items()}
    assert all(sha(Path(item["path"]).read_bytes()) == item["sha256"] for item in current.values())
    audit = {"schema": "card-4634-ap561-portion25-current-audit-v1",
             "created_utc": datetime.now(timezone.utc).isoformat(),
             "passed": True, "reviewer": "Direct human physical-page confirmation",
             "stage_manifest": {"path": str(manifest_path), "sha256": sha(manifest_path.read_bytes())},
             "pages": [{"page": "AP561", "eligible": True,
                        "artifact_schema": "reviewed-current-quartet-v1",
                        "source": manifest["source"],
                        "prior_quartet": manifest["prior_quartet"],
                        "current_quartet": current,
                        "checks": manifest["checks"], "change": manifest["change"]}]}
    content = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    AUDIT.write_text(content, encoding="utf-8")
    REPO_AUDIT.write_text(content, encoding="utf-8")
    print("Published AP561 AJ 463425")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("stage", "publish"))
    stage() if parser.parse_args().action == "stage" else publish()

"""Stage exact, source-reviewed 4191 readings without changing published ALDs.

This stages field corrections only. Wiring changes remain in the review ledger.
The candidate manifest binds each changed text/JSON pair to its predecessor
and original TIFF; publication requires a separate acceptance step.
"""

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
WORKSPACE = REPO.parent
STAGE = WORKSPACE / "tmp" / "ald-text" / "ald" / "card-4191-readings-stage"
LEDGER = REPO / "notes" / "Card-ALD" / "4191 review decisions.json"
ALD = REPO / "ALD" / "AP Parallel Adder"
MODELS = REPO / "json" / "AP Parallel Adder"
SCANS = Path(r"D:\Reference Materials\IBM 360\IBM_360_ALD\AP Parallel Adder")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def replace_near(lines, row, old, new, start, stop, context):
    assert len(old) == len(new), context
    line = lines[row]
    positions = []
    cursor = max(0, start)
    while (cursor := line.find(old, cursor, min(len(line), stop))) != -1:
        positions.append(cursor)
        cursor += len(old)
    if len(positions) != 1:
        raise ValueError(f"Expected one {old!r} at row {row} in {context}; "
                         f"found {positions}")
    pos = positions[0]
    lines[row] = line[:pos] + new + line[pos + len(old):]
    return pos


def pin_reference_replace(value, block, old, new):
    source = f"{block}.{old}"
    target = f"{block}.{new}"
    if isinstance(value, str):
        return value.replace(source, target)
    if isinstance(value, list):
        return [pin_reference_replace(item, block, old, new) for item in value]
    if isinstance(value, dict):
        return {key: pin_reference_replace(item, block, old, new)
                for key, item in value.items()}
    return value


def unit_edits(review):
    for decision in review["decisions"]:
        if decision.get("field") != "circuit identifier":
            continue
        pages = decision.get("pages", [decision.get("page")])
        portions = decision.get("portions", [decision.get("portion")])
        pairs = (zip(pages, portions, strict=True)
                 if len(pages) == len(portions)
                 else ((page, portion) for page in pages for portion in portions))
        for page, portion in pairs:
            yield page, {"kind": "unit", "portion": portion,
                         "block": decision.get("block"),
                         "from": decision["published"],
                         "to": decision["verified"]}


def function_edits(review):
    for decision in review["decisions"]:
        if decision.get("field") == "primary function":
            yield decision["page"], {
                "kind": "function", "portion": decision["portion"],
                "block": decision.get("block"),
                "from": decision["published"], "to": decision["verified"]}


def all_edits(review):
    changes = defaultdict(list)
    for page, edit in [*unit_edits(review), *function_edits(review)]:
        changes[page].append(edit)
    for item in [*review["confirmed_pin_corrections"],
                 *review.get("inferred_pin_corrections", [])]:
        changes[item["page"]].append({
            "kind": "pin", "block": item["block"], "side": item["side"],
            "from": item["from"], "to": item["to"],
            "method": item["method"]})
    return changes


def stage_page(page, edits):
    model_path, = MODELS.glob(page + "*.json")
    text_path = ALD / (model_path.stem + ".txt")
    scan_path, = SCANS.glob(page + "*.tif")
    before_model = model_path.read_bytes()
    before_text = text_path.read_bytes()
    model = json.loads(before_model)
    lines = before_text.decode("utf-8").splitlines()
    assert len(lines) == 103 and all(len(line) == 245 for line in lines), page
    applied = []
    for edit in edits:
        matches = [node for node in model["nodes"]
                   if node.get("card_type") == "4191" and
                   (node.get("id") == edit.get("block") if edit.get("block")
                    else str(node.get("portion")) == edit.get("portion"))]
        if len(matches) != 1:
            raise ValueError(f"Ambiguous 4191 node for {page} {edit}: {len(matches)}")
        node = matches[0]
        if edit.get("portion") and str(node.get("portion")) != edit["portion"]:
            raise ValueError(f"Wrong portion for {page} {edit}")
        x, top = int(node["column"]), int(node["row"])
        old, new = edit["from"], edit["to"]
        if edit["kind"] == "pin":
            pins = [pin for pin in node["pins"]
                    if pin.get("side") == edit["side"] and pin.get("pin") == old]
            if len(pins) != 1:
                raise ValueError(f"Expected one model pin for {page} {edit}")
            pin = pins[0]
            row = int(pin["row"])
            near = x - 3 if edit["side"] == "input" else x + 8
            pos = replace_near(lines, row, old, new, near - 3, near + 6,
                               f"{page} {node['id']} pin")
            pin["pin"] = new
            for label_key in ("printed_label", "printed_pin"):
                if pin.get(label_key) == old:
                    pin[label_key] = new
            model = pin_reference_replace(model, node["id"], old, new)
        else:
            key = "unit" if edit["kind"] == "unit" else "function"
            if node[key] != old:
                raise ValueError(f"Wrong predecessor {page} {node['id']} {key}: "
                                 f"{node[key]!r}, expected {old!r}")
            row = top + (3 if key == "unit" else 1)
            pos = replace_near(lines, row, old, new, x, x + 8,
                               f"{page} {node['id']} {key}")
            node[key] = new
        applied.append({**edit, "block": node["id"], "text_row": row,
                        "text_column": pos})
    after_text = ("\n".join(lines) + "\n").encode("utf-8")
    after_model = (json.dumps(model, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    assert all(len(line) == 245 for line in after_text.decode("utf-8").splitlines())
    assert before_text != after_text and before_model != after_model
    for root, source, raw in (("ALD", text_path, after_text),
                              ("json", model_path, after_model)):
        target = STAGE / root / "AP Parallel Adder" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return {
        "page": page, "scan": str(scan_path),
        "scan_sha256": digest(scan_path.read_bytes()),
        "text": str(text_path.relative_to(REPO)),
        "text_before_sha256": digest(before_text),
        "text_candidate_sha256": digest(after_text),
        "json": str(model_path.relative_to(REPO)),
        "json_before_sha256": digest(before_model),
        "json_candidate_sha256": digest(after_model),
        "edits": applied,
    }


def main():
    review_raw = LEDGER.read_bytes()
    review = json.loads(review_raw)
    edits = all_edits(review)
    records = [stage_page(page, page_edits)
               for page, page_edits in sorted(edits.items())]
    manifest = {
        "status": "private candidate; not published or independently accepted",
        "review_ledger_sha256": digest(review_raw),
        "scope": "Exact human/source-reviewed and uniquely cross-referenced function, circuit and pin readings; "
                 "nine A-to-OR wiring corrections remain outside this stage",
        "pages": records,
    }
    path = STAGE / "4191 reviewed readings candidate manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(len(records), "staged pages;", sum(len(r["edits"]) for r in records),
          "exact field edits;", path)


if __name__ == "__main__":
    main()

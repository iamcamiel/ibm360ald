"""Independently audit and prepare the source-bound 4191 correction release.

This reads the private candidate and accepted predecessor; it never changes
published ALD files. A separate guarded publication step consumes its manifest.
"""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


REPO = Path(__file__).resolve().parents[2]
WORKSPACE = REPO.parent
ROOT = WORKSPACE / "tmp/ald-text/ald"
COMBINED = ROOT / "card-4191-combined-stage"
READINGS = ROOT / "card-4191-readings-stage"
WIRING = ROOT / "card-4191-lower-link-stage"
RELEASE = ROOT / "card-4191-release"
LEDGER = REPO / "notes/Card-ALD/4191 review decisions.json"
MANIFEST = RELEASE / "manifest.json"
FONT = ImageFont.truetype(str(WORKSPACE / "tmp/ald-text/JuliaMono-Regular.ttf"), 20)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def replace_pin_refs(value, block, old, new):
    if isinstance(value, str):
        return value.replace(f"{block}.{old}", f"{block}.{new}")
    if isinstance(value, list):
        return [replace_pin_refs(item, block, old, new) for item in value]
    if isinstance(value, dict):
        return {key: replace_pin_refs(item, block, old, new)
                for key, item in value.items()}
    return value


def verify_field_edits(record, page):
    original_text = Path(record["text"]).read_text(encoding="utf-8").splitlines()
    original_model = load(Path(record["json"]))
    expected_text = [list(row) for row in original_text]
    expected_model = deepcopy(original_model)
    for edit in page["edits"]:
        old, new = edit["from"], edit["to"]
        row, col = edit["text_row"], edit["text_column"]
        assert len(old) == len(new)
        assert "".join(expected_text[row][col:col + len(old)]) == old
        expected_text[row][col:col + len(old)] = new
        node, = [n for n in expected_model["nodes"] if n["id"] == edit["block"]]
        assert str(node["card_type"]) == "4191"
        if edit.get("portion"):
            assert str(node["portion"]) == edit["portion"]
        if edit["kind"] == "pin":
            pin, = [p for p in node["pins"] if p.get("side") == edit["side"]
                    and p.get("pin") == old]
            pin["pin"] = new
            for key in ("printed_label", "printed_pin"):
                if pin.get(key) == old:
                    pin[key] = new
            expected_model = replace_pin_refs(expected_model, node["id"], old, new)
        else:
            key = "unit" if edit["kind"] == "unit" else "function"
            assert node[key] == old
            node[key] = new
    field_text = (READINGS / page["text"]).read_text(encoding="utf-8").splitlines()
    field_model = load(READINGS / page["json"])
    assert ["".join(row) for row in expected_text] == field_text, page["page"]
    assert expected_model == field_model, page["page"]
    return len(page["edits"])


def count_targets(model, driven):
    return sum(len(net.get("targets", [])) for net in model["nets"]
               if bool(net.get("driver")) == driven)


def render_preview(raw):
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 103 and all(len(line) == 245 for line in lines)
    image = Image.new("RGB", (2940, 1854), "white")
    draw = ImageDraw.Draw(image)
    for row, line in enumerate(lines):
        for col, char in enumerate(line):
            if char != " ":
                draw.text((col * 12, row * 18), char, font=FONT, fill="black")
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def main():
    combined = load(COMBINED / "manifest.json")
    field = load(READINGS / "4191 reviewed readings candidate manifest.json")
    wire = load(WIRING / "manifest.json")
    ledger = load(LEDGER)
    assert field["review_ledger_sha256"] == digest(LEDGER.read_bytes())
    assert combined["field_manifest_sha256"] == digest(
        (READINGS / "4191 reviewed readings candidate manifest.json").read_bytes())
    assert combined["wiring_manifest_sha256"] == digest((WIRING / "manifest.json").read_bytes())
    by_field = {page["page"]: page for page in field["pages"]}
    by_wire = {page["page"]: page for page in wire["records"]}
    assert len(combined["records"]) == 45
    assert len(by_field) == 41 and len(by_wire) == 10
    assert {r["page"] for r in combined["records"]} == set(by_field) | set(by_wire)
    reviewed_wires = set()
    for decision in ledger["decisions"]:
        if decision.get("source_verified_five_separate_A_wires") is True:
            reviewed_wires.update(decision.get("pages", [decision.get("page")]))
            evidence = decision["evidence"]
            for relative in evidence if isinstance(evidence, list) else [evidence]:
                assert (REPO / "notes/Card-ALD" / relative).is_file(), relative
    assert reviewed_wires == set(by_wire) - {"AP121"}
    ap121_review, = [d for d in ledger["decisions"]
                     if d.get("page") == "AP121" and d.get("field") == "B10 input-rail placement"]
    assert "AX.B10" in ap121_review["verified"]
    assert (REPO / "notes/Card-ALD" / ap121_review["evidence"]).is_file()
    for inferred in ledger["inferred_pin_corrections"]:
        matches = [p for p in by_field[inferred["page"]]["edits"]
                   if p["kind"] == "pin" and p["block"] == inferred["block"]
                   and p["from"] == inferred["from"] and p["to"] == inferred["to"]]
        assert len(matches) == 1
        peers = []
        for page in inferred["supporting_pages"]:
            model_path, = (REPO / "json/AP Parallel Adder").glob(page + "*.json")
            for node in load(model_path)["nodes"]:
                if str(node.get("card_type")) != "4191" or str(node.get("portion")) != inferred["portion"]:
                    continue
                if any(pin.get("side") == inferred["side"] and pin.get("pin") == inferred["to"]
                       for pin in node.get("pins", [])):
                    peers.append(page)
        assert peers, inferred

    records = []
    field_count = Counter()
    for record in combined["records"]:
        page = record["page"]
        assert record["field_edits"] == (page in by_field)
        assert record["wiring_edits"] == (page in by_wire)
        original_text = Path(record["text"]).read_bytes()
        original_json = Path(record["json"]).read_bytes()
        scan = Path(record["scan"])
        assert digest(original_text) == record["text_before_sha256"]
        assert digest(original_json) == record["json_before_sha256"]
        assert digest(scan.read_bytes()) == record["scan_sha256"]
        owner_text = WORKSPACE / "ALD_Visual_Transcriptions/ALD Diagrams" / Path(record["text"]).name
        owner_json = owner_text.with_suffix(".json")
        owner_notes = owner_text.with_name(owner_text.stem + " review notes.txt")
        preview_paths = [owner_text.with_name(owner_text.stem + suffix)
                         for suffix in (" preview.png", ".png", " JuliaMono preview.png", " JuliaMono.png")]
        owner_preview, = [path for path in preview_paths if path.is_file()]
        assert digest(owner_text.read_bytes()) == record["text_before_sha256"]
        assert digest(owner_json.read_bytes()) == record["json_before_sha256"]
        old_notes = owner_notes.read_bytes()
        old_notes.decode("utf-8")
        assert digest(render_preview(original_text)) == digest(owner_preview.read_bytes()), page
        candidate_text_path = COMBINED / page / owner_text.name
        candidate_json_path = COMBINED / page / owner_json.name
        candidate_text = candidate_text_path.read_bytes()
        candidate_json = candidate_json_path.read_bytes()
        assert digest(candidate_text) == record["text_candidate_sha256"]
        assert digest(candidate_json) == record["json_candidate_sha256"]
        if page in by_field:
            field_count.update(edit["kind"] for edit in by_field[page]["edits"])
            verify_field_edits(record, by_field[page])
        if page in by_wire:
            wire_record = by_wire[page]
            assert wire_record["source_scan_sha256"] == record["scan_sha256"]
            assert wire_record["published_text_sha256"] == record["text_before_sha256"]
            assert wire_record["published_json_sha256"] == record["json_before_sha256"]
            assert digest((WIRING / page / owner_text.name).read_bytes()) == wire_record["candidate_text_sha256"]
            assert digest((WIRING / page / owner_json.name).read_bytes()) == wire_record["candidate_json_sha256"]
        text = candidate_text.decode("utf-8").splitlines()
        assert len(text) == 103 and all(len(row) == 245 for row in text)
        model = json.loads(candidate_json)
        before_model = json.loads(original_json)
        assert model["page"] == page
        validation = model.get("validation", {})
        if "unreadable_characters" in validation:
            validation["unreadable_characters"] = candidate_text.decode("utf-8").count("�")
        for key, driven in (("driven_input_terminals", True),
                            ("driven_input_terminal_count", True),
                            ("undriven_or_isolated_input_terminals", False),
                            ("undriven_terminal_count", False)):
            if key in validation:
                validation[key] += (count_targets(model, driven) - count_targets(before_model, driven))
        for net in model["nets"]:
            if "candidate_basis" in net:
                assert page in by_wire and net.get("source_reviewed") is False
                net["source_review_basis"] = net.pop("candidate_basis")
                net["source_reviewed"] = True
        model["card_4191_correction_review"] = {
            "source_scan_sha256": record["scan_sha256"],
            "before_text_sha256": record["text_before_sha256"],
            "before_json_sha256": record["json_before_sha256"],
            "private_candidate_text_sha256": record["text_candidate_sha256"],
            "private_candidate_json_sha256": record["json_candidate_sha256"],
            "field_edits": len(by_field[page]["edits"]) if page in by_field else 0,
            "wiring_reviewed": page in by_wire,
            "scope": "Exact corrected 4191 fields and source-supported wire routes; prior whole-page review retained",
        }
        released_json = (json.dumps(model, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        folder = RELEASE / page
        folder.mkdir(parents=True, exist_ok=True)
        (folder / owner_text.name).write_bytes(candidate_text)
        (folder / owner_json.name).write_bytes(released_json)
        note_addition = (
            "\n\n4191 SCOPED SOURCE CORRECTION\n"
            f"Original TIFF SHA-256: {record['scan_sha256']}\n"
            f"Exact field corrections: {len(by_field[page]['edits']) if page in by_field else 0}; "
            f"wiring route correction: {'yes' if page in by_wire else 'no'}\n"
            "The correction is bound to the 4191 release audit in notes/Card-ALD. "
            "The earlier whole-page source review remains the predecessor.\n"
        ).encode("utf-8")
        released_notes = old_notes + note_addition
        (folder / owner_notes.name).write_bytes(released_notes)
        released_preview = render_preview(candidate_text)
        (folder / owner_preview.name).write_bytes(released_preview)
        records.append({
            **record,
            "owner_text": str(owner_text), "owner_json": str(owner_json),
            "release_text_sha256": digest(candidate_text),
            "release_json_sha256": digest(released_json),
            "owner_notes": str(owner_notes),
            "notes_before_sha256": digest(old_notes),
            "release_notes_sha256": digest(released_notes),
            "owner_preview": str(owner_preview),
            "preview_before_sha256": digest(owner_preview.read_bytes()),
            "release_preview_sha256": digest(released_preview),
            "field_edit_count": len(by_field[page]["edits"]) if page in by_field else 0,
        })
    assert sum(field_count.values()) == 82
    audit = {
        "schema": "card-4191-scoped-source-correction-release-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "independently audited private release; not yet published",
        "combined_manifest_sha256": digest((COMBINED / "manifest.json").read_bytes()),
        "review_ledger_sha256": digest(LEDGER.read_bytes()),
        "field_edit_counts": dict(sorted(field_count.items())),
        "wiring_page_count": len(by_wire),
        "records": records,
    }
    MANIFEST.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Prepared {len(records)} pages, {sum(field_count.values())} exact field edits, "
          f"{len(by_wire)} wiring pages; {MANIFEST}")


if __name__ == "__main__":
    main()

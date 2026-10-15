"""Read-only comparison of published 4191 ALD blocks with the card example.

The report is a candidate list. Differences from the K6/K7 example are not
automatically source corrections; the original scan must settle each one.
"""

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re

from source_4191 import SLICES


ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "json" / "AP Parallel Adder"
TEXT_DIR = ROOT / "ALD" / "AP Parallel Adder"
REPORT_DIR = ROOT / "notes" / "Card-ALD"
REVIEW_LEDGER = REPORT_DIR / "4191 review decisions.json"
PIN = re.compile(r"^[BDGJ](?:0[2-9]|1[0-3])$")
PINLIKE = re.compile(r"^(?:[0-9])?[A-Z�][0-9]{2}$")
PORTION_IN_TEXT = re.compile(r"(?<!\d)4191([0-9]{2}|B[12])(?![A-Z0-9])")


def expected_pattern():
    expected = {
        "03": ("N", "U03AF", {("input", "B08")}),
        "06": ("N", "U03AF", {("input", "B13"), ("output", "J02")}),
        "35": ("OR", "U03AF", {("input", p) for p in
                                ("D10", "B04", "G10", "D06")} |
               {("output", "D02")}),
        "B1": ("AR", "T06AA", {("input", "G08"), ("output", "G08")}),
        "B2": ("N", "U03AF", {("output", "J06")}),
    }
    for data in SLICES:
        for portion, unit, *pins in data["gates"]:
            expected[portion] = ("A", unit,
                                 {("input", p) for p in pins if p != "P3"})
        expected[data["term"][0]] = ("R T1", "U61AC",
                                      {("input", data["term"][1])})
        expected[data["resistor"][0]] = ("R", "U61AP",
                                          {("input", data["resistor"][1])})
        expected[data["join"]] = ("✲OR", "U03CN",
                                  {("output", data["net"])})
        for portion, pin in zip(data["n"], data["n_out"], strict=True):
            expected[portion] = ("N", "U03AF",
                                 {("input", data["net"]), ("output", pin)})
    # Native uses show D08 as an additional contact on four A portions;
    # portion 25 was settled by physical-page review on 2026-10-15.
    for portion in ("07", "13", "19", "25"):
        function, unit, pins = expected[portion]
        expected[portion] = (function, unit, pins | {("input", "D08")})
    assert len(expected) == 45
    return expected


def primary_function(value):
    value = (value or "").strip()
    if value.startswith("✲OR "):
        return "✲OR"
    if value.startswith("AR "):
        return "AR"
    return value


def physical_pin(raw):
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if len(value) == 4 and value[0].isdigit() and PIN.fullmatch(value[1:]):
        return value[1:]
    return value if PIN.fullmatch(value) else None


def reviewed_five_separate_pages():
    """Source-verified pages; absent pages remain unassessed, not negative."""
    ledger = json.loads(REVIEW_LEDGER.read_text(encoding="utf-8"))
    return {page
            for decision in ledger["decisions"]
            if decision.get("source_verified_five_separate_A_wires") is True
            for page in ([decision["page"]] if "page" in decision
                         else decision["pages"])}


def scan():
    pattern = expected_pattern()
    reviewed_separate = reviewed_five_separate_pages()
    rows = []
    page_summaries = []
    topology = []
    for model_path in sorted(MODEL_DIR.glob("*.json")):
        doc = json.loads(model_path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("nodes"), list):
            continue
        nodes = [n for n in doc["nodes"] if isinstance(n, dict)
                 and str(n.get("card_type")) == "4191"]
        if not nodes:
            continue
        text_path = TEXT_DIR / (model_path.stem + ".txt")
        if not text_path.is_file():
            raise ValueError(f"Missing published text: {text_path}")
        text = text_path.read_text(encoding="utf-8")
        model_portions = Counter(str(n.get("portion")) for n in nodes)
        text_portions = Counter(PORTION_IN_TEXT.findall(text))
        if model_portions != text_portions:
            raise ValueError(f"TXT/JSON portion disagreement: {model_path.name}")
        page_summaries.append({"page": doc.get("page"), "blocks": len(nodes),
                               "text": str(text_path.relative_to(ROOT)),
                               "model": str(model_path.relative_to(ROOT))})
        by_portion = {str(node.get("portion")): node for node in nodes}
        for slice_data in SLICES:
            join = by_portion.get(slice_data["join"])
            if join is None:
                continue
            gates = [by_portion.get(gate[0]) for gate in slice_data["gates"]]
            n_boxes = [by_portion.get(portion) for portion in slice_data["n"]]
            if not all(gates + n_boxes):
                raise ValueError(f"Incomplete 4191 adder slice: {doc['page']}")
            gate_ids = {gate["id"] for gate in gates}
            linked_ids = set()
            combined_nets = []
            for net in doc.get("nets", []):
                if not any(str(target).split(".", 1)[0] == join["id"]
                           for target in net.get("targets", [])):
                    continue
                sources = set(re.findall(r"\b([A-Z]{2})\.(?:output|OUT\d+)\b",
                                         str(net.get("driver", "")))) & gate_ids
                linked_ids.update(sources)
                if len(sources) > 1:
                    combined_nets.append(str(net.get("id")))

            def pins(box, side):
                return {str(pin.get("pin")) for pin in box.get("pins", [])
                        if pin.get("side") == side and pin.get("pin") is not None}

            def matches(first, second):
                return bool({physical_pin(p) or p for p in first} &
                            {physical_pin(p) or p for p in second})

            shared_pairs = {
                "terminator": (gates[0], by_portion.get(slice_data["term"][0])),
                "resistor": (gates[2], by_portion.get(slice_data["resistor"][0])),
            }
            pair_disagreements = []
            for name, (gate, resistance) in shared_pairs.items():
                if resistance is not None and not matches(pins(gate, "input"),
                                                           pins(resistance, "input")):
                    pair_disagreements.append(name)
            join_outputs = pins(join, "output")
            if not all(matches(join_outputs, pins(box, "input")) for box in n_boxes):
                pair_disagreements.append("join_to_N_pin")
            if not matches(pins(n_boxes[1], "output"), pins(gates[4], "input")):
                pair_disagreements.append("feedback_pin")
            topology.append({
                "page": str(doc.get("page")), "slice_join_portion": slice_data["join"],
                "expected_A_drivers": 5,
                "published_JSON_linked_A_driver_labels": len(linked_ids),
                "published_JSON_A_driver_portions_not_linked": " ".join(
                    gate["portion"] for gate in gates if gate["id"] not in linked_ids),
                "published_JSON_combined_driver_nets": " ".join(combined_nets),
                "source_review_verified_five_separate_A_wires":
                    "yes" if str(doc.get("page")) in reviewed_separate else "",
                "pin_pair_disagreements": " ".join(pair_disagreements),
                "model": str(model_path.relative_to(ROOT)),
            })
        for node in nodes:
            portion = str(node.get("portion"))
            if portion not in pattern:
                raise ValueError(f"Unknown 4191 portion {portion}: {model_path}")
            function, unit, expected_pins = pattern[portion]
            observations = []
            invalid = []
            placeholders = []
            for item in node.get("pins", []):
                raw = item.get("pin")
                direction = item.get("side")
                parsed = physical_pin(raw)
                if parsed:
                    observations.append((direction, parsed))
                elif isinstance(raw, str) and PINLIKE.fullmatch(raw):
                    invalid.append(f"{direction}:{raw}")
                elif raw is not None:
                    placeholders.append(f"{direction}:{raw}")
            observed_set = set(observations)
            flags = []
            if primary_function(node.get("function")) != function:
                flags.append("function")
            if node.get("unit") != unit:
                flags.append("circuit_identifier")
            if invalid:
                flags.append("invalid_physical_pin")
            if observed_set - expected_pins:
                flags.append("different_physical_pin")
            rows.append({
                "page": str(doc.get("page")), "block": str(node.get("id")),
                "grid": str(node.get("grid", "")),
                "location": str(node.get("location", "")),
                "portion": portion, "function": str(node.get("function", "")),
                "expected_primary_function": function,
                "circuit_identifier": str(node.get("unit", "")),
                "expected_circuit_identifier": unit,
                "pins": " ".join(f"{side}:{pin}" for side, pin in observations),
                "expected_pins": " ".join(f"{side}:{pin}" for side, pin in sorted(expected_pins)),
                "invalid_pinlike_labels": " ".join(invalid),
                "other_port_placeholders": " ".join(placeholders),
                "unexpected_pins": " ".join(f"{side}:{pin}" for side, pin in
                                             sorted(observed_set - expected_pins)),
                "expected_pins_not_shown": " ".join(f"{side}:{pin}" for side, pin in
                                                  sorted(expected_pins - observed_set)),
                "flags": ";".join(flags),
                "model": str(model_path.relative_to(ROOT)),
                "text": str(text_path.relative_to(ROOT)),
            })
    assert len(rows) == 644 and len(page_summaries) == 68 and len(topology) == 60
    return rows, page_summaries, topology


def write_reports(rows, pages, topology):
    out = REPORT_DIR / "4191 all-occurrence comparison.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    topology_out = REPORT_DIR / "4191 topology comparison.csv"
    with topology_out.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(topology[0]))
        writer.writeheader()
        writer.writerows(topology)
    # A portion can have unused inputs on a particular ALD block. Inventory
    # the union of observed contacts rather than demanding every example pin
    # on every use. Human-read AP041 pins remain separate from the published
    # model until its source-bound correction is accepted.
    contacts = defaultdict(list)
    for row in rows:
        for token in row["pins"].split():
            side, pin = token.split(":", 1)
            contacts[(row["portion"], side, pin)].append(row["page"])
    inventory = []
    for (portion, side, pin), observed_pages in sorted(contacts.items()):
        inventory.append({
            "portion": portion, "side": side, "pin": pin,
            "published_occurrences": len(observed_pages),
            "published_pages": " ".join(sorted(set(observed_pages))),
            "human_verified_pending_source_update": "AP041" if
                (portion, side, pin) in {("07", "input", "D08"),
                                        ("07", "input", "D12")} else "",
        })
    for pin in ("D08", "D12"):
        key = ("07", "input", pin)
        if key not in contacts:
            inventory.append({
                "portion": "07", "side": "input", "pin": pin,
                "published_occurrences": 0, "published_pages": "",
                "human_verified_pending_source_update": "AP041",
            })
    inventory.sort(key=lambda row: (row["portion"], row["side"], row["pin"]))
    inventory_out = REPORT_DIR / "4191 observed pin union.csv"
    with inventory_out.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(inventory[0]))
        writer.writeheader()
        writer.writerows(inventory)
    flags = Counter(flag for row in rows for flag in row["flags"].split(";") if flag)
    by_portion = defaultdict(Counter)
    for row in rows:
        for flag in row["flags"].split(";"):
            if flag:
                by_portion[row["portion"]][flag] += 1
    summary = {
        "scope": "Current published 4191 blocks in AP ALD TXT and JSON; read-only",
        "comparison_basis": "The 02B-E1 K6/K7 Card-ALD example; individual blocks may leave portion inputs unused",
        "occurrences": len(rows), "page_count": len(pages),
        "distinct_portions": len({r["portion"] for r in rows}),
        "all_text_json_portion_inventories_equal": True,
        "example_pins_not_shown_on_individual_blocks": sum(
            len(row["expected_pins_not_shown"].split()) for row in rows),
        "flags": dict(sorted(flags.items())),
        "by_portion": {key: dict(value) for key, value in sorted(by_portion.items())},
        "adder_slices": len(topology),
        "slices_with_all_five_A_driver_labels_linked_in_published_JSON": sum(
            r["published_JSON_linked_A_driver_labels"] == 5 for r in topology),
        "slices_with_combined_A_driver_nets_in_published_JSON": sum(
            bool(r["published_JSON_combined_driver_nets"]) for r in topology),
        "slices_source_review_verified_five_separate_A_wires": sum(
            r["source_review_verified_five_separate_A_wires"] == "yes"
            for r in topology),
        "pin_pair_disagreements": dict(sorted(Counter(
            name for row in topology for name in row["pin_pair_disagreements"].split()
        ).items())),
        "pages": pages,
        "comparison_csv": str(out.relative_to(ROOT)),
        "topology_csv": str(topology_out.relative_to(ROOT)),
        "pin_union_csv": str(inventory_out.relative_to(ROOT)),
    }
    summary_path = REPORT_DIR / "4191 all-occurrence comparison.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    return out, topology_out, summary_path, summary


if __name__ == "__main__":
    rows, pages, topology = scan()
    output, topology_out, summary_path, summary = write_reports(rows, pages, topology)
    print(summary["occurrences"], "blocks on", summary["page_count"], "pages")
    print(summary["flags"])
    print(summary["adder_slices"], "adder slices;",
          summary["slices_with_all_five_A_driver_labels_linked_in_published_JSON"],
          "have five driver labels linked in published JSON;")
    print(summary["slices_source_review_verified_five_separate_A_wires"],
          "have five separate driver wires verified against source")
    print(summary["pin_pair_disagreements"])
    print(output)
    print(topology_out)
    print(summary_path)

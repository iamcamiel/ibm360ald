"""Compare every published 4633/4634 occurrence with repeated card evidence.

The output is a review queue, not a source-correction authorization.  Some
different visible inputs are simply unused contacts on that ALD page.
"""

from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from audit_463x_occurrences import build as inventory, PIN, ROOT


TEXT_DIR = ROOT / "ALD"
JSON_DIR = ROOT / "json"
OUT = ROOT / "notes" / "Card-ALD"
SOURCE_CONFIRMED_VARIANTS = {
    ("4634", "AP701", "AK", "function"): "evidence/463x/4634-AP701-AK.png",
}


def variant_review(card, entry, kind):
    crop = SOURCE_CONFIRMED_VARIANTS.get((card, entry["page"], entry["node"], kind))
    if not crop:
        return {"adjudication": "review candidate"}
    assert (OUT / crop).is_file(), crop
    if (card, entry["page"], entry["node"]) == ("4634", "AP701", "AK"):
        return {"adjudication": "source-confirmed equivalent polarity notation",
                "basis": "U03AM A has plain inputs and a wedged output; other B1 blocks use OR with wedged inputs and a plain output",
                "native_crop": crop}
    return {"adjudication": "source-confirmed printed variant", "native_crop": crop}


def pin_classification(raw, basis):
    if raw in ("A", "B"):
        return "logical input designator, not physical pin"
    if basis.startswith("Printed open asterisk"):
        return "decoration, not physical-pin error"
    if basis.startswith("Leading box/wire mark"):
        return "leading border or wire mark"
    if str(raw).startswith(("IN", "OUT")):
        return "provisional internal label"
    return "needs physical pin review"


def suggested_pin(card, entry, port, by_portion):
    raw = str(port["pin"])
    if raw.endswith("✲") and PIN.fullmatch(raw[:-1]):
        return raw[:-1], "Printed open asterisk is a separate decoration"
    if len(raw) == 4 and raw[0] in "8BH" and PIN.fullmatch(raw[1:]):
        return raw[1:], "Leading box/wire mark precedes a valid physical pin"
    if re.fullmatch(r"[A-Z�][0-9]{2}", raw):
        same = Counter(
            p["pin"] for e in by_portion[entry["portion"]]
            for p in e["pins"]
            if p["side"] == port["side"] and p["pin"]
            and PIN.fullmatch(str(p["pin"])) and str(p["pin"])[1:] == raw[1:]
        )
        if len(same) == 1 and sum(same.values()) >= 3:
            return same.most_common(1)[0][0], f"Unique same-portion physical-pin reading ({sum(same.values())} other observations)"
    return None, "Requires native scan or socket/wire check"


def compare():
    result = {}
    for card, inv in inventory().items():
        by_portion = defaultdict(list)
        by_page = defaultdict(list)
        for entry in inv["occurrences"]:
            by_portion[entry["portion"]].append(entry)
            by_page[entry["page"]].append(entry)
        function_outliers = []
        circuit_outliers = []
        invalid_pins = []
        for portion, entries in by_portion.items():
            functions = Counter(e["primary_function"] for e in entries)
            circuits = Counter(e["unit"] for e in entries)
            function_mode = functions.most_common(1)[0][0]
            circuit_mode = circuits.most_common(1)[0][0]
            for entry in entries:
                where = {k: entry[k] for k in ("page", "node", "portion", "grid", "location")}
                if entry["primary_function"] != function_mode:
                    function_outliers.append({**where, "observed": entry["function"],
                                              "most_common": function_mode,
                                              "observed_count": functions[entry["primary_function"]],
                                              "comparison_count": len(entries),
                                              **variant_review(card, entry, "function")})
                if entry["unit"] != circuit_mode:
                    circuit_outliers.append({**where, "observed": entry["unit"],
                                             "most_common": circuit_mode,
                                             "observed_count": circuits[entry["unit"]],
                                             "comparison_count": len(entries),
                                             **variant_review(card, entry, "unit")})
                for port in entry["pins"]:
                    if not port["physical_pin_valid"]:
                        candidate, basis = suggested_pin(card, entry, port, by_portion)
                        invalid_pins.append({**where, "side": port["side"],
                                             "observed": port["pin"],
                                             "candidate": candidate, "basis": basis,
                                             "classification": pin_classification(port["pin"], basis)})

        # Count portion numbers in the actual UTF-8 sheet as an independent
        # guard against a model/report built from stale or shifted JSON.
        mismatches = []
        for page, entries in by_page.items():
            json_path = next(JSON_DIR.rglob(page + " *.json"), None)
            if json_path is None:
                mismatches.append({"page": page, "reason": "Missing JSON file"})
                continue
            text_path = TEXT_DIR / json_path.relative_to(JSON_DIR).with_suffix(".txt")
            if not text_path.is_file():
                mismatches.append({"page": page, "reason": "Missing TXT file"})
                continue
            text = text_path.read_text(encoding="utf-8")
            model_portions = Counter(e["portion"] for e in entries)
            text_portions = Counter(re.findall(rf"(?<!\d){card}([0-9]{{2}}|[A-Z][0-9])(?![A-Z0-9])", text))
            if model_portions != text_portions:
                mismatches.append({"page": page, "json": dict(model_portions),
                                   "text": dict(text_portions)})

        # An expected internal edge is only required where both portions
        # appear on one page in the same physical card.  Five separate
        # pages of agreement are the threshold for a useful comparison.
        pair_support = Counter()
        page_edges = {}
        page_nodes = {}
        for page, entries in by_page.items():
            json_path = next(JSON_DIR.rglob(page + " *.json"))
            doc = json.loads(json_path.read_text(encoding="utf-8"))
            nodes = {n["id"]: n for n in doc["nodes"] if str(n.get("card_type")) == card}
            page_nodes[page] = nodes
            edges = set()
            for net in doc.get("nets", []):
                driver = net.get("driver")
                if not isinstance(driver, str):
                    continue
                # Some printed wires join two outputs.  The semantic page
                # record retains one root driver plus the other physical
                # driver(s) in these fields; counting only the root falsely
                # reports an absent source→sink edge (notably AP511 A3→A5).
                driver_refs = {driver}
                for key in ("declared_physical_output_drivers", "route_owners"):
                    for ref in net.get(key, []) or []:
                        if isinstance(ref, str) and re.fullmatch(r"[A-Z]{2}\.[^\s/.]+", ref):
                            driver_refs.add(ref)
                for target in net.get("targets", []):
                    sink = nodes.get(str(target).split(".", 1)[0])
                    if sink is None:
                        continue
                    for ref in driver_refs:
                        source = nodes.get(ref.split(".", 1)[0])
                        if source and source.get("location") == sink.get("location"):
                            edges.add((str(source["portion"]), str(sink["portion"]),
                                       source.get("location")))
            page_edges[page] = edges
            pair_support.update((s, t) for s, t, _ in edges)
        topology_candidates = []
        for (source, target), count in pair_support.items():
            if count < 5:
                continue
            for page, entries in by_page.items():
                located = defaultdict(set)
                for entry in entries:
                    located[entry["location"]].add(entry["portion"])
                for location, portions in located.items():
                    if source in portions and target in portions and \
                            (source, target, location) not in page_edges[page]:
                        source_nodes = [n for n in page_nodes[page].values()
                                        if str(n["portion"]) == source and n.get("location") == location]
                        target_nodes = [n for n in page_nodes[page].values()
                                        if str(n["portion"]) == target and n.get("location") == location]
                        output_pins = {p.get("pin") for n in source_nodes for p in n.get("pins", [])
                                       if p.get("side") == "output" and PIN.fullmatch(str(p.get("pin")))}
                        input_pins = {p.get("pin") for n in target_nodes for p in n.get("pins", [])
                                      if p.get("side") == "input" and PIN.fullmatch(str(p.get("pin")))}
                        shared = sorted(output_pins & input_pins)
                        if shared:
                            adjudication = "same-card shared physical pin; captured as inferred Card-ALD connection"
                        elif (card, page, source, target) == ("4633", "AP091", "J5", "J7"):
                            adjudication = "source-confirmed separate G03/G04 contacts"
                        elif (card, page, source, target) == ("4634", "AP391", "46", "54"):
                            adjudication = "source-confirmed alternate route to portion 50"
                        else:
                            adjudication = "review candidate"
                        topology_candidates.append({"page": page, "location": location,
                                                    "source_portion": source,
                                                    "target_portion": target,
                                                    "comparison_pages": count,
                                                    "shared_physical_pins": shared,
                                                    "adjudication": adjudication})

        report = {
            "card_type": card,
            "scope": "All currently published ALD TXT/JSON; differences are candidates, not automatic corrections",
            "block_count": inv["block_count"],
            "page_count": inv["page_count"],
            "portion_count": inv["observed_portion_count"],
            "text_json_portion_inventory_mismatches": mismatches,
            "function_outliers": function_outliers,
            "circuit_outliers": circuit_outliers,
            "invalid_physical_pin_readings": invalid_pins,
            "invalid_pin_class_counts": dict(Counter(x["classification"] for x in invalid_pins)),
            "repeated_edge_topology_candidates": topology_candidates,
        }
        (OUT / f"{card} comparison findings.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        result[card] = report
    return result


if __name__ == "__main__":
    for card, report in compare().items():
        print(card, {key: len(value) for key, value in report.items()
                     if isinstance(value, list)})

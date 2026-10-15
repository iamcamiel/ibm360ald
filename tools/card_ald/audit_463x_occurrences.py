"""Inventory 4633/4634 card portions without inferring a complete pinout.

The structured ALD records include both literal print readings and a few
older OCR artifacts.  This audit is intentionally read-only with respect to
ALD sources: candidate repairs require native-scan and TXT review.
"""

from collections import Counter, defaultdict
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
JSON_DIR = ROOT / "json"
OUT = ROOT / "notes" / "Card-ALD"
CARD_TYPES = ("4633", "4634")
PIN = re.compile(r"[BDGJ](?:0[2-9]|1[0-3])\Z")


def primary(label):
    """Keep the first function name, as agreed for the card database."""
    label = (label or "").strip()
    if label.startswith("✲"):
        return label.split()[0]
    if label.startswith("R T"):
        return label.split()[0] + " " + label.split()[1]
    return label.split()[0] if label else ""


def source_files():
    for path in sorted(JSON_DIR.rglob("*.json")):
        if path.parent.name == "Card types":
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(doc, dict) and isinstance(doc.get("nodes"), list):
            yield path, doc


def build():
    reports = {}
    for card in CARD_TYPES:
        occurrences = []
        page_files = {}
        page_models = {}
        for path, doc in source_files():
            nodes = [n for n in doc["nodes"] if str(n.get("card_type")) == card]
            if not nodes:
                continue
            page = doc.get("page", path.stem.split()[0])
            page_files[page] = path
            page_models[page] = doc
            for node in nodes:
                pins = []
                for port in node.get("pins", []):
                    value = port.get("pin")
                    pins.append({
                        "side": port.get("side"),
                        "pin": value,
                        "physical_pin_valid": value is None or bool(PIN.fullmatch(str(value))),
                        "triangle": port.get("triangle"),
                        "row": port.get("row"),
                    })
                occurrences.append({
                    "page": page,
                    "node": node.get("id"),
                    "portion": str(node.get("portion")),
                    "function": node.get("function"),
                    "primary_function": primary(node.get("function")),
                    "unit": node.get("unit"),
                    "location": node.get("location"),
                    "grid": node.get("grid"),
                    "pins": pins,
                    "source_reviewed": node.get("source_reviewed"),
                })

        by_portion = defaultdict(list)
        for entry in occurrences:
            by_portion[entry["portion"]].append(entry)
        card_db_path = JSON_DIR / "Card types" / f"{card}.json"
        db = json.loads(card_db_path.read_text(encoding="utf-8"))
        portion_summary = {}
        for portion in sorted(set(db["portions"]) | set(by_portion)):
            obs = by_portion[portion]
            functions = Counter(e["primary_function"] for e in obs)
            units = Counter(e["unit"] for e in obs)
            labelled = defaultdict(Counter)
            for e in obs:
                for p in e["pins"]:
                    if p["pin"] is not None:
                        labelled[p["side"]][p["pin"]] += 1
            portion_summary[portion] = {
                "observations": len(obs),
                "functions": dict(functions),
                "circuits": dict(units),
                "labelled_ports": {k: dict(v) for k, v in labelled.items()},
            }

        invalid = [
            {"page": e["page"], "node": e["node"], "portion": e["portion"],
             "grid": e["grid"], "location": e["location"], "side": p["side"],
             "printed_model_pin": p["pin"]}
            for e in occurrences for p in e["pins"]
            if not p["physical_pin_valid"]
        ]

        # These edges are only the connections explicitly captured in each
        # page's net model.  A missing edge does not establish disconnection.
        edges = defaultdict(set)
        for page, doc in page_models.items():
            card_nodes = [n for n in doc["nodes"] if str(n.get("card_type")) == card]
            node_by_id = {n.get("id"): n for n in card_nodes}
            for net in doc.get("nets", []):
                driver = net.get("driver")
                if not isinstance(driver, str):
                    continue
                source_id = driver.split(".", 1)[0]
                source = node_by_id.get(source_id)
                if source is None:
                    continue
                for target in net.get("targets", []):
                    target_id = str(target).split(".", 1)[0]
                    sink = node_by_id.get(target_id)
                    if sink is None or sink.get("location") != source.get("location"):
                        continue
                    edges[(str(source["portion"]), str(sink["portion"]))].add(page)

        report = {
            "card_type": card,
            "part_number": f"580{card}",
            "scope": "Published structured ALD observations only; incomplete drawing of a portion is not a full pinout claim",
            "page_count": len(page_files),
            "block_count": len(occurrences),
            "observed_portion_count": len(by_portion),
            "database_portion_count": len(db["portions"]),
            "unobserved_database_portions": sorted(set(db["portions"]) - set(by_portion)),
            "invalid_physical_pin_readings": invalid,
            "function_variant_portions": [p for p, row in portion_summary.items() if len(row["functions"]) > 1],
            "circuit_variant_portions": [p for p, row in portion_summary.items() if len(row["circuits"]) > 1],
            "portions": portion_summary,
            "observed_same_instance_internal_edges": [
                {"source": a, "target": b, "pages": sorted(pages)}
                for (a, b), pages in sorted(edges.items())
            ],
            "occurrences": occurrences,
        }
        reports[card] = report
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{card} all-occurrence inventory.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return reports


if __name__ == "__main__":
    for key, value in build().items():
        print(f"{key}: {value['block_count']} blocks on {value['page_count']} pages; "
              f"{len(value['invalid_physical_pin_readings'])} invalid pin readings; "
              f"{len(value['function_variant_portions'])} function and "
              f"{len(value['circuit_variant_portions'])} circuit variant portions")

"""Audit SLT power contacts in the accepted ALD page models, read-only.

Physical supply contacts can be printed where a signal pin is tied to a rail.
They must not be mistaken for ordinary signal inputs or driven outputs.
Connector and non-SLT modules are outside this audit.
"""

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "normalization"))
import read_page as page_reader
import csv
import json
import re


ROOT = Path(__file__).resolve().parents[2]
SOCKETS = ROOT / "json/A1 Socket Listing/Socket reference.json"
CONTENT = ROOT / "notes/Content data manifest.json"
REVIEWED = ROOT / "notes/Reviewed export provenance.json"
RULE = ROOT / "notes/Pin validation/SLT supply contact rule.json"
REPORT = ROOT / "notes/Pin validation/SLT supply-pin audit.json"
ROWS = ROOT / "csv/Pin validation/SLT supply-pin occurrences.csv"
REVIEW_QUEUE = ROOT / "csv/Pin validation/SLT supply-pin review queue.csv"
SUPPLY = {"D08": "ground", "J08": "ground", "D03": "+3V", "J03": "+3V",
          "B06": "-3V", "G06": "-3V", "B11": "+6V", "G11": "+6V"}
PATTERN = re.compile(r"^(?P<prefix>[0-9]{0,2})(?P<contact>[BDGJ](?:0[2-9]|1[0-3]))(?P<mark>[✲*]?)$")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def card_kinds():
    kinds = defaultdict(set)
    for record in read(SOCKETS)["records"]:
        card = record.get("card_type")
        kind = str(record.get("kind", "")).upper().replace("_", " ")
        if card and ("SINGLE" in kind or "DOUBLE" in kind):
            kinds[str(card)].add("double" if "DOUBLE" in kind else "single")
    assert all(len(value) == 1 for value in kinds.values())
    return {card: next(iter(value)) for card, value in kinds.items()}


def classify(row):
    side = row["side"]
    nets = row["nets"]
    if side == "output":
        return "concern_output_on_supply_contact"
    if side != "input":
        return "concern_unknown_direction"
    if not nets:
        return "review_no_model_net"
    local_words = ("LOCAL", "JUMPER", "STRAP", "TIE", "UNUSED", "UNDRIVEN", "PASSIVE")
    voltage_words = ("GROUND", "GND", "SUPPLY", "POWER", "+3V", "-3V", "+6V")
    for net in nets:
        driver = str(net["driver"] or "").upper()
        if any(word in driver for word in voltage_words):
            continue
        if any(word in driver for word in local_words):
            continue
        if (driver.startswith("EXTERNAL") or re.match(r"^[A-Z]{2}\d{3}[A-Z]{2}\d", driver)
                or re.match(r"^[A-Z0-9]{2,4}\.[A-Z][0-9]{2}", driver)):
            return "concern_modeled_signal_drive_to_supply"
    if any(net["other_targets"] for net in nets):
        if any(any(t.split(".", 1)[0] != row["block"] for t in net["other_targets"]
                   if "." in t) for net in nets):
            return "review_shared_voltage_tie_or_signal"
        return "local_voltage_tie_candidate"
    return "review_standalone_supply_contact"


def audit():
    kinds = card_kinds()
    assert read(RULE)["contacts"] == SUPPLY
    reviewed = read(REVIEWED)
    accepted = {Path(entry["destination"]).resolve().relative_to(ROOT).as_posix()
                for entry in reviewed["exported"]}
    manifest = read(CONTENT)
    rows = []
    ordinary_pins = defaultdict(lambda: defaultdict(set))
    page_models = 0
    modeled_nodes = 0
    matched_model_texts = set()
    models_without_nodes = []
    for item in manifest["files"]:
        if item.get("role") != "Published page content model":
            continue
        path = ROOT / item["path"]
        txt = path.relative_to(ROOT).with_suffix(".txt")
        txt = Path("ALD") / Path(*txt.parts[1:])
        if txt.as_posix() not in accepted:
            continue
        matched_model_texts.add(txt.as_posix())
        assert digest(path) == item["sha256"], path
        data = page_reader.read(path)
        if not isinstance(data.get("nodes"), list):
            models_without_nodes.append(txt.as_posix())
            continue
        page_models += 1
        nodes = data["nodes"]
        modeled_nodes += len(nodes)
        nets = data.get("nets", [])
        by_target = defaultdict(list)
        for net in nets:
            for target in net.get("targets", []):
                by_target[str(target)].append(net)
        for node in nodes:
            card = str(node.get("card_type") or "")
            if card not in kinds:
                continue
            for index, pin in enumerate(node.get("pins", [])):
                raw = str(pin.get("pin") or "")
                matched = PATTERN.fullmatch(raw)
                if not matched:
                    continue
                contact = matched.group("contact")
                if contact not in SUPPLY:
                    ordinary_pins[(card, str(node.get("portion")), pin.get("side"))][contact].add(
                        str(data.get("page")))
                    continue
                block = str(node.get("id") or "")
                keys = {f"{block}.{raw}", f"{block}.{contact}"}
                if pin.get("reference"):
                    keys.add(str(pin["reference"]))
                linked = []
                for key in keys:
                    for net in by_target.get(key, []):
                        if net not in linked:
                            linked.append(net)
                compact_nets = [{
                    "id": net.get("id"), "driver": net.get("driver"),
                    "other_targets": [target for target in net.get("targets", [])
                                      if str(target) not in keys],
                    "kind": net.get("kind"),
                    "external": net.get("external"),
                } for net in linked]
                row = {
                    "page": data.get("page"), "folder": path.parent.name,
                    "model": item["path"], "model_sha256": item["sha256"],
                    "block": block, "card_type": card, "card_kind": kinds[card],
                    "portion": node.get("portion"), "location": node.get("location"),
                    "pin_index": index, "printed_pin": raw, "contact": contact,
                    "rail": SUPPLY[contact], "side": pin.get("side"),
                    "drawn_wire": pin.get("drawn_wire"), "reference": pin.get("reference"),
                    "nets": compact_nets,
                }
                row["classification"] = classify(row)
                rows.append(row)
    for row in rows:
        row["same_portion_ordinary_pin_comparison"] = []
        if row["classification"] != "concern_output_on_supply_contact":
            continue
        alternatives = ordinary_pins.get((row["card_type"], str(row["portion"]), "output"), {})
        row["same_portion_ordinary_pin_comparison"] = [
            {"pin": pin, "independent_pages": len(pages), "example_pages": sorted(pages)[:8]}
            for pin, pages in sorted(alternatives.items(), key=lambda pair: (-len(pair[1]), pair[0]))[:5]
        ]
    counts = Counter(row["classification"] for row in rows)
    contact_counts = Counter(row["contact"] for row in rows)
    concern_rows = [row for row in rows if row["classification"].startswith("concern")]
    review_rows = [row for row in rows if row["classification"] != "local_voltage_tie_candidate"]
    without_model = accepted - matched_model_texts
    report = {
        "schema": "slt-supply-pin-all-accepted-model-audit-v1",
        "scope": "Accepted ALD page models only; nodes whose card type has a SINGLE or DOUBLE SLT socket-listing classification. Connectors and other modules excluded.",
        "pin_rules": SUPPLY,
        "page_reader_tools": [{"path":str(path.relative_to(ROOT)),"sha256":digest(path)} for path in page_reader.runtime_paths(ROOT)],
        "source_bindings": {
            "socket_reference": {"path": str(SOCKETS.relative_to(ROOT)), "sha256": digest(SOCKETS)},
            "content_manifest": {"path": str(CONTENT.relative_to(ROOT)), "sha256": digest(CONTENT)},
            "reviewed_export": {"path": str(REVIEWED.relative_to(ROOT)), "sha256": digest(REVIEWED)},
            "owner_rule": {"path": str(RULE.relative_to(ROOT)), "sha256": digest(RULE)},
        },
        "counts": {
            "accepted_text_pages": len(accepted), "accepted_page_models_inspected": page_models,
            "accepted_pages_without_model": len(without_model),
            "accepted_models_without_nodes": len(models_without_nodes),
            "model_nodes_inspected": modeled_nodes, "supply_pin_occurrences": len(rows),
            "review_queue_occurrences": len(review_rows),
            "pages_with_supply_pins": len({row["page"] for row in rows}),
            "card_types_with_supply_pins": len({row["card_type"] for row in rows}),
            "classification": dict(sorted(counts.items())),
            "contact": dict(sorted(contact_counts.items())),
        },
        "concerns": concern_rows,
        "outside_node_audit_by_folder": {
            "without_model": dict(sorted(Counter(Path(page).parts[1] for page in without_model).items())),
            "model_without_nodes": dict(sorted(Counter(Path(page).parts[1] for page in models_without_nodes).items())),
        },
        "all_occurrences_csv": str(ROWS.relative_to(ROOT)),
        "review_queue_csv": str(REVIEW_QUEUE.relative_to(ROOT)),
        "card_diagram_mentions": [
            {"diagram": str(path.relative_to(ROOT)), "contacts": sorted(set(re.findall(
                r"(?<![A-Z0-9])(?:D08|J08|D03|J03|B06|G06|B11|G11)(?![A-Z0-9])",
                path.read_text(encoding="utf-8"))))}
            for path in sorted((ROOT / "Card-ALD").glob("*.txt"))
            if re.search(r"(?<![A-Z0-9])(?:D08|J08|D03|J03|B06|G06|B11|G11)(?![A-Z0-9])",
                         path.read_text(encoding="utf-8"))
        ],
        "interpretation": "Local voltage ties are candidates until their printed topology is checked. Outputs and modeled signal drivers on supply contacts are concerns; shared or standalone cases need review. No ALD transcription is changed by this audit.",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ROWS.parent.mkdir(parents=True, exist_ok=True)
    fields = ["page", "folder", "block", "card_type", "card_kind", "portion",
              "location", "printed_pin", "contact", "rail", "side", "classification",
              "drawn_wire", "model", "pin_index", "net_count", "net_ids",
              "same_portion_output_candidates"]

    def flat(row):
        return {**{key: row.get(key) for key in fields},
                "net_count": len(row["nets"]),
                "net_ids": ";".join(str(net["id"]) for net in row["nets"]),
                "same_portion_output_candidates": ";".join(
                    f"{candidate['pin']} ({candidate['independent_pages']} pages)"
                    for candidate in row["same_portion_ordinary_pin_comparison"])}

    with ROWS.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda row: (str(row["page"]), str(row["block"]), row["pin_index"])):
            writer.writerow(flat(row))
    severity = {"concern_output_on_supply_contact": 0,
                "concern_modeled_signal_drive_to_supply": 1,
                "concern_unknown_direction": 2}
    with REVIEW_QUEUE.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in sorted(review_rows, key=lambda row: (
                severity.get(row["classification"], 3), str(row["page"]),
                str(row["block"]), row["pin_index"])):
            writer.writerow(flat(row))
    report["all_occurrences_csv_sha256"] = digest(ROWS)
    report["review_queue_csv_sha256"] = digest(REVIEW_QUEUE)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    audit()

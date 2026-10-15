"""Read-only audit of physical ALD pin labels against the SLT card rules.

The source JSON and TIFF scans are never changed. Findings are exported to
csv/Pin validation, with a compact provenance summary under notes.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import csv
import json
import re


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "json" / "A1 Socket Listing" / "Socket reference.json"
OBSERVATIONS = ROOT / "csv" / "Card types" / "Pin observations.csv"
FINDINGS = ROOT / "csv" / "Pin validation" / "ALD pin findings.csv"
UNCLASSIFIED = ROOT / "csv" / "Pin validation" / "Unclassified ALD terminals.csv"
SUMMARY = ROOT / "notes" / "Pin validation" / "ALD pin audit summary.json"
PIN = re.compile(r"^([0-9]*)([A-Z])([0-9]{2})([✲*]?)$")


def card_kinds():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    kinds = defaultdict(set)
    for record in data["records"]:
        card_type = record.get("card_type")
        literal = str(record.get("kind", "")).upper()
        if not card_type:
            continue
        if "SINGLE" in literal:
            kinds[str(card_type)].add("single")
        elif "DOUBLE" in literal:
            kinds[str(card_type)].add("double")
    if any(len(value) > 1 for value in kinds.values()):
        raise ValueError("A card type is classified both single and double")
    return {card_type: next(iter(values)) for card_type, values in kinds.items()}


def issue(pin, kind):
    if "�" in pin and len(pin) <= 5 and any(ch.isdigit() for ch in pin):
        return "unreadable_pin"
    match = PIN.fullmatch(pin)
    if not match:
        return None  # another terminal/control label, not a parsed pin number
    _, letter, number_text, _ = match.groups()
    number = int(number_text)
    if not 2 <= number <= 13:
        return "number_outside_02_to_13"
    if letter not in "BDGJ":
        return "letter_outside_BDGJ"
    if kind == "single" and letter in "GJ":
        return "single_card_has_G_or_J"
    return None


def cross_page_support():
    """Count independent pages that show a valid pin on the same portion."""
    evidence = defaultdict(lambda: defaultdict(set))
    with OBSERVATIONS.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            pin = row.get("physical_pin") or ""
            if not PIN.fullmatch(pin) or issue(pin, "unknown"):
                continue
            key = (row.get("card_type"), row.get("portion"),
                   row.get("direction"), pin[-2:])
            evidence[key][pin].add(row.get("page"))
    return evidence


def audit():
    kinds = card_kinds()
    support = cross_page_support()
    fields = [
        "folder", "page", "json_file", "json_sha256", "node_id", "grid",
        "card_type", "portion", "card_kind", "pin_index", "pin", "direction",
        "reason", "best_guess", "supporting_pages", "source_scan", "source_reviewed",
    ]
    findings = []
    unclassified = []
    counts = Counter()
    by_folder = Counter()
    by_reason = Counter()
    by_page = Counter()
    json_files = 0
    pages_with_pin_fields = set()
    classified_pages = set()
    for path in sorted((ROOT / "json").rglob("*.json")):
        if path.parent.name in {"A1 Socket Listing", "Card types"}:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            counts["unreadable_json_files"] += 1
            continue
        if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
            continue
        json_files += 1
        page = str(data.get("page") or path.stem.split()[0])
        folder = path.parent.name
        source_scan = str(data.get("source") or "")
        digest = sha256(path.read_bytes()).hexdigest()
        for node_index, node in enumerate(data["nodes"]):
            if not isinstance(node, dict) or not isinstance(node.get("pins"), list):
                continue
            card_type = str(node.get("card_type") or "")
            kind = kinds.get(card_type, "unknown")
            for pin_index, field in enumerate(node["pins"]):
                if not isinstance(field, dict) or field.get("pin") is None:
                    continue
                pin = str(field["pin"]).strip()
                if not pin:
                    continue
                counts["terminal_fields_seen"] += 1
                if kind == "unknown":
                    if PIN.fullmatch(pin) or ("�" in pin and len(pin) <= 5 and any(ch.isdigit() for ch in pin)):
                        counts["unclassified_candidates"] += 1
                        pages_with_pin_fields.add((folder, page))
                        unclassified.append({
                            "folder": folder,
                            "page": page,
                            "json_file": str(path.relative_to(ROOT)).replace("\\", "/"),
                            "json_sha256": digest,
                            "node_id": node.get("id", ""),
                            "grid": node.get("grid", ""),
                            "card_type": card_type,
                            "portion": node.get("portion", ""),
                            "card_kind": kind,
                            "pin_index": pin_index,
                            "pin": pin,
                            "direction": field.get("side", ""),
                            "reason": "card_kind_unclassified",
                            "best_guess": "",
                            "supporting_pages": "",
                            "source_scan": source_scan,
                            "source_reviewed": node.get("source_reviewed", ""),
                        })
                    else:
                        counts["other_terminal_labels"] += 1
                    continue
                reason = issue(pin, kind)
                if not reason:
                    if PIN.fullmatch(pin):
                        counts["physical_pin_candidates"] += 1
                        counts["valid"] += 1
                        pages_with_pin_fields.add((folder, page))
                        classified_pages.add((folder, page))
                    else:
                        counts["other_terminal_labels"] += 1
                    continue
                counts["physical_pin_candidates"] += 1
                pages_with_pin_fields.add((folder, page))
                classified_pages.add((folder, page))
                counts["findings"] += 1
                by_folder[folder] += 1
                by_reason[reason] += 1
                by_page[(folder, page)] += 1
                guess = ""
                support_pages = ""
                match = PIN.fullmatch(pin)
                suffix = match.group(3) if match else pin[-2:] if len(pin) == 3 and pin[-2:].isdigit() else None
                if suffix:
                    key = (card_type, str(node.get("portion") or ""),
                           str(field.get("side") or ""), suffix)
                    choices = {
                        candidate: pages - {page}
                        for candidate, pages in support.get(key, {}).items()
                        if not issue(candidate, kind)
                        and ("�" not in pin or all(a == "�" or a == b for a, b in zip(pin, candidate)))
                    }
                    choices = {candidate: pages for candidate, pages in choices.items() if pages}
                    if len(choices) == 1:
                        guess, pages = next(iter(choices.items()))
                        support_pages = ";".join(sorted(pages))
                        counts["unique_cross_page_guess"] += 1
                findings.append({
                    "folder": folder,
                    "page": page,
                    "json_file": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "json_sha256": digest,
                    "node_id": node.get("id", ""),
                    "grid": node.get("grid", ""),
                    "card_type": card_type,
                    "portion": node.get("portion", ""),
                    "card_kind": kind,
                    "pin_index": pin_index,
                    "pin": pin,
                    "direction": field.get("side", ""),
                    "reason": reason,
                    "best_guess": guess,
                    "supporting_pages": support_pages,
                    "source_scan": source_scan,
                    "source_reviewed": node.get("source_reviewed", ""),
                })
    FINDINGS.parent.mkdir(parents=True, exist_ok=True)
    with FINDINGS.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(findings)
    with UNCLASSIFIED.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(unclassified)
    summary = {
        "schema": "ald-pin-rule-audit-v2",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "rule": {
            "single_card": "B02-B13 and D02-D13",
            "double_card": "B02-B13, D02-D13, G02-G13, J02-J13",
            "unknown_kind": "Only the universal BDGJ/02-13 range is checked",
        },
        "a1_source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "a1_sha256": sha256(SOURCE.read_bytes()).hexdigest(),
        "observation_source": str(OBSERVATIONS.relative_to(ROOT)).replace("\\", "/"),
        "observation_sha256": sha256(OBSERVATIONS.read_bytes()).hexdigest(),
        "json_page_files_scanned": json_files,
        "pages_with_pin_fields": len(pages_with_pin_fields),
        "pages_with_classified_card_pin_fields": len(classified_pages),
        "terminal_fields_seen": counts["terminal_fields_seen"],
        "physical_pin_candidates": counts["physical_pin_candidates"],
        "unclassified_terminal_candidates": counts["unclassified_candidates"],
        "other_terminal_labels": counts["other_terminal_labels"],
        "valid_fields": counts["valid"],
        "finding_count": counts["findings"],
        "unique_cross_page_guesses": counts["unique_cross_page_guess"],
        "unreadable_json_files": counts["unreadable_json_files"],
        "findings_by_reason": dict(sorted(by_reason.items())),
        "findings_by_folder": dict(sorted(by_folder.items())),
        "pages_with_findings": len(by_page),
        "csv": str(FINDINGS.relative_to(ROOT)).replace("\\", "/"),
        "csv_sha256": sha256(FINDINGS.read_bytes()).hexdigest(),
        "unclassified_csv": str(UNCLASSIFIED.relative_to(ROOT)).replace("\\", "/"),
        "unclassified_csv_sha256": sha256(UNCLASSIFIED.read_bytes()).hexdigest(),
        "scope_note": (
            "Checks parsed physical pin candidates on A1-classified SLT cards "
            "in published ALD JSON. Other terminals remain in a separate "
            "unclassified report; ZA service grounds and cable connectors may "
            "use other alphabets and must not be silently called misreadings. "
            "Numeric control prefixes and asterisk decorations are separated "
            "before applying the pin rule; words and non-pin control labels "
            "are not treated as pin numbers. "
            "It does not OCR the TIFFs or alter accepted TXT/JSON; every flagged "
            "reading must be checked against its source and acceptance record."
        ),
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = audit()
    print(json.dumps({key: result[key] for key in (
        "json_page_files_scanned", "pages_with_pin_fields", "terminal_fields_seen",
        "physical_pin_candidates", "unclassified_terminal_candidates",
        "valid_fields", "finding_count", "findings_by_reason",
    )}, indent=2))

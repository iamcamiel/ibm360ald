"""List observed 0141 U03AA input wedges against the plain-input card view.

This compares current accepted page models. A wedge is an ALD page-polarity
notation variant, not a different physical AND circuit.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bound(path, repo):
    return {"path": path.relative_to(repo).as_posix() if path.is_relative_to(repo) else str(path),
            "sha256": sha(path)}


def inputs(occurrence):
    result = {}
    repeated = []
    for pin in occurrence["pins"]:
        if pin["side"] != "input" or not pin.get("physical_pin_candidate"):
            continue
        key = pin["physical_pin_candidate"]
        state = bool(pin.get("triangle"))
        if key in result:
            repeated.append(key)
            if result[key] != state:
                result[key] = None  # Conflicting modeled polarity; review source.
        else:
            result[key] = state
    return result, sorted(set(repeated))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    catalog_path = repo / "json/Card types current/0141.json"
    manual_path = Path("D:/Reference Materials/IBM 360/Z22-2798-1_Solid_Logic_Technology_Component_Circuits.pdf")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    all_occurrences = catalog["diagram_occurrences"]
    portions = ("A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2")
    reference = {}
    for portion in portions:
        matches = [x for x in all_occurrences if x["page"] == "XX651" and x["portion"] == portion]
        assert len(matches) == 1 and matches[0]["circuit_identifier"] == "U03AA"
        reference[portion], repeats = inputs(matches[0])
        assert not repeats
        assert len(reference[portion]) == 2 and sum(reference[portion].values()) == 1
    compared = [x for x in all_occurrences if x["portion"] in portions
                and x["circuit_identifier"] == "U03AA" and x["primary_function"] == "A"]
    variations = []
    marked_contacts = Counter()
    duplicate_occurrences = []
    for occurrence in compared:
        expected = reference[occurrence["portion"]]
        actual, repeated = inputs(occurrence)
        if repeated:
            duplicate_occurrences.append({"page": occurrence["page"],
                                          "block": occurrence["node"],
                                          "portion": occurrence["portion"],
                                          "repeated_input_pin_labels": repeated})
        marked = [{"pin": pin, "low_active_wedge": True,
                   "also_marked_on_xx651": expected.get(pin)}
                  for pin, value in actual.items() if value is True]
        if not marked:
            continue
        for mark in marked:
            marked_contacts[(occurrence["portion"], mark["pin"])] += 1
        variations.append({
            "page": occurrence["page"], "block": occurrence["node"],
            "portion": occurrence["portion"], "circuit_identifier": "U03AA",
            "source_text": occurrence["source_text"],
            "node_pointer": occurrence["node_pointer"],
            "location": occurrence["location"],
            "observed_input_wedges": actual,
            "page_input_wedges": marked,
            "reference_pins_not_shown": sorted(set(expected) - set(actual)),
            "other_visible_input_pins": sorted(set(actual) - set(expected)),
            "repeated_input_pin_labels": repeated,
            "review_status": "Model-observed polarity notation; check native scan before calling any transcription wrong."})
    variations.sort(key=lambda x: (x["page"], x["block"], x["portion"]))
    xx = [x for x in variations if x["page"] == "XX651"]
    assert len(xx) == 8 and all(len(x["page_input_wedges"]) == 1 for x in xx)
    for row in xx:
        row["review_status"] = "Input wedge verified on the native XX651 group crop; retained only as source-page polarity notation."
        group = row["portion"][0]
        row["native_crop"] = bound(repo / f"notes/Card-ALD/evidence/0141/XX651-{group}-group-native.png", repo)
    kt = [x for x in compared if (x["page"], x["node"], x["portion"]) == ("KT755", "AM", "A2")]
    assert len(kt) == 1 and inputs(kt[0])[0] == {"D09": False, "B08": False}
    assert not any((x["page"], x["block"]) == ("KT755", "AM") for x in variations)
    report = {
        "schema": "card-0141-u03aa-input-wedge-variations-v2",
        "scope": "A1/A2 through D1/D2 U03AA AND portions; the Card-ALD function view uses plain inputs.",
        "interpretation": "U03AA is an AND circuit. Input wedges on ALD pages denote signal polarity; they do not alter the normalized card function. U03AE is an OR with inverted output in the card view.",
        "manual_reference": {**bound(manual_path, repo), "printed_pages": "24-25", "section": "Wedges"},
        "source_catalog": bound(catalog_path, repo),
        "source_page_example": "XX651", "xx651_input_wedges": reference,
        "plain_input_example": {"page": "KT755", "block": "AM", "portion": "A2",
                                "inputs": inputs(kt[0])[0],
                                "native_crop": bound(repo / "notes/Card-ALD/evidence/0141/pins/KT755-AM-A2-input-B06.png", repo),
                                "physical_pin_answer": "B08; the scan-only B06 was corrected separately"},
        "counts": {"u03aa_and_occurrences_compared": len(compared),
                   "occurrences_with_input_wedges": len(variations),
                   "pages_with_input_wedges": len({x["page"] for x in variations}),
                   "wedge_marked_contacts": sum(marked_contacts.values()),
                   "occurrences_with_repeated_input_pin_labels": len(duplicate_occurrences)},
        "wedge_marks_by_portion_and_pin": [
            {"portion": portion, "pin": pin, "occurrences": count}
            for (portion, pin), count in sorted(marked_contacts.items())],
        "variations": variations,
        "repeated_input_pin_labels": duplicate_occurrences,
        "caution": "These counts come from current page models. Native XX651 group crops confirm that page's wedges; other modeled marks need their own scan check before being called source-confirmed. No page model is changed based only on this comparison."
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"]))


if __name__ == "__main__":
    main()

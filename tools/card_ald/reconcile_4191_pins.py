"""Suggest 4191 pin-label readings from other occurrences of each portion.

This produces review candidates only; it does not edit accepted ALD text or
JSON. A contact can be unused on a particular block, so absence is ignored.
"""

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "notes" / "Card-ALD"


def read(name):
    with (REPORT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    rows = read("4191 all-occurrence comparison.csv")
    review = json.loads((REPORT / "4191 review decisions.json").read_text(
        encoding="utf-8"))
    confirmed = {(item["page"], item["block"], item["side"], item["from"]): item
                 for item in review["confirmed_pin_corrections"]}
    counts = defaultdict(Counter)
    by_location = defaultdict(Counter)
    evidence = defaultdict(set)
    for row in rows:
        for token in row["pins"].split():
            side, pin = token.split(":", 1)
            key = (row["portion"], side)
            counts[key][pin] += 1
            by_location[(row["portion"], side, row["location"])][pin] += 1
            evidence[(row["portion"], side, pin)].add(row["page"])
    result = []
    for row in rows:
        for token in row["invalid_pinlike_labels"].split():
            side, raw = token.split(":", 1)
            key = (row["portion"], side)
            same_digits = [pin for pin in counts[key] if pin[1:] == raw[-2:]]
            same_digits.sort(key=lambda pin: (-by_location[
                (row["portion"], side, row["location"])][pin],
                -counts[key][pin], pin))
            local = by_location[(row["portion"], side, row["location"])]
            local_matches = [pin for pin in same_digits if local[pin]]
            verified = confirmed.get((row["page"], row["block"], side, raw))
            if verified:
                assessment, guess = verified["method"], verified["to"]
            elif len(same_digits) == 1:
                assessment, guess = "unique same-number contact", same_digits[0]
            elif len(local_matches) == 1:
                assessment, guess = "unique contact at same socket", local_matches[0]
            elif same_digits:
                assessment, guess = "ambiguous", same_digits[0]
            else:
                assessment, guess = "no same-number contact", ""
            result.append({
                "page": row["page"], "block": row["block"],
                "portion": row["portion"], "location": row["location"],
                "side": side, "printed_model_pin": raw,
                "best_guess": guess, "assessment": assessment,
                "same_number_candidates": " ".join(same_digits),
                "same_socket_counts": " ".join(f"{pin}:{local[pin]}"
                                               for pin in same_digits),
                "all_occurrence_counts": " ".join(f"{pin}:{counts[key][pin]}"
                                                   for pin in same_digits),
                "supporting_pages": " ".join(sorted(evidence.get(
                    (row["portion"], side, guess), []))),
            })
    out = REPORT / "4191 pin reading candidates.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result[0]))
        writer.writeheader()
        writer.writerows(result)
    print(f"{len(result)} invalid labels; candidates in {out}")
    print(dict(Counter(item["assessment"] for item in result)))


if __name__ == "__main__":
    main()

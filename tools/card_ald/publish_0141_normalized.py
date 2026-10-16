"""Publish the owner-approved 0141 function view with an exact glyph delta."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT.parent / "tmp/ald-text/ald/card-0141-review/normalized-function"
NOTES = ROOT / "notes/Card-ALD"
HISTORY = NOTES / "history"
CURRENT = ROOT / "Card-ALD/0141.txt"
PROVENANCE = NOTES / "0141 drawing provenance.json"
RECEIPT = NOTES / "0141 diagram publication receipt.json"
CANDIDATE = WORK / "0141 candidate.txt"
CANDIDATE_PROVENANCE = WORK / "0141 candidate provenance.json"
ANSWER = WORK / "Human function presentation answer.json"
ANSWER_PUBLISHED = NOTES / "0141 function presentation answer.json"
DELTA = NOTES / "0141 normalized function delta review.json"
WEDGE_AUDIT = NOTES / "0141 input wedge variation audit.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def bound(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}


old = CURRENT.read_bytes()
candidate = CANDIDATE.read_bytes()
old_provenance = read(PROVENANCE)
old_receipt = read(RECEIPT)
candidate_provenance = read(CANDIDATE_PROVENANCE)
answer = read(ANSWER)
assert old_provenance["published_sha256"] == digest(CURRENT)
assert old_receipt["diagram"]["sha256"] == digest(CURRENT)
assert old_receipt["provenance"]["sha256"] == digest(PROVENANCE)
assert candidate_provenance["draft_sha256"] == digest(CANDIDATE)
assert answer["circuit_functions"] == {"U03AA": "AND", "U03AE": "OR with inverted output"}
for value in candidate_provenance["source_files"].values():
    assert digest(Path(value["path"])) == value["sha256"]
assert read(WEDGE_AUDIT)["counts"]["u03aa_and_occurrences_compared"] >= 8

before = old.decode("utf-8").splitlines()
after = candidate.decode("utf-8").splitlines()
assert before[:3] == after[:3]
assert after[4:6] == [
    "CARD FUNCTION: U03AA = AND; U03AE = OR WITH INVERTED OUTPUT (◺).",
    "XX651 INPUT WEDGES ARE PAGE POLARITY MARKS; SEE THE WEDGE VARIATION AUDIT.",
]
old_body, new_body = before[4:], after[7:]
assert len(old_body) == len(new_body) == 56
differences = []
for y, (a, b) in enumerate(zip(old_body, new_body)):
    assert len(a) == len(b), y
    differences.extend((x, y, ac, bc) for x, (ac, bc) in enumerate(zip(a, b)) if ac != bc)
expected = {(23, y, "◺", "│") for y in (1, 12, 15, 26, 29, 40, 43, 54)}
expected |= {(59, y, "│", "◺") for y in (10, 24, 38, 52)}
assert set(differences) == expected, differences

HISTORY.mkdir(parents=True, exist_ok=True)
historical = {
    HISTORY / "0141 XX651 source-style drawing.txt": old,
    HISTORY / "0141 XX651 source-style drawing provenance.json": PROVENANCE.read_bytes(),
    HISTORY / "0141 XX651 source-style publication receipt.json": RECEIPT.read_bytes(),
}
for path, contents in historical.items():
    if path.exists():
        assert path.read_bytes() == contents, path
    else:
        path.write_bytes(contents)

if ANSWER_PUBLISHED.exists():
    assert read(ANSWER_PUBLISHED) == answer
else:
    write(ANSWER_PUBLISHED, answer)

delta = {
    "schema": "card-0141-normalized-function-exact-delta-v1",
    "source_style_drawing": bound(HISTORY / "0141 XX651 source-style drawing.txt"),
    "source_style_provenance": bound(HISTORY / "0141 XX651 source-style drawing provenance.json"),
    "source_style_publication": bound(HISTORY / "0141 XX651 source-style publication receipt.json"),
    "normalized_candidate": {"path": str(CURRENT.relative_to(ROOT)), "sha256": digest(CANDIDATE)},
    "owner_instruction": bound(ANSWER_PUBLISHED),
    "page_variation_audit": bound(WEDGE_AUDIT),
    "checks": {
        "all_12_boxes_and_all_wires_unchanged": True,
        "input_pin_labels_unchanged": True,
        "output_pin_labels_unchanged": True,
        "eight_and_input_wedges_removed": True,
        "four_or_output_wedges_added": True,
        "no_other_body_glyph_changed": True,
    },
    "changed_body_cells": [
        {"column": x, "row": y, "before": ac, "after": bc}
        for x, y, ac, bc in sorted(differences, key=lambda t: (t[1], t[0]))
    ],
    "interpretation": "The card view shows U03AA AND inputs plainly and U03AE OR outputs inverted. XX651's input wedges remain faithfully transcribed in its ALD page and are recorded as a page-polarity variant.",
}
write(DELTA, delta)

CURRENT.write_bytes(candidate)
current_provenance = dict(old_provenance)
current_provenance.update({
    "schema": "card-ald-current-drawing-provenance-v2",
    "published_sha256": digest(CURRENT),
    "presentation": "Normalized card functions: U03AA AND with plain inputs; U03AE OR with inverted output.",
    "supersedes_source_style_provenance": bound(HISTORY / "0141 XX651 source-style drawing provenance.json"),
    "exact_delta_review": bound(DELTA),
    "owner_instruction": bound(ANSWER_PUBLISHED),
    "page_variation_audit": bound(WEDGE_AUDIT),
})
write(PROVENANCE, current_provenance)

current_receipt = dict(old_receipt)
current_receipt.update({
    "schema": "card-0141-normalized-diagram-publication-v2",
    "diagram": bound(CURRENT),
    "provenance": bound(PROVENANCE),
    "supersedes_source_style_publication": bound(HISTORY / "0141 XX651 source-style publication receipt.json"),
    "owner_instruction": bound(ANSWER_PUBLISHED),
    "exact_delta_review": bound(DELTA),
    "page_variation_audit": bound(WEDGE_AUDIT),
})
write(RECEIPT, current_receipt)
assert read(RECEIPT)["diagram"]["sha256"] == digest(CURRENT)
assert read(RECEIPT)["provenance"]["sha256"] == digest(PROVENANCE)
print(json.dumps({"diagram_sha256": digest(CURRENT), "changed_body_cells": len(differences),
                  "historical_artifacts": len(historical)}, indent=2))

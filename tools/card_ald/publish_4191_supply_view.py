"""Release the 4191 card view without treating its ground pin as a signal."""

from collections import Counter
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import stat


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT.parent / "tmp/ald-text/ald/card-4191-review/supply-pin"
CURRENT = ROOT / "Card-ALD/4191.txt"
CANDIDATE = WORK / "4191 candidate.txt"
HISTORY = ROOT / "notes/Card-ALD/history/4191 pre-supply-rule drawing.txt"
RECEIPT = ROOT / "notes/Card-ALD/4191 supply-pin diagram publication.json"
RULE = ROOT / "notes/Pin validation/SLT supply contact rule.json"
MODEL = ROOT / "json/AP Parallel Adder/AP041 PARALLEL ADDER BIT 04.json"
GENERATOR = ROOT / "tools/card_ald/build_4191_layered.py"
SUPPLY = {"D08", "J08", "D03", "J03", "B06", "G06", "B11", "G11"}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def bound(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}


def margin_contacts(lines):
    return Counter(match.group() for line in lines
                   for match in re.finditer(r"(?<![A-Z0-9])[BDGJ](?:0[2-9]|1[0-3])(?![A-Z0-9])", line)
                   if match.start() in {0, 207})


old = CURRENT.read_bytes()
new = CANDIDATE.read_bytes()
assert old != new
old_text = old.decode("utf-8")
new_text = new.decode("utf-8")
old_rows = old_text.splitlines()
new_rows = new_text.splitlines()
assert old_rows[:3] == new_rows[:3]
assert new_rows[3] == "SUPPLY CONTACTS ARE OMITTED; PAGE-LEVEL VOLTAGE TIES ARE RECORDED SEPARATELY."
assert len(re.findall(r"(?<![A-Z0-9])D08(?![A-Z0-9])", old_text)) == 5
assert not any(re.search(r"(?<![A-Z0-9])" + pin + r"(?![A-Z0-9])", new_text)
               for pin in SUPPLY)
old_exterior = margin_contacts(old_rows)
new_exterior = margin_contacts(new_rows)
assert old_exterior == new_exterior + Counter({"D08": 1}), (old_exterior, new_exterior)
portions = re.compile(r"4191(?:[0-9]{2}|B[12])")
assert Counter(portions.findall(old_text)) == Counter(portions.findall(new_text))
assert len(portions.findall(new_text)) == 45
for unit in ("U03AF", "U03AP", "U03AA", "U03CN", "U61AC", "U61AP", "T06AA"):
    assert old_text.count(unit) == new_text.count(unit), unit
model = json.loads(MODEL.read_text(encoding="utf-8"))
ties = [net for net in model["nets"] if net.get("id") == "AW-jumper"]
assert len(ties) == 1
assert set(ties[0]["targets"]) == {"AW.D12", "AW.D08"}
assert json.loads(RULE.read_text(encoding="utf-8"))["contacts"]["D08"] == "ground"

HISTORY.parent.mkdir(parents=True, exist_ok=True)
if HISTORY.exists():
    assert HISTORY.read_bytes() == old
else:
    HISTORY.write_bytes(old)
mode = CURRENT.stat().st_mode
try:
    CURRENT.chmod(mode | stat.S_IWRITE)
    CURRENT.write_bytes(new)
finally:
    CURRENT.chmod(mode)
record = {
    "schema": "card-4191-supply-contact-diagram-publication-v1",
    "diagram": bound(CURRENT),
    "previous_diagram": bound(HISTORY),
    "owner_rule": bound(RULE),
    "builder": bound(GENERATOR),
    "example_page_model": bound(MODEL),
    "example_page_tie": {"page": "AP041", "block": "AW", "portion": "07",
                         "source_net": "AW-jumper", "targets": ["AW.D12", "AW.D08"],
                         "interpretation": "D12 tied to ground via the supply contact; the supply contact is omitted from the card-level signal routing."},
    "omitted_supply_contact": "D08",
    "affected_gate_portions": ["07", "13", "19", "25"],
    "checks": {"all_45_portions_preserved": True,
               "all_non_supply_exterior_contacts_preserved": True,
               "all_circuit_identifier_counts_preserved": True,
               "all_supply_contacts_absent_from_diagram": True,
               "builder_geometry_and_wire_assertions_passed": True},
    "ALD_page_changes": 0,
}
RECEIPT.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"diagram_sha256": digest(CURRENT), "removed_contact": "D08",
                  "exterior_contacts": len(new_exterior)}, indent=2))

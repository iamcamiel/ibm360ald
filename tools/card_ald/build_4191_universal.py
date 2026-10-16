"""Build the complete 5804191 composite pinout with manual-standard symbols."""

from collections import defaultdict
from pathlib import Path
import argparse
import re

from source_4191 import Canvas, SLICES


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "Card-ALD" / "4191.txt"
INPUT_PIN = re.compile(r"^[BDGJ](?:0[2-9]|1[0-3])$")
DRIVEN = {
    "J02", "D10", "B04", "G10", "G03", "B09", "D07", "B02", "B07",
    "G09", "J11", "G04", "J07", "D02", "J06",
}
BASES = (14, 77, 140, 203)
GATE_SLOTS = (0, 2, 3, 5, 6)
WIDTH = 212
OUTPUT_COL = 207


def route(c, start_x, source_y, target_y, track):
    """Separate A-to-OR wires, with a bend between block columns."""
    if source_y == target_y:
        c.h(start_x, 129, source_y)
        return
    c.h(start_x, track - 1, source_y)
    if source_y < target_y:
        c.put(track, source_y, "┐")
        c.v(track, source_y + 1, target_y - 1)
        c.put(track, target_y, "└")
    else:
        c.put(track, source_y, "┘")
        c.v(track, target_y + 1, source_y - 1)
        c.put(track, target_y, "┌")
    c.h(track + 1, 129, target_y)


def output(c, pin, y, from_x, declared):
    assert pin in DRIVEN and pin not in declared, pin
    declared.add(pin)
    c.h(from_x, OUTPUT_COL - 1, y)
    c.text(OUTPUT_COL, y, pin)


def draw(c):
    external = defaultdict(list)  # one pin label, possibly many sinks
    internal = defaultdict(list)
    local_branch_pins = set()
    block_pins = []  # pin labels printed flush against their block borders
    declared = set()
    portions = set()

    # Shared drivers sit just before the first gates that need them.
    # The output of 03 has no physical pin; 06 drives J02 externally too.
    p3_top = BASES[0] + 7
    p3_row = p3_top + 3
    c.box(60, p3_top, p3_top + 6, "03", "N", "U03AF", wedge_out=p3_row)
    portions.add("03")
    external["B08"].append((60, p3_row))
    block_pins.append((60, p3_row, "B08", "input"))
    c.h(68, 79, p3_row)
    c.put(80, p3_row, "┐")

    # The clear lane immediately above bit 47 keeps J02 off its A/R boxes.
    j02_top = BASES[3] - 7
    j02_row = j02_top + 3
    c.box(60, j02_top, j02_top + 6, "06", "N", "U03AF", wedge_out=j02_row)
    portions.add("06")
    external["B13"].append((60, j02_row))
    block_pins.extend(((60, j02_row, "B13", "input"),
                       (60, j02_row, "J02", "output")))
    output(c, "J02", j02_row, 68, declared)
    c.put(85, j02_row, "◇")

    for index, data in enumerate(SLICES):
        base = BASES[index]
        # The fifth A gate returns from this bit's own second N output.
        # In particular, bit 45 uses B07; D07 belongs to bit 44.
        assert data["gates"][4][-1] == data["n_out"][1], data["bit"]
        c.text(95, base - 3, f"GROUP {index + 1}")
        gate_locations = {}

        # All five sibling A gates share one column, including the first
        # gate, which has no clock input. The fifth has a feedback input.
        for gate_index, (portion, circuit, *observed_pins) in enumerate(data["gates"]):
            top = base + 7 * GATE_SLOTS[gate_index]
            x = 95
            gate_locations[portion] = (x, top)
            portions.add(portion)
            c.box(x, top, top + 6, portion, "A", circuit)
            pins = list(observed_pins)
            # D08 is the SLT ground contact. Some ALD pages print a local
            # jumper from D08 to a used signal input. The card view omits
            # this supply contact; it is never an external signal rail.
            # Equivalent inputs may exchange rows. Keep the input shared
            # with an R portion closest to that R box, so its branch never
            # crosses another input to the same A portion.
            if gate_index in {0, 2}:
                shared_pin = (data["term"][1] if gate_index == 0
                              else data["resistor"][1])
                assert pins.count(shared_pin) == 1, (portion, shared_pin)
                pins.remove(shared_pin)
                pins.append(shared_pin)
            input_rows = ([top + 2, top + 5] if len(pins) == 2
                          else [top + 2, top + 3, top + 5])
            for pin, y in zip(pins, input_rows, strict=True):
                if pin != "P3":
                    block_pins.append((x, y, pin, "input"))
                if pin in {"P3", "J02", "D07", "B07", "J11", "J07"}:
                    internal[pin].append((x, y))
                else:
                    assert INPUT_PIN.fullmatch(pin), (portion, pin)
                    external[pin].append((x, y))
            route(c, x + 8, top + 3,
                  base + 22 + gate_index, (126, 121, 116, 106, 111)[gate_index])

        term, term_pin = data["term"]
        c.box(95, base + 7, base + 13, term, "R T1", "U61AC")
        external[term_pin].append((95, base + 10))
        block_pins.append((95, base + 10, term_pin, "input"))
        local_branch_pins.add(term_pin)
        portions.add(term)
        resistor, shared_pin, shared_gate = data["resistor"]
        assert shared_gate == data["gates"][2][0]
        c.box(95, base + 28, base + 34, resistor, "R", "U61AP")
        external[shared_pin].append((95, base + 31))
        block_pins.append((95, base + 31, shared_pin, "input"))
        local_branch_pins.add(shared_pin)
        portions.add(resistor)

        # Five A outputs enter the five available input rows of a seven-row OR.
        c.box(130, base + 21, base + 27, data["join"], "✲OR", "U03CN",
              wedge_out=base + 24, input_count=5)
        portions.add(data["join"])
        output(c, data["net"], base + 24, 138, declared)
        block_pins.append((130, base + 24, data["net"], "output"))
        c.v(151, base + 11, base + 44)
        c.put(151, base + 10, "┌")
        c.put(151, base + 24, "◇")
        c.put(151, base + 45, "└")

        for n_index, (portion, pin) in enumerate(zip(data["n"], data["n_out"], strict=True)):
            top = base + (7 if n_index == 0 else 42)
            row = top + 3
            c.box(160, top, top + 6, portion, "N", "U03AF", wedge_in=row)
            c.h(152, 159, row)
            output(c, pin, row, 168, declared)
            block_pins.extend(((160, row, data["net"], "input"),
                               (160, row, pin, "output")))
            portions.add(portion)

        # The first three OR outputs also feed the common OR35. Bit 47's
        # fourth OR35 input is D06, a distinct external input pin.
        if index < 3:
            rail = 183 - index
            input_row = (267, 268, 270)[index]
            c.put(rail, base + 24, "◇")
            c.v(rail, base + 25, input_row - 1)
            c.put(rail, input_row, "└")
            c.h(rail + 1, 189, input_row)

    # Feedback outputs stay in the output column. Their internal branches
    # return through a corridor below each bit section, never past the pins.
    feedback = {
        "D07": (BASES[0] + 45, 174),
        "B07": (BASES[1] + 45, 174),
        "J11": (BASES[2] + 45, 173),
        "J07": (BASES[3] + 45, 172),
    }
    for pin, (source_row, bus) in feedback.items():
        sinks = internal.pop(pin)
        last_corridor = max(y + 6 for _, y in sinks)
        c.put(bus, source_row, "◇")
        c.v(bus, source_row + 1, last_corridor)
        for x, y in sinks:
            assert x == 95
            corridor = y + 6
            c.h(91, bus - 1, corridor)
            c.put(bus, corridor, "┘")
            c.put(90, corridor, "└")
            c.v(90, y + 1, corridor - 1)
            c.put(90, y, "┌")
            c.h(91, 94, y)

    for pin, bus, source_row in (("P3", 80, p3_row), ("J02", 85, j02_row)):
        sinks = internal.pop(pin)
        assert sinks and min(y for _, y in sinks) > source_row
        c.v(bus, source_row + 1, max(y for _, y in sinks))
        for sink_index, (x, y) in enumerate(sinks):
            assert x == 95
            c.put(bus, y, "└" if sink_index == len(sinks) - 1 else "◇")
            c.h(bus + 1, x - 1, y)
    assert not internal, internal

    # Common OR35: three internally driven inputs and one external input.
    c.box(190, 266, 272, "35", "OR", "U03AF",
          wedge_in=267, input_count=4)
    for y in (268, 270, 271):
        c.put(190, y, "◺")
    external["D06"].append((190, 271))
    output(c, "D02", 269, 198, declared)
    block_pins.extend(((190, 267, "D10", "input"),
                       (190, 268, "B04", "input"),
                       (190, 270, "G10", "input"),
                       (190, 271, "D06", "input"),
                       (190, 269, "D02", "output")))
    portions.add("35")

    # G08 is the shared outward pin of AR portion B1. One B1 output net
    # serves that pin and the unpinned input of B2; no duplicate G08 stub.
    c.box(60, 280, 286, "B1", "AR", "T06AA")
    c.box(95, 287, 293, "B2", "N", "U03AF", wedge_in=290)
    external["G08"].append((60, 283))
    block_pins.append((60, 283, "G08", "input"))
    c.h(68, 84, 283)
    c.put(85, 283, "┐")
    c.v(85, 284, 289)
    c.put(85, 290, "└")
    c.h(86, 94, 290)
    output(c, "J06", 290, 103, declared)
    block_pins.append((95, 290, "J06", "output"))
    portions.update(("B1", "B2"))

    # External input labels occupy only the left pin column. Repeated uses
    # of one pin share an interior vertical bus; single uses go straight in.
    multi = sorted(pin for pin, sinks in external.items()
                   if len(sinks) > 1 and pin not in local_branch_pins)
    assert len(multi) <= 25
    tracks = {pin: 20 + 3 * i for i, pin in enumerate(multi)}
    for pin, sinks in sorted(external.items()):
        assert INPUT_PIN.fullmatch(pin) and pin not in DRIVEN, (pin, sinks)
        sinks = sorted(set(sinks), key=lambda pair: pair[1])
        if pin in local_branch_pins:
            assert len(sinks) == 2 and all(x == 95 for x, _ in sinks), (pin, sinks)
            upper, lower = sinks[0][1], sinks[1][1]
            c.text(0, upper, pin)
            c.h(3, 90, upper)
            c.put(91, upper, "◇")
            c.h(92, 94, upper)
            c.v(91, upper + 1, lower - 1)
            c.put(91, lower, "└")
            c.h(92, 94, lower)
        elif len(sinks) == 1:
            x, y = sinks[0]
            c.text(0, y, pin)
            c.h(3, x - 1, y)
        else:
            track = tracks[pin]
            first_row = sinks[0][1]
            c.text(0, first_row, pin)
            c.h(3, track - 1, first_row)
            c.v(track, first_row, sinks[-1][1])
            for sink_index, (x, y) in enumerate(sinks):
                c.put(track, y, "└" if sink_index == len(sinks) - 1 else "◇")
                c.h(track + 1, x - 1, y)

    expected = {f"{number:02d}" for number in range(1, 44)} | {"B1", "B2"}
    assert portions == expected, (expected - portions, portions - expected)
    assert declared == DRIVEN, (DRIVEN - declared, declared - DRIVEN)
    assert len(external) + len(declared) == 40
    # Add physical designations last, after routing. A designation replaces
    # the final three wire characters directly against the appropriate box.
    assert len({(x - 3 if side == "input" else x + 8, y)
                for x, y, _, side in block_pins}) == len(block_pins)
    for x, y, pin, side in block_pins:
        assert INPUT_PIN.fullmatch(pin), (x, y, pin, side)
        c.text(x - 3 if side == "input" else x + 8, y, pin)
    return c, external, declared, block_pins


def build(output_path=OUTPUT):
    c = Canvas(WIDTH, 301)
    _, inputs, outputs, block_pins = draw(c)
    from universal_card_symbols import normalize_canvas
    geometry = normalize_canvas(c, "4191")
    assert len(c.boxes) == 45
    assert all(top % 7 == 0 and bottom - top == 6
               for _, top, bottom, _ in c.boxes)
    for base in BASES:
        assert {top for x, top, _, _ in c.boxes
                if x == 95 and base <= top <= base + 42} == {
                    base + 7 * slot for slot in range(7)}
        assert all("┼" not in row[103:130]
                   for row in c.rows[base:base + 49])
    horizontal = set("─┼◇┌┐└┘BDGJ")
    vertical = set("│┼◇┌┐└┘")
    for y, row in enumerate(c.rows):
        for x, char in enumerate(row):
            if char != "◇":
                continue
            connections = sum((x > 0 and row[x - 1] in horizontal,
                               x + 1 < WIDTH and row[x + 1] in horizontal,
                               y > 0 and c.rows[y - 1][x] in vertical,
                               y + 1 < len(c.rows) and c.rows[y + 1][x] in vertical))
            assert connections >= 3, (x, y, connections)
    lines = [
        "CARD-ALD  5804191  DOUBLE CARD  UNIVERSAL COMPOSITE PINOUT",
        "ALL 45 PORTIONS AND ALL 40 NONPOWER CONTACTS; MANUAL-STANDARD SYMBOLS.",
        "PINS AT THE BOXES AND ONCE AT THE OUTER EDGE; SEVEN-LINE BOX GRID.",
        "POWER CONTACTS: GROUND D08 J08",
        "POWER CONTACTS: +3V D03 J03",
        "POWER CONTACTS: -3V B06 G06    +6V B11 G11",
        "",
        c.render(),
        "",
        "R PORTIONS SIT BELOW THE GATES WHOSE INPUTS THEY TERMINATE.",
        "THE FIFTH A IN EACH GROUP HAS AN INTERNAL FEEDBACK INPUT.",
        "THE INPUT G08 FEEDS B1; ITS PINLESS OUTPUT FEEDS B2; B2 DRIVES J06.",
        "NUMBERED FILES SHOW WITNESSED NOTATION VARIANTS WITH IDENTICAL WIRING.",
        "SOURCE AND MANUAL REFERENCES ARE RECORDED IN THE ACCOMPANYING NOTES.",
    ]
    result = "\n".join(lines) + "\n"
    rows = result.splitlines()
    label_re = re.compile(r"(?<![A-Z0-9])[BDGJ](?:0[2-9]|1[0-3])(?![A-Z0-9])")
    expected_labels = set(inputs) | outputs
    outside_labels = [match.group() for row in rows[7:] for match in label_re.finditer(row)
                      if match.start() in {0, OUTPUT_COL}]
    assert len(outside_labels) == len(set(outside_labels)) == len(expected_labels) == 40
    assert set(outside_labels) == expected_labels
    assert "D08" not in expected_labels and "D08" not in c.render()
    for x, y, pin, side in block_pins:
        start = x - 3 if side == "input" else x + 8
        assert rows[y + 7][start:start + 3] == pin, (x, y, pin, side)
    assert len(rows) < 390 and max(map(len, rows)) <= WIDTH
    assert all("│" not in row[:3] and "│" not in row[OUTPUT_COL:] for row in rows)
    assert "U04" not in result and "U11" not in result and "U12" not in result
    portions = re.findall(r"4191([0-9]{2}|B[12])", result)
    assert len(portions) == len(set(portions)) == 45
    for row_index, row in enumerate(rows):
        for match in re.finditer(r"4191(?:[0-9]{2}|B[12])", row):
            if row_index < 7:
                continue
            assert rows[row_index + 2][match.start() - 1:match.start() + 7] == "└──────┘"
    from universal_card_symbols import save_geometry
    save_geometry(output_path, geometry, 7)
    output_path.write_text(result, encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    build(parser.parse_args().output)

"""Draw source-bound examples of 5804633 and 5804634 card wiring.

Each example combines ALD pages for one installed physical card.  It does
not turn absent, unused portion inputs into claims about its full pinout.
"""

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from source_4191 import Canvas


ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "json" / "AP Parallel Adder"
OUT = ROOT / "Card-ALD"
NOTES = ROOT / "notes" / "Card-ALD"
PIN = re.compile(r"[BDGJ](?:0[2-9]|1[0-3])\Z")
CONFIG = {
    "4633": {
        "location": "B-E1H6",
        "pages": ("AP441", "AP451", "AP461", "AP471", "AP473"),
        "socket": "02B-E1 H6",
    },
    "4634": {
        "location": "B-D2E3",
        "pages": ("AP071", "AP081", "AP091", "AP101", "AP111", "AP157"),
        "socket": "02B-D2 E3/E4",
    },
}

def physical_pin(card, page, portion, raw):
    if raw is None:
        return None
    raw = str(raw)
    if PIN.fullmatch(raw):
        return raw
    # The extra mark at a box edge or polarity annotation is distinct from
    # its three-character physical contact.  The native crops show these.
    if raw.endswith("✲") and PIN.fullmatch(raw[:-1]):
        return raw[:-1]
    if len(raw) == 4 and raw[0] in "8BH" and PIN.fullmatch(raw[1:]):
        return raw[1:]
    raise ValueError(f"Unresolved example pin {(card, page, portion, raw)}")


def load(card):
    cfg = CONFIG[card]
    groups = []
    all_nodes = {}
    for page in cfg["pages"]:
        path = next(MODEL.glob(page + " *.json"))
        doc = json.loads(path.read_text(encoding="utf-8"))
        nodes = [dict(n) for n in doc["nodes"] if n.get("card_type") == card
                 and n.get("location") == cfg["location"]]
        if not nodes:
            raise ValueError(f"No {card} instance on {page}")
        by_id = {n["id"]: n for n in nodes}
        for node in nodes:
            node["_page"] = page
            node["_inputs"] = []
            node["_outputs"] = []
            portion = str(node["portion"])
            if portion in all_nodes:
                raise ValueError((card, "Repeated example portion", portion))
            all_nodes[portion] = node
            for port in node.get("pins", []):
                pin = physical_pin(card, page, portion, port.get("pin"))
                entry = {"pin": pin, "raw": port.get("pin"),
                         "triangle": bool(port.get("triangle")),
                         "row": int(port.get("row", 0)),
                         "side": port.get("side"),
                         "ref": str(port.get("pin") or "input")}
                if entry["side"] == "input":
                    node["_inputs"].append(entry)
                elif entry["side"] == "output":
                    node["_outputs"].append(entry)
        edges = []
        for net in doc.get("nets", []):
            driver = net.get("driver")
            if not isinstance(driver, str):
                continue
            sid = driver.split(".", 1)[0]
            if sid not in by_id:
                continue
            for target in net.get("targets", []):
                tid = str(target).split(".", 1)[0]
                if tid in by_id:
                    edges.append((str(by_id[sid]["portion"]),
                                  str(by_id[tid]["portion"]),
                                  driver.split(".", 1)[-1],
                                  str(target).split(".", 1)[-1]))
        groups.append((page, nodes, edges))
    return groups, all_nodes


def primary_function(raw):
    raw = str(raw or "").strip()
    if raw.startswith("R T"):
        return " ".join(raw.split()[:2])
    return raw.split()[0] if raw else "�"


def depths(nodes, edges):
    depth = {str(n["portion"]): 0 for n in nodes}
    for _ in nodes:
        changed = False
        for source, target, _, _ in edges:
            if depth[target] <= depth[source]:
                depth[target] = depth[source] + 1
                changed = True
        if not changed:
            return depth
    raise ValueError("Unexpected same-card feedback cycle")


def order_with_terminators(nodes, global_depth):
    """Place an R directly below the nearest gate using its input contact.

    This only changes same-depth layout.  A shared pin does not create a
    directed graph edge from the R to that gate.
    """
    ordered = sorted(nodes, key=lambda n: (global_depth[str(n["portion"])],
                                           n.get("row", 0), n.get("column", 0)))
    last_for_anchor = {}
    resistors = [n for n in ordered if primary_function(n.get("function", "")).startswith("R T")]
    for resistor in resistors:
        pins = [p["pin"] for p in resistor["_inputs"] if p["pin"]]
        if len(pins) != 1:
            continue
        options = [n for n in nodes if n is not resistor
                   and not primary_function(n.get("function", "")).startswith("R T")
                   and global_depth[str(n["portion"])] == global_depth[str(resistor["portion"])]
                   and any(p["pin"] == pins[0] for p in n["_inputs"])]
        if not options:
            continue
        anchor = min(options, key=lambda n: (abs(n["row"] - resistor["row"]),
                                             abs(n["column"] - resistor["column"]),
                                             n["row"], n["column"], n["id"]))
        ordered.remove(resistor)
        preceding = last_for_anchor.get(str(anchor["portion"]), anchor)
        ordered.insert(ordered.index(preceding) + 1, resistor)
        last_for_anchor[str(anchor["portion"])] = resistor
    return ordered


def put_line(c, x1, x2, y):
    if x1 <= x2:
        c.h(x1, x2, y)


def draw_route(c, sx, sy, tx, ty, track):
    assert sx < track < tx, (sx, tx, track)
    put_line(c, sx + 1, track - 1, sy)
    if sy < ty:
        c.put(track, sy, "┐")
        c.v(track, sy + 1, ty - 1)
        c.put(track, ty, "└")
    elif sy > ty:
        c.put(track, sy, "┘")
        c.v(track, ty + 1, sy - 1)
        c.put(track, ty, "┌")
    else:
        c.put(track, sy, "─")
    put_line(c, track + 1, tx - 1, ty)


def build(card):
    groups, by_portion = load(card)
    db = json.loads((ROOT / "json" / "Card types" / f"{card}.json").read_text(encoding="utf-8"))
    missing = sorted(set(db["portions"]) - set(by_portion))
    width = 470
    height = 7 * (sum(len(nodes) + 2 for _, nodes, _ in groups) + 6)
    c = Canvas(width, height)
    c.text(0, 0, f"CARD-ALD  580{card}  DOUBLE CARD  EXAMPLE {CONFIG[card]['socket']}")
    c.text(0, 1, "SEVEN-ROW ALD BOX GRID.  OUTER PHYSICAL PINS ARE LISTED ONCE.")
    c.text(0, 2, "CONNECTIONS COME FROM PAGE NETS OR MATCHED PHYSICAL PINS ON THIS CARD.")
    all_edges = []
    for page, _, edges in groups:
        all_edges += [(page, *e) for e in edges]
    outputs_by_pin = defaultdict(set)
    inputs_by_pin = defaultdict(set)
    for portion, node in by_portion.items():
        for p in node["_outputs"]:
            if p["pin"]:
                outputs_by_pin[p["pin"]].add(portion)
        for p in node["_inputs"]:
            if p["pin"]:
                inputs_by_pin[p["pin"]].add(portion)
    # A pinless-looking page jump may still be a documented same-card
    # contact.  Matching its one physical driver to consumers on other ALD
    # pages completes the source-bound card graph.
    existing = {(s, t) for _, s, t, _, _ in all_edges}
    for pin in sorted(outputs_by_pin.keys() & inputs_by_pin.keys()):
        for source in sorted(outputs_by_pin[pin]):
            for target in sorted(inputs_by_pin[pin]):
                if source != target and (source, target) not in existing:
                    all_edges.append((f"SHARED {pin}", source, target, pin, pin))
                    existing.add((source, target))
    global_depth = depths(list(by_portion.values()),
                          [(s, t, out_ref, in_ref)
                           for _, s, t, out_ref, in_ref in all_edges])

    y_slot = 2
    group_data = []
    for page, nodes, edges in groups:
        # Keep the page tag outside the routed internal tracks.  Its card
        # identity and socket are already stated in the document header.
        c.text(0, 7 * y_slot + 2, page)
        y_slot += 1
        ordered = order_with_terminators(nodes, global_depth)
        for node in ordered:
            node["_depth"] = global_depth[str(node["portion"])]
            node["_x"] = 90 + 55 * node["_depth"]
            node["_top"] = 7 * y_slot
            node["_ports"] = []
            y_slot += 1
        y_slot += 1
        group_data.append((page, ordered, edges))

    # Identify physical output pins first.  If a pin is driven anywhere on
    # this installed card, its outer-edge occurrence belongs on the right.
    output_owners = defaultdict(list)
    for node in by_portion.values():
        for p in node["_outputs"]:
            if p["pin"]:
                output_owners[p["pin"]].append(str(node["portion"]))
    driven_pins = set(output_owners)
    for pin, owners in output_owners.items():
        if len(set(owners)) > 1:
            raise ValueError((card, "Multiple blocks driving physical pin", pin, owners))

    # Associate each captured internal edge with a distinct left-border row.
    targets = defaultdict(list)
    sources = defaultdict(list)
    for page, source, target, output_ref, input_ref in all_edges:
        targets[target].append((source, output_ref, input_ref))
        sources[source].append((target, output_ref, input_ref))
    external_sinks = defaultdict(list)
    output_rows = defaultdict(list)
    internal_rows = {}
    for portion, node in by_portion.items():
        incoming = targets[portion]
        physical_inputs = []
        seen = set()
        for p in node["_inputs"]:
            pin = p["pin"]
            if pin and pin not in seen:
                physical_inputs.append(p)
                seen.add(pin)
        # Each incoming internal connection consumes one input position.
        # When its source output carries a physical pin, the same contact
        # printed at the sink is an internal branch, not an external input.
        internal_pins = set()
        for source, out_ref, in_ref in incoming:
            source_pins = {p["pin"] for p in by_portion[source]["_outputs"]}
            internal_pins.update(pin for pin in source_pins if pin)
        external = [p for p in physical_inputs if p["pin"] not in internal_pins
                    and p["pin"] not in driven_pins]
        # Input captions that are physically driven on this card are shown
        # at the box but linked by their explicit internal edge below.
        count = len(external) + len(incoming)
        if count > 5:
            raise ValueError((card, portion, "More than five drawn inputs", count))
        rows = [node["_top"] + i for i in range(1, 6)]
        # Put the physically labelled inputs first, leaving separate rows
        # for the pinless internal returns.
        for p, y in zip(external, rows):
            node["_ports"].append(("input", y, p["pin"], p["triangle"]))
            external_sinks[p["pin"]].append((portion, y))
        pinless_inputs = sorted((p for p in node["_inputs"] if not p["pin"]),
                                key=lambda p: p["row"])
        pinless_index = 0
        for edge, y in zip(incoming, rows[len(external):]):
            source, out_ref, in_ref = edge
            matching = next((p for p in physical_inputs if p["pin"] and
                             p["pin"] in {q["pin"] for q in by_portion[source]["_outputs"]}), None)
            label = matching["pin"] if matching else None
            if matching is None and pinless_index < len(pinless_inputs):
                matching = pinless_inputs[pinless_index]
                pinless_index += 1
            node["_ports"].append(("input", y, label,
                                   matching["triangle"] if matching else True))
            internal_rows[(source, portion, out_ref, in_ref)] = y
        for p in physical_inputs:
            if p["pin"] in driven_pins and all(
                    p["pin"] != label for side, _, label, _ in node["_ports"] if side == "input"):
                raise ValueError((card, portion, "Driven contact lacks captured edge", p["pin"]))
        out = []
        for p in node["_outputs"]:
            key = p["pin"] if p["pin"] else "PINLESS"
            if key not in [q[0] for q in out]:
                out.append((key, p))
        if not out and sources[portion]:
            out = [("PINLESS", {"pin": None, "triangle": False})]
        available = [node["_top"] + i for i in (3, 2, 4, 1, 5)]
        for (key, p), y in zip(out, available):
            node["_ports"].append(("output", y, p["pin"], p["triangle"]))
            output_rows[portion].append((key, y))

    # Boxes are drawn before routing so no wire can run through one.
    for page, nodes, _ in group_data:
        for node in nodes:
            x, top = node["_x"], node["_top"]
            fn = primary_function(node.get("function"))
            if len(fn) > 6:
                raise ValueError((card, node["portion"], fn))
            c.box(x, top, top + 6, str(node["portion"]), fn,
                  str(node.get("unit") or "�")[:5])
            # Canvas.box has the 4191 card prefix in its reusable body.
            c.text(x + 1, top + 4, f"{card}{node['portion']}")
            for side, y, pin, triangle in node["_ports"]:
                c.put(x if side == "input" else x + 7, y,
                      "◺" if triangle else "│")

    # Route individual internal signals in distinct tracks.  Shared-driver
    # stems are deliberately joined with a diamond; unrelated crossings
    # remain ┼ via Canvas.h / Canvas.v.
    net_edges = defaultdict(list)
    for page, source, target, out_ref, in_ref in all_edges:
        net_edges[(source, out_ref)].append((target, in_ref, page))
    track_count = Counter()
    branch_points = []
    for (source, out_ref), sinks in net_edges.items():
        src = by_portion[source]
        srow = next((y for key, y in output_rows[source]
                     if key == out_ref or key == "PINLESS"), output_rows[source][0][1])
        gap = src["_depth"]
        track = src["_x"] + 14 + 2 * track_count[gap]
        track_count[gap] += 1
        sink_rows = []
        for target, in_ref, page in sinks:
            dst = by_portion[target]
            trow = internal_rows[(source, target, out_ref, in_ref)]
            if track >= dst["_x"] - 6:
                raise ValueError((card, page, "Too many tracks", source, target, track))
            sink_rows.append((target, trow))
        span = [srow] + [y for _, y in sink_rows]
        if min(span) < max(span):
            c.v(track, min(span), max(span))
        label = next((p["pin"] for p in src["_outputs"]
                      if p["pin"] and p["pin"] == out_ref), None)
        start = src["_x"] + 7 + (len(label) if label else 0)
        put_line(c, start + 1, track - 1, srow)
        for target, trow in sink_rows:
            put_line(c, track + 1, by_portion[target]["_x"] - 1, trow)
            c.put(track, trow, "◇" if min(span) < trow < max(span)
                  else "┌" if trow == min(span) else "└")
        branch_points.append((srow, track, label is not None,
                              min(span) < srow < max(span), max(span)))

    # One left-side label per physical input.  Shared contacts have a
    # vertical trunk between their sink rows, wholly inside the pin edges.
    for number, (pin, sinks) in enumerate(sorted(external_sinks.items())):
        sink_rows = sorted(set(y for _, y in sinks))
        first = sink_rows[0]
        c.text(0, first, pin)
        if len(sink_rows) == 1:
            portion, y = sinks[0]
            put_line(c, 3, by_portion[portion]["_x"] - 1, y)
        else:
            trunk = 18 + 3 * number
            if trunk >= 104:
                raise ValueError((card, "Input bus margin exhausted", pin))
            put_line(c, 3, trunk - 1, first)
            c.v(trunk, first, sink_rows[-1])
            for portion, y in sinks:
                put_line(c, trunk + 1, by_portion[portion]["_x"] - 1, y)
                c.put(trunk, y, "◇")

    # A physical pin appears exactly once at the outer output edge, even if
    # the source block prints it twice or an internal sink repeats its name.
    for pin, owners in sorted(output_owners.items()):
        owner = by_portion[owners[0]]
        row = next(y for key, y in output_rows[owners[0]] if key == pin)
        put_line(c, owner["_x"] + 8 + 3, width - 5, row)
        c.text(width - 4, row, pin)

    # Restore labels at the box faces after laying out the orthogonal wires.
    for portion, node in by_portion.items():
        x = node["_x"]
        for side, y, pin, _ in node["_ports"]:
            if pin:
                c.text(x - 3 if side == "input" else x + 8, y, pin)
    for row, track, has_outer_output, between_targets, last_row in branch_points:
        c.put(track, row, "◇" if has_outer_output or between_targets
              else "┐" if row < last_row else "┘")

    if missing:
        c.text(90, 7 * y_slot + 2,
               "UNROUTED IN THIS INSTANCE; OBSERVED ON OTHER ALD PAGES")
        y_slot += 1
        for index, portion in enumerate(missing):
            record = db["portions"][portion]
            functions = [x["value"] for x in record.get("function_facts", [])]
            circuits = [x["value"] for x in record.get("unit_code_facts", [])]
            function = "A/OR" if set(functions) == {"A", "OR"} else primary_function(functions[0])
            unit = next((value for value in circuits if len(value) == 5), "�")
            x = 90 + 110 * index
            top = 7 * y_slot
            c.box(x, top, top + 6, portion, function, unit)
            c.text(x + 1, top + 4, f"{card}{portion}")

    header = [
        f"CARD-ALD  580{card}  DOUBLE CARD  EXAMPLE {CONFIG[card]['socket']}",
        "THIS DRAWING JOINS THE SHOWN PAGES FOR ONE INSTALLED CARD; IT IS NOT A UNIVERSAL PINOUT.",
        f"OBSERVED PORTIONS IN EXAMPLE: {len(by_portion)} OF {len(db['portions'])} IN THE CARD DATABASE.",
        "DATABASE PORTIONS NOT SEEN IN THIS INSTALLATION: " + (", ".join(missing) if missing else "NONE"),
        "UNROUTED PORTIONS BELOW ARE OBSERVED ELSEWHERE; NO CONNECTIONS ARE INFERRED FOR THIS INSTALLATION.",
    ]
    result = c.render().splitlines()
    result[:3] = ["", "", ""]
    # Seven prefatory rows preserve the regular seven-line box grid.
    text = "\n".join(header + ["", ""] + result).rstrip() + "\n"
    OUT.mkdir(exist_ok=True)
    target = OUT / f"{card}.txt"
    target.write_text(text, encoding="utf-8")
    sources = []
    source_dir = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder")
    for page in CONFIG[card]["pages"]:
        model = next(MODEL.glob(page + " *.json"))
        native = next(source_dir.glob(page + " *.tif"))
        sources.append({
            "page": page,
            "model": str(model.relative_to(ROOT)),
            "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "source_tiff": str(native),
            "source_sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
        })
    provenance = {
        "schema": "card-ald-example-provenance-v1",
        "card_type": card,
        "part_number": f"580{card}",
        "installed_location": CONFIG[card]["socket"],
        "diagram": str(target.relative_to(ROOT)),
        "diagram_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "pages": sources,
        "observed_portions": len(by_portion),
        "database_portions": len(db["portions"]),
        "unrouted_portions": missing,
        "direct_page_net_edges": sum(not page.startswith("SHARED ") for page, *_ in all_edges),
        "cross_page_shared_pin_edges": sum(page.startswith("SHARED ") for page, *_ in all_edges),
        "interpretation": "Direct edges come from individual page JSON nets. Shared-pin edges join an output to an input on the same installed card by physical pin, under the user's rule. Unrouted portions are shown without inferred connections.",
        "working_pin_normalizations": [],
    }
    NOTES.mkdir(parents=True, exist_ok=True)
    (NOTES / f"{card} drawing provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target, len(by_portion), len(all_edges), len(external_sinks), len(output_owners)


if __name__ == "__main__":
    for card in CONFIG:
        print(card, build(card))

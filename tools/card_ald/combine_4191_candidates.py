"""Combine source-bound 4191 field and wiring candidates for one review set.

This performs a guarded three-way merge and does not modify published files.
"""

import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO.parent / "tmp/ald-text/ald"
READINGS = ROOT / "card-4191-readings-stage"
WIRING = ROOT / "card-4191-lower-link-stage"
OUT = ROOT / "card-4191-combined-stage"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def merge_text(original, readings, wiring):
    assert len(original) == len(readings) == len(wiring)
    rows = []
    for old_line, read_line, wire_line in zip(original, readings, wiring, strict=True):
        assert len(old_line) == len(read_line) == len(wire_line)
        chars = []
        for old, read, wire in zip(old_line, read_line, wire_line, strict=True):
            if read != old and wire != old and read != wire:
                raise ValueError("Conflicting 4191 text edits")
            chars.append(wire if wire != old else read)
        rows.append("".join(chars))
    return rows


def merge_json(original, readings, wiring):
    assert original["wire_paths"] == readings["wire_paths"]
    merged = readings
    merged["wire_paths"] = wiring["wire_paths"]
    assert original["unjoined_crossings"] == readings["unjoined_crossings"]
    merged["unjoined_crossings"] = wiring["unjoined_crossings"]
    assert original["junctions"] == readings["junctions"]
    merged["junctions"] = wiring["junctions"]
    old_nets = {n["id"]: n for n in original["nets"]}
    wired_nets = {n["id"]: n for n in wiring["nets"]}
    read_nets = {n["id"]: n for n in readings["nets"]}
    changed_old = {key for key in old_nets if old_nets[key] != wired_nets.get(key)}
    added = {key for key in wired_nets if key not in old_nets}
    for key in changed_old:
        assert read_nets[key] == old_nets[key], (original["page"], key)
    merged["nets"] = [
        (wired_nets[n["id"]] if n["id"] in changed_old else n)
        for n in readings["nets"] if n["id"] in wired_nets
    ] + [wired_nets[key] for key in sorted(added)]
    assert len({n["id"] for n in merged["nets"]}) == len(merged["nets"])
    old_nodes = {n["id"]: n for n in original["nodes"]}
    wired_nodes = {n["id"]: n for n in wiring["nodes"]}
    if original["page"] == "AP121":
        read_nodes = {n["id"]: n for n in merged["nodes"]}
        aw = read_nodes["AW"]
        ax = read_nodes["AX"]
        aw["pins"] = [pin for pin in aw["pins"]
                      if not (pin.get("pin") == "B10" and pin.get("row") == 52)]
        assert len(aw["pins"]) == len(wired_nodes["AW"]["pins"])
        assert not any(pin.get("pin") == "B10" for pin in ax["pins"])
        ax["pins"].insert(0, wired_nodes["AX"]["pins"][0])
    for node in merged["nodes"]:
        if original["page"] == "AP121" and node["id"] in ("AW", "AX"):
            continue
        old_pins = old_nodes[node["id"]]["pins"]
        wired_pins = wired_nodes[node["id"]]["pins"]
        assert len(node["pins"]) == len(old_pins) == len(wired_pins)
        for pin, old_pin, wired_pin in zip(node["pins"], old_pins, wired_pins, strict=True):
            if old_pin.get("net") != wired_pin.get("net"):
                assert pin.get("net") == old_pin.get("net")
                pin["net"] = wired_pin.get("net")
    return merged


def main():
    r_manifest = json.loads((READINGS / "4191 reviewed readings candidate manifest.json")
                            .read_text(encoding="utf-8"))
    w_manifest = json.loads((WIRING / "manifest.json").read_text(encoding="utf-8"))
    r_pages = {record["page"]: record for record in r_manifest["pages"]}
    w_pages = {record["page"]: record for record in w_manifest["records"]}
    records = []
    for page in sorted(r_pages.keys() | w_pages.keys()):
        r = r_pages.get(page)
        w = w_pages.get(page)
        text_path = (REPO / r["text"]) if r else Path(w["published_text"])
        json_path = (REPO / r["json"]) if r else Path(w["published_json"])
        old_text = text_path.read_bytes()
        old_json = json_path.read_bytes()
        if r:
            read_text = (READINGS / r["text"]).read_bytes()
            read_json = (READINGS / r["json"]).read_bytes()
            assert sha(old_text) == r["text_before_sha256"]
            assert sha(old_json) == r["json_before_sha256"]
            assert sha(read_text) == r["text_candidate_sha256"]
            assert sha(read_json) == r["json_candidate_sha256"]
        else:
            read_text, read_json = old_text, old_json
        if w:
            wire_text = (WIRING / page / text_path.name).read_bytes()
            wire_json = (WIRING / page / json_path.name).read_bytes()
            assert sha(old_text) == w["published_text_sha256"]
            assert sha(old_json) == w["published_json_sha256"]
            assert sha(wire_text) == w["candidate_text_sha256"]
            assert sha(wire_json) == w["candidate_json_sha256"]
        else:
            wire_text, wire_json = old_text, old_json
        if r and w:
            old_lines = old_text.decode("utf-8").splitlines()
            read_lines = read_text.decode("utf-8").splitlines()
            wire_lines = wire_text.decode("utf-8").splitlines()
            combined_text = ("\n".join(merge_text(old_lines, read_lines, wire_lines)) + "\n").encode("utf-8")
            combined_json = (json.dumps(
                merge_json(json.loads(old_json), json.loads(read_json), json.loads(wire_json)),
                indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        elif r:
            combined_text, combined_json = read_text, read_json
        else:
            combined_text, combined_json = wire_text, wire_json
        lines = combined_text.decode("utf-8").splitlines()
        assert len(lines) == 103 and all(len(line) == 245 for line in lines)
        out = OUT / page
        out.mkdir(parents=True, exist_ok=True)
        (out / text_path.name).write_bytes(combined_text)
        (out / json_path.name).write_bytes(combined_json)
        records.append({
            "page": page, "field_edits": bool(r), "wiring_edits": bool(w),
            "text": str(text_path), "text_before_sha256": sha(old_text),
            "text_candidate_sha256": sha(combined_text),
            "json": str(json_path), "json_before_sha256": sha(old_json),
            "json_candidate_sha256": sha(combined_json),
            "scan": (r["scan"] if r else w["source_scan"]),
            "scan_sha256": (r["scan_sha256"] if r else w["source_scan_sha256"]),
        })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps({
        "status": "private source-bound combined candidate; pending independent acceptance",
        "field_manifest_sha256": sha((READINGS / "4191 reviewed readings candidate manifest.json").read_bytes()),
        "wiring_manifest_sha256": sha((WIRING / "manifest.json").read_bytes()),
        "records": records,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Combined {len(records)} pages; {sum(bool(r['field_edits'] and r['wiring_edits']) for r in records)} have both edit types")


if __name__ == "__main__":
    main()

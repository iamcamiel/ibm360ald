"""Verify the private combined 4191 TXT/JSON set against scans and sources."""

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3] / "tmp/ald-text/ald/card-4191-combined-stage"
JOIN_INPUT = re.compile(r"(?:BJ|BK|BL)\.(?:input[1-5]|input(?:67|68|72|73|74)|IN(?:67|68|72|73|74)|6)$")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    records = manifest["records"]
    assert len({r["page"] for r in records}) == len(records)
    links_checked = 0
    input_rail_checked = 0
    for record in records:
        page = record["page"]
        folder = ROOT / page
        text_raw = (folder / Path(record["text"]).name).read_bytes()
        json_raw = (folder / Path(record["json"]).name).read_bytes()
        assert sha(text_raw) == record["text_candidate_sha256"], page
        assert sha(json_raw) == record["json_candidate_sha256"], page
        assert sha(Path(record["text"]).read_bytes()) == record["text_before_sha256"], page
        assert sha(Path(record["json"]).read_bytes()) == record["json_before_sha256"], page
        assert sha(Path(record["scan"]).read_bytes()) == record["scan_sha256"], page
        lines = text_raw.decode("utf-8").splitlines()
        assert len(lines) == 103 and all(len(line) == 245 for line in lines), page
        model = json.loads(json_raw)
        assert model["page"] == page
        ids = {net["id"] for net in model["nets"]}
        assert len(ids) == len(model["nets"]), page
        assert all(junction["net"] in ids for junction in model["junctions"]), page
        assert all(all(net in ids for net in crossing["nets"])
                   for crossing in model["unjoined_crossings"]), page
        if record["wiring_edits"]:
            if page == "AP121":
                nodes = {node["id"]: node for node in model["nodes"]}
                assert not any(pin.get("pin") == "B10" for pin in nodes["AW"]["pins"])
                assert any(pin.get("pin") == "B10" and pin.get("row") == 59
                           for pin in nodes["AX"]["pins"])
                av4, = [net for net in model["nets"] if net["id"] == "AV4"]
                assert av4["targets"] == ["AX.B10"]
                for row in (54, 55):
                    assert lines[row][137] == "┼"
                    assert any(c.get("column") == 137 and c.get("row") == row
                               and c.get("joined") is False
                               for c in model["unjoined_crossings"])
                input_rail_checked += 1
                continue
            links = [(net["driver"], target)
                     for net in model["nets"] if net["driver"]
                     for target in net["targets"] if JOIN_INPUT.fullmatch(target)]
            assert len(links) == 5, (page, links)
            assert len({driver for driver, _ in links}) == 5, page
            assert len({target for _, target in links}) == 5, page
            links_checked += 1
    print(f"Verified {len(records)} source-bound TXT/JSON pairs, "
          f"{links_checked} five-driver joins and {input_rail_checked} AP121 input rail")


if __name__ == "__main__":
    main()

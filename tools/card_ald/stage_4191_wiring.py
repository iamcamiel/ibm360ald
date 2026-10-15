"""Stage 4191 adder and AP121 input wiring corrections for source review.

The published ALD and JSON remain untouched. The original scan, predecessor
files, and candidate files are hashed into a review manifest.
"""

import glob
import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
STAGE = REPO.parent / "tmp/ald-text/ald/card-4191-lower-link-stage"
SCANS = Path(r"D:\Reference Materials\IBM 360\IBM_360_ALD\AP Parallel Adder")
CASES = {
    "AP541": ("N38", "N39", "BJ.input5"),
    "AP551": ("N46", "N52", "BK.input5"),
    "AP561": ("N51", "N46", "BK.input5"),
    "AP571": ("N48", "N30", "BK.input5"),
    "AP581": ("N45", "N40", "BK.input5"),
    "AP591": ("N53", "N48", "BL.input5"),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def one(pattern):
    hits = glob.glob(str(pattern))
    if len(hits) != 1:
        raise ValueError((pattern, hits))
    return Path(hits[0])


def stage(page, source_id, stub_id, target):
    model_path = one(REPO / "json/AP Parallel Adder" / (page + "*.json"))
    text_path = one(REPO / "ALD/AP Parallel Adder" / (page + "*.txt"))
    scan_path = one(SCANS / (page + "*.tif"))
    old_model = model_path.read_bytes()
    old_text = text_path.read_bytes()
    model = json.loads(old_model)
    source, = [n for n in model["nets"] if n["id"] == source_id]
    stub, = [n for n in model["nets"] if n["id"] == stub_id]
    assert source["driver"] and not source["targets"]
    assert stub["driver"] is None and stub["targets"] == [target]
    source["targets"] = [target]
    source["source_reviewed"] = False
    source["candidate_basis"] = "Human-confirmed fifth distinct driver; native scan lower wire"
    model["nets"].remove(stub)
    node_id, = target.split(".", 1)[:1]
    node, = [n for n in model["nodes"] if n["id"] == node_id]
    pin, = [p for p in node["pins"] if p.get("terminal_id") == target]
    assert pin["net"] == stub_id
    pin["net"] = source_id
    paths = model["wire_paths"]
    source_path, = [p for p in paths if p["net"] == source_id]
    stub_path, = [p for p in paths if p["net"] == stub_id]
    assert source_path["points"][-1] in ([138, 74], [139, 75])
    assert stub_path["points"] == [[140, 74], [141, 74]]
    if page == "AP541":
        assert source_path["points"][-2:] == [[138, 75], [139, 75]]
        source_path["points"] = source_path["points"][:-2]
    source_path["points"][-1] = [142, 74]
    paths.remove(stub_path)

    lines = old_text.decode("utf-8").splitlines(keepends=True)
    line = list(lines[74])
    assert line[138] in "┐┘" and line[139] == " " and line[140:142] == ["─", "─"]
    line[138:140] = ["─", "─"]
    lines[74] = "".join(line)
    if page == "AP541":
        line = list(lines[75])
        assert line[138:140] == ["└", "─"]
        line[138:140] = [" ", " "]
        lines[75] = "".join(line)
    new_text = "".join(lines).encode("utf-8")
    new_model = (json.dumps(model, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    assert len(new_text.decode("utf-8").splitlines()) == len(old_text.decode("utf-8").splitlines())
    out = STAGE / page
    out.mkdir(parents=True, exist_ok=True)
    (out / text_path.name).write_bytes(new_text)
    (out / model_path.name).write_bytes(new_model)
    return {
        "page": page,
        "link": {"driver_net": source_id, "removed_stub_net": stub_id, "target": target},
        "source_scan": str(scan_path), "source_scan_sha256": sha(scan_path.read_bytes()),
        "published_text": str(text_path), "published_text_sha256": sha(old_text),
        "candidate_text_sha256": sha(new_text),
        "published_json": str(model_path), "published_json_sha256": sha(old_model),
        "candidate_json_sha256": sha(new_model),
    }


def stage_ap521():
    page = "AP521"
    model_path = one(REPO / "json/AP Parallel Adder" / (page + "*.json"))
    text_path = one(REPO / "ALD/AP Parallel Adder" / (page + "*.txt"))
    scan_path = one(SCANS / (page + "*.tif"))
    old_model = model_path.read_bytes()
    old_text = text_path.read_bytes()
    model = json.loads(old_model)
    nets = model["nets"]
    combined, = [n for n in nets if n["id"] == "AZBA"]
    gap73, = [n for n in nets if n["id"] == "BJgap73"]
    gap74, = [n for n in nets if n["id"] == "BJgap74"]
    assert combined["driver"] == "AZ.OUT75 / BA.OUT82" and combined["targets"] == []
    assert gap73["driver"] is gap74["driver"] is None
    assert gap73["targets"] == ["BJ.IN73"] and gap74["targets"] == ["BJ.IN74"]
    combined.update(id="AZ.OUT75", driver="AZ.OUT75", targets=["BJ.IN73"],
                    source_reviewed=False,
                    candidate_basis="Human-confirmed separate fourth and fifth driver wires")
    ba = dict(combined, id="BA.OUT82", driver="BA.OUT82", targets=["BJ.IN74"])
    nets.extend([ba])
    nets.remove(gap73)
    nets.remove(gap74)
    paths = model["wire_paths"]
    combined_paths = [p for p in paths if p["net"] == "AZBA"]
    assert len(combined_paths) == 2
    assert sorted(p["points"][0] for p in combined_paths) == [[128, 75], [128, 82]]
    for p in combined_paths:
        if p["points"][0] == [128, 75]:
            p.update(net="AZ.OUT75", points=[[128, 75], [134, 75], [134, 73], [142, 73]])
        else:
            p.update(net="BA.OUT82", points=[[128, 82], [133, 82], [133, 74], [142, 74]])
    for p in list(paths):
        if p["net"] in ("BJgap73", "BJgap74"):
            paths.remove(p)
    old_junction, = [j for j in model["junctions"] if j.get("net") == "AZBA"]
    assert (old_junction["column"], old_junction["row"]) == (134, 74)
    model["junctions"].remove(old_junction)
    model["unjoined_crossings"].extend([
        {"column": 134, "row": 74, "nets": ["AZ.OUT75", "BA.OUT82"], "joined": False},
        {"column": 133, "row": 75, "nets": ["AZ.OUT75", "BA.OUT82"], "joined": False},
    ])

    lines = old_text.decode("utf-8").splitlines(keepends=True)
    edits = {
        73: {134: (" ", "┌")},
        74: {133: (" ", "┌"), 134: ("◇", "┼"), 141: (" ", "─")},
        75: {133: ("─", "┼"), 134: ("┼", "┘")},
        76: {133: (" ", "│"), 134: ("│", " ")},
        77: {133: (" ", "│"), 134: ("│", " ")},
        78: {133: (" ", "│"), 134: ("│", " ")},
        79: {133: (" ", "│"), 134: ("│", " ")},
        80: {133: (" ", "│"), 134: ("│", " ")},
        81: {133: (" ", "│"), 134: ("│", " ")},
        82: {133: ("─", "┘"), 134: ("┘", " ")},
    }
    for row, columns in edits.items():
        line = list(lines[row])
        for col, (before, after) in columns.items():
            assert line[col] == before, (page, row, col, line[col], before)
            line[col] = after
        lines[row] = "".join(line)
    new_text = "".join(lines).encode("utf-8")
    new_model = (json.dumps(model, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    out = STAGE / page
    out.mkdir(parents=True, exist_ok=True)
    (out / text_path.name).write_bytes(new_text)
    (out / model_path.name).write_bytes(new_model)
    return {
        "page": page,
        "link": {"drivers": ["AZ.OUT75", "BA.OUT82"],
                 "targets": ["BJ.IN73", "BJ.IN74"],
                 "removed_combined_net": "AZBA"},
        "source_scan": str(scan_path), "source_scan_sha256": sha(scan_path.read_bytes()),
        "published_text": str(text_path), "published_text_sha256": sha(old_text),
        "candidate_text_sha256": sha(new_text),
        "published_json": str(model_path), "published_json_sha256": sha(old_model),
        "candidate_json_sha256": sha(new_model),
    }


def stage_ap441():
    page = "AP441"
    model_path = one(REPO / "json/AP Parallel Adder" / (page + "*.json"))
    text_path = one(REPO / "ALD/AP Parallel Adder" / (page + "*.txt"))
    scan_path = one(SCANS / (page + "*.tif"))
    old_model = model_path.read_bytes()
    old_text = text_path.read_bytes()
    model = json.loads(old_model)
    joined, = [n for n in model["nets"] if n["id"] == "AWAX"]
    assert joined["driver"] == "AW.output/AX.output"
    assert joined["targets"] == ["BJ.input67", "BJ.input68"]
    model["nets"].remove(joined)
    for block, target in (("AW", "BJ.input67"), ("AX", "BJ.input68")):
        model["nets"].append({
            "id": block, "driver": block + ".output", "targets": [target],
            "external": None, "source_reviewed": False,
            "candidate_basis": "Native scan crossing has no junction; human confirmed separate driver wires",
        })
    paths = [p for p in model["wire_paths"] if p["net"] == "AWAX"]
    assert sorted(p["points"][0] for p in paths) == [[127, 54], [127, 61]]
    for p in paths:
        p["net"] = "AW" if p["points"][0][1] == 54 else "AX"
    old_junction, = [j for j in model["junctions"] if j.get("net") == "AWAX"]
    assert (old_junction["column"], old_junction["row"]) == (137, 67)
    model["junctions"].remove(old_junction)
    model["unjoined_crossings"].append({
        "column": 137, "row": 67, "nets": ["AW", "AX"], "joined": False})
    lines = old_text.decode("utf-8").splitlines(keepends=True)
    line = list(lines[67])
    assert line[137] == "◇"
    line[137] = "┼"
    lines[67] = "".join(line)
    new_text = "".join(lines).encode("utf-8")
    new_model = (json.dumps(model, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    out = STAGE / page
    out.mkdir(parents=True, exist_ok=True)
    (out / text_path.name).write_bytes(new_text)
    (out / model_path.name).write_bytes(new_model)
    return {
        "page": page, "link": {"split_net": "AWAX", "drivers": ["AW", "AX"]},
        "source_scan": str(scan_path), "source_scan_sha256": sha(scan_path.read_bytes()),
        "published_text": str(text_path), "published_text_sha256": sha(old_text),
        "candidate_text_sha256": sha(new_text),
        "published_json": str(model_path), "published_json_sha256": sha(old_model),
        "candidate_json_sha256": sha(new_model),
    }


def stage_ap531():
    page = "AP531"
    model_path = one(REPO / "json/AP Parallel Adder" / (page + "*.json"))
    text_path = one(REPO / "ALD/AP Parallel Adder" / (page + "*.txt"))
    scan_path = one(SCANS / (page + "*.tif"))
    old_model = model_path.read_bytes()
    old_text = text_path.read_bytes()
    model = json.loads(old_model)
    nets = model["nets"]
    stub, = [n for n in nets if n["id"] == "BJstub"]
    joined, = [n for n in nets if n["id"] == "AZBA"]
    assert stub["driver"] is None and stub["targets"] == ["BJ.input73"]
    assert joined["driver"] == "AZ.output / BA.output" and joined["targets"] == ["BJ.input74"]
    stub.update(id="BA", driver="BA.output", source_reviewed=False,
                candidate_basis="Human-confirmed distinct BA driver into BJ.input73")
    joined.update(id="AZ", driver="AZ.output", source_reviewed=False,
                  candidate_basis="Human-confirmed distinct AZ driver into BJ.input74")
    paths = model["wire_paths"]
    stub_path, = [p for p in paths if p["net"] == "BJstub"]
    assert stub_path["points"] == [[134, 73], [141, 73]]
    stub_path.update(net="BA", points=[[127, 82], [131, 82], [131, 73], [141, 73]])
    joined_paths = [p for p in paths if p["net"] == "AZBA"]
    assert sorted(p["points"][0] for p in joined_paths) == [[127, 75], [127, 82]]
    az_path, = [p for p in joined_paths if p["points"][0] == [127, 75]]
    az_path["net"] = "AZ"
    paths.remove(next(p for p in joined_paths if p["points"][0] == [127, 82]))
    old_junction, = [j for j in model["junctions"] if j.get("net") == "AZBA"]
    assert (old_junction["column"], old_junction["row"]) == (134, 75)
    model["junctions"].remove(old_junction)
    model["unjoined_crossings"].append({
        "column": 131, "row": 75, "nets": ["AZ", "BA"], "joined": False})
    lines = old_text.decode("utf-8").splitlines(keepends=True)
    edits = {
        73: {133: (" ", "─")},
        74: {131: (" ", "│")},
        75: {131: ("─", "┼"), 134: ("◇", "┘")},
        76: {131: (" ", "│"), 134: ("│", " ")},
        77: {131: (" ", "│"), 134: ("│", " ")},
        78: {131: (" ", "│"), 134: ("│", " ")},
        79: {131: (" ", "│"), 134: ("│", " ")},
        80: {131: (" ", "│"), 134: ("│", " ")},
        81: {131: (" ", "│"), 134: ("│", " ")},
        82: {131: ("─", "┘"), 132: ("─", " "),
             133: ("─", " "), 134: ("┘", " ")},
    }
    for row, columns in edits.items():
        line = list(lines[row])
        for col, (before, after) in columns.items():
            assert line[col] == before, (page, row, col, line[col], before)
            line[col] = after
        lines[row] = "".join(line)
    new_text = "".join(lines).encode("utf-8")
    new_model = (json.dumps(model, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    out = STAGE / page
    out.mkdir(parents=True, exist_ok=True)
    (out / text_path.name).write_bytes(new_text)
    (out / model_path.name).write_bytes(new_model)
    return {
        "page": page, "link": {"split_net": "AZBA", "drivers": ["AZ", "BA"]},
        "source_scan": str(scan_path), "source_scan_sha256": sha(scan_path.read_bytes()),
        "published_text": str(text_path), "published_text_sha256": sha(old_text),
        "candidate_text_sha256": sha(new_text),
        "published_json": str(model_path), "published_json_sha256": sha(old_model),
        "candidate_json_sha256": sha(new_model),
    }


def stage_ap121():
    page = "AP121"
    model_path = one(REPO / "json/AP Parallel Adder" / (page + "*.json"))
    text_path = one(REPO / "ALD/AP Parallel Adder" / (page + "*.txt"))
    scan_path = one(SCANS / (page + "*.tif"))
    old_model = model_path.read_bytes()
    old_text = text_path.read_bytes()
    model = json.loads(old_model)
    aw, = [n for n in model["nodes"] if n["id"] == "AW"]
    ax, = [n for n in model["nodes"] if n["id"] == "AX"]
    wrong, = [p for p in aw["pins"] if p.get("pin") == "B10" and p["row"] == 52]
    aw["pins"].remove(wrong)
    assert not any(p.get("pin") == "B10" for p in ax["pins"])
    corrected_pin = dict(wrong, row=59, source_reviewed=False)
    ax["pins"].insert(0, corrected_pin)
    av4, = [n for n in model["nets"] if n["id"] == "AV4"]
    assert av4["targets"] == ["AW.B10"]
    av4["targets"] = ["AX.B10"]
    av4["source_reviewed"] = False
    av4["candidate_basis"] = "Native AP121 scan places B10 on portion 08, below two nonjoining crossings"
    route, = [p for p in model["wire_paths"] if p["net"] == "AV4" and
              p["points"][-1] == [138, 52]]
    assert route["points"] == [[153, 47], [137, 47], [137, 52], [138, 52]]
    route["points"] = [[153, 47], [137, 47], [137, 59], [138, 59]]
    for row in (54, 55):
        assert not any(c.get("column") == 137 and c.get("row") == row
                       for c in model["unjoined_crossings"])
        model["unjoined_crossings"].append({
            "column": 137, "row": row,
            "nets": ["AV4", "AW-jumper"], "joined": False})
    lines = old_text.decode("utf-8").splitlines(keepends=True)
    edits = {
        52: {137: ("└", "│"), 138: ("─", " "), 139: ("B", " "),
             140: ("1", " "), 141: ("0", " ")},
        53: {137: (" ", "│")},
        54: {137: ("─", "┼")},
        55: {137: ("─", "┼")},
        56: {137: (" ", "│")},
        57: {137: (" ", "│")},
        58: {137: (" ", "│")},
        59: {137: (" ", "└"), 138: (" ", "─"), 139: (" ", "B"),
             140: (" ", "1"), 141: (" ", "0")},
    }
    for row, columns in edits.items():
        line = list(lines[row])
        for col, (before, after) in columns.items():
            assert line[col] == before, (page, row, col, line[col], before)
            line[col] = after
        lines[row] = "".join(line)
    new_text = "".join(lines).encode("utf-8")
    new_model = (json.dumps(model, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    out = STAGE / page
    out.mkdir(parents=True, exist_ok=True)
    (out / text_path.name).write_bytes(new_text)
    (out / model_path.name).write_bytes(new_model)
    return {
        "page": page,
        "link": {"driver": "AV4", "old_target": "AW.B10", "new_target": "AX.B10",
                 "unjoined_crossings": [[137, 54], [137, 55]]},
        "source_scan": str(scan_path), "source_scan_sha256": sha(scan_path.read_bytes()),
        "published_text": str(text_path), "published_text_sha256": sha(old_text),
        "candidate_text_sha256": sha(new_text),
        "published_json": str(model_path), "published_json_sha256": sha(old_model),
        "candidate_json_sha256": sha(new_model),
    }


def main():
    records = [stage(page, *args) for page, args in CASES.items()]
    records.append(stage_ap521())
    records.append(stage_ap441())
    records.append(stage_ap531())
    records.append(stage_ap121())
    manifest = {
        "status": "private source-bound candidates; pending independent native review",
        "scope": "Nine 4191 A-to-OR driver repairs plus AP121 B10 input-rail placement",
        "records": records,
    }
    STAGE.mkdir(parents=True, exist_ok=True)
    (STAGE / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Staged {len(records)} private wiring candidates in {STAGE}")


if __name__ == "__main__":
    main()

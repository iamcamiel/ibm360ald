"""Stage the AP041 three-way portion-label correction for independent review.

This script writes only to the private stage beside the source-bound candidate.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path("D:/Github/IBM360")
HERE = Path(__file__).resolve().parent
CANDIDATE = HERE / "AP041 three-way portion correction candidate.json"
STAGE = HERE / "three-way-private-stage"
FONT = ROOT / "tmp/ald-text/JuliaMono-Regular.ttf"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def model_bytes(model: dict) -> bytes:
    return (json.dumps(model, ensure_ascii=False, indent=2) + "\n").replace("\n", "\r\n").encode("utf-8")


def text_edit(raw: bytes, changes: list[dict]) -> bytes:
    rows = raw.decode("utf-8").splitlines(keepends=True)
    after = rows.copy()
    for change in changes:
        r, c = change["text_zero_based_row"], change["text_zero_based_col"]
        old, new = change["before"]["text"], change["after"]["text"]
        require(len(old) == len(new) == 6, "Unexpected card portion width")
        require(after[r][c:c + 6] == old, f"Unexpected TXT cell for {change['node']}")
        after[r] = after[r][:c] + new + after[r][c + 6:]
    result = "".join(after).encode("utf-8")
    reverse = after.copy()
    for change in changes:
        r, c = change["text_zero_based_row"], change["text_zero_based_col"]
        old = change["before"]["text"]
        reverse[r] = reverse[r][:c] + old + reverse[r][c + 6:]
    require("".join(reverse).encode("utf-8") == raw, "Unrelated TXT change")
    require(len(result) == len(raw), "TXT byte length changed")
    return result


def preview_config(path: Path, lines: list[str]) -> dict:
    import importlib.util

    shared = ROOT / "tmp/ald-text/ald/card-type-database/prepare_non_ap_OR_corrections.py"
    spec = importlib.util.spec_from_file_location("ap041_shared_renderer", shared)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    with Image.open(path) as image:
        config = {"size": list(image.size), "font_size": 20, "row_height": 18,
                  "x": (image.width - 2940) // 2, "y": (image.height - 1854) // 2}
        if list(image.size) == [2956, 1870]:
            config["anchor"] = "lt"
        rendered = module.render(lines, config)
        require(ImageChops.difference(image.convert("RGB"), rendered).getbbox() is None,
                "Accepted preview does not exactly reproduce current text")
    return config, module


def main() -> None:
    require(not STAGE.exists(), "Private stage already exists; refusing overwrite")
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    require(candidate["status"] == "private-source-bound-candidate-only", "Unexpected candidate status")
    require(sha(Path(candidate["source_tiff"]["path"])) == candidate["source_tiff"]["sha256"],
            "Original TIFF changed")
    for item in candidate["corroboration"]:
        require(sha(Path(item["path"])) == item["sha256"], "Corroboration changed")
    for change in candidate["corrections"]:
        crop = change["source_crop"]
        require(sha(Path(crop["path"])) == crop["sha256"], "Native crop changed")
    cmp = candidate["comparison"]
    require(sha(Path(cmp["path"])) == cmp["sha256"], "Native comparison changed")
    originals = candidate["published_before"]
    txt = Path(originals["canonical_txt"]["path"])
    model_path = Path(originals["canonical_json"]["path"])
    require(sha(txt) == originals["canonical_txt"]["sha256"], "Canonical TXT epoch changed")
    require(sha(model_path) == originals["canonical_json"]["sha256"], "Canonical JSON epoch changed")
    require(sha(Path(originals["repository_txt"]["path"])) == originals["repository_txt"]["sha256"],
            "Repository TXT epoch changed")
    stem = txt.stem
    sources = {"txt": txt, "json": model_path,
               "notes": txt.with_name(stem + " review notes.txt"),
               "preview": txt.with_name(stem + " preview.png")}
    require(all(p.is_file() for p in sources.values()), "Missing canonical quartet member")
    require(STAGE.parent.is_dir(), "Missing stage parent")
    STAGE.mkdir()
    before = STAGE / "before"
    after = STAGE / "candidate"
    before.mkdir()
    after.mkdir()
    for source in sources.values():
        shutil.copy2(source, before / source.name)
    raw_text = txt.read_bytes()
    changed_text = text_edit(raw_text, candidate["corrections"])
    (after / txt.name).write_bytes(changed_text)

    raw_model = model_path.read_bytes()
    model = json.loads(raw_model)
    require(model_bytes(model) == raw_model, "Unexpected JSON serialization")
    updated = copy.deepcopy(model)
    history_key = "source_native_ap041_three_way_portion_correction_v1"
    require(history_key not in updated, "History key already exists")
    edits = []
    for change in candidate["corrections"]:
        nodes = [x for x in updated["nodes"] if x["id"] == change["node"]]
        require(len(nodes) == 1, "Node id not unique")
        node = nodes[0]
        require(node["grid"] == change["grid"] and node["function"] == change["function"],
                "Node identity/function changed")
        node_index = updated["nodes"].index(node)
        for key in ("portion", "printed_card_portion"):
            old, new = change["before"][key], change["after"][key]
            require(node[key] == old, f"Unexpected {key} on {change['node']}")
            node[key] = new
            edits.append({"json_pointer": f"/nodes/{node_index}/{key}", "before": old, "after": new})
        old = change["before"]["socket_listing_evidence.portion"]
        new = change["after"]["socket_listing_evidence.portion"]
        require(node["socket_listing_evidence"]["portion"] == old,
                f"Unexpected socket listing portion on {change['node']}")
        node["socket_listing_evidence"]["portion"] = new
        edits.append({"json_pointer": f"/nodes/{node_index}/socket_listing_evidence/portion",
                      "before": old, "after": new})
    updated[history_key] = {
        "authority": "Direct user observation that AP041 OR portion is 4633K8; confirmed on original TIFF",
        "original_tiff": binding(Path(candidate["source_tiff"]["path"])),
        "candidate": binding(CANDIDATE),
        "predecessor_txt_sha256": sha(txt),
        "predecessor_json_sha256": sha(model_path),
        "scope": "Three printed portion codes only; all functions, pins, wiring, and coordinates preserved",
        "status_at_creation": "private stage awaiting independent audit",
    }
    (after / model_path.name).write_bytes(model_bytes(updated))
    shared_path = ROOT / "tmp/ald-text/ald/card-type-database/prepare_non_ap_OR_corrections.py"
    config, shared = preview_config(sources["preview"], raw_text.decode("utf-8").splitlines())
    observed_edits = shared.diff(model, updated)
    require(sorted(x["json_pointer"] for x in observed_edits) ==
            sorted([x["json_pointer"] for x in edits] + ["/" + history_key]),
            "Unexpected JSON delta")

    notes_raw = sources["notes"].read_bytes()
    newline = b"\r\n" if b"\r\n" in notes_raw else b"\n"
    entry = ("Native AP041 portion correction: original TIFF and AP081/AP441 corroboration show "
             "AS/4E OR = 4633K8, AU/5B A = 4633K4, BB/6B N = 4633K6. "
             "The three-way reassignment preserves the K1-K9 portion set on B-D2J4. "
             "No function, pin, wire, or coordinate was changed. "
             f"Original TIFF SHA-256 {candidate['source_tiff']['sha256']}.")
    appended = notes_raw + (b"" if notes_raw.endswith(newline) else newline) + entry.encode("utf-8") + newline
    (after / sources["notes"].name).write_bytes(appended)
    rendered = shared.render(changed_text.decode("utf-8").splitlines(), config)
    rendered.save(after / sources["preview"].name)
    with Image.open(after / sources["preview"].name) as check:
        require(ImageChops.difference(rendered, check.convert("RGB")).getbbox() is None,
                "Preview render mismatch")

    manifest = {
        "schema": "ap041-three-way-source-bound-private-stage-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PRIVATE; independent audit and coordinator release required before publication",
        "original_tiff": binding(Path(candidate["source_tiff"]["path"])),
        "source_candidate": binding(CANDIDATE),
        "shared_renderer": binding(shared_path),
        "font": binding(FONT),
        "stage_script": binding(Path(__file__)),
        "before_quartet": {k: binding(before / p.name) for k, p in sources.items()},
        "candidate_quartet": {k: binding(after / p.name) for k, p in sources.items()},
        "canonical_before_quartet": {k: binding(p) for k, p in sources.items()},
        "text_edits": [{k: x[k] for k in ("node", "grid", "text_zero_based_row", "text_zero_based_col", "before", "after")}
                       for x in candidate["corrections"]],
        "model_edits": edits,
        "model_history_key": history_key,
        "render_config": config,
        "native_crops": [binding(Path(x["source_crop"]["path"])) for x in candidate["corrections"]],
        "comparison": binding(Path(candidate["comparison"]["path"])),
        "corroboration": [binding(Path(x["path"])) for x in candidate["corroboration"]],
        "writes": {"canonical": 0, "repository": 0, "source_tiff": 0},
    }
    manifest_path = STAGE / "AP041 three-way private stage manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": binding(manifest_path), "model_edits": len(edits),
                      "text_edits": len(candidate["corrections"]), "writes": manifest["writes"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

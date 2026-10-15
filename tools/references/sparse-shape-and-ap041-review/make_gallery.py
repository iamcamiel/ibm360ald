"""Assemble and verify the 17 sparse card-function shape comparisons."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parent
MANIFESTS = [
    ROOT / "agent1/gallery_cases.json",
    ROOT / "agent2/Gallery manifest.json",
    ROOT / "agent3/Sparse shape cases 13-17 native crop bindings.json",
]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def panel(raw: dict, agent: int) -> dict:
    if agent == 1:
        crop, source = Path(raw["crop"]), Path(raw["source"])
        bounds = raw["crop_bbox_xyxy"]
        label = raw["label"]
        crop_hash, source_hash = raw["crop_sha256"], raw["source_sha256"]
        node = raw["node"]
        station = raw["grid"]
    elif agent == 2:
        crop, source = Path(raw["crop_png"]), Path(raw["source_tiff"])
        bounds = raw["source_pixel_bounds"]
        label = raw["function"]
        crop_hash, source_hash = raw["crop_png_sha256"], raw["source_tiff_sha256"]
        node = raw["node_id"]
        station = raw["grid"]
    else:
        crop, source = Path(raw["crop"]), Path(raw["source_TIFF"])
        bounds = raw["crop_bbox_xyxy"]
        label = raw["function_literal"]
        crop_hash, source_hash = raw["crop_sha256"], raw["source_TIFF_sha256"]
        node = raw["node_identifier"]
        station = raw["station"]
    assert crop.is_relative_to(ROOT) and crop.is_file()
    assert source.is_file() and source.suffix.lower() in {".tif", ".tiff"}
    assert digest(crop) == crop_hash, crop
    assert digest(source) == source_hash, source
    with Image.open(source) as original, Image.open(crop) as saved:
        exact = original.crop(tuple(bounds))
        assert exact.size == saved.size, crop
        assert ImageChops.difference(exact.convert("RGB"), saved.convert("RGB")).getbbox() is None, crop
    return {
        "page": raw["page"],
        "scan_id": raw["scan_id"],
        "node": node,
        "station": station,
        "label": label,
        "crop": crop.relative_to(ROOT).as_posix(),
        "crop_sha256": crop_hash,
        "source_TIFF": str(source),
        "source_TIFF_sha256": source_hash,
        "source_pixel_bounds": bounds,
    }


def main() -> None:
    human = json.loads((ROOT / "Human review of 17 sparse shape cases.json").read_text(encoding="utf-8"))["interpretation"]
    legitimate = set(human["accepted_as_legitimate_different_shape"])
    awaiting_crop = set(human["review_after_corrected_crop"])
    recheck = set(human["native_recheck_card_portion"])
    data = [json.loads(path.read_text(encoding="utf-8")) for path in MANIFESTS]
    batches = [data[0]["cases"], data[1], data[2]["records"]]
    cases = []
    for agent, batch in enumerate(batches, 1):
        for raw in batch:
            index = raw.get("number", raw.get("index", raw.get("review_index")))
            normal = raw.get("normal_comparator", raw.get("normal", raw.get("normal_same_portion")))
            assert normal is not None and len(raw["flagged"]) == 2
            cases.append({
                "index": index,
                "card_type": raw["card_type"],
                "portion": raw["portion"],
                "shape_id": raw["shape_id"],
                "flagged": [panel(item, agent) for item in raw["flagged"]],
                "normal": panel(normal, agent),
                "normal_has_same_shape": False,
                "interpretation": raw.get("interpretation", "Different printed functions share this recorded port shape; no correction inferred."),
            })
    cases.sort(key=lambda x: x["index"])
    assert [x["index"] for x in cases] == list(range(1, 18))
    assert len({x["card_type"] + x["portion"] for x in cases}) == 17
    (ROOT / "All 17 source-crop evidence.json").write_text(
        json.dumps({"cases": cases, "verification": "51 PNG crops are pixel-exact rectangles from their SHA-256-bound original TIFFs; no textual corrections inferred."}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    intro = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>17 sparse ALD function-shape comparisons</title>
<style>body{font:16px/1.45 system-ui,sans-serif;max-width:1500px;margin:2rem auto;padding:0 1.2rem;color:#17212b;background:#fafbfc}
h1{margin-bottom:.2rem} .note{background:#edf3f8;border-left:4px solid #557b9b;padding:.75rem 1rem}
nav{display:flex;flex-wrap:wrap;gap:.4rem;margin:1.2rem 0}nav a{padding:.25rem .5rem;background:#e5edf5;border-radius:4px}
section{background:white;border:1px solid #cbd5df;border-radius:7px;margin:1.3rem 0;padding:1rem}
.panels{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem}figure{margin:0;min-width:0}img{width:100%;height:auto;border:1px solid #adb8c4;background:white}figcaption{margin:.35rem 0;font-weight:600}
.meta{font-size:.8rem;color:#53616f;overflow-wrap:anywhere}a{color:#12568d}@media(max-width:900px){.panels{grid-template-columns:1fr}}
</style></head><body><h1>17 sparse ALD function-shape comparisons</h1>
<p class="note">Each row shows two flagged uses of the same card portion and port shape, followed by an ordinary use of that portion. The ordinary reference has a <strong>different port shape</strong>; it gives context, not proof that either flagged label is wrong. All 51 crops are exact rectangles of the original TIFF pixels. No ALD text or card database reading was changed from this review.</p>
<nav>"""
    parts = [intro]
    for case in cases:
        parts.append(f'<a href="#case-{case["index"]}">{case["index"]}. {html.escape(case["card_type"] + case["portion"])}</a>')
    parts.append("</nav>")
    for case in cases:
        labels = " / ".join(x["label"] for x in case["flagged"])
        portion = case["card_type"] + case["portion"]
        if portion in legitimate:
            status = "User reviewed: shape variation appears legitimate; no correction proposed."
        elif portion in awaiting_crop:
            status = "First crop corrected to show the block; awaiting user review."
        else:
            assert portion in recheck
            status = "Resolved after native review: AP041 AS/OR is 4633K8, AU/A is 4633K4, and BB/N is 4633K6. This row records the earlier database misgrouping; the current database no longer flags 4633K4."
        parts.append(f'<section id="case-{case["index"]}"><h2>{case["index"]}. {html.escape(portion)} — {html.escape(labels)}</h2><p><strong>{html.escape(status)}</strong></p><div class="panels">')
        for role, item in [("Flagged occurrence 1", case["flagged"][0]), ("Flagged occurrence 2", case["flagged"][1]), ("Ordinary same-portion reference; different shape", case["normal"])]:
            href = quote(item["crop"], safe="/")
            caption = f'{item["page"]} {item["node"]}/{item["station"]}: {item["label"]}'
            bounds = ", ".join(str(n) for n in item["source_pixel_bounds"])
            parts.append(f'<figure><figcaption>{html.escape(role)}<br>{html.escape(caption)}</figcaption><a href="{href}"><img loading="lazy" src="{href}" alt="Original TIFF crop of {html.escape(caption, quote=True)}"></a><div class="meta">Scan {html.escape(str(item["scan_id"]))}; TIFF SHA-256 {item["source_TIFF_sha256"]}; bounds {bounds}</div></figure>')
        parts.append("</div></section>")
    parts.append("</body></html>\n")
    (ROOT / "All 17 function-shape source crops.html").write_text("\n".join(parts), encoding="utf-8")
    print(json.dumps({"cases": len(cases), "verified_source_crops": len(cases) * 3, "gallery": str(ROOT / "All 17 function-shape source crops.html")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

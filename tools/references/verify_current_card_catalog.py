"""Verify a current card catalog against its accepted repository snapshot."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--catalog", type=Path, required=True)
    args = ap.parse_args()
    repo, root = args.repo.resolve(), args.catalog.resolve()
    manifest = read(root / "notes/Card types current/Build manifest.json")
    assert manifest["schema"] == "current-card-catalog-build-v1"
    bindings = manifest["source_binding"]
    assert digest(repo / "notes/Reviewed export provenance.json") == bindings["reviewed_export_provenance_sha256"]
    assert digest(repo / "notes/Content data manifest.json") == bindings["content_data_manifest_sha256"]
    accepted = read(repo / "notes/Reviewed export provenance.json")["exported"]
    accepted_sha = {Path(x["destination"]).resolve().relative_to(repo).as_posix(): x["text_sha256"]
                    for x in accepted}
    content = {x["path"]: x["sha256"] for x in read(repo / "notes/Content data manifest.json")["files"]}
    for text_path, binding in manifest["source_pages"].items():
        assert text_path in accepted_sha and binding["text_sha256"] == accepted_sha[text_path], text_path
        assert digest(repo / text_path) == binding["text_sha256"], text_path
        model_path = binding["model"]
        assert model_path in content and content[model_path] == binding["model_sha256"], model_path
        assert digest(repo / model_path) == binding["model_sha256"], model_path
    for item in manifest["files"]:
        assert digest(root / item["path"]) == item["sha256"], item["path"]
    generated = {p.relative_to(root).as_posix()
                 for branch in ("json/Card types current", "csv/Card types current", "notes/Card types current")
                 for p in (root / branch).glob("*") if p.is_file()}
    assert generated == {x["path"] for x in manifest["files"]} | {
        "notes/Card types current/Build manifest.json"}

    occurrences = 0
    profiles = 0
    models = {}
    for path in sorted((root / "json/Card types current").glob("*.json")):
        card = read(path)
        assert card["card_type"] == path.stem and path.stem.isdigit() and len(path.stem) == 4
        for occurrence in card["diagram_occurrences"]:
            assert occurrence["source_text"] in manifest["source_pages"]
            model = models.get(occurrence["source_text"])
            if model is None:
                model = read(repo / manifest["source_pages"][occurrence["source_text"]]["model"])
                models[occurrence["source_text"]] = model
            index = int(occurrence["node_pointer"].split("/")[-1])
            node = model["nodes"][index]
            assert node["card_type"] == path.stem
            assert node.get("portion") == occurrence["portion"]
            assert node.get("id") == occurrence["node"]
        occurrences += len(card["diagram_occurrences"])
        profiles += len(card["portion_profiles"])
    counts = manifest["counts"]
    assert occurrences == counts["card_occurrences"]
    assert profiles == manifest["portion_profiles"]
    assert len(list((root / "json/Card types current").glob("*.json"))) == manifest["card_types"]
    with (root / "csv/Card types current/Diagram occurrences.csv").open(encoding="utf-8", newline="") as stream:
        assert sum(1 for _ in csv.DictReader(stream)) == occurrences
    print(json.dumps({"passed": True, "card_types": manifest["card_types"],
                      "diagram_occurrences": occurrences, "portion_profiles": profiles,
                      "source_pages": len(manifest["source_pages"]),
                      "files": len(manifest["files"]) + 1}))


if __name__ == "__main__":
    main()

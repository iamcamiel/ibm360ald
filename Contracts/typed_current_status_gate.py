"""Read-only typed status gate for direct current-card verification.

This deliberately does not import the held consumer or invoke its strict_current
adapter. It admits one current family to the unchanged original verifier only.
"""
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re

INDEX = "notes/Card-ALD/Universal card diagrams publication.json"
CHECKPOINT = "notes/Source status.json"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def module_at(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "Missing typed gate dependency")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate typed status JSON key: " + key)
            result[key] = value
        return result
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite typed status JSON: " + value)))


def current_status_guards(card, root):
    """Return exact input guards after admitting a typed, live current entry.

    Every returned byte is checked again by the original verifier's final guard
    loop. No acceptance, output, metadata reconciliation or mutation occurs here.
    """
    require(isinstance(card, str) and re.fullmatch(r"[0-9]{4}", card), "Use exactly four ASCII digits")
    root = Path(root).absolute()
    require(root == root.resolve(), "Typed status root is a filesystem alias")
    contracts = module_at(Path(__file__).resolve().parents[1] / "auxiliary_held_contracts.py",
                          "_typed_current_closed_contracts")
    guards = {}

    def inside(relative):
        require(isinstance(relative, str) and PurePosixPath(relative).as_posix() == relative,
                "Noncanonical typed status path")
        path = root / relative
        require(path.is_relative_to(root) and path == path.resolve(), "Typed status path escapes root or uses alias")
        cursor = path
        while cursor != root:
            require(not cursor.is_symlink() and not getattr(cursor, "is_junction", lambda: False)(),
                    "Typed status filesystem alias rejected")
            cursor = cursor.parent
        return path

    def capture(relative):
        path = inside(relative)
        require(path.is_file(), "Missing authoritative typed status input: " + relative)
        raw = path.read_bytes()
        require(path not in guards or guards[path] == raw, "Typed status input changed during gate")
        guards[path] = raw
        return path, raw

    def checked(binding):
        contracts.validate(binding, "binding")
        path, raw = capture(binding["path"])
        require(hashlib.sha256(raw).hexdigest() == binding["sha256"], "Stale typed status binding: " + binding["path"])
        return path, raw

    _, raw = capture(INDEX)
    doc = contracts.validate(read(raw), "index")
    _, base_raw = checked(doc["base_inventory"])
    base = read(base_raw)
    require(isinstance(base, dict) and base.get("schema") == "shared-card-renderer-publication-v1"
            and isinstance(base.get("cards"), list), "Unsupported typed status base inventory")
    families = [row.get("card_type") if isinstance(row, dict) else None for row in base["cards"]]
    require(all(isinstance(x, str) and re.fullmatch(r"[0-9]{4}", x) for x in families)
            and len(set(families)) == len(families), "Duplicate or invalid typed status base family")
    rows = {row["card_type"]: row for row in doc["entries"]}
    require(len(rows) == len(doc["entries"]) and set(rows) == set(families),
            "Typed status family partition must be disjoint and exhaustive")
    counts = {"families": len(rows), "current": 0, "held": 0, "legacy_proof_only": 0}
    for row in rows.values():
        counts[row["status"].replace("-", "_")] += 1
    require(doc["counts"] == counts, "Typed status counts differ")
    require(card in rows, "Family absent from authoritative typed status index")
    row = rows[card]
    require(row["status"] == "current", "Direct current verification rejects " + row["status"] + ": " + card)
    checkpoint_path, checkpoint_raw = checked(doc["current_checkpoint"])
    require(checkpoint_path == inside(CHECKPOINT), "Typed status checkpoint must bind live notes/Source status.json")
    checkpoint = module_at(inside("tools/reviews/current_checkpoint.py"), "_typed_current_source_checkpoint")
    checkpoint.load_checkpoint(root)
    require(checkpoint_path.read_bytes() == checkpoint_raw, "Checkpoint changed during typed status gate")
    generation_path, _ = checked(row["generation"])
    require(generation_path == inside("notes/Card-ALD/Generation/" + card + ".json"),
            "Typed current generation must bind live family generation")
    return guards

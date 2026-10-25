"""Publish one independently reviewed card using current, portable records only.

The exact candidate, fresh use audit and default builder must agree. Publication
updates one current generation receipt and an exact inventory allowlist; Git
retains older states. Dry-run validation writes nothing to the repository.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Contracts'))
import legacy_index_mutation_guard as index_guard
import typed_current_status_gate
index_guard.dependency_paths(index_guard.repository_root(__file__),__file__)

import audit_card_uses
import build_card_data
import generate_card as renderer
index_guard.require_guarded_renderer(renderer)

ROOT = renderer.ROOT
AUDIT_KEYS = ("catalog", "source_bindings", "occurrences", "coverage_limitations",
              "known_reviewed_source_corrections")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def state(path):
    return path.read_bytes() if path.is_file() else None


def remove_protected(path):
    index_guard.guard_existing_ancestor_index(path,'publish_card_candidate.remove_protected')
    mode = path.stat().st_mode
    try:
        path.chmod(mode | stat.S_IWRITE)
        path.unlink()
    except BaseException:
        if path.exists():
            path.chmod(mode)
        raise


def checked_target(root, path):
    """Reject escapes and filesystem aliases before installing any payload."""
    path = Path(path).absolute()
    require(path.is_relative_to(root) and path.resolve() == path,
            "Output escaped repository or follows a filesystem alias: " + str(path))
    require(path != root and not path.is_dir(), "Output is not a file target: " + str(path))
    require(not path.exists() or path.stat().st_nlink <= 1, "Output has hard-link aliases: " + str(path))
    return path


def atomic_install(path, raw, expected, mode=None):
    index_guard.guard_existing_ancestor_index(path,'publish_card_candidate.atomic_install')
    """Install exact bytes only while the immediate predecessor still agrees."""
    require(state(path) == expected, "Concurrent change before target write: " + str(path))
    if raw is None:
        # Deletions are limited to positively identified duplicate current notes.
        require(expected is not None, "Deletion has no predecessor")
        require(state(path) == expected, "Concurrent change before target removal: " + str(path))
        remove_protected(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_mode = path.stat().st_mode if path.exists() else None
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary)
    installed = False
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(state(path) == expected, "Concurrent change before atomic replace: " + str(path))
        if previous_mode is not None:
            path.chmod(previous_mode | stat.S_IWRITE)
        require(path.resolve() == path.absolute(), "Target became a filesystem alias before atomic replace: " + str(path))
        require(state(path) == expected, "Concurrent change before atomic replace: " + str(path))
        os.replace(temporary, path)
        installed = True
        restored_mode = mode if mode is not None else previous_mode
        if restored_mode is not None:
            path.chmod(restored_mode)
    finally:
        if temporary.exists():
            temporary.unlink()
        if not installed and previous_mode is not None and state(path) == expected:
            path.chmod(previous_mode)


class PublicationRollbackError(RuntimeError):
    def __init__(self, original, issues):
        self.original = original
        self.rollback_issues = issues
        super().__init__(str(original) + "; rollback preserved concurrent changes or could not restore: " + "; ".join(issues))


def same_json(left, right):
    options = dict(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return json.dumps(left, **options) == json.dumps(right, **options)


def resolved(root, value):
    require(isinstance(value, str) and value.strip(), "Evidence path is missing")
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def binding(path, root=None):
    path = Path(path).resolve()
    return {"path": path.relative_to(root).as_posix() if root else str(path),
            "sha256": digest(path.read_bytes())}


def binding_list(value):
    return list(value.values()) if isinstance(value, dict) else list(value or [])


def verify_binding(root, item, guards):
    path = resolved(root, item.get("path", item.get("file")))
    raw = state(path)
    require(raw is not None and digest(raw) == item.get("sha256"), "Stale or missing evidence: " + str(path))
    require(path not in guards or guards[path] == raw, "Evidence changed during validation: " + str(path))
    guards[path] = raw
    return path


def recursive_bindings(root, value, guards):
    if isinstance(value, dict):
        if ("path" in value or "file" in value) and value.get("sha256"):
            verify_binding(root, value, guards)
        for child in value.values():
            recursive_bindings(root, child, guards)
    elif isinstance(value, list):
        for child in value:
            recursive_bindings(root, child, guards)


def portable_bindings(root, value, field=None):
    """Current runtime dependencies must live in this repository, not drafts."""
    value = deepcopy(value)
    if isinstance(value, dict):
        if ("path" in value or "file" in value) and value.get("sha256"):
            key = "path" if "path" in value else "file"
            path = resolved(root, value[key])
            require(path.is_relative_to(root), "Nonportable runtime dependency: " + str(path))
            value[key] = path.relative_to(root).as_posix()
        return {key: portable_bindings(root, child, key) for key, child in value.items()}
    if isinstance(value, list):
        return [portable_bindings(root, child, field) for child in value]
    if isinstance(value, str) and field in {"path", "file", "model", "model_path"}:
        path = Path(value)
        if path.is_absolute() and path.resolve().is_relative_to(root):
            return path.resolve().relative_to(root).as_posix()
    return value


def card_state(root, card):
    """Protect every other card artifact, not merely its rendered text."""
    result = {}
    for folder in ("Card-ALD", "json/Card-ALD", "notes/Card-ALD"):
        for path in (root / folder).rglob("*"):
            match = re.match(r"([0-9]{4})(?:\D|$)", path.name)
            if path.is_file() and match and match.group(1) != card:
                result[path] = path.read_bytes()
    return result


def index_rows(raw):
    fields = ["card_type", "file", "kind", "source_pages", "source_locations", "sha256"]
    if raw is None:
        return fields, []
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    require(reader.fieldnames and set(fields) <= set(reader.fieldnames), "Unsupported notation index")
    return reader.fieldnames, list(reader)


def make_index(raw, card, outputs, witness_index):
    fields, rows = index_rows(raw)
    current = [row for row in rows if row["card_type"] == card]
    require(len({row["file"] for row in current}) == len(current), "Duplicate card notation index row")
    require(all(re.fullmatch(card + r"(?:-[0-9]+)?\.txt", row["file"]) for row in current), "Current notation row escaped card namespace")
    others = [row for row in rows if row["card_type"] != card]
    require(not any(row["file"] in outputs for row in others), "Notation index namespace collision")
    witnesses = {int(row["number"]): row for row in (witness_index or {}).get("variants", [])}
    for name, content in outputs.items():
        number = int(re.fullmatch(card + r"(?:-([0-9]+))?\.txt", name).group(1) or 0)
        witness = witnesses.get(number, {})
        row = {field: "" for field in fields}
        row.update(card_type=card, file=name, sha256=digest(content),
                   kind="canonical" if not number else "observed notation variant")
        for key in ("source_pages", "source_locations"):
            values = witness.get(key, [])
            row[key] = values if isinstance(values, str) else "; ".join(sorted(set(map(str, values))))
        others.append(row)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(others)
    return b"\xef\xbb\xbf" + stream.getvalue().encode("utf-8")


def inventory_refresh(root, before, payload):
    """Prepare an established exact allowlist; the outer transaction installs it."""
    index_guard.reject_held_index(root,'publish_card_candidate.inventory_refresh')
    sys.path.insert(0, str(root / "tools/repository"))
    import refresh_inventory
    manifest = root / "notes/Repository records manifest.json"
    require((root / "notes/Source status.json").is_file(), "Current source status is required for compact inventory refresh")
    original = before[manifest]
    require(original is not None, "Repository inventory missing")
    recorded = {row["path"]: row["sha256"] for row in json.loads(original.decode("utf-8-sig"))["files"]}
    entries = []
    for path, raw in payload.items():
        if path == manifest or before[path] == raw:
            continue
        relative = path.relative_to(root).as_posix()
        prior = recorded.get(relative)
        require(prior == (digest(before[path]) if before[path] is not None else None),
                "Unrecorded predecessor differs from current inventory: " + relative)
        item = dict(path=relative, before_sha256=prior, after_sha256=digest(raw) if raw is not None else None,
                    authority="Independently reviewed current card candidate publication")
        if raw is None:
            item["action"] = "remove"
        entries.append(item)
    with tempfile.TemporaryDirectory(prefix="card-inventory-") as private:
        allowlist = Path(private) / "Allowlist.json"
        allowlist.write_bytes(encode(dict(schema="repository-inventory-allowlist-v1",
            baseline_manifest={"path": str(manifest), "sha256": digest(original)}, entries=entries)))
        prepared = refresh_inventory.prepare(root, allowlist, preserve_history=False)
        report, target, old, new, preserved, guards = prepared
        require(preserved is None and report["retention"] == "compact-current", "Inventory preparation attempted historical copies")
        for path, expected in guards.items():
            actual = digest(path.read_bytes()) if path.is_file() else None
            require(actual == expected, "Input changed before inventory install: " + str(path))
        return target, old, new


def prepare(card, definition, overrides, audit, review, root):
    require(re.fullmatch(r"[0-9]{4}", str(card)), "Use exactly four ASCII digits")
    root = Path(root).resolve()
    definition, overrides, audit, review = [Path(p).resolve() for p in (definition, overrides, audit, review)]
    guards = {path: path.read_bytes() for path in (definition, overrides, audit, review)}
    approval = read(review)
    require(approval.get("passed") is True and not approval.get("failures"), "Independent review has not passed")
    bound = binding_list(approval.get("candidate_bindings"))
    require(bound, "Independent review must name exact candidate_bindings")
    reviewed = {verify_binding(root, item, guards) for item in bound}
    require({definition, overrides, audit} <= reviewed, "Candidate not covered by independent review")
    supporting = binding_list(approval.get("supporting_files"))
    for item in supporting:
        verify_binding(root, item, guards)
    spec, supplement, source_audit = map(read, (definition, overrides, audit))
    require(all(doc.get("card_type") == card for doc in (spec, supplement, source_audit)), "Candidate card identities differ")
    outputs, checks = renderer.build(spec)
    require(all(re.fullmatch(card + r"(?:-[0-9]+)?\.txt", name) for name in outputs), "Rendered file escaped card namespace")
    require(source_audit.get("schema") == "card-use-audit-v1" and source_audit.get("read_only") is True, "Invalid source audit")
    require(not source_audit.get("review") and source_audit["summary"]["needs_review"] == 0, "Unresolved source findings")
    require(source_audit["definition"]["sha256"] == digest(guards[definition]), "Audit definition differs")
    require(source_audit.get("overrides", {}).get("sha256") == digest(guards[overrides]), "Audit supplement differs")
    for value in (spec.get("provenance", {}), supplement.get("source_bindings", []), source_audit):
        recursive_bindings(root, value, guards)
    fresh = audit_card_uses.audit(card, root=root, definition_path=definition, overrides_path=overrides)
    require(not fresh["review"] and fresh["summary"]["needs_review"] == 0, "Current sources no longer pass the card-use audit")
    require(all(same_json(fresh.get(key), source_audit.get(key)) for key in AUDIT_KEYS), "Current use audit differs")
    recursive_bindings(root, fresh, guards)
    rebuilt, _evidence = build_card_data.build(card, root=root, overrides_path=overrides)
    require(rebuilt is not None and renderer.build(rebuilt)[0] == outputs, "Default builder does not reproduce reviewed candidate")
    witness_index = None
    if approval.get("variant_index"):
        path = verify_binding(root, approval["variant_index"], guards)
        require(path in reviewed | {verify_binding(root, item, guards) for item in supporting}, "Variant index lacks reviewed binding")
        witness_index = read(path)
        require(witness_index.get("card_type") == card and witness_index.get("publication_policy") == "complete-witnesses", "Invalid witnessed variant publication policy")
        variants = witness_index.get("variants", [])
        indexed = {row["number"]: row for row in variants}
        require(len(indexed) == len(variants) and set(indexed) == {v["number"] for v in spec["variants"]}, "Witness index does not cover variants exactly")
        for variant in spec["variants"]:
            witness = indexed[variant["number"]]
            require(witness.get("witnesses") and witness.get("source_pages") and witness.get("source_locations") and witness.get("complete_witnesses", 0) > 0, "Variant lacks a complete source witness")
            require("variant_definition" not in witness or same_json(witness["variant_definition"], variant), "Witness pattern differs")
        witness_index = portable_bindings(root, witness_index)
    require(not spec["variants"] or witness_index is not None, "Numbered variants need an independently reviewed witness index")
    require(not [p.name for p in (root / "Card-ALD").glob(card + "-[0-9]*.txt") if re.fullmatch(card + r"-[0-9]+\.txt", p.name) and p.name not in outputs], "Unlisted older variants require review")
    require(not list((root / "Card-ALD").glob(card + ".*.txt")), "Unexpected card namespace")
    canonical = root / f"json/Card-ALD/definitions/{card}.json"
    override_path = root / f"json/Card-ALD/build-overrides/{card}.json"
    spec, supplement = portable_bindings(root, spec), portable_bindings(root, supplement)
    canonical_raw, override_raw = encode(spec), encode(supplement)
    current_audit = portable_bindings(root, {key: value for key, value in fresh.items() if key not in ("definition", "overrides", "created_utc")})
    current_audit.update(definition={"path": canonical.relative_to(root).as_posix(), "sha256": digest(canonical_raw)},
                         overrides={"path": override_path.relative_to(root).as_posix(), "sha256": digest(override_raw)})
    audit_relative = f"notes/Card-ALD/Audits/{card}.json"
    receipt_relative = f"notes/Card-ALD/Generation/{card}.json"
    payload = {canonical: canonical_raw, override_path: override_raw, root / audit_relative: encode(current_audit)}
    if witness_index is not None:
        payload[root / f"notes/Card-ALD/Notation witnesses/{card}.json"] = encode(witness_index)
    file_records = [{"path": "Card-ALD/" + name, "sha256": digest(raw)} for name, raw in outputs.items()]
    receipt = dict(schema="card-ald-current-publication-v1", card_type=card,
        canonical=f"Card-ALD/{card}.txt", diagram_sha256=digest(outputs[card + ".txt"]),
        definition=current_audit["definition"], overrides=current_audit["overrides"],
        source_audit={"path": audit_relative, "sha256": digest(payload[root / audit_relative])},
        independent_review={"sha256": digest(guards[review]), "passed": True},
        reviewed_candidates={"definition_sha256": digest(guards[definition]), "overrides_sha256": digest(guards[overrides]), "audit_sha256": digest(guards[audit])},
        validation=checks, files=file_records, default_builder_reproduced=True,
        renderer_sha256=digest(Path(renderer.__file__).read_bytes()),
        builder_sha256=digest(Path(build_card_data.__file__).read_bytes()),
        auditor_sha256=digest(Path(audit_card_uses.__file__).read_bytes()))
    if witness_index is not None:
        relative = f"notes/Card-ALD/Notation witnesses/{card}.json"
        receipt["notation_witness_index"] = {"path": relative, "sha256": digest(payload[root / relative])}
    payload[root / receipt_relative] = encode(receipt)
    payload[root / f"json/Card-ALD/{card}.json"] = encode(dict(schema="card-ald-generated-model-v1", card_type=card,
        drawing=receipt["canonical"], drawing_sha256=receipt["diagram_sha256"], render_definition=receipt["definition"], generation_receipt=receipt_relative))
    old_generation = state(root / receipt_relative)
    duplicates = set()
    for relative in (f"notes/Card-ALD/{card} drawing provenance.json", f"notes/Card-ALD/{card} diagram publication receipt.json"):
        if old_generation is not None and state(root / relative) == old_generation:
            payload[root / relative] = None
            duplicates.add(root / relative)
    for name, raw in outputs.items():
        payload[root / "Card-ALD" / name] = raw
    index = root / "csv/Card-ALD/Notation variants.csv"
    payload[index] = make_index(state(index), card, outputs, witness_index)
    shared = root / "notes/Card-ALD/Universal card diagrams publication.json"
    inventory = read(shared) if shared.exists() else dict(schema="shared-card-renderer-publication-v1", cards=[], published_files=[])
    require(inventory.get("schema") == "shared-card-renderer-publication-v1", "Unsupported shared card index")
    require(sum(row["card_type"] == card for row in inventory["cards"]) <= 1, "Duplicate current card in shared index")
    inventory["cards"] = [row for row in inventory["cards"] if row["card_type"] != card] + [dict(card_type=card,
        canonical=receipt["canonical"], diagram_sha256=receipt["diagram_sha256"], variant_count=len(spec["variants"]), generation_receipt=receipt_relative)]
    inventory["published_files"] = [row for row in inventory["published_files"] if not re.fullmatch(r"Card-ALD/" + card + r"(?:-[0-9]+)?\.txt", row["path"])] + file_records
    payload[shared] = encode(inventory)
    targets = [checked_target(root, path) for path in payload]
    require(len({str(path).casefold() for path in targets}) == len(targets), "Payload has aliased output targets")
    for path, raw in payload.items():
        require(path not in guards or guards[path] == raw,
                "Output would overwrite source or independent review evidence: " + str(path))
    before = {path: state(path) for path in payload}
    require(before[root / receipt_relative] == old_generation and all(before[path] == old_generation for path in duplicates),
            "Current generation receipt or duplicate changed during preparation")
    for path, raw in guards.items():
        require(state(path) == raw, "Source changed during preparation: " + str(path))
    report = dict(card_type=card, files=len(outputs), variants=len(spec["variants"]), source_occurrences=fresh["summary"]["occurrences"],
                  renderer_checks=checks, coverage_limitations=fresh["summary"]["coverage_limitations"], checked=True, published=False,
                  changed_files=sum(before[path] != raw for path, raw in payload.items()), retention="compact-current")
    return root, payload, before, guards, outputs, report


def publish(card, definition, overrides, audit, review, root=ROOT, check_only=False, refresh_inventory=True):
    if not check_only:index_guard.reject_held_index(root,'publish_card_candidate.publish')
    root, payload, before, guards, outputs, report = prepare(card, definition, overrides, audit, review, root)
    if check_only:
        return report
    unrelated = card_state(root, card)
    manifest = checked_target(root, root / "notes/Repository records manifest.json")
    if refresh_inventory:
        before[manifest] = state(manifest)
    lock = checked_target(root, root / ".card-publication.lock")
    lock_token = os.urandom(16).hex().encode()
    with lock.open("xb") as stream:
        stream.write(lock_token)
    try:
        owned_after = {}
        modes = {path: path.stat().st_mode if path.exists() else None for path in payload}
        if refresh_inventory:
            modes[manifest] = manifest.stat().st_mode if manifest.exists() else None
        try:
            for path, expected in {**guards, **before, **unrelated}.items():
                require(state(path) == expected, "Concurrent change before publication: " + str(path))
            for path, raw in payload.items():
                checked_target(root, path)
                require(state(path) == before[path], "Concurrent change before target write: " + str(path))
                if raw == before[path]:
                    continue
                owned_after[path] = raw
                atomic_install(path, raw, before[path])
            rebuilt, _evidence = build_card_data.build(card, root=root, overrides_path=root / f"json/Card-ALD/build-overrides/{card}.json")
            require(rebuilt is not None and renderer.build(rebuilt)[0] == outputs, "Published default builder differs from reviewed build")
            require(all(state(path) == raw for path, raw in payload.items()), "Publication verification failed")
            require(card_state(root, card) == unrelated, "Unrelated card namespace changed")
            for path, expected in guards.items():
                if path not in payload:
                    require(state(path) == expected, "Source changed during publication: " + str(path))
            if refresh_inventory:
                target, old, new = inventory_refresh(root, before, payload)
                require(target == manifest and old == before[manifest], "Inventory target or predecessor changed")
                checked_target(root, target)
                owned_after[target] = new
                atomic_install(target, new, old)
                require(state(target) == new, "Current inventory changed after publication")
            require(all(state(path) == raw for path, raw in payload.items()), "Current output changed after publication")
            require(card_state(root, card) == unrelated, "Unrelated card namespace changed after publication")
            require(state(lock) == lock_token, "Publication lock changed during transaction")
            report.update(published=True, inventory_refreshed=refresh_inventory,
                          receipt=f"notes/Card-ALD/Generation/{card}.json", unrelated_cards_unchanged=True)
            return report
        except BaseException as original:
            issues = []
            for path, after in reversed(list(owned_after.items())):
                try:
                    checked_target(root, path)
                    current = state(path)
                    if current == before[path]:
                        continue
                    if current != after:
                        issues.append("preserved concurrent target " + str(path))
                        continue
                    checked_target(root, path)
                    atomic_install(path, before[path], after, modes[path])
                except BaseException as rollback_error:
                    issues.append(str(path) + ": " + str(rollback_error))
            for path, old in before.items():
                if path not in owned_after:
                    try:
                        checked_target(root, path)
                        if state(path) != old:
                            issues.append("preserved concurrent untouched target " + str(path))
                    except BaseException as rollback_error:
                        issues.append(str(path) + ": " + str(rollback_error))
            if issues:
                raise PublicationRollbackError(original, issues) from original
            raise
    finally:
        if state(lock) == lock_token:
            lock.unlink()


def verify_current(card, root=ROOT):
    """Verify a published current record without opening any private review files."""
    require(re.fullmatch(r"[0-9]{4}", str(card)), "Use exactly four ASCII digits")
    root = Path(root).resolve()
    status_guards = typed_current_status_gate.current_status_guards(card, root)
    receipt = read(root / f"notes/Card-ALD/Generation/{card}.json")
    portable_bindings(root, receipt)
    require(receipt.get("schema") == "card-ald-current-publication-v1" and receipt.get("card_type") == card,
            "Unsupported current card receipt")
    require(receipt.get("independent_review", {}).get("passed") is True and
            re.fullmatch(r"[0-9a-f]{64}", receipt["independent_review"].get("sha256", "")),
            "Current record lacks accepted independent review identity")
    guards = dict(status_guards)
    for key in ("definition", "overrides", "source_audit"):
        verify_binding(root, receipt[key], guards)
    spec = read(root / receipt["definition"]["path"])
    source_audit = read(root / receipt["source_audit"]["path"])
    outputs, checks = renderer.build(spec)
    expected = {row["path"]: row["sha256"] for row in receipt["files"]}
    require(expected == {"Card-ALD/" + name: digest(raw) for name, raw in outputs.items()}, "Current rendered file index differs")
    for name, raw in outputs.items():
        require(state(root / "Card-ALD" / name) == raw, "Current rendered card differs: " + name)
    recursive_bindings(root, spec.get("provenance", {}), guards)
    recursive_bindings(root, source_audit, guards)
    if receipt.get("notation_witness_index"):
        verify_binding(root, receipt["notation_witness_index"], guards)
    fresh = audit_card_uses.audit(card, root=root, definition_path=root / receipt["definition"]["path"],
                                  overrides_path=root / receipt["overrides"]["path"])
    fresh = {**fresh, **portable_bindings(root, {key: fresh.get(key) for key in AUDIT_KEYS})}
    require(not fresh["review"] and fresh["summary"]["needs_review"] == 0 and
            all(same_json(fresh.get(key), source_audit.get(key)) for key in AUDIT_KEYS), "Current source audit differs")
    rebuilt, _evidence = build_card_data.build(card, root=root, overrides_path=root / receipt["overrides"]["path"])
    require(rebuilt is not None and renderer.build(rebuilt)[0] == outputs, "Current default builder differs")
    for path, raw in guards.items():
        require(state(path) == raw, "Input changed during current verification: " + str(path))
    return dict(passed=True, card_type=card, files=len(outputs), validation=checks,
                private_evidence_opened=False, retention="compact-current")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card_type")
    for name in ("definition", "overrides", "audit", "review"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--verify-current", action="store_true", help="Verify published data without private candidate/review files")
    parser.add_argument("--defer-inventory-refresh", action="store_true", help="Outer reviewed batch must refresh the exact inventory before completion")
    args = parser.parse_args()
    if args.verify_current:
        print(json.dumps(verify_current(args.card_type, args.root), ensure_ascii=False))
        return
    if any(getattr(args, name) is None for name in ("definition", "overrides", "audit", "review")):
        parser.error("--definition, --overrides, --audit and --review are required to prepare a publication")
    print(json.dumps(publish(args.card_type, args.definition, args.overrides, args.audit, args.review,
        root=args.root, check_only=args.check, refresh_inventory=not args.defer_inventory_refresh), ensure_ascii=False))


if __name__ == "__main__":
    main()

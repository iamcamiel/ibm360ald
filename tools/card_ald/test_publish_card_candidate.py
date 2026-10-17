"""Transaction and proof-gate tests; circuit/render semantics have their own tests."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import stat
import os
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("compact_publisher", Path(__file__).with_name("publish_card_candidate.py"))
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fixture-", dir=Path(__file__).parent)
        self.home = Path(self.temp.name)
        self.root = self.home / "repo"
        self.root.mkdir()
        self.private = self.home / "candidate"
        self.private.mkdir()
        self.source = self.root / "json/ALD/page.json"
        self.write(self.source, {"current": True})
        self.definition = self.private / "Definition.json"
        self.overrides = self.private / "Overrides.json"
        self.audit = self.private / "Audit.json"
        self.review = self.private / "Review.json"
        self.witness = self.private / "Witness.json"
        self.model = dict(card_type="0006", variants=[], provenance={"source": pub.binding(self.source)})
        self.other = self.root / "Card-ALD/1124.txt"
        self.other.parent.mkdir()
        self.other.write_bytes(b"untouched other card\n")
        self.other_definition = self.root / "json/Card-ALD/definitions/1124.json"
        self.write(self.other_definition, {"must": "stay"})
        self.make_candidate()
        self.patches = [patch.object(pub.renderer, "build", side_effect=self.render),
                        patch.object(pub.build_card_data, "build", side_effect=self.rebuild),
                        patch.object(pub.audit_card_uses, "audit", side_effect=self.fresh_audit)]
        for handle in self.patches:
            handle.start()

    def tearDown(self):
        for handle in reversed(self.patches):
            handle.stop()
        self.temp.cleanup()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pub.encode(value))

    def make_candidate(self, variants=None):
        if variants is not None:
            self.model["variants"] = variants
        self.write(self.definition, self.model)
        self.write(self.overrides, dict(card_type="0006", source_bindings=[pub.binding(self.source)], render_definition=self.model))
        self.observed_audit = dict(schema="card-use-audit-v1", card_type="0006", read_only=True, review=[],
            summary=dict(needs_review=0, occurrences=4, coverage_limitations=0),
            definition=pub.binding(self.definition), overrides=pub.binding(self.overrides),
            catalog=pub.binding(self.source), source_bindings=[pub.binding(self.source)],
            occurrences=[{"portion": "A1", "status": "match", "model": str(self.source)}], coverage_limitations=[], known_reviewed_source_corrections=[])
        self.write(self.audit, self.observed_audit)
        review = dict(passed=True, failures=[], candidate_bindings=[pub.binding(path) for path in (self.definition, self.overrides, self.audit)])
        if self.model["variants"]:
            self.write(self.witness, dict(card_type="0006", publication_policy="complete-witnesses", variants=[dict(number=v["number"],
                witnesses=["PAGE.A1"], source_pages=["PAGE"], source_locations=["A1"], complete_witnesses=1,
                variant_definition=v) for v in self.model["variants"]]))
            review["variant_index"] = pub.binding(self.witness)
            review["supporting_files"] = [pub.binding(self.witness)]
        self.write(self.review, review)

    def reapprove(self):
        current = pub.read(self.review)
        current["candidate_bindings"] = [pub.binding(path) for path in (self.definition, self.overrides, self.audit)]
        if self.witness.exists():
            current["variant_index"] = pub.binding(self.witness)
            current["supporting_files"] = [pub.binding(self.witness)]
        self.write(self.review, current)

    @staticmethod
    def render(model):
        outputs = {model["card_type"] + ".txt": b"canonical diagram\n"}
        for row in model["variants"]:
            outputs[model["card_type"] + f'-{row["number"]:02}.txt'] = f'variant {row["number"]}\n'.encode()
        return outputs, {"passed": True}

    def rebuild(self, card, root, overrides_path):
        return pub.read(overrides_path)["render_definition"], {}

    def fresh_audit(self, *args, **kwargs):
        return deepcopy(self.observed_audit)

    def publish(self, **kwargs):
        return pub.publish("0006", self.definition, self.overrides, self.audit, self.review,
                           root=self.root, refresh_inventory=False, **kwargs)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        self.assertFalse(self.publish(check_only=True)["published"])
        self.assertEqual(self.snapshot(), before)

    def test_current_publication_has_one_receipt_and_portable_runtime_inputs(self):
        self.assertTrue(self.publish()["published"])
        files = self.snapshot()
        self.assertFalse(any("history" in name or "Accepted candidates" in name for name in files))
        self.assertEqual([name for name in files if "/Generation/" in name], ["notes/Card-ALD/Generation/0006.json"])
        self.assertNotIn(str(self.private), "\n".join(raw.decode("utf-8-sig") for raw in files.values()))
        self.assertEqual(self.other.read_bytes(), b"untouched other card\n")
        self.assertEqual(pub.read(self.other_definition), {"must": "stay"})
        self.assertFalse((self.root / ".card-publication.lock").exists())
        self.assertEqual(pub.read(self.root / "notes/Card-ALD/Audits/0006.json")["occurrences"][0]["model"], "json/ALD/page.json")

    def test_repeat_is_idempotent(self):
        self.publish()
        first = self.snapshot()
        result = self.publish()
        self.assertEqual(result["changed_files"], 0)
        self.assertEqual(first, self.snapshot())

    def test_current_verification_does_not_need_private_review_files(self):
        self.publish()
        for path in (self.definition, self.audit, self.overrides, self.review):
            path.unlink()
        result = pub.verify_current("0006", self.root)
        self.assertTrue(result["passed"])
        self.assertFalse(result["private_evidence_opened"])

    def test_current_verification_detects_changed_sources(self):
        self.publish()
        self.write(self.source, {"different": True})
        with self.assertRaisesRegex(ValueError, "Stale or missing"):
            pub.verify_current("0006", self.root)

    def test_stale_candidate_rejected(self):
        self.definition.write_bytes(self.definition.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "Stale or missing"):
            self.publish()

    def test_failed_independent_review_rejected(self):
        review = pub.read(self.review)
        review["passed"] = False
        self.write(self.review, review)
        with self.assertRaisesRegex(ValueError, "review has not passed"):
            self.publish()

    def test_missing_candidate_binding_rejected(self):
        review = pub.read(self.review)
        review["candidate_bindings"] = review["candidate_bindings"][:-1]
        self.write(self.review, review)
        with self.assertRaisesRegex(ValueError, "not covered"):
            self.publish()

    def test_current_source_change_rejected(self):
        self.write(self.source, {"current": False})
        with self.assertRaisesRegex(ValueError, "Stale or missing"):
            self.publish()

    def test_source_changing_during_audit_rejected_without_writes(self):
        before = self.snapshot()
        def change(*args, **kwargs):
            self.write(self.source, {"new": True})
            return deepcopy(self.observed_audit)
        with patch.object(pub.audit_card_uses, "audit", side_effect=change):
            with self.assertRaisesRegex(ValueError, "Stale or missing"):
                self.publish()
        self.assertFalse((self.root / "Card-ALD/0006.txt").exists())
        before.pop("json/ALD/page.json")
        after = self.snapshot(); after.pop("json/ALD/page.json")
        self.assertEqual(before, after)

    def test_fabricated_zero_review_audit_rejected(self):
        self.observed_audit["review"] = ["real discrepancy"]
        self.observed_audit["summary"]["needs_review"] = 1
        with self.assertRaisesRegex(ValueError, "no longer pass"):
            self.publish()

    def test_changed_fresh_occurrence_rejected(self):
        self.observed_audit["occurrences"].append({"status": "not previously reviewed"})
        with self.assertRaisesRegex(ValueError, "audit differs"):
            self.publish()

    def test_default_builder_mismatch_rejected(self):
        with patch.object(pub.build_card_data, "build", return_value=(None, {})):
            with self.assertRaisesRegex(ValueError, "does not reproduce"):
                self.publish()

    def test_complete_witness_variant_publishes_and_indexes(self):
        self.make_candidate([{"number": 1, "box_overrides": {}}])
        self.publish()
        self.assertEqual((self.root / "Card-ALD/0006-01.txt").read_bytes(), b"variant 1\n")
        _, rows = pub.index_rows((self.root / "csv/Card-ALD/Notation variants.csv").read_bytes())
        self.assertEqual(rows[1]["kind"], "observed notation variant")
        self.assertEqual(rows[1]["source_pages"], "PAGE")

    def test_partial_witness_cannot_be_published(self):
        self.make_candidate([{"number": 1, "box_overrides": {}}])
        value = pub.read(self.witness)
        value["variants"][0]["complete_witnesses"] = 0
        self.write(self.witness, value); self.reapprove()
        with self.assertRaisesRegex(ValueError, "complete source witness"):
            self.publish()

    def test_unreviewed_variant_index_cannot_be_published(self):
        self.make_candidate([{"number": 1, "box_overrides": {}}])
        value = pub.read(self.review); value["supporting_files"] = []
        self.write(self.review, value)
        with self.assertRaisesRegex(ValueError, "lacks reviewed binding"):
            self.publish()

    def test_unlisted_older_variant_cannot_be_deleted_implicitly(self):
        (self.root / "Card-ALD/0006-02.txt").write_bytes(b"old variant")
        with self.assertRaisesRegex(ValueError, "Unlisted older"):
            self.publish()

    def test_private_runtime_dependency_rejected(self):
        extra = self.private / "Evidence.json"
        self.write(extra, {"draft": True})
        self.model["provenance"]["private"] = pub.binding(extra)
        self.make_candidate()
        with self.assertRaisesRegex(ValueError, "Nonportable runtime dependency"):
            self.publish()

    def test_write_failure_rolls_back_all_original_bytes(self):
        self.publish()
        # Force one changed current output, and then fail while writing another.
        target = self.root / "Card-ALD/0006.txt"
        target.write_bytes(b"previous canonical")
        (self.root / "json/Card-ALD/0006.json").write_bytes(b"{}\n")
        self.write(self.root / "notes/Card-ALD/0006 drawing provenance.json", {"old duplicate": True})
        before = self.snapshot()
        original = pub.atomic_install
        count = 0
        def fail_once(path, raw, expected, mode=None):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("injected write failure")
            original(path, raw, expected, mode)
        with patch.object(pub, "atomic_install", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "injected"):
                self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_existing_publication_lock_prevents_write(self):
        lock = self.root / ".card-publication.lock"
        lock.write_bytes(b"another publisher")
        before = self.snapshot()
        with self.assertRaises(FileExistsError):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_postwrite_default_builder_failure_rolls_back(self):
        before = self.snapshot()
        calls = 0
        def late_failure(*args, **kwargs):
            nonlocal calls
            calls += 1
            return self.rebuild(*args, **kwargs) if calls == 1 else (None, {})
        with patch.object(pub.build_card_data, "build", side_effect=late_failure):
            with self.assertRaisesRegex(ValueError, "Published default builder differs"):
                self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_unrelated_index_row_bytes_are_preserved_as_values(self):
        index = self.root / "csv/Card-ALD/Notation variants.csv"
        index.parent.mkdir(parents=True)
        index.write_bytes(b"card_type,file,kind,source_pages,source_locations,sha256\r\n1124,1124.txt,canonical,EXAMPLE,A1,unchanged\r\n")
        self.publish()
        _, rows = pub.index_rows(index.read_bytes())
        self.assertEqual(rows[0], dict(card_type="1124", file="1124.txt", kind="canonical", source_pages="EXAMPLE", source_locations="A1", sha256="unchanged"))

    def test_duplicate_current_index_cannot_be_silently_repaired(self):
        index = self.root / "csv/Card-ALD/Notation variants.csv"
        index.parent.mkdir(parents=True)
        index.write_bytes(b"card_type,file,kind,source_pages,source_locations,sha256\n0006,0006.txt,canonical,,,a\n0006,0006.txt,canonical,,,b\n")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Duplicate card notation"):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_current_generation_receipts_are_retired(self):
        old = [self.root / "notes/Card-ALD/0006 drawing provenance.json", self.root / "notes/Card-ALD/0006 diagram publication receipt.json"]
        self.write(self.root / "notes/Card-ALD/Generation/0006.json", {"duplicate": True})
        for path in old:
            self.write(path, {"duplicate": True})
        self.publish()
        self.assertFalse(any(path.exists() for path in old))

    def test_readonly_duplicate_receipt_can_be_retired(self):
        old = self.root / "notes/Card-ALD/0006 drawing provenance.json"
        self.write(self.root / "notes/Card-ALD/Generation/0006.json", {"duplicate": True})
        self.write(old, {"duplicate": True})
        old.chmod(stat.S_IREAD)
        self.publish()
        self.assertFalse(old.exists())

    def test_inventory_failure_rolls_back_current_card_outputs(self):
        manifest = self.root / "notes/Repository records manifest.json"
        self.write(manifest, {"schema": "fixture", "files": []})
        before = self.snapshot()
        def failure(*args):
            raise ValueError("inventory gate failed")
        with patch.object(pub, "inventory_refresh", side_effect=failure):
            with self.assertRaisesRegex(ValueError, "inventory gate"):
                pub.publish("0006", self.definition, self.overrides, self.audit, self.review, root=self.root)
        self.assertEqual(self.snapshot(), before)

    def test_unknown_inventory_writer_is_preserved_and_other_outputs_rolled_back(self):
        manifest = self.root / "notes/Repository records manifest.json"
        self.write(manifest, {"schema": "fixture", "files": []})
        before = self.snapshot()
        concurrent = b"concurrent inventory writer"
        def failure(*args):
            manifest.write_bytes(concurrent)
            raise ValueError("inventory gate failed")
        with patch.object(pub, "inventory_refresh", side_effect=failure):
            with self.assertRaisesRegex(pub.PublicationRollbackError, "preserved concurrent untouched target"):
                pub.publish("0006", self.definition, self.overrides, self.audit, self.review, root=self.root)
        self.assertEqual(manifest.read_bytes(), concurrent)
        before[manifest.relative_to(self.root).as_posix()] = concurrent
        self.assertEqual(self.snapshot(), before)

    def test_first_atomic_failure_leaves_predecessors_intact(self):
        before = self.snapshot()
        with patch.object(pub, "atomic_install", side_effect=OSError("first atomic failure")):
            with self.assertRaisesRegex(OSError, "first atomic failure"):
                self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_future_target_concurrent_writer_survives_before_guard_failure(self):
        later = self.root / "json/Card-ALD/0006.json"
        concurrent = b"concurrent later target"
        before = self.snapshot()
        real = pub.atomic_install
        injected = False
        def inject(path, raw, expected, mode=None):
            nonlocal injected
            real(path, raw, expected, mode)
            if not injected:
                injected = True
                later.parent.mkdir(parents=True, exist_ok=True)
                later.write_bytes(concurrent)
        with patch.object(pub, "atomic_install", side_effect=inject):
            with self.assertRaisesRegex(pub.PublicationRollbackError, "Concurrent change before target write"):
                self.publish()
        before[later.relative_to(self.root).as_posix()] = concurrent
        self.assertEqual(self.snapshot(), before)

    def test_concurrent_change_to_already_written_target_is_not_overwritten(self):
        first = self.root / "json/Card-ALD/definitions/0006.json"
        concurrent = b"concurrent canonical definition"
        before = self.snapshot()
        calls = 0
        def late_failure(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return self.rebuild(*args, **kwargs)
            first.write_bytes(concurrent)
            return None, {}
        with patch.object(pub.build_card_data, "build", side_effect=late_failure):
            with self.assertRaisesRegex(pub.PublicationRollbackError, "preserved concurrent target"):
                self.publish()
        before[first.relative_to(self.root).as_posix()] = concurrent
        self.assertEqual(self.snapshot(), before)

    def test_known_owned_inventory_after_bytes_are_rolled_back(self):
        manifest = self.root / "notes/Repository records manifest.json"
        self.write(manifest, {"schema": "fixture", "files": []})
        before = self.snapshot()
        old = manifest.read_bytes()
        new = b"our exact prepared inventory"
        real = pub.atomic_install
        failed = False
        def fail_after_commit(path, raw, expected, mode=None):
            nonlocal failed
            real(path, raw, expected, mode)
            if path == manifest and raw == new and not failed:
                failed = True
                raise OSError("failure after our inventory commit")
        with patch.object(pub, "inventory_refresh", return_value=(manifest, old, new)), patch.object(pub, "atomic_install", side_effect=fail_after_commit):
            with self.assertRaisesRegex(OSError, "after our inventory commit"):
                pub.publish("0006", self.definition, self.overrides, self.audit, self.review, root=self.root)
        self.assertEqual(self.snapshot(), before)

    def test_unique_source_notes_are_preserved(self):
        self.write(self.root / "notes/Card-ALD/Generation/0006.json", {"generation": True})
        unique = self.root / "notes/Card-ALD/0006 drawing provenance.json"
        self.write(unique, {"source_exception": "Human confirmed the original torn scan"})
        before = unique.read_bytes()
        self.publish()
        self.assertEqual(unique.read_bytes(), before)

    def test_hard_link_target_alias_to_source_is_rejected(self):
        target = self.root / "json/Card-ALD/definitions/0006.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.source.read_bytes())
        before = self.snapshot()
        real_stat = Path.stat
        def reported_alias(path, *args, **kwargs):
            original = real_stat(path, *args, **kwargs)
            if path == target:
                values = list(original); values[3] = 2
                return os.stat_result(values)
            return original
        with patch.object(Path, "stat", reported_alias):
            with self.assertRaisesRegex(ValueError, "hard-link aliases"):
                self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_payload_cannot_replace_its_source_or_independent_review_input(self):
        canonical = self.root / "json/Card-ALD/definitions/0006.json"
        canonical.write_bytes(self.definition.read_bytes())
        self.definition = canonical
        self.observed_audit["definition"] = pub.binding(canonical)
        self.write(self.audit, self.observed_audit)
        self.reapprove()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "overwrite source or independent review evidence"):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_payload_outside_repository_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "escaped repository"):
            pub.checked_target(self.root, self.root.parent / "outside.json")

    def test_real_compact_inventory_refresh_accepts_exact_publication(self):
        text = self.root / "ALD/ALD/page.txt"
        text.parent.mkdir(parents=True)
        text.write_bytes(b"page text unchanged\n")
        self.write(self.root / "notes/Source status.json", dict(schema="ald-current-source-checkpoint-v1", records=[dict(
            page="page", scan_reference=dict(id="1", relative_path="original/page.tif"), status="reviewed",
            repository=dict(txt=pub.binding(text, self.root), json=pub.binding(self.source, self.root)))]))
        # Seed an old duplicate receipt so exact authorized retirement is tested too.
        duplicate = self.root / "notes/Card-ALD/0006 drawing provenance.json"
        self.write(self.root / "notes/Card-ALD/Generation/0006.json", {"old": "duplicate"})
        self.write(duplicate, {"old": "duplicate"})
        manifest = self.root / "notes/Repository records manifest.json"
        self.write(manifest, dict(schema="ald-current-repository-inventory-v1", files=[pub.binding(path, self.root)
            for path in self.root.rglob("*") if path.is_file()]))
        actual_tools = Path(pub.renderer.__file__).resolve().parents[1] / "repository"
        old_path = list(sys.path)
        sys.path.insert(0, str(actual_tools))
        try:
            result = pub.publish("0006", self.definition, self.overrides, self.audit, self.review, root=self.root)
        finally:
            sys.path[:] = old_path
        self.assertTrue(result["inventory_refreshed"])
        recorded = {row["path"]: row["sha256"] for row in pub.read(manifest)["files"]}
        actual = {path.relative_to(self.root).as_posix(): pub.digest(path.read_bytes())
                  for path in self.root.rglob("*") if path.is_file() and path != manifest}
        self.assertEqual(recorded, actual)
        self.assertNotIn(duplicate.relative_to(self.root).as_posix(), recorded)
        self.assertFalse(any("predecessor" in path.lower() or "history" in path.lower() for path in recorded))


if __name__ == "__main__":
    unittest.main()

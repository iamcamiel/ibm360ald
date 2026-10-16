"""Disposable exact-successor chain and fail-closed acceptance fixtures."""
from copy import deepcopy
import ast
import importlib.util
from pathlib import Path
import unittest

import source_review as sr
import successor_registry as registry
import test_source_review as fixtures


class RegistryTests(unittest.TestCase):
    setUp = fixtures.StageTests.setUp
    tearDown = fixtures.StageTests.tearDown
    save_intent = fixtures.StageTests.save_intent
    create = fixtures.StageTests.create
    acceptance = fixtures.StageTests.acceptance

    def release(self):
        self.create()
        sr.publish(self.stage / 'manifest.json', self.acceptance())
        self.regpath = self.base / 'registry.json'
        return self.stage / 'publication.json'

    def register(self, pub):
        return registry.register(self.regpath, pub, self.base, self.target, self.base)

    def verify(self):
        return registry.accepted_successors(self.regpath, self.base, self.target, self.base)

    def test_register_current_exact_quartet_and_retry(self):
        pub = self.release(); result = self.register(pub)
        self.assertEqual(result['release_count'], 1)
        self.assertEqual(result['records'][0]['current_quartet']['txt'], sr.binding(self.text))
        self.assertTrue(self.register(pub)['idempotent_retry'])
        self.assertEqual(self.verify()['release_count'], 1)

    def test_missing_registry_is_not_empty_acceptance(self):
        self.regpath = self.base / 'missing.json'
        with self.assertRaises(FileNotFoundError): self.verify()

    def test_stale_live_model_blocks_even_when_text_matches(self):
        pub = self.release(); self.register(pub)
        self.model.write_bytes(sr.encode({'nodes': []}))
        with self.assertRaises(ValueError): self.verify()

    def test_missing_registered_publication_blocks(self):
        pub = self.release(); self.register(pub); pub.unlink()
        with self.assertRaises(FileNotFoundError): self.verify()

    def test_stale_source_binding_blocks(self):
        pub = self.release(); self.register(pub); self.source.write_bytes(b'changed scan')
        with self.assertRaises(ValueError): self.verify()

    def test_published_quartet_claim_cannot_differ_from_stage(self):
        pub = self.release(); doc = sr.read_json(pub)
        doc['pages'][0]['current_quartet']['json']['sha256'] = '0' * 64
        pub.write_bytes(sr.encode(doc))
        with self.assertRaises(ValueError): self.register(pub)
        self.assertFalse(self.regpath.exists())

    def test_wrong_independent_acceptance_hash_blocks(self):
        pub = self.release(); doc = sr.read_json(pub)
        ap = Path(doc['independent_acceptance']['path']); ap.write_bytes(b'{}')
        with self.assertRaises(ValueError): self.register(pub)

    def test_registered_two_releases_keep_history_and_verify_latest_epoch(self):
        first = self.release(); self.register(first)
        self.intent['review_id'] = 'second-fixture'
        self.intent['pages'][0]['prior_quartet'] = {k: sr.binding(p) for k, p in [('txt', self.text), ('json', self.model), ('notes', self.notes), ('preview', self.preview)]}
        self.intent['pages'][0]['cell_edits'] = [{'row': 0, 'column': 1, 'before': 'Z', 'after': 'Y'}]
        self.intent['pages'][0]['json_patches'] = [{'pointer': '/nodes/0/function', 'before': 'A', 'after': 'AR'}]
        self.stage = self.base / 'stage-two'; self.create()
        second = self.stage / 'publication.json'; sr.publish(self.stage / 'manifest.json', self.acceptance())
        result = self.register(second)
        self.assertEqual(result['release_count'], 2)
        self.assertEqual(len(result['records']), 1)
        self.assertEqual(result['records'][0]['release_id'], 'second-fixture')
        self.assertEqual(self.verify()['records'][0]['current_quartet']['txt'], sr.binding(self.text))
        self.assertTrue(list((self.base / 'registry.json.history').glob('*.json')))

    def test_unregistered_live_successor_cannot_claim_old_review(self):
        pub = self.release(); self.register(pub)
        self.text.write_bytes(self.text.read_bytes().replace(b'AZCD', b'AYCD'))
        with self.assertRaises(ValueError): self.verify()

    def test_target_scope_cannot_be_widened(self):
        pub = self.release()
        with self.assertRaises(ValueError):
            registry.register(self.base / 'registry.json', pub, self.base, self.base / 'other', self.base)

    def exporter(self):
        path = Path(__file__).resolve().parent.parent / 'legacy/ald/repository-export/export_reviewed.py'
        spec = importlib.util.spec_from_file_location('registry_fixture_exporter', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        module.ROOT = self.base; module.EXPORTS = self.target; module.SOURCE = self.base; module.AUDIT = self.base
        return module, path

    def test_exporter_current_and_missing_registry_fail_closed(self):
        pub = self.release(); self.regpath = self.base / 'Source review successor registry.json'
        self.register(pub); exporter, _ = self.exporter()
        self.assertEqual(exporter.source_review_successor_records()[0]['hashes'], [sr.binding(self.text)['sha256']])
        self.regpath.unlink()
        with self.assertRaises(FileNotFoundError): exporter.source_review_successor_records()

    def test_exporter_stale_model_cannot_fall_back_to_old_text_review(self):
        pub = self.release(); self.regpath = self.base / 'Source review successor registry.json'
        self.register(pub); exporter, _ = self.exporter()
        self.model.write_bytes(sr.encode({'nodes': []}))
        with self.assertRaises(ValueError): exporter.source_review_successor_records()

    def test_exporter_receipts_apply_registry_last_without_suppressing_errors(self):
        exporter, path = self.exporter(); tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        receipts = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'receipts')
        self.assertIsInstance(receipts.body[-1], ast.Return)
        self.assertIsInstance(receipts.body[-2], ast.For)
        call = receipts.body[-2].iter
        self.assertIsInstance(call, ast.Call)
        self.assertEqual(call.func.id, 'source_review_successor_records')
        self.assertFalse(any(isinstance(n, ast.Try) for n in ast.walk(receipts.body[-2])))


if __name__ == '__main__': unittest.main()

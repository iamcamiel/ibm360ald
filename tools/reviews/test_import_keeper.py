"""Future full-import preservation fixtures; no live import is executed."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
IMPORTER = HERE.parent/'repository/import_review_records.py'
spec = importlib.util.spec_from_file_location('source_review_keeper_fixture', IMPORTER)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


class KeeperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE)
        self.repo = Path(self.temp.name)

    def tearDown(self):
        assert self.repo.is_relative_to(HERE)
        self.temp.cleanup()

    def put(self, relative, raw=b'fixture'):
        path = self.repo/relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        return path

    def entries(self): return {relative: path for path, relative in module.source_review_repository_keepers(self.repo)}

    def pointer(self):
        quartet = {}
        for kind, relative in {'txt':'ALD/Folder/PAGE.txt', 'json':'json/Folder/PAGE.json',
                               'notes':'notes/Folder/PAGE review notes.txt', 'preview':'notes/Folder/PAGE preview.png'}.items():
            path = self.put(relative)
            quartet[kind] = {'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        doc = {'schema':'source-review-repository-current-v1', 'current_repository_quartet':quartet}
        pointer = self.put('notes/Folder/PAGE source review current.json', json.dumps(doc).encode())
        return pointer, doc

    def test_all_reusable_tools_and_validation_files_are_kept(self):
        wanted = ['tools/reviews/source_review.py', 'tools/reviews/README.txt',
                  'tools/reviews/validation/Result.json', 'tools/repository/import_source_review.py',
                  'tools/repository/test_import_source_review.py']
        for name in wanted: self.put(name)
        self.put('tools/reviews/__pycache__/cache.pyc'); self.put('tools/reviews/ledger.lock')
        self.put('tools/reviews/partial.tmp')
        self.assertEqual(set(self.entries()), set(wanted))

    def test_portable_evidence_fonts_receipts_and_predecessors_keep_exact_bytes(self):
        wanted = ['notes/Source reviews/Evidence/hash/font.ttf',
                  'notes/Source reviews/Evidence/hash/receipt.json',
                  'notes/Source reviews/Evidence/hash/registry.json',
                  'notes/Source reviews/Tool predecessors/old-exporter.py']
        for name in wanted: self.put(name, name.encode())
        actual = self.entries(); self.assertEqual(set(actual), set(wanted))
        for name, path in actual.items(): self.assertEqual(path.read_bytes(), name.encode())

    def test_uniform_socket_tools_survive_a_future_import(self):
        wanted = ['tools/references/build_uniform_socket_listings.py',
                  'tools/references/verify_uniform_socket_listings.py',
                  'tools/references/socket_text_parser.py',
                  'tools/references/audit_socket_ald.py',
                  'tools/references/socket_ald_matching.py',
                  'tools/references/socket_ald_pin_audit.py',
                  'tools/references/socket_ald_reverse.py',
                  'tools/references/socket_ald_identity_adapter.py',
                  'tools/references/socket_ald_reconciliation.py',
                  'tools/reviews/test_register_a1_table.py',
                  'tools/references/investigate_absent_ald_references.py',
                  'tools/references/socket_pin_validation.py',
                  'tools/references/test_uniform_socket_listings.py',
                  'tools/references/README.txt']
        for name in wanted:self.put(name, name.encode())
        self.put('tools/references/__pycache__/cache.pyc')
        self.put('tools/references/temporary-probe.py')
        self.assertEqual(set(self.entries()), set(wanted))

    def test_uniform_socket_dataset_and_its_proof_survive_a_future_import(self):
        wanted = ['json/Socket listings uniform/Socket listings.json',
                  'json/Socket listings uniform/pages/A1 Socket Listing/A1111-01.json',
                  'csv/Socket listings uniform/Portion references.csv',
                  'notes/Socket listings uniform/Build manifest.json',
                  'notes/Reference data/Uniform socket listings/Independent verification.json']
        for name in wanted:self.put(name, name.encode())
        self.assertEqual(set(self.entries()), set(wanted))

    def test_current_pointer_and_preview_included_with_quartet_hash_validation(self):
        pointer, doc = self.pointer()
        self.assertEqual(set(self.entries()), {'notes/Folder/PAGE source review current.json', 'notes/Folder/PAGE preview.png'})

    def test_stale_quartet_hash_blocks_inventory_rebuild(self):
        pointer, doc = self.pointer(); (self.repo/doc['current_repository_quartet']['json']['path']).write_bytes(b'changed')
        with self.assertRaises(AssertionError): self.entries()

    def test_pointer_cannot_preserve_file_outside_expected_branch(self):
        pointer, doc = self.pointer(); doc['current_repository_quartet']['preview']['path'] = '.git/config'
        self.put('.git/config'); pointer.write_bytes(json.dumps(doc).encode())
        with self.assertRaises(AssertionError): self.entries()

    def test_unknown_pointer_schema_is_not_silently_kept(self):
        pointer, doc = self.pointer(); doc['schema'] = 'unknown'; pointer.write_bytes(json.dumps(doc).encode())
        with self.assertRaises(AssertionError): self.entries()

    def test_keeper_is_in_full_import_planning_before_conflict_gate(self):
        tree = ast.parse(IMPORTER.read_text(encoding='utf-8-sig'))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        calls = [n for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'source_review_repository_keepers']
        self.assertEqual(len(calls), 1)
        conflict = next(n for n in ast.walk(main) if isinstance(n, ast.Assert) and 'Independent repository changes' in ast.unparse(n))
        self.assertLess(calls[0].lineno, conflict.lineno)


if __name__ == '__main__': unittest.main()

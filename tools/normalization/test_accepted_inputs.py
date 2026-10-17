"""Compact-current acceptance fixtures; no history or TIFF files required."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import accepted_inputs as A


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


class Fixture:
    def __init__(self, root):
        self.root = root; self.files = {}
        self.model = 'json/Test/XX001.json'; self.text = 'ALD/Test/XX001.txt'; self.notes = 'notes/Test/XX001 review notes.txt'
        self.doc = {'page': 'XX001', 'source_reviewed': True, 'nodes': [], 'nets': []}
        self.put(self.model, encoded(self.doc)); self.put(self.text, b'XX001\n'); self.put(self.notes, b'Current source review\n')
        self.record = {'page': 'XX001', 'scan_reference': {'id': '100', 'relative_path': 'Test/XX001.tif'}, 'status': 'reviewed',
                       'repository': {k: {'path': p, 'sha256': self.files[p]} for k, p in [('json', self.model), ('txt', self.text), ('notes', self.notes)]}}
        self.content = {'files': [{'path': self.model, 'sha256': self.files[self.model], 'role': 'Published page content model'}]}
        self.write()

    def put(self, relative, raw):
        p = self.root / relative; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw)
        self.files[relative] = hashlib.sha256(raw).hexdigest()

    def write(self):
        self.put(A.STATUS, encoded({'schema': 'ald-current-source-checkpoint-v1', 'records': [self.record]}))
        self.put(A.CONTENT, encoded(self.content))
        self.put(A.INVENTORY, encoded({'schema': 'ald-current-repository-inventory-v1', 'files': [{'path': p, 'sha256': h} for p, h in self.files.items() if p != A.INVENTORY]}))

    def load(self):
        return A.load_accepted_inputs(self.root, expected_count=1)


class AcceptedTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).resolve().parents[2] / 'test-temp'
        folder.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder); self.root = Path(self.temp.name); self.f = Fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_current_exact_collection_no_historical_or_scan_io(self):
        accepted = self.f.load()
        self.assertEqual(len(accepted.pages), 1)
        self.assertEqual(accepted.recheck(), {'passed': True, 'files_checked': 6, 'models': 1})
        self.assertEqual(accepted.pages[0]['context']['accepted_page']['provenance_binding']['path'], A.STATUS)
        self.assertFalse((self.root / 'Test/XX001.tif').exists())

    def test_missing_false_or_null_review_literals_are_preserved(self):
        for present, value in [(False, None), (True, False), (True, None), (True, True), (True, 0)]:
            doc = deepcopy(self.f.doc); doc.pop('source_reviewed', None)
            if present: doc['source_reviewed'] = value
            self.f.put(self.f.model, encoded(doc))
            self.f.record['repository']['json']['sha256'] = self.f.files[self.f.model]
            self.f.content['files'][0]['sha256'] = self.f.files[self.f.model]; self.f.write()
            page = self.f.load().pages[0]
            self.assertEqual(page['model'], doc)
            self.assertEqual(page['context']['accepted_page']['source_reviewed_present'], present)
            self.assertEqual('source_reviewed' in page['context']['accepted_page'], present)

    def test_false_or_pending_checkpoint_is_not_accepted(self):
        for value in [False, None, 'pending', 'accepted', True]:
            self.f.record['status'] = value; self.f.write()
            with self.assertRaisesRegex(A.AcceptedInputError, 'not reviewed'): self.f.load()

    def test_changed_model_text_or_notes_fails_closed(self):
        for rel in [self.f.model, self.f.text, self.f.notes]:
            p = self.root / rel; before = p.read_bytes(); p.write_bytes(before + b' ')
            with self.assertRaisesRegex(A.AcceptedInputError, 'Changed input'): self.f.load()
            p.write_bytes(before)

    def test_recheck_detects_changed_globals_and_missing_files(self):
        for rel in [self.f.model, self.f.text, self.f.notes, A.STATUS, A.CONTENT, A.INVENTORY]:
            loaded = self.f.load(); p = self.root / rel; before = p.read_bytes(); p.write_bytes(before + b' ')
            with self.assertRaisesRegex(A.AcceptedInputError, 'Input changed'): loaded.recheck()
            p.write_bytes(before)
        loaded = self.f.load(); (self.root / self.f.model).unlink()
        with self.assertRaisesRegex(A.AcceptedInputError, 'missing/unreadable'): loaded.recheck()

    def test_unsafe_and_case_alias_paths_are_rejected(self):
        for value in ['../outside', 'C:/outside', '/outside', 'json\\XX.json', 'json/../outside.json', './json/p.json', 'json//p.json', 'notes/x:stream']:
            with self.subTest(value=value), self.assertRaises(A.AcceptedInputError): A._relative(value)
        self.f.record['repository']['json']['path'] = 'json/../../outside.json'; self.f.write()
        with self.assertRaisesRegex(A.AcceptedInputError, 'Unsafe'): self.f.load()

    def test_unowned_or_hash_disagreeing_model_is_rejected(self):
        inv = json.loads((self.root / A.INVENTORY).read_text())
        inv['files'] = [f for f in inv['files'] if f['path'] != self.f.model]
        (self.root / A.INVENTORY).write_bytes(encoded(inv))
        with self.assertRaisesRegex(A.AcceptedInputError, 'not owned'): self.f.load()
        self.f.write(); self.f.content['files'][0]['sha256'] = 'f' * 64; self.f.write()
        with self.assertRaisesRegex(A.AcceptedInputError, 'membership/hash differs'): self.f.load()

    def test_exact_membership_not_just_count(self):
        self.f.content['files'].append({'path': 'json/Test/missing.json', 'sha256': 'f' * 64, 'role': 'Published page content model'}); self.f.write()
        with self.assertRaisesRegex(A.AcceptedInputError, 'membership differs'): self.f.load()

    def test_duplicate_or_nonfinite_json_rejected(self):
        for raw in [b'{"a":1,"a":2}', b'{"a":NaN}']:
            with self.assertRaises(A.AcceptedInputError): A._json(raw, 'fixture')

    def test_duplicate_case_inventory_and_duplicate_scan_rejected(self):
        inv = json.loads((self.root / A.INVENTORY).read_text()); inv['files'].append(deepcopy(inv['files'][0])); (self.root / A.INVENTORY).write_bytes(encoded(inv))
        with self.assertRaisesRegex(A.AcceptedInputError, 'Duplicate/case-aliased'): self.f.load()
        self.f.write(); status = json.loads((self.root / A.STATUS).read_text()); status['records'].append(deepcopy(status['records'][0])); self.f.put(A.STATUS, encoded(status))
        inv = {'schema': 'ald-current-repository-inventory-v1', 'files': [{'path': p, 'sha256': h} for p, h in self.f.files.items() if p != A.INVENTORY]}; self.f.put(A.INVENTORY, encoded(inv))
        with self.assertRaisesRegex(A.AcceptedInputError, 'Duplicate source scan'): self.f.load()

    def test_expected_count_is_optional_and_strict(self):
        self.assertEqual(len(A.load_accepted_inputs(self.root).pages), 1)
        with self.assertRaisesRegex(A.AcceptedInputError, 'page count'): A.load_accepted_inputs(self.root, expected_count=2)
        with self.assertRaisesRegex(A.AcceptedInputError, 'Invalid expected'): A.load_accepted_inputs(self.root, expected_count=True)

    def test_uniform_model_reloads_exact_source_view_with_canonical_hash(self):
        from pages import normalize_page
        self.f.doc['source_reviewed'] = False
        normalized = normalize_page(self.f.doc, self.f.model, '100')['data']
        self.f.put(self.f.model, encoded(normalized))
        self.f.record['repository']['json']['sha256'] = self.f.files[self.f.model]
        self.f.content['files'][0]['sha256'] = self.f.files[self.f.model]; self.f.write()
        loaded = self.f.load(); page = loaded.pages[0]
        self.assertEqual(page['model'], self.f.doc)
        self.assertEqual(page['model_sha256'], hashlib.sha256(encoded(normalized)).hexdigest())
        self.assertIs(page['context']['accepted_page']['source_reviewed'], False)
        self.assertEqual(normalize_page(page['model'], page['model_relative'], page['source_scan_id'], context=page['context'])['data'], normalized)


if __name__ == '__main__':
    unittest.main()

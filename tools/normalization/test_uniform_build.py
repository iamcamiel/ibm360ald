"""Build/verify orchestration guards with a tiny deterministic page mapper."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_accepted_inputs import Fixture
import build_uniform_pages as B
import verify_uniform_build as V


def normalize(raw, model_relative, scan_id, context=None):
    return {'data': {'schema': 'fixture', 'page': {'kind': 'ald-diagram'}, 'objects': [], 'nets': [], 'junctions': [],
                     'literal': raw, 'source_status_ref': {'path': 'notes/Source status.json', 'scan_id': str(scan_id)}}}


class BuildTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).resolve().parents[2] / 'test-temp'; folder.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder); self.root = Path(self.temp.name)
        self.repo = self.root / 'repository'; self.repo.mkdir(); self.fixture = Fixture(self.repo)
        self.output = self.root / 'candidate'
        self.patch = patch.dict('sys.modules', pages=SimpleNamespace(normalize_page=normalize, restore_page=lambda x:x['literal'], SCHEMA='fixture'))
        self.patch.start()

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def test_one_current_file_original_path_no_history_and_exact_verify(self):
        result = B.build(self.repo, self.output, 1)
        self.assertEqual(result['counts']['pages'], 1)
        actual = {p.relative_to(self.output).as_posix() for p in self.output.rglob('*') if p.is_file()}
        self.assertEqual(actual, {B.MANIFEST, self.fixture.model})
        manifest = json.loads((self.output / B.MANIFEST).read_text())
        self.assertEqual(manifest['pages'][0]['normalized']['path'], self.fixture.model)
        self.assertTrue(V.verify(self.repo, self.output, 1)['passed'])

    def test_in_repo_existing_or_ancestor_output_rejected(self):
        for output in [self.repo, self.repo / 'new-candidate', self.root]:
            with self.subTest(output=output), self.assertRaises(ValueError): B.build(self.repo, output, 1)
        B.build(self.repo, self.output, 1)
        with self.assertRaisesRegex(ValueError, 'fresh'): B.build(self.repo, self.output, 1)

    def test_candidate_changes_or_unlisted_file_detected(self):
        B.build(self.repo, self.output, 1)
        p = self.output / self.fixture.model; before = p.read_bytes(); p.write_bytes(before + b' ')
        with self.assertRaisesRegex(ValueError, 'output/hash/current projection'): V.verify(self.repo, self.output, 1)
        p.write_bytes(before); (self.output / 'unexpected.txt').write_text('not listed')
        with self.assertRaisesRegex(ValueError, 'unlisted files'): V.verify(self.repo, self.output, 1)

    def test_source_change_during_build_cannot_emit_manifest(self):
        def mutating(raw, model, scan, context=None):
            p = self.repo / self.fixture.model; p.write_bytes(p.read_bytes() + b' ')
            return normalize(raw, model, scan, context)
        with patch.dict('sys.modules', pages=SimpleNamespace(normalize_page=mutating, restore_page=lambda x:x['literal'], SCHEMA='fixture')):
            with self.assertRaisesRegex(ValueError, 'Input changed'): B.build(self.repo, self.output, 1)
        self.assertFalse((self.output / B.MANIFEST).exists())

    def test_resume_replays_current_projection_without_overwriting(self):
        self.output.mkdir(); data = normalize(self.fixture.doc, self.fixture.model, '100')['data']
        B.put(self.output, self.fixture.model, B.page_encoded(data))
        self.assertTrue(B.build(self.repo, self.output, 1, resume=True)['source_recheck']['passed'])
        with self.assertRaisesRegex(ValueError, 'incomplete'): B.build(self.repo, self.output, 1, resume=True)

    def test_resume_changed_incomplete_output_fails_without_replacing(self):
        self.output.mkdir(); p = self.output / self.fixture.model; p.parent.mkdir(parents=True); p.write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError, 'differs from fresh current projection'): B.build(self.repo, self.output, 1, resume=True)
        self.assertEqual(p.read_bytes(), b'wrong'); self.assertFalse((self.output / B.MANIFEST).exists())

    def test_compact_page_json_preserves_facts_and_separate_manifest_format(self):
        data = {'unicode': '◺─✲', 'literal': [None, False, 0, '', {'row': 5}]}
        compact = B.page_encoded(data)
        self.assertEqual(json.loads(compact), data)
        self.assertLess(len(compact), len(B.encoded(data)))
        self.assertEqual(compact.count(b'\n'), 1)
        self.assertEqual(B.page_encoded({'b': 1, 'a': 2}), B.page_encoded({'a': 2, 'b': 1}))

    def update_candidate(self, value):
        raw = B.encoded(value); (self.output / self.fixture.model).write_bytes(raw)
        manifest = json.loads((self.output / B.MANIFEST).read_text())
        manifest['pages'][0]['normalized'].update(sha256=B._sha(raw), bytes=len(raw))
        (self.output / B.MANIFEST).write_bytes(B.encoded(manifest))

    def test_reencode_replays_all_facts_and_changes_only_key_order(self):
        B.build(self.repo, self.output, 1)
        actual = json.loads((self.output / self.fixture.model).read_text())
        self.update_candidate(actual)
        result = B.reencode_current(self.repo, self.output, 1)
        self.assertTrue(result['logical_values_unchanged'])
        self.assertEqual(result['current_pages_replayed'], 1)
        self.assertTrue(V.verify(self.repo, self.output, 1)['passed'])

    def test_reencode_cannot_hide_typed_value_change(self):
        B.build(self.repo, self.output, 1)
        actual = json.loads((self.output / self.fixture.model).read_text()); actual['literal']['source_reviewed'] = 1
        self.update_candidate(actual)
        before = (self.output / self.fixture.model).read_bytes()
        with self.assertRaisesRegex(ValueError, 'logical data differs'): B.reencode_current(self.repo, self.output, 1)
        self.assertEqual((self.output / self.fixture.model).read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

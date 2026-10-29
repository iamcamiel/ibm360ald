"""End-of-build counts use current, content-bound review findings."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_browser_cache as builder
from browser_cache.publication import BuildError, Snapshot, digest


class FindingTests(unittest.TestCase):
    def test_render_discrepancies_count_without_uncertainties(self):
        self.assertTrue(builder.has_findings({}, {
            'uncertainties': [], 'render comparison': {'different cells': 7}}))

    def test_current_uncertainties_and_questions_count(self):
        for field in ('uncertainties', 'format questions'):
            for entry in ({'status': 'unresolved'}, {'status': 'pending'}, {}):
                with self.subTest(field=field, entry=entry):
                    self.assertTrue(builder.has_findings({}, {field: [entry]}))

    def test_resolved_history_normalizations_and_warnings_are_not_findings(self):
        self.assertFalse(builder.has_findings({}, {
            'uncertainties': [{'status': 'resolved'}],
            'format questions': [{'status': 'resolved'}],
            'warnings': [{'code': 'title_frame_path'}],
            'render comparison': {'different cells': 8, 'unresolved different cells': 0,
                                  'rendered': True}}))

    def test_explicit_disclosure_and_failed_render_count(self):
        self.assertTrue(builder.has_findings({'unresolved discrepancies': True}, {}))
        self.assertTrue(builder.has_findings({}, {'render comparison': {'rendered': False}}))
        self.assertTrue(builder.has_findings({}, {
            'publication issues': {'status': 'open', 'summary': 'Wiring review incomplete'}}))
        self.assertFalse(builder.has_findings({}, {
            'publication issues': {'status': 'resolved', 'summary': 'Historical issue'}}))

    def test_unknown_optional_finding_metadata_is_not_reported_clean(self):
        self.assertTrue(builder.has_findings({}, {'render comparison': {'different cells': None}}))
        self.assertTrue(builder.has_findings({}, {'format questions': 'unclassified'}))


class StatisticsTests(unittest.TestCase):
    def test_kind_totals_and_ald_buckets_are_exhaustive(self):
        pages = [{'id': 'old', 'type': 'ald'},
                 {'id': 'clean', 'type': 'ald', 'format': 'v4'},
                 {'id': 'diff', 'type': 'ald', 'format': 'v4'},
                 {'id': 'unknown', 'type': 'ald', 'format': 'v4'}]
        pages += [{'type': kind} for kind in
                  ('card-ald', 'socket-listing', 'miscellaneous', 'cas', 'ros-listing')]
        reviews = {'clean': ({}, {}),
                   'diff': ({}, {'render comparison': {'different cells': 2}}),
                   'unknown': ({}, {'uncertainties': [{'status': 'unresolved'}]})}
        result = builder.page_statistics(pages, lambda page: reviews[page['id']])
        self.assertEqual(result['pageCount'], 9)
        self.assertEqual(result['pagesByKind'], {
            'ald': 4, 'card-ald': 1, 'cas': 1, 'miscellaneous': 1,
            'ros-listing': 1, 'socket-listing': 1})
        self.assertEqual((result['aldV3PageCount'], result['aldV4WithoutFindingsPageCount'],
                          result['aldV4WithFindingsPageCount']), (1, 1, 2))

    def test_empty_catalogue_counts(self):
        result = builder.page_statistics([], lambda page: self.fail('No review expected'))
        self.assertEqual(result['pageCount'], 0)
        self.assertEqual(result['pagesByKind'], {})
        self.assertEqual(result['aldV4WithFindingsPageCount'], 0)

    def test_cli_keeps_stdout_json_and_prints_readable_statistics(self):
        result = builder.page_statistics([{'type': 'ald'}], lambda page: None)
        result.update(catalogueChanged=True, assetsWritten=0,
                      catalogueSha256='example', output='cache')
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(builder, 'build', return_value=result), \
                patch('sys.argv', ['build_browser_cache.py']), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            builder.main()
        self.assertEqual(json.loads(stdout.getvalue()), result)
        for text in ('Total pages: 1', 'ald: 1', 'V3: 1',
                     'V4 without findings: 0', 'V4 with findings: 0'):
            self.assertIn(text, stderr.getvalue())


class BoundReviewTests(unittest.TestCase):
    def test_read_review_is_bound_to_snapshot_and_collector_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'json/review').mkdir(parents=True)
            model = root / 'json/page.json'
            details = root / 'json/review/page.json'
            review = {'uncertainties': [], 'render comparison': {'different cells': 3}}
            model.write_text(json.dumps({'review': {'details': 'review/page.json'}}), encoding='utf8')
            details.write_text(json.dumps(review), encoding='utf8')
            snapshot = Snapshot(root)
            snapshot.read(model)
            signature = digest(snapshot.read(details))
            entry = {'_model': 'json/page.json', '_reviewSignature': [None, signature]}
            self.assertEqual(builder.read_review(entry, root, snapshot)[1], review)
            with self.assertRaisesRegex(BuildError, 'Review changed'):
                builder.read_review({**entry, '_reviewSignature': [None, 'wrong']}, root, snapshot)
            details.write_text('{}', encoding='utf8')
            with self.assertRaisesRegex(BuildError, 'Input changed'):
                builder.read_review(entry, root, snapshot)

    def test_review_reference_cannot_escape_its_model_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'json').mkdir()
            (root / 'outside.json').write_text('{}', encoding='utf8')
            (root / 'json/page.json').write_text(
                json.dumps({'review': {'details': '../outside.json'}}), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'Unsafe review'):
                builder.read_review({'_model': 'json/page.json'}, root, Snapshot(root))


if __name__ == '__main__':
    unittest.main()

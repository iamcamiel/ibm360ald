"""Progress reflects completed work without changing generated payloads."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_progress import Progress
from browser_cache.interactions import enrich_interactions
from browser_cache.publication import BuildError, Publication, Snapshot
import render_all_json


class ProgressTests(unittest.TestCase):
    def test_one_line_per_step_in_place_and_deduplicated(self):
        stream = io.StringIO()
        with Progress('Generating 2604 UTF-8 pages', stream) as progress:
            for done in range(2605):
                progress.update(done, 2604)
        text = stream.getvalue()
        self.assertEqual(text.count('\n'), 1)
        self.assertIn('\rGenerating 2604 UTF-8 pages: 56%', text)
        self.assertTrue(text.endswith('\rGenerating 2604 UTF-8 pages: 100%\n'))
        self.assertEqual(text.count('100%'), 1)
        self.assertEqual(text.count('\r'), 100)

    def test_failed_or_incomplete_step_does_not_report_success(self):
        for exception in (True, False):
            stream = io.StringIO()
            with self.subTest(exception=exception):
                try:
                    with Progress('Building cross-page index', stream) as progress:
                        progress.update(1, 2)
                        if exception:
                            raise ValueError('test')
                        progress.failed = True
                except ValueError:
                    pass
                self.assertNotIn('100%', stream.getvalue())
                self.assertTrue(stream.getvalue().endswith('50% (failed)\n'))

    def test_empty_step_finishes_and_stdout_stays_empty(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with Progress('Empty') as progress:
                progress.update(0, 0)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(stderr.getvalue(), 'Empty: 0%\rEmpty: 100%\n')


class IndexProgressTests(unittest.TestCase):
    def test_progress_monotonic_and_assets_identical_with_real_cross_page_link(self):
        entries = [{'id': 'a', 'page': 'AA001', 'type': 'ald', 'textSha256': 'a'},
                   {'id': 'b', 'page': 'BB001', 'type': 'ald', 'textSha256': 'b'}]
        views = {
            'a': {'nets': [{'id': 'AA001AA4', 'label': 'signal', 'identity': 'a',
                            'destinationPages': ['BB001'], 'sourceReferences': []}], 'blocks': []},
            'b': {'nets': [{'id': 'input', 'label': 'signal', 'identity': 'b',
                            'destinationPages': [], 'sourceReferences': ['AA001AA4']}], 'blocks': []}}
        for entry in entries:
            entry['modelSha256'] = entry['id']
        expected_entries = copy.deepcopy(entries)
        arguments = ({}, {'a': '', 'b': ''}, views)
        expected = enrich_interactions(expected_entries, *arguments,
                                       native_outputs_by_id={'a': ['AA001AA4'], 'b': []})
        events = []
        actual = enrich_interactions(entries, *arguments,
                                     native_outputs_by_id={'a': ['AA001AA4'], 'b': []},
                                     progress=lambda done, total: events.append(done / total))
        self.assertEqual(actual, expected)
        self.assertEqual(entries, expected_entries)
        self.assertEqual(events, sorted(events))
        self.assertEqual((events[0], events[-1]), (0, 1))
        self.assertTrue(any(json.loads(value)['nets'][0].get('links') for value in actual.values()))

    def test_empty_index_reports_completion(self):
        events = []
        self.assertEqual(enrich_interactions([], {}, {}, {},
                         progress=lambda done, total: events.append(done / total)), {})
        self.assertEqual((events[0], events[-1]), (0, 1))


class VerificationProgressTests(unittest.TestCase):
    def test_changed_input_fails_before_catalogue_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.txt'
            source.write_bytes(b'old')
            snapshot = Snapshot(root)
            snapshot.read(source)
            source.write_bytes(b'changed')
            stream = io.StringIO()
            with Publication(root, root / 'cache') as publication:
                with self.assertRaises(BuildError), Progress('Verifying', stream) as progress:
                    publication.publish({'pages': []}, snapshot, progress.update)
            self.assertFalse((root / 'cache/catalogue.json').exists())
            self.assertNotIn('100%', stream.getvalue())
            self.assertIn('(failed)', stream.getvalue())

    def test_both_verification_passes_and_noop_keep_same_catalogue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.txt'
            source.write_bytes(b'data')
            snapshot = Snapshot(root)
            snapshot.read(source)
            events = []
            catalogue = {'schema': 'aldbrowser-catalogue-v1', 'pages': []}
            with Publication(root, root / 'cache') as publication:
                changed, sha = publication.publish(catalogue, snapshot,
                                  lambda done, total: events.append(done / total))
            self.assertTrue(changed)
            self.assertEqual(events, [0.5, 1])
            with Publication(root, root / 'cache') as publication:
                self.assertEqual(publication.publish(catalogue, snapshot), (False, sha))


class RendererProgressTests(unittest.TestCase):
    def test_actual_render_count_and_failure_reporting_preserve_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'notes').mkdir()
            (root / 'json').mkdir()
            (root / 'ALD').mkdir()
            (root / 'notes/Source status.json').write_text('{"records": []}', encoding='utf8')
            (root / 'json/page.json').write_text('{"schema": "ibm360-ald-page-v3"}', encoding='utf8')
            target = root / 'ALD/page.txt'
            target.write_bytes(b'old')
            for failure in (False, True):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr), patch.object(render_all_json, 'render',
                        side_effect=ValueError('invalid model') if failure else None,
                        return_value=b'new'):
                    result = render_all_json.run(root, check=True)
                self.assertEqual(target.read_bytes(), b'old')
                self.assertIn('Generating 1 UTF-8 pages:', stderr.getvalue())
                self.assertEqual(bool(result['failures']), failure)
                self.assertEqual('100%' in stderr.getvalue(), not failure)


if __name__ == '__main__':
    unittest.main()

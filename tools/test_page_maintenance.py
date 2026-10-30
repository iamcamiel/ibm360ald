import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import migrate_pin_annotations as migration
import page_maintenance as maintenance
import render_all_json as rendering


class AnnotationMigrationTests(unittest.TestCase):
    def page(self):
        return {'$schema': maintenance.V4_SCHEMA,
                'blocks': [{'serial': 'AA', 'grid position': '1A', 'pins': [{'side': 'L', 'line': 2, 'pin': None}]}],
                'nets': [{'net number': 'ZZ001AA4', 'nodes': ['blocks/AA/pins/L/2'],
                          'routing': [[[1, 2], [5, 2]]]}]}

    def details(self, marker='3'):
        return {'uncertainties': [{'field': 'blocks/AA/pins/L/2/pin', 'status': 'unresolved',
                                  'visible text': marker, 'kind': 'illegible'}]}

    def test_migration_is_exact_preserves_routes_and_keeps_resolved_evidence(self):
        for marker in ('2', '3', '8', 'L'):
            with self.subTest(marker=marker):
                page, details = self.page(), self.details(marker)
                original = copy.deepcopy((page, details))
                changed, review, moves, blocked = migration.migrate(page, details)
                self.assertEqual(len(blocked), 1)  # Deliberately unanchored fixture route
                self.assertEqual(len(moves), 1)
                self.assertNotIn('pin', changed['blocks'][0]['pins'][0])
                self.assertEqual(changed['nets'][0]['annotations'], [{'at': 'blocks/AA/pins/L/2', 'text': marker}])
                self.assertEqual(changed['nets'][0]['routing'], page['nets'][0]['routing'])
                self.assertEqual(review['uncertainties'][0]['visible text'], marker)
                self.assertEqual(review['uncertainties'][0]['status'], 'resolved')
                self.assertEqual(review['content sha256'], maintenance.content_digest(changed))
                self.assertEqual((page, details), original)
                self.assertEqual(migration.migrate(changed, review)[2], [])

    def test_unknown_membership_and_annotation_conflicts_are_not_guessed(self):
        for mode in ('missing', 'multiple', 'duplicate', 'annotation'):
            page = self.page()
            if mode == 'missing':
                page['nets'] = []
            elif mode == 'multiple':
                page['nets'].append(copy.deepcopy(page['nets'][0]))
            elif mode == 'duplicate':
                page['nets'][0]['nodes'] *= 2
            else:
                page['nets'][0]['annotations'] = [{'at': 'blocks/AA/pins/L/2', 'text': '*'}]
            changed, _, moves, blocked = migration.migrate(page, self.details())
            self.assertEqual(changed['blocks'], page['blocks'])
            self.assertEqual(changed['nets'], page['nets'])
            self.assertEqual(moves, [])
            self.assertGreaterEqual(len(blocked), 1)

    def test_compound_or_established_pin_is_not_reclassified(self):
        for label in ('23', 'B03', 'L3', '3B02'):
            page = self.page()
            page['blocks'][0]['pins'][0]['pin'] = label
            self.assertEqual(migration.migrate(page, self.details())[2:], ([], []))


class RecoverableBatchTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'notes').mkdir()
        path = root / 'ALD/test.txt'
        path.parent.mkdir()
        path.write_bytes(b'old')
        status = {'records': [{'repository': {'txt': {'path': 'ALD/test.txt',
                                                     'sha256': maintenance.sha(b'old')}}}]}
        status_path = root / 'notes/Source status.json'
        status_path.write_bytes(maintenance.encode(status))
        return path, status_path

    def test_exact_backup_status_refresh_and_noop(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, status_path = self.fixture(root)
            result = maintenance.apply_changes(root, [(path, b'old', b'new')], 'test', {})
            receipt = json.loads(Path(result['receipt']).read_bytes())
            self.assertTrue(receipt['completed'])
            self.assertEqual(Path(receipt['files'][0]['preimage']).read_bytes(), b'old')
            self.assertEqual(json.loads(status_path.read_bytes())['records'][0]['repository']['txt']['sha256'], maintenance.sha(b'new'))
            self.assertIsNone(maintenance.apply_changes(root, [(path, b'new', b'new')], 'test', {})['receipt'])

    def test_preflight_prevents_partial_writes_and_stale_status(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, status_path = self.fixture(root)
            before = status_path.read_bytes()
            for expected in (b'stale',):
                with self.assertRaises(ValueError):
                    maintenance.apply_changes(root, [(path, expected, b'new')], 'test', {})
            self.assertEqual(path.read_bytes(), b'old')
            self.assertEqual(status_path.read_bytes(), before)

    def test_failed_second_write_rolls_back_first(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, status_path = self.fixture(root)
            before = status_path.read_bytes()
            original = maintenance.atomic
            failed = False
            def write(target, data):
                nonlocal failed
                if target == status_path and not failed:
                    failed = True
                    raise OSError('simulated write failure')
                return original(target, data)
            with patch.object(maintenance, 'atomic', side_effect=write), self.assertRaises(OSError):
                maintenance.apply_changes(root, [(path, b'old', b'new')], 'test', {})
            self.assertEqual(path.read_bytes(), b'old')
            self.assertEqual(status_path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

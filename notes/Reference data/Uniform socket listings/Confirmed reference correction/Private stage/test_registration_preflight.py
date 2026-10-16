"""Read-only regression checks against independently published stage bindings.

All negative fixtures are in memory. This does not execute registration.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import register_a1_application as app

BASE = Path(__file__).resolve().parent
WORKSPACE = Path('D:/Github/IBM360')
ADAPTER = WORKSPACE/'tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Recorded and recovered UTF8 application current audit.json'
REGISTRY = WORKSPACE/'tmp/ald-text/ald/repository-export/A1 table application registry.json'
EXPORTS = WORKSPACE/'ALD_Visual_Transcriptions'
SOURCE = Path('D:/Reference Materials/IBM 360/IBM_360_ALD')


class PreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter_before = ADAPTER.read_bytes()
        cls.registry_before = REGISTRY.read_bytes() if REGISTRY.exists() else None
        cls.adapter, cls.registry, cls.item = app.prepare(BASE/'Stage manifest.json', BASE/'Publication receipt.json',
            BASE/'Independent acceptance.json', ADAPTER, REGISTRY, WORKSPACE, EXPORTS, SOURCE)

    def guard(self, adapter=None, registry=None):
        return app.validate_registered_applications(REGISTRY, ADAPTER, WORKSPACE, EXPORTS, SOURCE,
            adapter=deepcopy(self.adapter if adapter is None else adapter),
            registry=deepcopy(self.registry if registry is None else registry))

    def test_exact_published_stage_preflight(self):
        self.assertTrue(self.guard()['passed'])

    def test_other_seventy_items_preserved(self):
        original = json.loads(self.adapter_before.decode('utf-8-sig'))
        self.assertEqual(original['pages'], self.adapter['pages'][:-1])
        self.assertEqual(self.item['page'], 'A1232-01')

    def test_historical_arrays_unchanged(self):
        stage = app.read(BASE/'Stage manifest.json')
        for name in ['predecessor_acceptance', 'historical_repository_acceptance']:
            app.checked(stage[name])

    def test_live_auxiliary_scope_is_page_specific(self):
        auxiliary = self.item['current_auxiliary_existing_data']
        self.assertEqual(len(auxiliary), 2)
        self.assertTrue(all(Path(link['path']).is_relative_to(WORKSPACE/'tmp/ald-text/a1') for link in auxiliary))
        self.assertTrue(any(Path(link['path']).name.endswith('columns reference correction.json') for link in auxiliary))
        self.assertTrue(any(Path(link['path']).name.endswith('columns reviewed.json') for link in auxiliary))

    def test_unrelated_shared_table_successor_does_not_invalidate_page(self):
        stage = app.read(BASE/'Stage manifest.json')
        shared_targets = {Path(record['target']).resolve() for record in stage['files']
                          if record['role'] == 'current auxiliary reference mirror'}
        self.assertTrue(shared_targets)
        original = Path.read_bytes
        consulted = []
        def successor_bytes(path):
            if path.resolve() in shared_targets:
                consulted.append(path)
                return b'{"independently_reviewed_unrelated_successor":true}\n'
            return original(path)
        with patch.object(Path, 'read_bytes', successor_bytes):
            self.assertTrue(self.guard()['passed'])
        self.assertEqual(consulted, [], 'Registered page must not read current shared tables')

    def test_missing_registered_item_rejected(self):
        adapter = deepcopy(self.adapter); adapter['pages'].remove(self.item)
        with self.assertRaisesRegex(ValueError, 'missing or changed'): self.guard(adapter=adapter)

    def test_changed_registered_item_rejected(self):
        adapter = deepcopy(self.adapter); adapter['pages'][-1]['current_quartet']['txt']['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'missing or changed'): self.guard(adapter=adapter)

    def test_changed_publication_binding_rejected(self):
        registry = deepcopy(self.registry); registry['entries'][-1]['publication']['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'Stale binding'): self.guard(registry=registry)

    def test_duplicate_registration_rejected(self):
        registry = deepcopy(self.registry); registry['entries'].append(deepcopy(registry['entries'][-1]))
        with self.assertRaisesRegex(ValueError, 'Duplicate/outside'): self.guard(registry=registry)

    def test_no_adapter_or_registry_mutation(self):
        self.assertEqual(ADAPTER.read_bytes(), self.adapter_before)
        self.assertEqual(REGISTRY.read_bytes() if REGISTRY.exists() else None, self.registry_before)

    def test_missing_mandatory_registry_rejected(self):
        absent = BASE/'intentionally-absent-registry.json'
        self.assertFalse(absent.exists())
        with self.assertRaisesRegex(ValueError, 'registry is missing'):
            app.validate_registered_applications(absent, ADAPTER, WORKSPACE, EXPORTS, SOURCE,
                                                  adapter=self.adapter)


if __name__ == '__main__': unittest.main()

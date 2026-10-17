"""Reviewed source corrections must preserve the uniform canonical page format."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'normalization'))
import test_compact_source_import as fixtures
import compact_source_import as M
import source_review as sr
import current_checkpoint
import read_page
from pages import normalize_page, renormalize_page, SCHEMA


class UniformImportTests(unittest.TestCase):
    def setUp(self):
        fixtures.CompactImportTests.setUp(self)
        raw=sr.read_json(self.paths['json'])
        self.paths['json'].write_bytes(sr.encode(normalize_page(raw,'json/Test/PAGE.json','1')['data']))
        status=sr.read_json(self.status)
        status['records'][0]['repository']['json']['sha256']=sr.digest(self.paths['json'].read_bytes())
        self.status.write_bytes(sr.encode(status))
        fixtures.CompactImportTests.save_inventory(self)

    tearDown=fixtures.CompactImportTests.tearDown

    def plan(self):
        return M.prepare(self.repo,self.stage/'manifest.json',self.acceptance_path,self.base)

    def test_corrected_model_remains_uniform_and_retry_is_idempotent(self):
        before={p:p.read_bytes()for p in self.repo.rglob('*')if p.is_file()}
        plan=self.plan()
        self.assertEqual({p:p.read_bytes()for p in before},before)
        M.apply(plan)
        canonical=sr.read_json(self.paths['json'])
        self.assertEqual(canonical['schema'],SCHEMA)
        source=read_page.source_view(canonical)
        self.assertEqual(source['nodes'][0]['function'],'A')
        self.assertEqual(source['untouched'],{'truth':True,'false_value':False,'null_value':None})
        self.assertFalse((self.repo/'notes/Source reviews').exists())
        self.assertEqual(self.plan()['changes'],{})
        self.assertTrue(current_checkpoint.load_checkpoint(self.repo,inventory=sr.read_json(self.inventory)).report()['passed'])

    def test_different_current_semantics_rejected_after_valid_representation(self):
        canonical=sr.read_json(self.paths['json']);raw=read_page.source_view(canonical)
        raw['nodes'][0]['unit']='U99ZZ'
        self.paths['json'].write_bytes(sr.encode(renormalize_page(raw,canonical)))
        status=sr.read_json(self.status)
        status['records'][0]['repository']['json']['sha256']=sr.digest(self.paths['json'].read_bytes())
        self.status.write_bytes(sr.encode(status))
        fixtures.CompactImportTests.save_inventory(self)
        with self.assertRaisesRegex(ValueError,'different current semantics'):
            self.plan()


if __name__=='__main__':unittest.main()

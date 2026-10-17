"""Strict reader dispatch and detached legacy-view regression checks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import types
import sys
import unittest
from unittest.mock import patch
import read_page as reader

class ReaderTests(unittest.TestCase):
    def test_legacy_deepcopy_preserves_types_presence_order(self):
        raw={"nodes":[{"id":"AA","pins":[{"pin":None,"triangle":False}],"a":0}],"empty":[]}
        got=reader.view(raw)
        self.assertEqual(got,raw);self.assertIsNot(got,raw)
        got['nodes'][0]['pins'][0]['triangle']=True
        self.assertFalse(raw['nodes'][0]['pins'][0]['triangle'])
    def test_uniform_dispatch_is_detached(self):
        uniform={'schema':reader.SCHEMA};legacy={'nodes':[]}
        mod=types.ModuleType('pages');mod.restore_page=lambda doc:legacy
        with patch.dict(sys.modules,{'pages':mod}):got=reader.view(uniform)
        self.assertEqual(got,legacy);self.assertIsNot(got,legacy)
    def test_unknown_uniform_schema_rejected(self):
        for schema in ['ibm360-ald-page-v1','ibm360-ald-page-v99']:
            with self.assertRaisesRegex(ValueError,'Unsupported'):reader.loads(json.dumps({'schema':schema}))
    def test_duplicate_keys_nested_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):reader.loads('{"nodes":[{"pin":null,"pin":"B02"}]}')
    def test_nonfinite_rejected(self):
        for value in ['NaN','Infinity','-Infinity']:
            with self.assertRaises(ValueError):reader.loads('{"x":'+value+'}')
    def test_top_level_type_rejected(self):
        for value in ['[]','null','false','0','"x"']:
            with self.assertRaises(ValueError):reader.loads(value)
    def test_utf8_bom_read(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'page.json';p.write_bytes(b'\xef\xbb\xbf'+json.dumps({'page':'AP001','pin':'B08✲'},ensure_ascii=False).encode())
            self.assertEqual(reader.read(p)['pin'],'B08✲')
    def test_input_type_rejected(self):
        with self.assertRaises(TypeError):reader.loads({})
    def test_runtime_paths_are_portable(self):
        self.assertEqual([p.as_posix() for p in reader.runtime_paths(Path('REPO'))],['REPO/tools/normalization/'+n for n in reader.RUNTIME_FILES])
if __name__=='__main__':unittest.main()

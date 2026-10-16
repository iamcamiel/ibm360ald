from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import refresh_inventory as R


class GuardedInventory(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/'tmp');self.w=Path(self.temp.name);self.repo=self.w/'repo'
        self.file=self.repo/'ALD/XX/XX001.txt';self.file.parent.mkdir(parents=True);self.file.write_bytes(b'old')
        self.other=self.repo/'notes/other.txt';self.other.parent.mkdir(parents=True);self.other.write_bytes(b'unchanged')
        self.manifest=self.repo/'notes/Repository records manifest.json';self.manifest.write_bytes(R.encode({'files':[{'path':str(p.relative_to(self.repo).as_posix()),'sha256':R.digest(p.read_bytes())} for p in [self.file,self.other]]}))
        self.old=self.manifest.read_bytes();self.file.write_bytes(b'new')
        self.allow=self.w/'allow.json';self.document={'schema':'repository-inventory-allowlist-v1','baseline_manifest':R.sr.binding(self.manifest),'entries':[{'path':'ALD/XX/XX001.txt','before_sha256':R.digest(b'old'),'after_sha256':R.digest(b'new'),'authority':'Reviewed source publication.'}]};self.save()
    def tearDown(self):self.temp.cleanup()
    def save(self):self.allow.write_bytes(R.encode(self.document))
    def prepare(self):return R.prepare(self.repo,self.allow)
    def test_default_plan_does_not_change_inventory(self):
        prepared=self.prepare();self.assertEqual(self.manifest.read_bytes(),self.old);self.assertEqual(len(prepared[0]['authorized_changes']),1)
    def test_success_preserves_exact_predecessor(self):
        p=self.prepare();report=R.apply(p);self.assertTrue(report['passed']);self.assertEqual(p[4].read_bytes(),self.old)
        self.assertEqual(self.file.read_bytes(),b'new');self.assertEqual(self.other.read_bytes(),b'unchanged')
    def test_unexplained_delta_rejected(self):
        self.other.write_bytes(b'changed');self.assertRaises(ValueError,self.prepare)
    def test_incorrect_before_hash_rejected(self):
        self.document['entries'][0]['before_sha256']='bad';self.save();self.assertRaises(ValueError,self.prepare)
    def test_incorrect_current_hash_rejected(self):
        self.document['entries'][0]['after_sha256']='bad';self.save();self.assertRaises(ValueError,self.prepare)
    def test_stale_inventory_rejected(self):
        self.manifest.write_bytes(self.old+b' ');self.assertRaises(ValueError,self.prepare)
    def test_exact_new_file_can_be_added(self):
        p=self.repo/'tools/new.py';p.parent.mkdir();p.write_bytes(b'print(1)')
        self.document['entries'].append({'path':'tools/new.py','before_sha256':None,'after_sha256':R.digest(p.read_bytes()),'authority':'Authorized generic tool.'});self.save()
        self.assertEqual(len(self.prepare()[0]['authorized_changes']),2)
    def test_changes_after_plan_are_rejected(self):
        p=self.prepare();self.file.write_bytes(b'newer');self.assertRaises(ValueError,R.apply,p);self.assertEqual(self.manifest.read_bytes(),self.old)
    def test_failed_atomic_replace_restores_inventory(self):
        p=self.prepare();actual=R.sr.atomic_write;failed=False
        def fail(path,raw):
            nonlocal failed
            actual(path,raw)
            if Path(path)==self.manifest and not failed:failed=True;raise OSError('injected')
        with patch.object(R.sr,'atomic_write',side_effect=fail):self.assertRaises(OSError,R.apply,p)
        self.assertEqual(self.manifest.read_bytes(),self.old)


if __name__=='__main__':unittest.main()

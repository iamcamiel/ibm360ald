"""Current status adapters and no-archive inventory fixtures."""
from pathlib import Path
import hashlib,json,sys,unittest
from unittest.mock import patch
import refresh_inventory as R
import import_source_review as I
import test_refresh_inventory as fixtures

class CompactInventory(fixtures.GuardedInventory):
    def setUp(self):
        super().setUp()
        self.status=self.repo/'notes/Source status.json'
        doc={'schema':'ald-current-source-checkpoint-v1','records':[{'page':'XX001','scan_reference':{'id':'1','relative_path':'XX/Missing.tif'},'status':'reviewed',
            'repository':{'txt':{'path':'ALD/XX/XX001.txt','sha256':R.digest(b'new')}}}]}
        self.status.write_bytes(R.encode(doc))
        self.document['entries'].append({'path':'notes/Source status.json','before_sha256':None,'after_sha256':R.digest(self.status.read_bytes()),'authority':'Current source checkpoint authorized.'});self.save()

    # Override historical-specific assumptions; inherited hash/failure fixtures
    # still exercise the same compact guards and rollback behavior.
    def test_default_plan_does_not_change_inventory(self):
        prepared=self.prepare();self.assertEqual(self.manifest.read_bytes(),self.old)
        self.assertEqual(prepared[0]['retention'],'compact-current');self.assertIsNone(prepared[4])
        new=json.loads(prepared[3]);self.assertNotIn('scoped_inventory_reviews',new)
        self.assertIn('current_inventory_review',new)
    def test_success_preserves_exact_predecessor(self):
        report=R.apply(self.prepare());self.assertTrue(report['passed'])
        self.assertFalse((self.repo/'notes/Source reviews/Inventory predecessors').exists())
        self.assertEqual(self.file.read_bytes(),b'new')
    def test_exact_new_file_can_be_added(self):
        p=self.repo/'tools/new.py';p.parent.mkdir();p.write_bytes(b'print(1)')
        self.document['entries'].append({'path':'tools/new.py','before_sha256':None,'after_sha256':R.digest(p.read_bytes()),'authority':'Authorized generic tool.'});self.save()
        self.assertEqual(len(self.prepare()[0]['authorized_changes']),3)
    def test_checkpoint_change_after_plan_fails(self):
        prepared=self.prepare();self.status.write_bytes(self.status.read_bytes()+b' ')
        with self.assertRaises(ValueError):R.apply(prepared)
        self.assertEqual(self.manifest.read_bytes(),self.old)
    def test_unowned_checkpoint_is_not_ambiently_adopted(self):
        self.document['entries']=self.document['entries'][:1];self.save()
        with self.assertRaisesRegex(ValueError,'Checkpoint inventory'):self.prepare()
    def test_explicit_legacy_retention_still_supported(self):
        prepared=R.prepare(self.repo,self.allow,preserve_history=True)
        self.assertEqual(prepared[0]['retention'],'legacy-history');self.assertIsNotNone(prepared[4])
    def test_compact_import_refuses_implicit_history_before_opening_registry(self):
        with self.assertRaisesRegex(ValueError,'Compact Source status'):
            I.build_plan(self.w/'missing-registry',self.w,self.repo,self.w/'exports',self.w/'scans')
        # Explicit old workflow remains available; this reaches the registry
        # function rather than silently choosing compact or inventing evidence.
        with patch.object(I.registry_api,'accepted_successors',side_effect=ValueError('legacy reached')):
            with self.assertRaisesRegex(ValueError,'legacy reached'):
                I.build_plan(self.w/'missing-registry',self.w,self.repo,self.w/'exports',self.w/'scans',legacy_history=True)

    def test_exact_explicit_already_removed_record_can_be_retired(self):
        self.other.unlink()
        self.document['entries'].append({'path':'notes/other.txt','action':'remove','before_sha256':R.digest(b'unchanged'),
            'after_sha256':None,'authority':'User authorized repository clutter removal.'});self.save()
        prepared=self.prepare();after=json.loads(prepared[3])
        self.assertNotIn('notes/other.txt',{x['path']for x in after['files']})
        self.assertEqual([c['action']for c in prepared[0]['authorized_changes'] if c.get('action')=='remove'],['remove'])
        R.apply(prepared);self.assertFalse(self.other.exists())

    def test_missing_unlisted_or_wrong_preimage_retirement_is_rejected(self):
        self.other.unlink()
        with self.assertRaisesRegex(ValueError,'Missing recorded'):self.prepare()
        self.document['entries'].append({'path':'notes/other.txt','action':'remove','before_sha256':'bad',
            'after_sha256':None,'authority':'Explicit cleanup.'});self.save()
        with self.assertRaisesRegex(ValueError,'retirement predecessor'):self.prepare()

if __name__=='__main__':unittest.main()

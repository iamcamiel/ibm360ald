from pathlib import Path
from copy import deepcopy
import hashlib,json,tempfile,unittest
import current_checkpoint as C

def encode(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()

class CheckpointTests(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).resolve().parents[3]/'tmp/current-checkpoint-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.temp.name)
        self.doc={'schema':C.SCHEMA,'records':[]}
        for index in range(2):
            text=f'ALD/Test/P{index}.txt';p=self.root/text;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'ALD source\n')
            repository={'txt':{'path':text,'sha256':sha(p.read_bytes())}}
            if index==0:
                model='json/Test/P0.json';p=self.root/model;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(encode({'page':'P0','nodes':[]}))
                repository['json']={'path':model,'sha256':sha(p.read_bytes())}
            self.doc['records'].append({'page':'REPEATED_PRINTED_ID','scan_reference':{'id':str(index),'relative_path':f'Test/Missing{index}.tif'},'status':'reviewed','repository':repository})
        self.save()
    def tearDown(self):self.temp.cleanup()
    def save(self):
        p=self.root/C.DEFAULT_PATH;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(encode(self.doc));return p
    def load(self,**kwargs):return C.load_checkpoint(self.root,**kwargs)

    def test_current_bindings_text_only_and_no_scan_history_reads(self):
        result=self.load();self.assertEqual(result.report()['current_files'],{'txt':2,'json':1,'notes':0})
        self.assertFalse(result.report()['history_replayed']);self.assertFalse(result.report()['scan_bytes_read'])
        self.assertEqual(result.report()['records'],2);self.assertTrue(result.recheck()['passed'])
    def test_explicit_status_is_not_inherited_from_model(self):
        self.doc['records'][0]['status']='unreviewed';self.save()
        self.assertEqual(self.load().report()['reviewed_records'],1)
        self.doc['records'][0]['status']=True;self.save()
        with self.assertRaisesRegex(ValueError,'review status'):self.load()
    def test_changed_current_source_and_late_drift_rejected(self):
        loaded=self.load();p=self.root/'ALD/Test/P0.txt';p.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'bytes changed'):loaded.recheck()
        with self.assertRaisesRegex(ValueError,'hash differs'):self.load()
    def test_changed_checkpoint_and_missing_source_rejected(self):
        loaded=self.load();p=self.root/C.DEFAULT_PATH;p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'bytes changed'):loaded.recheck()
        p=self.root/'ALD/Test/P0.txt';p.unlink()
        with self.assertRaisesRegex(ValueError,'Missing current'):self.load()
    def test_duplicate_scan_and_artifact_case_alias_rejected(self):
        old=deepcopy(self.doc)
        self.doc['records'][1]['scan_reference']['id']='0';self.save()
        with self.assertRaisesRegex(ValueError,'Duplicate current scan'):self.load()
        self.doc=old;self.doc['records'][1]['repository']['txt']=deepcopy(self.doc['records'][0]['repository']['txt']);self.save()
        with self.assertRaisesRegex(ValueError,'Duplicate artifact'):self.load()
    def test_path_traversal_absolute_backslash_and_unnormalized_paths(self):
        for value in ('.','../x','/x','C:/x','notes\\x','notes//x','./notes/x'):
            with self.subTest(value=value),self.assertRaises(ValueError):C.relative(value)
    def test_no_self_hash_and_model_text_identity_guard(self):
        self.doc['records'][0]['repository']['notes']={'path':C.DEFAULT_PATH,'sha256':'a'*64};self.save()
        with self.assertRaisesRegex(ValueError,'self-bound'):self.load()
        del self.doc['records'][0]['repository']['notes']
        self.doc['records'][0]['repository']['json']['path']='json/Test/Wrong.json';self.save()
        with self.assertRaises(ValueError):self.load()
    def test_inventory_optional_but_exact_when_supplied(self):
        items=[]
        for record in self.doc['records']:items.extend(deepcopy(list(record['repository'].values())))
        items.append({'path':C.DEFAULT_PATH,'sha256':sha(self.save().read_bytes())})
        inv={'files':items};self.assertTrue(self.load(inventory=inv).report()['passed'])
        inv['files'][0]['sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'inventory differs'):self.load(inventory=inv)
    def test_optional_working_targets_are_not_opened_or_mutated(self):
        self.doc['records'][0]['working_quartet']={k:{'path':'ALD_Visual_Transcriptions/MISSING.'+k,'sha256':'a'*64}for k in ('txt','json','notes','preview')};self.save()
        self.assertTrue(self.load().report()['passed'])
        self.assertFalse((self.root/'ALD_Visual_Transcriptions').exists())
    def test_historical_pointer_fields_and_duplicate_json_keys_rejected(self):
        self.doc['records'][0]['prior_review']={'path':'MISSING'};self.save()
        with self.assertRaisesRegex(ValueError,'historical'):self.load()
        self.save().write_bytes(b'{"schema":"x","schema":"y","records":[]}')
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.load()
    def test_current_corrections_and_unresolved_short_notes(self):
        self.doc['records'][0]['significant_corrections']=['Human confirmed D06.']
        self.doc['records'][0]['unresolved']=['Faint source identifier remains unreadable.'];self.save()
        self.assertEqual(self.load().records[0]['unresolved'],self.doc['records'][0]['unresolved'])
        self.doc['records'][0]['unresolved']={'historical_chain':[]};self.save()
        with self.assertRaisesRegex(ValueError,'short text arrays'):self.load()

    def test_inventory_coverage_cannot_silently_omit_a_current_source(self):
        items=[deepcopy(link)for r in self.doc['records']for link in r['repository'].values()]
        self.doc['records'].pop();self.save()
        items.append({'path':C.DEFAULT_PATH,'sha256':sha(self.save().read_bytes())})
        with self.assertRaisesRegex(ValueError,'TXT membership'):self.load(inventory={'files':items})

if __name__=='__main__':unittest.main()

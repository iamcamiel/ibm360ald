"""New generic-stage compact mirror fixtures; no old registries/receipt trees."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest,subprocess

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reviews'))
import source_review as sr
import test_source_review as source_fixtures
import compact_source_import as M
import current_checkpoint
import compact_metadata


class CompactImportTests(unittest.TestCase):
    def setUp(self):
        source_fixtures.StageTests.setUp(self)
        self.repo=self.base/'repo';self.repo.mkdir()
        raw=sr.read_json(self.model);raw['review_notes']=[{'before':'old OCR','after':'current literal'}]
        raw['untouched'].update(false_value=False,null_value=None)
        self.model.write_bytes(sr.encode(raw));self.prior['json']=sr.binding(self.model)
        self.intent['pages'][0]['prior_quartet']=self.prior
        self.intent['pages'][0]['notes_append']='Exception: {"note":"Reviewed current source-role exception retained."}'
        clean,notes=compact_metadata.prune_history(raw)
        self.paths={'txt':self.repo/'ALD/Test/PAGE.txt','json':self.repo/'json/Test/PAGE.json','notes':self.repo/'notes/Test/PAGE review notes.txt'}
        for p in self.paths.values():p.parent.mkdir(parents=True,exist_ok=True)
        self.paths['txt'].write_bytes(self.text.read_bytes());self.paths['json'].write_bytes(sr.encode(clean))
        self.paths['notes'].write_text('Correction: {"field":"old","before":"R","after":"B"}\nUnresolved: {"field":"other","status":"retained current uncertainty"}\n',encoding='utf-8')
        self.status=self.repo/current_checkpoint.DEFAULT_PATH
        self.status.write_bytes(sr.encode({'schema':current_checkpoint.SCHEMA,'records':[{'page':'PAGE','scan_reference':{'id':'1','relative_path':'original.tif'},'status':'reviewed',
            'repository':{k:{'path':p.relative_to(self.repo).as_posix(),'sha256':sr.digest(p.read_bytes())}for k,p in self.paths.items()}}]}))
        self.content=self.repo/M.CONTENT;self.content.write_bytes(sr.encode({'files':[{'path':self.paths['json'].relative_to(self.repo).as_posix(),'sha256':sr.digest(self.paths['json'].read_bytes()),'role':'Published page content model'}],
            'managed_files':{self.paths['json'].relative_to(self.repo).as_posix():sr.digest(self.paths['json'].read_bytes())}}))
        self.provenance=self.repo/M.PROVENANCE;self.provenance.write_bytes(sr.encode({'exported':[{'page':'PAGE','source_scan_id':'1','source_relative':'original.tif',
            'destination':str(self.paths['txt']),'notes_destination':str(self.paths['notes']),'text_sha256':sr.digest(self.paths['txt'].read_bytes()),'notes_sha256':sr.digest(self.paths['notes'].read_bytes()),'review_record':current_checkpoint.DEFAULT_PATH}],
            'managed_files':{str(p):sr.digest(p.read_bytes())for k,p in self.paths.items()if k in ('txt','notes')}}))
        self.inventory=self.repo/M.INVENTORY
        self.inventory.write_bytes(sr.encode({'files':[{'path':p.relative_to(self.repo).as_posix(),'sha256':sr.digest(p.read_bytes())}for p in [*self.paths.values(),self.status,self.content,self.provenance]]}))
        source_fixtures.StageTests.save_intent(self);sr.create_stage(self.intent_path,self.stage)
        self.acceptance_path=source_fixtures.StageTests.acceptance(self)
        sr.publish(self.stage/'manifest.json',self.acceptance_path)

    def tearDown(self):source_fixtures.StageTests.tearDown(self)
    def plan(self):return M.prepare(self.repo,self.stage/'manifest.json',self.acceptance_path,self.base)
    def save_inventory(self):
        doc=sr.read_json(self.inventory)
        for e in doc['files']:e['sha256']=sr.digest((self.repo/e['path']).read_bytes())
        self.inventory.write_bytes(sr.encode(doc))

    def test_dryrun_readonly_then_compact_import_current_scope(self):
        before={p:p.read_bytes()for p in self.repo.rglob('*')if p.is_file()};plan=self.plan()
        self.assertEqual({p:p.read_bytes()for p in before},before)
        self.assertEqual(plan['report']['planned_writes'],7)
        result=M.apply(plan);self.assertTrue(result['write'])
        self.assertEqual(self.paths['txt'].read_bytes(),self.text.read_bytes())
        model=sr.read_json(self.paths['json']);self.assertEqual(model['nodes'][0]['function'],'A');self.assertNotIn('review_notes',model)
        notes=self.paths['notes'].read_text(encoding='utf-8')
        self.assertIn('retained current uncertainty',notes)
        self.assertIn('Reviewed current source-role exception retained',notes)
        corrections=[json.loads(line.partition(':')[2])for line in notes.splitlines()if line.startswith('Correction:')]
        self.assertIn({'field':'old','before':'R','after':'B'},corrections);self.assertIn('/nodes/0/function',notes)
        self.assertEqual(model['untouched'],{'truth':True,'false_value':False,'null_value':None})
        self.assertFalse(any(p.suffix=='.png'for p in self.repo.rglob('*')))
        self.assertFalse((self.repo/'notes/Source reviews').exists())
        self.assertEqual(sr.read_json(self.provenance)['exported'][0]['review_record'],current_checkpoint.DEFAULT_PATH)
        self.assertTrue(current_checkpoint.load_checkpoint(self.repo,inventory=sr.read_json(self.inventory)).report()['passed'])
        again=self.plan();self.assertTrue(again['report']['idempotent_retry']);self.assertEqual(again['changes'],{})
        self.assertEqual(M.apply(again)['written_files'],0)

    def test_stale_txt_predecessor_rejected_even_if_checkpoint_resigned(self):
        self.paths['txt'].write_bytes(b'different accepted current text')
        doc=sr.read_json(self.status);doc['records'][0]['repository']['txt']['sha256']=sr.digest(self.paths['txt'].read_bytes());self.status.write_bytes(sr.encode(doc));self.save_inventory()
        with self.assertRaisesRegex(ValueError,'TXT is not'):self.plan()

    def test_answered_pointer_question_cleared_by_current_stage(self):
        with self.paths['notes'].open('a',encoding='utf-8')as stream:
            stream.write('Unresolved: {"field":"/nodes/0/function","status":"old physical-page question"}\n')
        doc=sr.read_json(self.status);doc['records'][0]['repository']['notes']['sha256']=sr.digest(self.paths['notes'].read_bytes())
        self.status.write_bytes(sr.encode(doc));self.save_inventory()
        M.apply(self.plan())
        notes=self.paths['notes'].read_text(encoding='utf-8')
        self.assertNotIn('old physical-page question',notes)
        self.assertIn('retained current uncertainty',notes)

    def test_unresolved_notes_follow_current_data_and_rebuild_unreadable_fields(self):
        raw={'nodes':[{'unit':'U03AF','pin':'B\ufffd8','source_driver_unresolved':True}],'a/b':{'~field':'\ufffd'}}
        existing='\n'.join('Unresolved: '+json.dumps(item)for item in [
            {'field':'/nodes/0/unit','status':'answered'}, {'field':'/removed','status':'removed'},
            {'field':'/nodes/0/pin','status':'still unreadable'},
            {'field':'/nodes/0/source_driver_unresolved','status':'explicit current flag'},
            {'note':'free-form unresolved context'}])
        clean,rendered=M._notes_after(raw,existing,[])
        items=[json.loads(line.partition(':')[2])for line in rendered.decode().splitlines()if line.startswith('Unresolved:')]
        self.assertFalse(any(x.get('status')in ('answered','removed')for x in items))
        self.assertTrue(any(x.get('status')=='explicit current flag'for x in items))
        self.assertTrue(any(x.get('note')=='free-form unresolved context'for x in items))
        self.assertEqual(sum(x.get('field')=='/nodes/0/pin'for x in items),1)
        self.assertTrue(any(x.get('field')=='/a~1b/~0field'for x in items))

    def test_before_model_semantic_difference_rejected(self):
        doc=sr.read_json(self.paths['json']);doc['nodes'][0]['unit']='U99ZZ';self.paths['json'].write_bytes(sr.encode(doc))
        status=sr.read_json(self.status);status['records'][0]['repository']['json']['sha256']=sr.digest(self.paths['json'].read_bytes());self.status.write_bytes(sr.encode(status));self.save_inventory()
        with self.assertRaisesRegex(ValueError,'different current semantics'):self.plan()

    def test_existing_importer_cli_defaults_to_dryrun_and_requires_explicit_write(self):
        script=Path(__file__).with_name('import_source_review.py')
        command=[sys.executable,'-B','-X','utf8',str(script),'--repo',str(self.repo),'--workspace',str(self.base),
                 '--source-root',str(self.base),'--compact-stage',str(self.stage/'manifest.json'),'--acceptance',str(self.acceptance_path)]
        old=self.paths['txt'].read_bytes()
        dry=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',check=True)
        self.assertFalse(json.loads(dry.stdout)['write']);self.assertEqual(self.paths['txt'].read_bytes(),old)
        written=subprocess.run(command+['--write'],capture_output=True,text=True,encoding='utf-8',check=True)
        self.assertTrue(json.loads(written.stdout)['write']);self.assertEqual(self.paths['txt'].read_bytes(),self.text.read_bytes())
        self.assertFalse((self.repo/'notes/Source reviews').exists())

    def test_independent_acceptance_failure_and_unpublished_stage_rejected(self):
        before=self.acceptance_path.read_bytes();doc=sr.read_json(self.acceptance_path);doc['passed']=False;self.acceptance_path.write_bytes(sr.encode(doc))
        with self.assertRaisesRegex(ValueError,'did not pass'):self.plan()
        self.acceptance_path.write_bytes(before);(self.stage/'publication.json').unlink()
        with self.assertRaises(FileNotFoundError):self.plan()

    def test_publication_claim_tamper_rejected(self):
        p=self.stage/'publication.json';doc=sr.read_json(p);doc['pages'][0]['eligible']=False;p.write_bytes(sr.encode(doc))
        with self.assertRaisesRegex(ValueError,'artifact claims'):self.plan()

    def test_export_scan_mismatch_not_adopted(self):
        doc=sr.read_json(self.provenance);doc['exported'][0]['source_relative']='other.tif';self.provenance.write_bytes(sr.encode(doc));self.save_inventory()
        with self.assertRaisesRegex(ValueError,'scan/page reference'):self.plan()

    def test_source_identity_and_path_aliases_fail_closed(self):
        doc=sr.read_json(self.status);doc['records'][0]['scan_reference']['relative_path']='other.tif';self.status.write_bytes(sr.encode(doc));self.save_inventory()
        with self.assertRaisesRegex(ValueError,'exactly one current page/scan'):self.plan()
        with self.assertRaises(ValueError):M.safe_target(self.repo,'ALD/../outside.txt')

    def test_symlink_resolution_guard_without_platform_link_privileges(self):
        alternate=self.repo/'alias.txt';alternate.write_bytes(self.paths['txt'].read_bytes());actual=Path.resolve
        def alias(path,*args,**kwargs):
            if path==self.paths['txt']:return alternate
            return actual(path,*args,**kwargs)
        with patch.object(Path,'resolve',alias):
            with self.assertRaisesRegex(ValueError,'aliases another path'):self.plan()

    def test_changed_input_between_prepare_and_commit_rejected(self):
        plan=self.plan();before=self.paths['json'].read_bytes();self.paths['txt'].write_bytes(b'changed later')
        with self.assertRaises(ValueError):M.apply(plan)
        self.assertEqual(self.paths['json'].read_bytes(),before)

    def test_write_failure_after_replace_rolls_back_without_archive(self):
        plan=self.plan();before={p:p.read_bytes()for p in plan['changes']};actual=sr.atomic_write;failed=False
        def fail(path,raw):
            nonlocal failed
            actual(path,raw)
            if Path(path)==self.content and not failed:failed=True;raise OSError('injected after replacement')
        with patch.object(sr,'atomic_write',side_effect=fail):
            with self.assertRaises(OSError):M.apply(plan)
        self.assertEqual({p:p.read_bytes()for p in before},before)
        self.assertFalse((self.repo/'notes/Source reviews').exists())

    def test_concurrent_target_is_preserved_while_other_owned_writes_roll_back(self):
        plan=self.plan();before={p:p.read_bytes()for p in plan['changes']};actual=sr.atomic_write;failed=False
        def fail(path,raw):
            nonlocal failed
            actual(path,raw)
            if Path(path)==self.content and not failed:
                failed=True;self.paths['json'].write_bytes(b'concurrent different owner');raise OSError('injected')
        with patch.object(sr,'atomic_write',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'Concurrent target preserved'):M.apply(plan)
        self.assertEqual(self.paths['json'].read_bytes(),b'concurrent different owner')
        for path,raw in before.items():
            if path!=self.paths['json']:self.assertEqual(path.read_bytes(),raw)

if __name__=='__main__':unittest.main()

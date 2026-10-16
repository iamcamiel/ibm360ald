"""Private fixtures for bounded accepted-source mirroring transactions."""
from copy import deepcopy
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import import_source_review as M


class ScopedMirror(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/'tmp')
        self.w=Path(self.temp.name);self.repo=self.w/'repo';self.exports=self.w/'exports';self.source=self.w/'sources'
        self.audit=self.w/'tmp/ald-text/ald/repository-export';self.audit.mkdir(parents=True)
        for p in [self.repo,self.exports,self.source]:p.mkdir()
        self.sourcefile=self.source/'XX Group/XX001 TEST.tif';self.write(self.sourcefile,b'original image')
        self.registry=self.audit/'registry.json'
        stage=self.w/'stage';self.stage=stage
        self.old={};self.new={};prior={};before={};after={};current={}
        for kind,name,a,z in [('txt','XX001 TEST.txt',b'OLD\n',b'NEW\n'),('json','XX001 TEST.json',b'{"nodes": [], "value": 1}\n',b'{"nodes": [], "value": 2}\n'),('notes','XX001 TEST review notes.txt',b'OLD NOTES\n',b'NEW NOTES\n'),('preview','XX001 TEST preview.png',b'old preview',b'new preview')]:
            oldpath=stage/('before-'+name);newpath=stage/name;live=self.exports/name
            self.write(oldpath,a);self.write(newpath,z);self.write(live,z)
            prior[kind]={'path':str(live),'sha256':M.digest(a)};before[kind]=M.sr.binding(oldpath);after[kind]=M.sr.binding(newpath);current[kind]=M.sr.binding(live)
            self.old[kind]=a;self.new[kind]=z
        self.manifest=stage/'manifest.json';self.write(self.manifest,M.encode({'records':[{'page':'XX001','prior_quartet':prior,'before_saved':before,'staged_quartet':after}]}))
        self.publication=stage/'publication.json';self.write(self.publication,M.encode({'manifest':M.sr.binding(self.manifest)}))
        self.write(self.registry,M.encode({'releases':[{'publication':M.sr.binding(self.publication)}]}))
        self.proof=self.w/'old review.json';self.write(self.proof,b'{"accepted": true}\n')
        self.txt=self.repo/'ALD/XX Group/XX001 TEST.txt';self.model=self.repo/'json/XX Group/XX001 TEST.json';self.notes=self.repo/'notes/XX Group/XX001 TEST review notes.txt'
        self.write(self.txt,self.old['txt']);self.write(self.model,self.old['json']);self.write(self.notes,str(self.proof).encode()+b'\n'+self.old['notes'])
        entry={'page':'XX001','source_relative':'XX Group/XX001 TEST.tif','transcription_source':str(self.exports/'XX001 TEST.txt'),'destination':str(self.txt),'notes_destination':str(self.notes),'text_sha256':M.digest(self.old['txt']),'notes_sha256':M.digest(self.notes.read_bytes()),'review_record':str(self.proof)}
        baseline={'exported':[entry],'managed_files':{str(self.txt):entry['text_sha256'],str(self.notes):entry['notes_sha256']},'conflicts':[]}
        self.write(self.audit/'export plan.json',M.encode(baseline));self.write(self.audit/'last export manifest.json',M.encode(baseline));self.write(self.repo/'notes/Reviewed export provenance.json',M.encode(baseline))
        key=self.model.relative_to(self.repo).as_posix();content={'files':[{'path':key,'role':'Published page content model','sha256':M.digest(self.old['json'])}],'managed_files':{key:M.digest(self.old['json'])}}
        self.write(self.repo/'notes/Content data manifest.json',M.encode(content))
        records={'files':[{'path':p.relative_to(self.repo).as_posix(),'sha256':M.digest(p.read_bytes()),'role':'Repository file'} for p in [self.txt,self.model,self.notes,self.repo/'notes/Reviewed export provenance.json',self.repo/'notes/Content data manifest.json']]}
        # A known unrelated inventory delta must not get silently accepted.
        self.write(self.repo/'tools/unrelated.py',b'changed');records['files'].append({'path':'tools/unrelated.py','sha256':'historical','role':'Repository file'})
        self.write(self.repo/'notes/Repository records manifest.json',M.encode(records))
        self.write(self.source/'ALD Scan Order.csv',('newpath,newname,path,scan_timestamp\n"'+str(self.sourcefile)+'",XX001 TEST.tif,old.tif,2014\n').encode())
        exporter=self.audit/'export_reviewed.py';self.write(exporter,b"def note_content(source,txt,meta,row,previous,following,proof):\n return (proof+'\\n').encode()+txt.with_name(txt.stem+' review notes.txt').read_bytes()\n")
        self.record={'page':'XX001','release_id':'test','receipt':str(self.publication.relative_to(self.w)),'text_path':str(self.exports/'XX001 TEST.txt'),'source_path':str(self.sourcefile),'source':M.sr.binding(self.sourcefile),'current_quartet':current,'publication':M.sr.binding(self.publication),'manifest':M.sr.binding(self.manifest),'independent_acceptance':M.sr.binding(self.publication)}
        self.verified={'passed':True,'registry':M.sr.binding(self.registry),'records':[self.record],'preservation_files':[M.sr.binding(p) for p in [self.registry,self.manifest,self.publication]]}
        self.mock=patch.object(M.registry_api,'accepted_successors',return_value=self.verified);self.mock.start()
    def tearDown(self):self.mock.stop();self.temp.cleanup()
    def write(self,p,raw):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    def plan(self):return M.build_plan(self.registry,self.w,self.repo,self.exports,self.source)
    def test_dry_run_is_read_only_and_scope_is_bounded(self):
        old=self.txt.read_bytes();report,changes,guards=self.plan()
        self.assertEqual(self.txt.read_bytes(),old);self.assertEqual(len(report['pages']),1)
        self.assertNotIn(self.repo/'tools/unrelated.py',changes)
        content=M.read(changes[self.repo/'notes/Repository records manifest.json'])
        self.assertEqual(next(x for x in content['files'] if x['path']=='tools/unrelated.py')['sha256'],'historical')
    def test_success_updates_quartets_and_exact_notes_export(self):
        report,changes,guards=self.plan();M.apply_plan(report,changes,guards,self.w/'history')
        self.assertEqual(self.txt.read_bytes(),self.new['txt']);self.assertEqual(self.model.read_bytes(),self.new['json'])
        self.assertEqual(self.notes.read_bytes(),self.record['receipt'].encode()+b'\n'+self.new['notes'])
        self.assertEqual((self.repo/'notes/Reviewed export provenance.json').read_bytes(),(self.audit/'last export manifest.json').read_bytes())
        self.assertEqual(self.proof.read_bytes(),b'{"accepted": true}\n')
    def test_stale_repository_preimage_is_rejected(self):
        self.txt.write_bytes(b'unknown');self.assertRaises(ValueError,self.plan)
    def test_stale_baseline_pair_is_rejected(self):
        p=self.audit/'export plan.json';d=M.read(p.read_bytes());d['exported'][0]['review_record']='other';p.write_bytes(M.encode(d))
        self.assertRaises(ValueError,self.plan)
    def test_guard_rechecks_before_any_write(self):
        report,changes,guards=self.plan();self.sourcefile.write_bytes(b'changed image')
        self.assertRaises(ValueError,M.apply_plan,report,changes,guards,self.w/'history')
        self.assertFalse((self.w/'history').exists());self.assertEqual(self.txt.read_bytes(),self.old['txt'])
    def test_late_failure_rolls_back_all_writes(self):
        report,changes,guards=self.plan();before={p:p.read_bytes() if p.exists() else None for p in changes};actual=M.sr.atomic_write
        def fail(path,raw):
            if Path(path)==self.repo/'notes/Content data manifest.json':raise OSError('injected failure')
            return actual(path,raw)
        with patch.object(M.sr,'atomic_write',side_effect=fail):self.assertRaises(OSError,M.apply_plan,report,changes,guards,self.w/'history')
        for p,old in before.items():self.assertEqual(p.read_bytes() if p.exists() else None,old,str(p))
    def test_receipt_failure_rolls_back(self):
        report,changes,guards=self.plan();before=self.txt.read_bytes();actual=M.sr.atomic_write
        def fail(path,raw):
            if Path(path).name=='receipt.json':raise OSError('injected receipt failure')
            return actual(path,raw)
        with patch.object(M.sr,'atomic_write',side_effect=fail):self.assertRaises(OSError,M.apply_plan,report,changes,guards,self.w/'history')
        self.assertEqual(self.txt.read_bytes(),before)
    def test_atomic_failure_after_replacement_rolls_back_that_target(self):
        report,changes,guards=self.plan();before=self.txt.read_bytes();actual=M.sr.atomic_write;failed=False
        def fail(path,raw):
            nonlocal failed
            result=actual(path,raw)
            if Path(path)==self.txt and not failed:
                failed=True;raise OSError('post-replace verification failure')
            return result
        with patch.object(M.sr,'atomic_write',side_effect=fail):self.assertRaises(OSError,M.apply_plan,report,changes,guards,self.w/'history')
        self.assertEqual(self.txt.read_bytes(),before)
    def test_registry_validation_failure_is_not_ignored(self):
        with patch.object(M.registry_api,'accepted_successors',side_effect=ValueError('bad registry')):self.assertRaises(ValueError,self.plan)
    def test_unknown_page_selection_rejected(self):
        self.assertRaises(ValueError,M.build_plan,self.registry,self.w,self.repo,self.exports,self.source,['XX999'])
    def test_second_import_is_idempotent(self):
        report,changes,guards=self.plan();M.apply_plan(report,changes,guards,self.w/'history')
        report,changes,guards=self.plan();self.assertFalse(changes)


if __name__=='__main__':unittest.main()

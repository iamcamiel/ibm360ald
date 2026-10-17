"""Catalogue classification regressions using independent uniform fixtures."""
from copy import deepcopy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import build_current_card_catalog as builder
import verify_current_card_catalog as verifier
import test_verify_uniform_socket_listings as uniform_fixtures


def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CatalogueClassificationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=uniform_fixtures.VerificationTests('test_valid_mixed_endings_bom_continuation_and_diagnostics')
        self.fixture.setUp();self.repo=self.fixture.repo;self.output=self.fixture.base/'catalogue'
        self.nodes=[
            {'id':'AA','card_type':'3308','portion':'A1','function':'A','unit':'T03AA','location':'A-A1A2','grid':'1A','pins':[]},
            {'id':'AB','card_type':'0000','portion':'B1','function':'OR','unit':'T03AB','location':'A-A1B2','pins':[]},
            {'id':'AC','card_type':'0000','portion':'00','function':'SERV','unit':'GROUND','symbol_only':True,'pins':[]},
            {'id':'AD','card_type':'3308','portion':'A1','function':'A','annotation_only':True,'pins':[]},
            {'id':'AE','card_type':'','function':'OR','annotation_block':True,'pins':[]},
            {'id':'AF','card_type':'DOT','function':'OR','pins':[]}]
        self.model={'page':'MA905','nodes':self.nodes,
            # Both historical paths contain a readable conflicting copy. Neither
            # is a source for listings; the uniform continuation owns one record.
            'board':'02A-A1','records':[{'sockets':['A2'],'card_type':'3308','part_number':'5809999','kind':'CONTINUATION'}]}
        self.model_rel='json/MA Misc/MA905 TEST.json';self.text_rel='ALD/MA Misc/MA905 TEST.txt'
        self.put(self.model_rel,encoded(self.model));self.put(self.text_rel,b'Accepted ALD fixture\n')
        self.fixture.accepted.append({'destination':'Z:/original checkout/'+self.text_rel,'text_sha256':sha(self.repo/self.text_rel),
            'page':'MA905','source_scan_id':'3','source_relative':'MA Misc/MA905 TEST.tif'})
        self.put('notes/Reviewed export provenance.json',encoded({'exported':self.fixture.accepted}))
        legacy='json/A1 Socket Listing/Legacy duplicate.json';self.put(legacy,encoded({'board':'02A-A1','records':self.model['records']}))
        content={'files':[{'path':self.model_rel,'sha256':sha(self.repo/self.model_rel),'role':'Published page content model'},
            {'path':legacy,'sha256':sha(self.repo/legacy),'role':'Accepted existing A1 board model or source-column table'}]}
        self.put('notes/Content data manifest.json',encoded(content))
        for name in ['build_current_card_catalog.py','verify_current_card_catalog.py','verify_uniform_socket_listings.py','current_card_identity.py']:
            self.put('tools/references/'+name,Path(__file__).with_name(name).read_bytes())
        self.sync_uniform()

    def tearDown(self):self.fixture.tearDown()
    def put(self,relative,raw):
        path=self.repo/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    def sync_uniform(self):
        self.fixture.write();shutil.copytree(self.fixture.data,self.repo,dirs_exist_ok=True)
    def build(self):
        with patch('sys.argv',['build','--repo',str(self.repo),'--output',str(self.output)]),contextlib.redirect_stdout(io.StringIO()):builder.main()
    def manifest(self):return verifier.read(self.output/'notes/Card types current/Build manifest.json')
    def card(self,number):return verifier.read(self.output/f'json/Card types current/{number}.json')
    def rebound(self,path,value):
        path=self.output/path;path.write_bytes(encoded(value));m=self.manifest()
        for f in m['files']:
            if f['path']==path.relative_to(self.output).as_posix():f['sha256']=sha(path)
        (self.output/'notes/Card types current/Build manifest.json').write_bytes(encoded(m))

    def test_complete_uniform_coverage_without_legacy_or_continuation_duplicates(self):
        self.build();result=verifier.verify(self.repo,self.output);card=self.card('3308')
        self.assertEqual(result['physical_card_records'],1);self.assertEqual(result['listing_records'],1)
        self.assertEqual(len(card['listing_records']),1);r=card['listing_records'][0]
        self.assertEqual(r['record_id'],'1:0:1');self.assertEqual(r['part_number'],'5803308')
        self.assertEqual(r['physical_sockets'],['A2']);self.assertEqual(r['sockets'],['A2T'])
        self.assertEqual(card['listing_kinds_observed'],['SINGLE CARD'])
        self.assertEqual({s['scan_id']for s in r['source_spans']},{'1','2'})
        self.assertEqual(r['references'][0]['printed_portions'],['A1','B1'])

    def test_explicit_annotations_excluded_but_real_0000_kept(self):
        self.build();result=verifier.verify(self.repo,self.output)
        self.assertEqual([x['node']for x in self.card('0000')['diagram_occurrences']],['AB'])
        self.assertEqual([x['node']for x in self.card('3308')['diagram_occurrences']],['AA'])
        self.assertEqual(result['annotation_nodes_excluded'],3)
        excluded=verifier.read(self.output/'notes/Card types current/Excluded annotation nodes.json')
        self.assertEqual({x['node']for x in excluded['observations']},{'AC','AD','AE'})
        self.assertTrue(all(x['source_model_sha256']==sha(self.repo/self.model_rel)for x in excluded['observations']))

    def test_unknown_width_not_inferred_from_card_label(self):
        f=self.fixture;f.record['kind']='unspecified';f.record['kind_literal']='CARD (WIDTH NOT PRINTED HERE)'
        f.index['counts']['record_kinds']={'unspecified':1};f.pages[0]['records'][0]=deepcopy(f.record)
        for row in f.csvrows:row[3]='unspecified'
        self.sync_uniform();self.build();verifier.verify(self.repo,self.output)
        r=self.card('3308');self.assertEqual(r['physical_card_widths_observed'],[])
        self.assertIsNone(r['listing_records'][0]['kind']);self.assertEqual(r['listing_records'][0]['kind_literal'],'CARD (WIDTH NOT PRINTED HERE)')

    def test_duplicate_uniform_id_rejected(self):
        path=self.repo/builder.UNIFORM_DATA;doc=verifier.read(path);doc['records'].append(deepcopy(doc['records'][0]));self.put(builder.UNIFORM_DATA,encoded(doc))
        m=verifier.read(self.repo/builder.UNIFORM_MANIFEST)
        for f in m['files']:
            if f['path']==builder.UNIFORM_DATA:f['sha256']=sha(path)
        self.put(builder.UNIFORM_MANIFEST,encoded(m))
        with self.assertRaisesRegex(ValueError,'Duplicate uniform'):self.build()

    def test_changed_accepted_socket_text_rejected(self):
        target=self.repo/self.fixture.pages[1]['source']['text_path'];target.write_bytes(b'changed\n')
        with self.assertRaisesRegex(ValueError,'changed uniform input'):self.build()

    def test_changed_dataset_hash_rejected(self):
        path=self.repo/builder.UNIFORM_DATA;path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'Changed source'):self.build()

    def test_rebound_missing_listing_fails_independent_verification(self):
        self.build();card=self.card('3308');card['listing_records']=[]
        card['listing_kinds_observed']=[];card['physical_card_widths_observed']=[]
        self.rebound('json/Card types current/3308.json',card)
        with self.assertRaisesRegex(ValueError,'omits physical listings'):verifier.verify(self.repo,self.output)

    def test_rebound_wrong_listing_source_evidence_fails(self):
        self.build();card=self.card('3308');card['listing_records'][0]['source_spans'][0]['literal']='wrong'
        self.rebound('json/Card types current/3308.json',card)
        with self.assertRaisesRegex(ValueError,'fields/evidence'):verifier.verify(self.repo,self.output)

    def test_rebound_duplicate_listing_fails(self):
        self.build();card=self.card('3308');card['listing_records'].append(deepcopy(card['listing_records'][0]));self.rebound('json/Card types current/3308.json',card)
        with self.assertRaisesRegex(ValueError,'duplicate physical'):verifier.verify(self.repo,self.output)

    def test_changed_uniform_source_after_build_fails(self):
        self.build();p=self.repo/self.fixture.pages[0]['source']['text_path'];p.write_bytes(b'changed\n')
        with self.assertRaisesRegex(ValueError,'Uniform independent'):verifier.verify(self.repo,self.output)

    def test_missing_declared_uniform_input_fails(self):
        self.build();m=self.manifest();m['source_inputs']=[x for x in m['source_inputs']if x['path']!=builder.UNIFORM_DATA]
        (self.output/'notes/Card types current/Build manifest.json').write_bytes(encoded(m))
        with self.assertRaisesRegex(ValueError,'input inventory'):verifier.verify(self.repo,self.output)

    def test_rebound_annotation_in_physical_catalogue_fails(self):
        self.build();card=self.card('0000');fake=deepcopy(card['diagram_occurrences'][0]);fake['node']='AC';fake['node_pointer']='/nodes/2';card['diagram_occurrences'].append(fake);self.rebound('json/Card types current/0000.json',card)
        with self.assertRaisesRegex(ValueError,'annotation physical'):verifier.verify(self.repo,self.output)

    def test_changed_content_model_fails(self):
        self.build();self.put(self.model_rel,encoded({'page':'MA905','nodes':[]}))
        with self.assertRaisesRegex(ValueError,'Changed catalogue/source'):verifier.verify(self.repo,self.output)


if __name__=='__main__':unittest.main()

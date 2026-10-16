from pathlib import Path
import json
import tempfile
import unittest
import audit_socket_ald as audit

class AuditAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.repo=Path(self.temp.name).resolve()
    def tearDown(self):self.temp.cleanup()
    def fixture(self,scan='1',scan_page='AP001',model_page='AP001'):
        name=scan_page+' TEST';text=self.repo/'ALD/Folder'/(name+'.txt');model=self.repo/'json/Folder'/(name+'.json')
        text.parent.mkdir(parents=True,exist_ok=True);model.parent.mkdir(parents=True,exist_ok=True)
        text.write_bytes(b'accepted text\r\n')
        node={'id':'AA','location':'B-E1K6T','card_type':'4191','portion':'03','printed_card_portion':'419103','pins':[]}
        model.write_bytes(audit.encoded({'page':model_page,'nodes':[node]}))
        accepted={'destination':str(text),'text_sha256':audit.sha(text.read_bytes()),'source_scan_id':scan,
                  'source_relative':'Folder/'+name+'.tif'}
        content={'path':model.relative_to(self.repo).as_posix(),'sha256':audit.sha(model.read_bytes()),'role':'Published page content model'}
        return accepted,content,node
    def listing(self,page='AP001'):
        return {'id':'listing1','board':'02B-E1','sockets':['K6T','K7'],'physical_sockets':['K6','K7'],
                'card_type':'4191','kind':'double_card','part_number':'5804191',
                'header_source':{'page':'A1111-01','scan_id':'7'},
                'references':[{'page':page,'portions':['03']}]}
    def test_bound_raw_node_adapted_without_mutation(self):
        a,c,node=self.fixture();wrappers,pages,bindings,issues=audit.load_ald(self.repo,{'exported':[a]},{'files':[c]})
        self.assertEqual(wrappers[0]['node'],node);self.assertEqual(len(bindings),2);self.assertEqual(issues,[])
        results,absent=audit.match_all([self.listing()],wrappers,{'AP001'})
        self.assertEqual(results[0]['classification'],'exact');self.assertEqual(absent,{})
        self.assertNotIn('_socket_ald_identity',wrappers[0])
    def test_stale_text_or_model_rejected(self):
        a,c,_=self.fixture();Path(a['destination']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Changed accepted input'):audit.load_ald(self.repo,{'exported':[a]},{'files':[c]})
        a,c,_=self.fixture();c['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Changed accepted input'):audit.load_ald(self.repo,{'exported':[a]},{'files':[c]})
    def test_model_page_conflict_is_coverage_issue_not_exact(self):
        a,c,_=self.fixture(model_page='AP041')
        wrappers,_,_,issues=audit.load_ald(self.repo,{'exported':[a]},{'files':[c]})
        self.assertEqual(len(issues),1)
        results,_=audit.match_all([self.listing()],wrappers,{'AP001'})
        self.assertNotEqual(results[0]['classification'],'exact')
    def test_unavailable_model_and_unavailable_page_are_distinct(self):
        records=[self.listing('AP001'),dict(self.listing('JA001'),id='listing2')]
        results,absent=audit.match_all(records,[],{'AP001'})
        self.assertEqual([r['classification'] for r in results],['model_unavailable','page_unavailable'])
        self.assertEqual(absent,{'JA001':1})
    def test_separate_scan_variants_retained(self):
        a,c,_=self.fixture(scan_page='AP001-01');b,d,_=self.fixture(scan='2',scan_page='AP001-02')
        wrappers,_,_,_=audit.load_ald(self.repo,{'exported':[a,b]},{'files':[c,d]})
        results,_=audit.match_all([self.listing()],wrappers,{'AP001'})
        self.assertEqual(results[0]['classification'],'multiple_exact')
        self.assertEqual({m['binding']['scan_id'] for m in results[0]['matches']},{'1','2'})
    def test_duplicate_model_and_unknown_acceptance_rejected(self):
        a,c,_=self.fixture()
        with self.assertRaisesRegex(ValueError,'Duplicate page model'):audit.load_ald(self.repo,{'exported':[a]},{'files':[c,c]})
        with self.assertRaisesRegex(ValueError,'without accepted text'):audit.load_ald(self.repo,{'exported':[]},{'files':[c]})
    def test_csv_keeps_literal_leading_zero_portion(self):
        result=list(audit.claims_from([self.listing()]))[0]
        self.assertEqual(result['portion'],'03');self.assertEqual(result['sockets'],['K6T','K7'])
        raw=audit.csv_bytes([{'portion':result['portion']}],['portion'])
        self.assertIn(b'03',raw)

    def test_transitive_inputs_preserved_and_conflicting_epochs_rejected(self):
        source={'path':'ALD/listing.txt','sha256':'a'*64}
        tool={'path':'tools/parser.py','sha256':'b'*64}
        merged=audit.merge_input_bindings([source],[source,tool])
        self.assertEqual(merged,{source['path']:source,tool['path']:tool})
        with self.assertRaisesRegex(ValueError,'Conflicting input epochs'):
            audit.merge_input_bindings([source],[dict(source,sha256='c'*64)])

    def test_every_record_including_non_portion_entries_has_disposition(self):
        listing=self.listing();cable=dict(self.listing(),id='cable',kind='cable',references=[],pin_references=[{}])
        rows=audit.record_inventory([listing,cable],[{'classification':'missing_block','claim':list(audit.claims_from([listing]))[0]}])
        self.assertEqual([r['classification'] for r in rows],['portion_claims_checked','connector_pin_references_inventoried'])
        self.assertEqual(rows[0]['outstanding_claims'],1)
        with self.assertRaisesRegex(ValueError,'every listed portion'):
            audit.record_inventory([listing],[])

    def test_every_node_has_forward_or_reverse_coverage(self):
        a,c,_=self.fixture();wrappers,models,_,_=audit.load_ald(self.repo,{'exported':[a]},{'files':[c]})
        forward,_=audit.match_all([self.listing()],wrappers,{'AP001'})
        from socket_ald_reverse import audit_reverse
        reverse=audit_reverse([self.listing()],wrappers,forward)
        rows=audit.node_inventory(wrappers,forward,reverse)
        self.assertEqual(rows[0]['classification'],'forward_exact_hit')
        with self.assertRaisesRegex(ValueError,'Unaccounted ALD node'):
            audit.node_inventory(wrappers,[],{'results':[]})
        pages,bindings=audit.page_inventory(self.repo,{'exported':[a]},models)
        self.assertEqual(pages[0]['nodes_field_status'],'present');self.assertEqual(pages[0]['node_count'],1)
        self.assertEqual(len(bindings),1)

if __name__=='__main__':unittest.main()

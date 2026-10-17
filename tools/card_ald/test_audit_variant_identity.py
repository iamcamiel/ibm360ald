"""Exact aliases, source-pointer multiplicity and accepted-review inheritance."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,tempfile,unittest
import audit_card_uses as A
import collect_card_variants as C
def encode(v):return(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class IdentityCoverage(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.model=self.root/'json/XX/XX001.json';self.txt=self.root/'ALD/XX/XX001.txt'
        self.nodes=[];boxes=[]
        for portion,pin,out in [('A1','D04','B03'),('B1','B05','D02')]:
            ports=[{'side':'input','pin':pin,'triangle':False,'row':1},{'side':'output','pin':out,'triangle':True,'row':3}]
            self.nodes.append({'id':None,'card':'1234'+portion,'function':'A','unit':'U03AF','location':'A-A1J6','pins':deepcopy(ports)})
            boxes.append({'portion':portion,'function':'A','circuit_identifier':'U03AF','ports':[dict(id='i1'if p['side']=='input'else'o1',**p)for p in ports]})
        self.doc={'page':'XX001','source_reviewed':True,'nodes':self.nodes,'nets':[]}
        self.definition=self.root/'definition.json';self.put(self.definition,{'card_type':'1234','boxes':boxes,'power_contacts':{},'variants':[],'nets':[]})
        self.txt.parent.mkdir(parents=True);self.txt.write_text('accepted fixture source\n')
        self.catalog=self.root/'json/Card types current/1234.json'
        self.cat={'card_type':'1234','diagram_occurrences':[{'page':'XX001','node':None,'node_pointer':f'/nodes/{i}','source_text':'ALD/XX/XX001.txt','portion':p}for i,p in enumerate(['A1','B1'])]}
        self.publish()
    def tearDown(self):self.temp.cleanup()
    def put(self,p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(encode(value))
    def publish(self):
        self.put(self.model,self.doc);self.put(self.catalog,self.cat)
        prov=self.root/'notes/Reviewed export provenance.json';content=self.root/'notes/Content data manifest.json'
        self.put(prov,{'exported':[{'destination':str(self.txt),'text_sha256':sha(self.txt)}]})
        self.put(content,{'files':[{'path':'json/XX/XX001.json','sha256':sha(self.model),'role':'Published page content model'}]})
        self.put(self.root/'notes/Card types current/Build manifest.json',{'source_binding':{'reviewed_export_provenance_sha256':sha(prov),'content_data_manifest_sha256':sha(content)},'source_pages':{'ALD/XX/XX001.txt':{'model':'json/XX/XX001.json','model_sha256':sha(self.model),'text_sha256':sha(self.txt)}}})
    def audit(self):return A.audit('1234',self.root,self.definition)
    def collect(self):return C.collect('1234',self.definition,self.root,publication_policy='complete-witnesses')
    def test_two_anonymous_legacy_aliases_are_each_audited_and_witnessed(self):
        before=self.model.read_bytes();audit=self.audit();variants=self.collect()
        self.assertEqual(audit['summary']['occurrences'],2);self.assertEqual({o['node_pointer']for o in audit['occurrences']},{'/nodes/0','/nodes/1'})
        self.assertEqual(audit['identity_coverage']['catalogue_observations'],2);self.assertEqual(audit['identity_coverage']['catalogue_coverage_issues'],0)
        self.assertEqual(audit['summary']['coverage_limitations'],2) # Anonymous IDs cannot certify named wires.
        self.assertEqual(variants['counts']['occurrences'],2);self.assertEqual(variants['counts']['complete_field_observation_witnesses'],1)
        self.assertEqual({n['node_pointer']for n in variants['canonical_pattern_witnesses'][0]['nodes']},{'/nodes/0','/nodes/1'})
        self.assertEqual(self.model.read_bytes(),before)
    def test_part_and_printed_aliases_are_supported(self):
        self.nodes[0]['part']=self.nodes[0].pop('card');self.nodes[1]['printed_card_portion']=self.nodes[1].pop('card');self.publish()
        self.assertEqual(self.audit()['summary']['occurrences'],2);self.assertEqual(self.collect()['counts']['occurrences'],2)
    def test_explicit_false_and_none_are_never_overwritten(self):
        for value in [False,None]:
            with self.subTest(value=value):
                self.nodes[0]['source_reviewed']=value;self.publish();audit=self.audit();variants=self.collect()
                self.assertIs(audit['occurrences'][0]['source_reviewed'],value)
                self.assertTrue(any(r['field']=='source_review_acceptance'for r in audit['review']))
                self.assertEqual(variants['counts']['complete_field_observation_witnesses'],0)
    def test_unbound_page_true_does_not_confer_review(self):
        (self.root/'notes/Card types current/Build manifest.json').unlink()
        audit=self.audit();variants=self.collect()
        self.assertFalse(any(o['source_review_inherited']for o in audit['occurrences']))
        self.assertEqual(audit['summary']['source_uncertainties'],2);self.assertEqual(variants['counts']['complete_field_observation_witnesses'],0)
    def test_stale_txt_or_global_acceptance_fails_closed(self):
        self.txt.write_text('changed fixture source')
        for call in [self.audit,self.collect]:
            with self.assertRaisesRegex(ValueError,'changed'):call()
        self.txt.write_text('accepted fixture source\n');self.publish()
        (self.root/'notes/Reviewed export provenance.json').write_text('{}')
        for call in [self.audit,self.collect]:
            with self.assertRaisesRegex(ValueError,'stale'):call()
    def test_conflicting_alias_never_selected_or_hidden_by_clean_report(self):
        self.nodes[0]['part']='1234B1';self.publish();audit=self.audit();variants=self.collect()
        self.assertTrue(any(r['field']=='source_identity'for r in audit['review']))
        self.assertGreater(audit['summary']['source_uncertainties'],0);self.assertTrue(variants['coverage_issues'])
        self.assertEqual(variants['counts']['complete_field_observation_witnesses'],0)
    def test_wrong_explicit_pointer_never_uses_other_id(self):
        self.nodes[0]['id']='AA';self.cat['diagram_occurrences'][0].update(node='AA',node_pointer='/nodes/99');self.publish()
        self.assertTrue(any(r['field']=='catalog_coverage'for r in self.audit()['review']))
        self.assertTrue(self.collect()['coverage_issues'])
    def test_pointer_optional_id_mismatch_is_coverage_uncertainty(self):
        self.nodes[0]['id']='AA';self.cat['diagram_occurrences'][0]['node']='BB';self.publish()
        self.assertGreater(self.audit()['identity_coverage']['catalogue_coverage_issues'],0)
    def test_unique_non_null_id_fallback_remains_compatible(self):
        self.nodes[0]['id']='AA';self.cat['diagram_occurrences'][0].update(node='AA');self.cat['diagram_occurrences'][0].pop('node_pointer');self.publish()
        self.assertEqual(self.audit()['identity_coverage']['catalogue_coverage_issues'],0)
    def test_anonymous_missing_pointer_is_not_guessed(self):
        self.cat['diagram_occurrences'][0].pop('node_pointer');self.publish()
        self.assertGreater(self.audit()['identity_coverage']['catalogue_coverage_issues'],0)
    def test_duplicate_catalogue_rows_are_not_set_collapsed(self):
        self.cat['diagram_occurrences'].append(deepcopy(self.cat['diagram_occurrences'][0]));self.publish();audit=self.audit()
        self.assertEqual(audit['identity_coverage']['catalogue_observations'],3)
        self.assertGreater(audit['identity_coverage']['catalogue_coverage_issues'],0)
    def test_extra_source_occurrence_is_reported_even_when_catalogue_omits_it(self):
        extra=deepcopy(self.nodes[0]);extra['id']='CC';self.nodes.append(extra);self.publish();audit=self.audit()
        self.assertEqual(audit['summary']['occurrences'],3);self.assertGreater(audit['identity_coverage']['catalogue_coverage_issues'],0)
    def test_duplicate_non_null_ids_keep_distinct_occurrence_pointers(self):
        self.nodes[0]['id']=self.nodes[1]['id']='AA'
        for o in self.cat['diagram_occurrences']:o['node']='AA'
        self.publish();audit=self.audit();self.assertEqual(audit['summary']['occurrences'],2);self.assertEqual(audit['identity_coverage']['exact_model_pointer_keys'],2)
        self.assertEqual(audit['summary']['coverage_limitations'],2)
    def test_correction_with_null_id_requires_pointer(self):
        context=A.accepted_page_context(self.root);docs,_=A.load_documents(self.root,self.cat,context);p=self.model.resolve();b={'path':str(p),'sha256':sha(p)}
        correction={'page':'XX001','node':None,'model_binding':b,'function':{'A':'OR'}}
        report=A.apply_scoped_corrections(self.root,'1234',docs,{'source_corrections':[correction]})
        self.assertEqual(report[0]['status'],'source_uncertainty')
        correction['node_pointer']='/nodes/1';report=A.apply_scoped_corrections(self.root,'1234',docs,{'source_corrections':[correction]})
        self.assertEqual(docs[p]['document']['nodes'][0]['function'],'A');self.assertEqual(docs[p]['document']['nodes'][1]['function'],'OR')
    def test_only_explicit_true_annotation_flags_exclude_nonphysical_nodes(self):
        extra=deepcopy(self.nodes[0]);extra.update(id='SYMBOL',annotation_only=True);self.nodes.append(extra);self.publish()
        audit=self.audit();self.assertEqual(audit['summary']['occurrences'],2);self.assertEqual(audit['identity_coverage']['catalogue_coverage_issues'],0)
        self.assertEqual(self.collect()['counts']['occurrences'],2)
        extra['annotation_only']=False;self.publish();self.assertEqual(self.audit()['summary']['occurrences'],3)
    def test_accepted_txt_is_rechecked_after_identity_iteration(self):
        context=A.accepted_page_context(self.root);docs,_=A.load_documents(self.root,self.cat,context)
        self.txt.write_text('changed after identity iteration')
        with self.assertRaisesRegex(ValueError,'TXT changed'):A.recheck_identity_context(context,docs)
    def test_annotation_duplicate_id_does_not_hide_the_physical_block(self):
        self.nodes[0]['id']='AA';self.nodes[1]['id']='BB'
        for o,name in zip(self.cat['diagram_occurrences'],['AA','BB']):o['node']=name
        annotation=deepcopy(self.nodes[0]);annotation['annotation_only']=True;self.nodes.append(annotation);self.publish()
        context=A.accepted_page_context(self.root);docs,_=A.load_documents(self.root,self.cat,context)
        wire_docs,issues=A.unambiguous_wiring_documents(docs,'1234')
        self.assertEqual(issues,[]);self.assertEqual([n['id']for n in wire_docs[self.model.resolve()]['document']['nodes']],['AA','BB'])
if __name__=='__main__':unittest.main()

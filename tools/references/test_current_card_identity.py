"""Strict combined-identity coverage, source-review inheritance and tampering guards."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import shutil
import unittest
import current_card_identity as adapter
import verify_current_card_catalog as verifier
import test_current_card_catalog_classification as fixtures

class ExactAliasTests(unittest.TestCase):
    def test_detached_exact_alias(self):
        raw={'card':'1125AA','pins':[{'pin':'J11','triangle':True}],'location':'C-A2C6'};before=deepcopy(raw)
        view,proof=adapter.catalogue_identity(raw)
        self.assertEqual(raw,before);self.assertEqual((view['card_type'],view['portion']),('1125','AA'))
        self.assertEqual(view['pins'],raw['pins']);self.assertEqual(proof['source_fields'],{'card':'1125AA'})
    def test_independent_derivation_agrees(self):
        for raw in ({'card':'1125AA'},{'part':'0503B1'},{'printed_card_portion':'3308A1'},
                    {'card':'1125AA','card_type':'1125','portion':'AA','printed_card_portion':'1125AA'}):
            view,proof=adapter.catalogue_identity(raw);other,op=verifier.expected_identity(raw)
            self.assertEqual((view,proof),(other,op))
    def test_conflicts_not_chosen(self):
        for raw in ({'card':'1125AA','card_type':'1126'},{'card':'1125AA','portion':'AB'},
                    {'card':'1125AA','part':'1125AB'},{'card':'1125AA','printed_card_portion':'1125A�'},
                    {'card':'1125AA','card_type':'11�5'}):
            view,proof=adapter.catalogue_identity(raw);self.assertEqual(view,raw);self.assertEqual(proof['status'],'conflict')
            with self.assertRaises(ValueError):verifier.expected_identity(raw)
    def test_no_format_repair_or_socket_guess(self):
        for value in ('5801125','C-A2C6','1125A�',' 1125AA','1125aa','1125AAA','1125A'):
            raw={'card':value};self.assertEqual(adapter.catalogue_identity(raw)[0],raw)
            self.assertEqual(verifier.expected_identity(raw)[0],raw)

class CatalogueIdentityTests(fixtures.CatalogueClassificationTests):
    def setUp(self):
        super().setUp()
        here=Path(__file__).parent
        for name in ('build_current_card_catalog.py','verify_current_card_catalog.py','current_card_identity.py'):
            self.put('tools/references/'+name,(here/name).read_bytes())
    def publish_model(self):
        self.put(self.model_rel,fixtures.encoded(self.model))
        path=self.repo/'notes/Content data manifest.json';doc=verifier.read(path)
        next(e for e in doc['files']if e['path']==self.model_rel)['sha256']=fixtures.sha(self.repo/self.model_rel)
        path.write_bytes(fixtures.encoded(doc))
    def exact_raw_alias(self):
        self.nodes[0].pop('card_type');self.nodes[0].pop('portion');self.nodes[0]['card']='3308A1'
        self.model['source_reviewed']=True;self.publish_model()
    def test_combined_alias_adds_coverage_without_source_mutation(self):
        self.exact_raw_alias();before=(self.repo/self.model_rel).read_bytes();self.build();verifier.verify(self.repo,self.output)
        obs=self.card('3308')['diagram_occurrences'][0]
        self.assertEqual(obs['portion'],'A1');self.assertTrue(obs['source_reviewed'])
        self.assertEqual(obs['identity_adaptation']['source_fields'],{'card':'3308A1'})
        self.assertEqual((self.repo/self.model_rel).read_bytes(),before)
    def test_explicit_node_false_retained(self):
        self.exact_raw_alias();self.nodes[0]['source_reviewed']=False;self.publish_model();self.build();verifier.verify(self.repo,self.output)
        obs=self.card('3308')['diagram_occurrences'][0];self.assertIs(obs['source_reviewed'],False);self.assertNotIn('source_review_basis',obs)
    def test_page_false_not_inherited_as_acceptance(self):
        self.exact_raw_alias();self.model['source_reviewed']=False;self.publish_model();self.build();verifier.verify(self.repo,self.output)
        self.assertIs(self.card('3308')['diagram_occurrences'][0]['source_reviewed'],False)
    def test_conflicting_combined_identity_rejected(self):
        self.nodes[0]['card']='3308A2';self.publish_model()
        with self.assertRaisesRegex(ValueError,'Conflicting source identity'):self.build()
    def test_rebound_wrong_derived_portion_rejected(self):
        self.exact_raw_alias();self.build();card=self.card('3308');card['diagram_occurrences'][0]['portion']='A2';self.rebound('json/Card types current/3308.json',card)
        with self.assertRaisesRegex(ValueError,'portion differs'):verifier.verify(self.repo,self.output)
    def test_rebound_wrong_review_acceptance_rejected(self):
        self.exact_raw_alias();self.nodes[0]['source_reviewed']=False;self.publish_model();self.build();card=self.card('3308');card['diagram_occurrences'][0]['source_reviewed']=True;self.rebound('json/Card types current/3308.json',card)
        with self.assertRaisesRegex(ValueError,'review inheritance'):verifier.verify(self.repo,self.output)
    def test_rebound_wrong_alias_proof_rejected(self):
        self.exact_raw_alias();self.build();card=self.card('3308');card['diagram_occurrences'][0]['identity_adaptation']['source_fields']['card']='3308A2';self.rebound('json/Card types current/3308.json',card)
        with self.assertRaisesRegex(ValueError,'alias proof'):verifier.verify(self.repo,self.output)
    def test_card_data_raw_alias_crosscheck_uses_same_identity(self):
        self.exact_raw_alias();self.build();shutil.copytree(self.output/'json',self.repo/'json',dirs_exist_ok=True)
        candidate=Path(__file__).parents[1]/'card_ald/build_card_data.py'
        spec=importlib.util.spec_from_file_location('private_identity_card_data',candidate);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.ROOT=self.repo
        _,_,_,_,_,_,uncertainties=module.load_evidence('3308',{})
        self.assertFalse(any(x['kind']=='catalog facts differ from current hash-bound model'for x in uncertainties))

    def load_card_data_module(self):
        candidate=Path(__file__).parents[1]/'card_ald/build_card_data.py'
        spec=importlib.util.spec_from_file_location('private_identity_card_data_locator',candidate);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.ROOT=self.repo
        return module
    def test_two_anonymous_nodes_use_exact_source_pointers(self):
        self.exact_raw_alias();self.nodes[0]['id']=None;self.nodes[1].update(id=None,card_type='3308',portion='B1',function='OR',unit='T03AB');self.publish_model();self.build()
        shutil.copytree(self.output/'json',self.repo/'json',dirs_exist_ok=True)
        module=self.load_card_data_module();_,observations,_,_,_,_,uncertainties=module.load_evidence('3308',{})
        self.assertEqual(len(observations),2)
        self.assertFalse(any(x['kind']in('catalog facts differ from current hash-bound model','catalog node unresolved in current hash-bound model')for x in uncertainties))
        a,_=module.locate_catalog_node(self.model,{'node':None,'node_pointer':'/nodes/0'});b,_=module.locate_catalog_node(self.model,{'node':None,'node_pointer':'/nodes/1'})
        self.assertEqual(a['portion']if'portion'in a else a['card'][-2:],'A1');self.assertEqual(b['portion'],'B1')
    def test_pointer_id_mismatch_is_not_repaired_by_id_fallback(self):
        module=self.load_card_data_module();node,why=module.locate_catalog_node(self.model,{'node':'AB','node_pointer':'/nodes/0'})
        self.assertIsNone(node);self.assertIn('disagree',why['reason'])
    def test_invalid_pointer_fails_closed(self):
        module=self.load_card_data_module()
        for pointer in ('/nodes/-1','/nodes/999','/nodes/00','/nodes/0/id','/other/0',0,''):
            node,_=module.locate_catalog_node(self.model,{'node':'AA','node_pointer':pointer});self.assertIsNone(node)
    def test_id_fallback_requires_unique_non_null_id(self):
        module=self.load_card_data_module();node,_=module.locate_catalog_node(self.model,{'node':'AA'});self.assertEqual(node['id'],'AA')
        for occurrence in ({'node':None},{'node':''},{'node':'MISSING'}):self.assertIsNone(module.locate_catalog_node(self.model,occurrence)[0])
    def test_duplicate_id_and_nonobject_pointer_fail_closed(self):
        module=self.load_card_data_module();model={'nodes':[{'id':'AA'},{'id':'AA'},None]}
        self.assertIsNone(module.locate_catalog_node(model,{'node':'AA'})[0]);self.assertIsNone(module.locate_catalog_node(model,{'node_pointer':'/nodes/2'})[0])

if __name__=='__main__':unittest.main()

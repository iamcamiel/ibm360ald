"""Small source fixtures for the generic observed-variant collector."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('collector',Path(__file__).with_name('collect_card_variants.py'))
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)

class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/"tmp");self.root=Path(self.temp.name);(self.root/'json/XX').mkdir(parents=True)
        self.definition=self.root/'definition.json'
        boxes=[]
        for portion,pin,out in [('A1','D04','B03'),('B1','B05','D02')]:
            boxes.append({'portion':portion,'function':'A','circuit_identifier':'U03AF','ports':[
                {'id':'input:1','side':'input','pin':pin,'triangle':False,'row':1},
                {'id':'output:1','side':'output','pin':out,'triangle':True,'row':3}]})
        self.definition.write_text(json.dumps({'card_type':'1234','boxes':boxes,'power_contacts':['D03'],'variants':[]}),encoding='utf-8')
    def tearDown(self):self.temp.cleanup()
    def node(self,portion,**kwargs):
        p,o={'A1':('D04','B03'),'B1':('B05','D02')}[portion]
        n={'id':portion,'location':'A-A1J6','card_type':'1234','portion':portion,'unit':'U03AF','function':'N','pins':[
            {'side':'input','pin':p,'triangle':False},{'side':'output','pin':o,'triangle':True}]};n.update(kwargs);return n
    def page(self,page,nodes):
        (self.root/'json/XX'/f'{page}.json').write_text(json.dumps({'page':page,'nodes':nodes}),encoding='utf-8')
    def test_compatible_cross_page_is_complete(self):
        self.page('XX001',[self.node('A1')]);self.page('XX011',[self.node('B1')])
        r=C.collect('1234',self.definition,self.root)
        self.assertEqual(r['counts']['distinct_observed_variants'],1)
        self.assertEqual(r['counts']['complete_field_observation_witnesses'],1)
        self.assertEqual(r['variants'][0]['source_pages'],['XX001','XX011'])
        self.assertEqual(set(r['variants'][0]['variant_definition']['box_overrides']),{'A1','B1'})
    def test_conflicting_card_separates_pages(self):
        self.page('XX001',[self.node('A1')]);self.page('XX011',[self.node('A1',function='N OR')])
        r=C.collect('1234',self.definition,self.root)
        self.assertEqual(r['counts']['conflicting_physical_card_sites'],1)
        self.assertEqual(r['counts']['distinct_observed_variants'],2)
        self.assertTrue(all(v['partial_witnesses']==1 for v in r['variants']))
    def test_omitted_port_can_be_completed(self):
        partial=self.node('A1');partial['pins']=partial['pins'][:1]
        self.page('XX001',[partial]);self.page('XX011',[self.node('A1'),self.node('B1')])
        r=C.collect('1234',self.definition,self.root)
        self.assertEqual(r['counts']['complete_field_observation_witnesses'],1)
        self.assertFalse(r['profiles_left_uncertain'])
    def test_supply_tie_and_border_schema(self):
        n=self.node('A1',function='N AND');n['pins'][0].pop('triangle');n['pins'][0]['border_marker']='◺'
        n['pins'].append({'side':'input','pin':'8D03','triangle':False})
        self.page('XX001',[n])
        r=C.collect('1234',self.definition,self.root);v=r['variants'][0]
        self.assertEqual(v['variant_definition']['box_overrides']['A1']['function'],'N AND')
        self.assertEqual(v['variant_definition']['box_overrides']['A1']['port_triangles'],{'input:1':True})
        self.assertEqual(len(v['witnesses'][0]['ignored_supply_ties']),1)
    def test_other_card_and_same_page_distinct_location_not_combined(self):
        self.page('XX001',[self.node('A1'),self.node('B1',location='B-A1J6'),self.node('B1',card_type='9999')])
        r=C.collect('1234',self.definition,self.root)
        self.assertEqual(r['counts']['occurrences'],2)
        self.assertEqual(r['counts']['complete_field_observation_witnesses'],0)
        self.assertEqual(r['counts']['distinct_observed_variants'],2)
    def test_page_socket_option(self):
        self.page('XX001',[self.node('A1')]);self.page('XX011',[self.node('B1')])
        r=C.collect('1234',self.definition,self.root,'page-socket')
        self.assertEqual(r['counts']['installation_witnesses'],2)
        self.assertEqual(r['counts']['complete_field_observation_witnesses'],0)
    def test_uncertain_circuit_not_assumed_variant(self):
        self.page('XX001',[self.node('A1',unit='U03A�')])
        r=C.collect('1234',self.definition,self.root)
        self.assertEqual(r['counts']['distinct_observed_variants'],0)
        self.assertEqual(len(r['profiles_left_uncertain']),1)
        self.assertEqual(r['profiles_left_uncertain'][0]['fields_not_inferred'][0]['field'],'circuit_identifier')

    def test_conflicting_duplicate_contact_does_not_choose_first_mark(self):
        n=self.node('A1');n['pins'][0]['triangle']=True
        n['pins'].append({'side':'input','pin':'D04','triangle':False})
        self.page('XX001',[n]);r=C.collect('1234',self.definition,self.root)
        overrides=r['variants'][0]['variant_definition']['box_overrides']['A1']
        self.assertNotIn('port_triangles',overrides)
        self.assertNotIn('input:1',r['variants'][0]['witnesses'][0]['observed_fields']['A1'])
        self.assertTrue(any('Conflicting source uses' in x['reason'] for x in r['profiles_left_uncertain'][0]['fields_not_inferred']))
    def test_contradictory_mirrors_are_unmapped_not_prioritized(self):
        n=self.node('A1');n['pins'][1].update(physical_pin='D02',printed_pin='B03',triangle=False)
        self.assertIsNone(C.physical(n['pins'][1]))
        self.page('XX001',[n]);r=C.collect('1234',self.definition,self.root)
        overrides=r['variants'][0]['variant_definition']['box_overrides']['A1']
        self.assertNotIn('port_triangles',overrides)
        self.assertNotIn('output:1',r['variants'][0]['witnesses'][0]['observed_fields']['A1'])
        self.assertTrue(any('physical_contact_readings' in x for x in r['profiles_left_uncertain'][0]['fields_not_inferred']))
    def test_annotated_mirrors_of_same_contact_are_compatible(self):
        n=self.node('A1');n['pins'][1].update(physical_pin='B03',printed_pin='2B03✲T')
        self.assertEqual(C.physical(n['pins'][1]),'B03')
        self.page('XX001',[n]);r=C.collect('1234',self.definition,self.root)
        self.assertFalse(r['profiles_left_uncertain'])


    def test_complete_policy_excludes_partial_profile_without_losing_evidence(self):
        self.page('XX001',[self.node('A1')])
        discovery=C.collect('1234',self.definition,self.root)
        selected=C.collect('1234',self.definition,self.root,publication_policy='complete-witnesses')
        self.assertEqual(discovery['publication_policy'],'all-observed')
        self.assertEqual(len(discovery['variants']),1)
        self.assertEqual(selected['variants'],[])
        self.assertEqual(selected['excluded_partial_profiles'],discovery['variants'])
        self.assertEqual(selected['counts']['distinct_observed_variants'],1)
        self.assertEqual(selected['counts']['selected_publication_variants'],0)
        self.assertTrue(selected['excluded_partial_profiles'][0]['witnesses'][0]['unobserved_portions_kept_canonical'])
    def test_complete_policy_preserves_existing_profile_numbers(self):
        definition=json.loads(self.definition.read_text())
        definition['variants']=[{'number':7,'box_overrides':{'A1':{'function':'N'},'B1':{'function':'N'}}}]
        self.definition.write_text(json.dumps(definition))
        self.page('XX001',[self.node('A1')]);self.page('XX011',[self.node('B1')])
        self.page('XX021',[self.node('A1',location='B-A1J6')])
        discovery=C.collect('1234',self.definition,self.root)
        selected=C.collect('1234',self.definition,self.root,publication_policy='complete-witnesses')
        self.assertEqual([v['number'] for v in selected['variants']],[7])
        self.assertEqual([v['number'] for v in selected['excluded_partial_profiles']],[1])
        self.assertEqual(sorted(selected['variants']+selected['excluded_partial_profiles'],key=lambda v:v['number']),discovery['variants'])
        self.assertEqual(selected['variants'][0]['source_pages'],['XX001','XX011'])
    def test_policy_roundtrip_retains_every_source_profile(self):
        self.page('XX001',[self.node('A1')])
        discovery=C.collect('1234',self.definition,self.root)
        selected=C.apply_publication_policy(discovery,'complete-witnesses')
        restored=C.apply_publication_policy(selected,'all-observed')
        self.assertEqual(restored,discovery)

if __name__=='__main__':unittest.main()


"""Source-form polarity stays joint and exact; unknown never means false."""
from copy import deepcopy
import sys,unittest
sys.path.insert(1,'D:/Github/IBM360/ibm360ald/tools/card_ald')
import build_card_data as B
import audit_card_uses as A

class SourceTriangleProfiles(unittest.TestCase):
    def make_node(self):
        return {'portion':'A1','_reviewed_component':{'printed_function':'SW'},
            '_inputs':[{'pin':'B02','side':'input','triangle':False}],
            '_outputs':[{'pin':'D02','side':'output','triangle':False}],
            '_mixed_triangle_slots':[('input','B02'),('output','D02')]}
    def occurrence(self,page,input_mark,output_mark):
        return {'page':page,'node':'AA','node_pointer':'/nodes/0',
            '_model_binding':{'path':'json/'+page+'.json','sha256':'a'*64},'pins':[
            {'side':'input','pin':'B02','triangle':input_mark,'_symbols':{'selected_presentation':{},'prefix':[],'suffix':[],'unplaced':[],'observations':[]}},
            {'side':'output','pin':'D02','triangle':output_mark,'_symbols':{'selected_presentation':{},'prefix':[],'suffix':[],'unplaced':[],'observations':[]}}]}
    def test_joint_witness_keeps_two_triangles_together(self):
        node=self.make_node();issues=[]
        B.select_notation_baseline(node,[self.occurrence('AA001',True,True),self.occurrence('ZZ001',False,False)],issues)
        self.assertEqual([],issues)
        self.assertEqual([True,True],[p['triangle']for p in node['_inputs']+node['_outputs']])
        self.assertEqual([[True,True],[False,False]],[[p['triangle']for p in w['ports']]for w in node['_source_notation_variants']])
    def test_consistent_source_stars_still_get_scoped_profiles_for_starless_canonical_forms(self):
        node=self.make_node();node.pop('_reviewed_component');node.pop('_mixed_triangle_slots');node['_observed_symbol_slots']=[('output','D02')]
        occurrence=self.occurrence('AA001',False,False)
        occurrence['pins'][1]['_symbols']={'selected_presentation':{'suffix_mark_ids':['star']},
            'prefix':[],'suffix':[{'mark_id':'star','marks':[{'literal':'✲'}]}],'unplaced':[]}
        B.select_notation_baseline(node,[occurrence],[])
        self.assertEqual(['✲'],node['_source_notation_variants'][0]['ports'][1]['pin_symbols']['suffix'])

    def test_missing_or_conflicting_triangle_cannot_be_selected(self):
        node=self.make_node();issues=[]
        B.select_notation_baseline(node,[self.occurrence('AA001',None,True)],issues)
        self.assertTrue(issues);self.assertNotIn('_source_notation_baseline_witness',node)
    def test_ordinary_manual_polarity_is_not_replaced_by_source_variant(self):
        node=self.make_node();node.pop('_reviewed_component');node['_mixed_symbol_slots']=[('input','B02')]
        B.select_notation_baseline(node,[self.occurrence('AA001',True,True)],[])
        self.assertEqual([False,False],[p['triangle']for p in node['_inputs']+node['_outputs']])
    def test_reviewed_relayout_retains_current_slot_evidence_without_copying_source_geometry(self):
        current=self.make_node();current['_source_notation_variants']=[{'page':'XX001','ports':[]}]
        current['_source_notation_baseline_witness']={'page':'XX001'}
        current['_inputs'][0].update(source_triangle_observations=[{'terminal_id':'n/t:0','triangle':False}],
            source_pin_symbol_observations=[{'terminal_id':'n/t:0'}],pin_symbols={'prefix':[],'suffix':['✲']})
        model={'card_type':'1234','observations':1,'pages':1,'portions':{'A1':current}}
        overlay={'reviewed_portions':{'A1':{'function':'SW','unit':'S06AA','ports':[
            {'id':'in','pin':'B02','side':'input','triangle':False},
            {'id':'out','pin':'D02','side':'output','triangle':False}]}},
            'reviewed_nets':[['PIN:B02','PORT:A1:in'],['PIN:D02','PORT:A1:out']],'power_contacts':{}}
        replay=B.reviewed_routing_model(overlay,model)['portions']['A1']
        self.assertEqual(current['_source_notation_variants'],replay['_source_notation_variants'])
        self.assertEqual(current['_source_notation_baseline_witness'],replay['_source_notation_baseline_witness'])
        self.assertEqual(current['_inputs'][0]['source_triangle_observations'],replay['_inputs'][0]['source_triangle_observations'])
        self.assertEqual(current['_inputs'][0]['pin_symbols'],replay['_inputs'][0]['pin_symbols'])
        self.assertEqual('in',replay['_inputs'][0]['id'])

    def test_scoped_triangle_profile_is_a_boolean_not_truthy_string(self):
        spec={'boxes':[{'portion':'A1','function':'SW','ports':[{'id':'in','side':'input','pin':'B02','triangle':False,'row':2}]}],
              'source_notation_profiles':[{'portion':'A1','source_variants':[{'node_pointer':'/nodes/0','model_binding':{'path':'json/X.json','sha256':'a'*64},'ports':[{'side':'input','pin':'B02','triangle':'false'}]}]}]}
        forms=A.expected_forms(spec)['A1']
        self.assertEqual(1,len(forms))

if __name__=='__main__':unittest.main()

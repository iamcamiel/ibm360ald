"""Ordinary cards retain exact current source notation; no cross-page waiver."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
sys.path.insert(1,'D:/Github/IBM360/ibm360ald/tools/card_ald')
import component_forms as C
import audit_card_uses as A
import card_source as S
class OrdinaryProfiles(unittest.TestCase):
    def setUp(self):
        witness={'page':'XX001','node':'AA','node_pointer':'/nodes/0',
            'model_binding':{'path':'json/XX001.json','sha256':'a'*64},
            'conflicting_source_fields':[], 'ports':[
                {'side':'input','pin':'D12','pin_symbols':{'prefix':[],'suffix':[]}},
                {'side':'output','pin':'D09','pin_symbols':{'prefix':[],'suffix':['✲']}}]}
        self.spec={'boxes':[{'portion':'B1','function':'A','circuit_identifier':'U03AD','ports':[
            {'row':2,'id':'in','pin':'D12','side':'input','triangle':False},
            {'row':3,'id':'out','pin':'D09','side':'output','triangle':True}]}],
            'power_contacts':{},'wiring':{},'nets':[['PIN:D09','PORT:B1:out']],
            'canvas':{'width':100,'height':30},'exterior_pins':[]}
        self.model={'portions':{'B1':{'_inputs':[{'pin':'D12','side':'input'}],
            '_outputs':[{'pin':'D09','side':'output'}],
            '_source_notation_variants':[witness], '_source_notation_baseline_witness':deepcopy(witness)}}}
    def test_current_ordinary_partial_star_is_exact_source_scoped(self):
        before=deepcopy(self.spec)
        C.decorate_definition(self.spec,self.model)
        self.assertTrue(self.spec['source_notation_profiles'])
        for field in ('boxes','wiring','nets','canvas','exterior_pins'):
            self.assertEqual(before[field],self.spec[field])
        witness=next(w for p in self.spec['source_notation_profiles'] for w in p['source_variants'] if w['page']=='XX001')
        node={'id':'AA','function':'N','unit':'U03AD','_source_pointer':'/nodes/0','pins':[
            {'pin':'D12','side':'input','triangle':True},
            {'pin':'D09✲','side':'output','triangle':False,'_symbols':{
                'selected_presentation':{'observation_id':'label:0','prefix_mark_ids':[],
                    'suffix_mark_ids':['m:0'],'unplaced_mark_ids':[]},
                'observations':[{'observation_id':'label:0','selected_presentation':True,
                    'prefix_mark_ids':[],'suffix_mark_ids':['m:0'],'unplaced_mark_ids':[]}],
                'prefix':[],'suffix':[{'mark_id':'m:0','marks':[{'literal':'✲','order':0}]}],'unplaced':[]}}]}
        node.update(_source_page='XX001',_source_model_binding=witness['model_binding'])
        box=next(b for b in self.spec['boxes'] if b['portion']=='B1')
        forms=A.expected_forms(self.spec)['B1']
        findings=A.compare_occurrence(node,box,forms,self.spec['power_contacts'])
        self.assertFalse([f for f in findings if f['status'] in ('discrepancy','source_uncertainty')])
        self.assertTrue(any(f.get('source_notation_witness') for f in findings))
        node['_source_page']='WRONG'
        findings=A.compare_occurrence(node,box,forms,self.spec['power_contacts'])
        self.assertTrue(any(f['status']=='discrepancy' for f in findings))
    def test_supplement_cannot_claim_other_source_witness(self):
        C.decorate_definition(self.spec,self.model)
        overlay={'source_notation_profiles':deepcopy(self.spec['source_notation_profiles'])}
        C.decorate_definition(self.spec,self.model,overlay)
        overlay['source_notation_profiles'][0]['source_variants'][0]['page']='OTHER'
        with self.assertRaisesRegex(ValueError,'source_notation_profiles'):
            C.decorate_definition(self.spec,self.model,overlay)
    def test_current_profile_roundtrip_is_idempotent(self):
        C.decorate_definition(self.spec,self.model)
        before=deepcopy(self.spec)
        C.decorate_definition(self.spec,self.model)
        self.assertEqual(before,self.spec)

if __name__=='__main__':unittest.main()

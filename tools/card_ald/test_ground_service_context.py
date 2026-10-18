"""Page supply context never fabricates a physical contact or internal card link."""
from copy import deepcopy
import unittest
import audit_card_uses as M

def fixture():
    return {'nodes':[{'id':'G','kind':'service','unit':'GND','card_type':'','portion':'','source_reviewed':True,
        'non_card_evidence':'Printed reviewed ground service','pins':[{'side':'output','pin':'D08','triangle':False,'source_reviewed':True}]},
        {'id':'T','function':'SW','unit':'S61AY','card_type':'1234','portion':'A1','source_reviewed':True,'_source_pointer':'/nodes/1',
         'pins':[{'side':'input','pin':None,'triangle':False,'row':10,'source_reviewed':True},
                 {'side':'output','pin':'D06','triangle':False,'row':10,'source_reviewed':True}]}],
        'nets':[{'id':'ground','source_reviewed':True,'driver':'G.D08','targets':['T.'],'target_coordinates':{'T.':[20,10]}}]}

class GroundServiceTests(unittest.TestCase):
    def test_exact_ground_service_context_omits_only_unique_anonymous_input(self):
        doc=fixture();before=deepcopy(doc);context=M.ground_service_inputs(doc,{'D08':'GROUND'})
        self.assertEqual(set(context),{('T',0)});self.assertEqual(doc,before)
        box={'portion':'A1','function':'SW','circuit_identifier':'S61AY','ports':[{'id':'o','pin':'D06','side':'output','triangle':False,'row':3}]}
        flags=M.compare_occurrence(doc['nodes'][1],box,[dict(box,variant_number=0)],{'D08':'GROUND'},context)
        self.assertFalse(any(f['status']in('source_uncertainty','discrepancy')for f in flags))
        self.assertEqual([f['field']for f in flags].count('page_ground_service_input'),1)
    def test_mixed_or_unresolved_drivers_prove_nothing(self):
        for field in ('drivers','declared_physical_output_drivers','route_owners'):
            doc=fixture();doc['nets'][0][field]=['X.D02']
            self.assertEqual(M.ground_service_inputs(doc,{'D08':'GROUND'}),{})
    def test_anonymous_input_on_another_source_net_is_not_certified_ground(self):
        doc=fixture();doc['nets'].append({'id':'other','driver':'UNKNOWN.D02','targets':['T.']})
        self.assertEqual(M.ground_service_inputs(doc,{'D08':'GROUND'}),{})
    def test_unreviewed_node_port_or_net_proves_nothing(self):
        for where in ('source','sourceport','target','targetport','net'):
            doc=fixture();target={'source':doc['nodes'][0],'sourceport':doc['nodes'][0]['pins'][0],
                'target':doc['nodes'][1],'targetport':doc['nodes'][1]['pins'][0],'net':doc['nets'][0]}[where]
            target['source_reviewed']=False
            self.assertEqual(M.ground_service_inputs(doc,{'D08':'GROUND'}),{})
    def test_real_card_or_missing_noncard_authority_cannot_be_ground_service(self):
        for field,value in (('card_type','1234'),('portion','A1'),('kind','card'),('unit','PWR'),('non_card_evidence','')):
            doc=fixture();doc['nodes'][0][field]=value
            self.assertEqual(M.ground_service_inputs(doc,{'D08':'GROUND'}),{})
    def test_wrong_supply_rail_or_label_does_not_match(self):
        for powers in ({'D08':'+3V'},{'D03':'GROUND'},{}):
            self.assertEqual(M.ground_service_inputs(fixture(),powers),{})
    def test_ambiguous_alias_duplicate_node_and_bad_geometry_do_not_match(self):
        for kind in ('second-port','duplicate-node','bad-row','bad-reference','numbered'):
            doc=fixture()
            if kind=='second-port':doc['nodes'][1]['pins'].append(deepcopy(doc['nodes'][1]['pins'][0]))
            elif kind=='duplicate-node':doc['nodes'].append(deepcopy(doc['nodes'][1]))
            elif kind=='bad-row':doc['nets'][0]['target_coordinates']['T.']=[20,11]
            elif kind=='bad-reference':doc['nets'][0]['targets']=['T.unknown']
            else:doc['nodes'][1]['pins'][0]['pin']='B02'
            self.assertEqual(M.ground_service_inputs(doc,{'D08':'GROUND'}),{})
    def test_context_cannot_hide_a_second_non_ground_anonymous_input(self):
        doc=fixture();context=M.ground_service_inputs(doc,{'D08':'GROUND'})
        doc['nodes'][1]['pins'].append({'pin':None,'side':'input','triangle':False,'row':11})
        box={'function':'SW','circuit_identifier':'S61AY','ports':[{'id':'o','pin':'D06','side':'output','triangle':False,'row':3}]}
        flags=M.compare_occurrence(doc['nodes'][1],box,[dict(box,variant_number=0)],{'D08':'GROUND'},context)
        self.assertTrue(any(f['status']=='source_uncertainty'for f in flags))

if __name__=='__main__':unittest.main()

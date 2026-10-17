"""Generic regression cases for inferred card-internal edge boundaries."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_card_data as B


class InferredInternalEdges(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/'tmp')
        self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def occurrence(self,node,portion,pins):
        return {'page':'XX001','node':node,'portion':portion,'circuit_identifier':'U03AF',
                'function_label':'N','_instance':('02A-A1','J6'),'pins':deepcopy(pins)}
    def derive(self,source_pins,sink_pins,driver='AA.output',target='AB.input',power=None):
        observations=[self.occurrence('AA','A1',source_pins),self.occurrence('AB','B1',sink_pins)]
        uncertainties=[]
        with patch.object(B,'ROOT',self.root):
            result,_=B.derive_semantics('1234',{'listing_portions':['A1','B1']},observations,
                {'XX001':{'nets':[{'driver':driver,'targets':[target]}]}},power or B.SINGLE_POWER,uncertainties)
        return result,uncertainties
    def test_distinct_contacts_resolved_from_generic_suffix_are_not_internal(self):
        result,_=self.derive([{'pin':'B03','side':'output'}],[{'pin':'B05','side':'input'}])
        self.assertEqual(result['edges'],[])
        self.assertEqual(len(result['rejected_installation_or_unmapped_edges']),1)
        self.assertIn('installation strap',result['rejected_installation_or_unmapped_edges'][0]['reason'])
    def test_same_physical_contact_is_retained(self):
        result,_=self.derive([{'pin':'B03','side':'output'}],[{'pin':'B03','side':'input'}])
        self.assertEqual(len(result['edges']),1)
        self.assertEqual((result['edges'][0]['output_ref'],result['edges'][0]['input_ref']),('B03','B03'))
        self.assertFalse(result['rejected_installation_or_unmapped_edges'])
    def test_actual_pinless_internal_connection_is_retained(self):
        result,_=self.derive([{'pin':None,'side':'output'}],[{'pin':None,'side':'input'}])
        self.assertEqual(len(result['edges']),1)
        self.assertEqual((result['edges'][0]['output_ref'],result['edges'][0]['input_ref']),('PINLESS','PINLESS'))
        self.assertEqual(result['portions']['A1']['_outputs'][0]['pin'],None)
        self.assertEqual(result['portions']['B1']['_inputs'][0]['pin'],None)
    def test_physical_output_to_real_pinless_input_is_retained(self):
        result,_=self.derive([{'pin':'B03','side':'output'}],[{'pin':None,'side':'input'}])
        self.assertEqual(len(result['edges']),1)
        self.assertEqual((result['edges'][0]['output_ref'],result['edges'][0]['input_ref']),('B03','PINLESS'))
    def test_power_tie_is_not_a_signal_internal_edge(self):
        result,_=self.derive([{'pin':'D03','side':'output'}],[{'pin':'D03','side':'input'}],driver='AA.D03',target='AB.D03')
        self.assertFalse(result['edges'])
        self.assertNotIn('D03',result['signal_pins'])
    def test_explicit_distinct_contacts_remain_rejected(self):
        result,_=self.derive([{'pin':'B03','side':'output'}],[{'pin':'B05','side':'input'}],driver='AA.B03',target='AB.B05')
        self.assertFalse(result['edges'])
        self.assertIn('installation strap',result['rejected_installation_or_unmapped_edges'][0]['reason'])
    def test_unmapped_multiple_inputs_remain_uncertain(self):
        result,_=self.derive([{'pin':'B03','side':'output'}],[{'pin':'B05','side':'input'},{'pin':'B07','side':'input'}])
        self.assertFalse(result['edges'])
        self.assertIn('unresolved exact side-specific endpoint',result['rejected_installation_or_unmapped_edges'][0]['reason'])


if __name__=='__main__':unittest.main()

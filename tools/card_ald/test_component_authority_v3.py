import unittest,json,tempfile,sys,copy,os
from pathlib import Path
r=Path(os.environ.get('IBM360ALD_TEST_REPO',Path(__file__).resolve().parents[2]));out=Path(__file__).resolve().parent
sys.path[:0]=[str(out),str(r/'tools/card_ald')]
import component_forms as f
class SplitAuthority(unittest.TestCase):
 def setUp(self):
  self.form={'printed_function':'INT','approved_source_form':True,'authority':'Standing human printed-source instruction'}
  self.single={'card_width':'SINGLE CARD','contact_banks':'BD','power_contacts':{},'power_contact_role':'not_established','supply_connection_inference_allowed':False,'authority':'Exact part/socket listing'}
  self.double={**self.single,'card_width':'DOUBLE CARD','contact_banks':'BDGJ'}
  self.doc={'circuits':{'S61AU':self.form},'card_parts':{'5803129':self.single,'5804193':self.double}}
  self.obs=[{'circuit_identifier':'S61AU','function_label':'INT'}]
 def select(self,part='5803129',width='SINGLE CARD'):
  return f.select_v3(self.doc,self.obs,{width},{width},[part])
 def test_same_circuit_on_different_widths(self):
  self.assertEqual(self.select()['S61AU']['contact_banks'],'BD');self.assertEqual(self.select('5804193','DOUBLE CARD')['S61AU']['contact_banks'],'BDGJ')
 def test_mixed_ordinary_portions_not_relabelled(self):
  self.obs.append({'circuit_identifier':'T03AC','function_label':'A'});self.assertEqual(set(self.select()),{'S61AU'})
 def test_unknown_parts_not_inferred(self):self.assertEqual(self.select('5809999'),{})
 def test_listing_disagreement_rejected(self):
  with self.assertRaisesRegex(ValueError,'mechanical'):self.select('5804193')
 def test_unknown_supply_stays_empty(self):self.assertEqual(self.select()['S61AU']['power_contacts'],{})
 def test_contradicting_parts_not_combined(self):
  with self.assertRaisesRegex(ValueError,'disagree'):f.select_v3(self.doc,self.obs,{'SINGLE CARD'},{'SINGLE CARD'},['5803129','5804193'])
 def test_unknown_power_status_rejected(self):
  self.single['power_contact_role']='ordinary_slt'
  with self.assertRaisesRegex(ValueError,'status'):self.select()
 def test_different_source_label_rejected(self):
  self.obs[0]['function_label']='OR'
  with self.assertRaisesRegex(ValueError,'primary'):self.select()
 def test_3707_scheme_scoped_not_global(self):
  self.single['contact_banks']='ABCDE';self.assertEqual(self.select()['S61AU']['contact_banks'],'ABCDE')
 def test_mixed_display_does_not_overwrite_manual_gate_marks(self):
  model={'portions':{'A1':{'_inputs':[{'side':'input','pin':'B02','triangle':True}],'_outputs':[]}}}
  spec={'boxes':[{'portion':'A1','ports':[{'id':'in','side':'input','pin':'B02','triangle':False}]}]}
  f.copy_port_decorations(spec,model,copy_physical=True,component_only=True)
  self.assertFalse(spec['boxes'][0]['ports'][0]['triangle'])
 def test_current_authority_scopes_stay_separate(self):
  authority=Path(os.environ.get('IBM360ALD_TEST_COMPONENT_AUTHORITY',r/'json/Card-ALD/component-forms.json'))
  doc=json.loads(authority.read_text(encoding='utf-8-sig'))
  self.assertTrue(doc['circuits']);self.assertTrue(doc['card_parts'])
  for form in doc['circuits'].values():
   self.assertFalse(set(form)&{'card_width','contact_banks','power_contacts','applicable_part_numbers'})
  for part,scope in doc['card_parts'].items():
   self.assertEqual(len(part),7);self.assertIn(scope['card_width'],('SINGLE CARD','DOUBLE CARD'))
if __name__=='__main__':unittest.main()

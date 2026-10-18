import copy,unittest
import component_forms as forms
class ComponentSourcePolarity(unittest.TestCase):
 def fixture(self):
  current={'side':'input','pin':'G10','triangle':True,'source_triangle_observations':[{'page':'ED101','node':'BB','terminal_id':'nodes:2/t:0','triangle':True}]}
  model={'portions':{'B1':{'_reviewed_component':{'approved_source_form':True},'_inputs':[current],'_outputs':[]}}}
  spec={'boxes':[{'portion':'B1','ports':[{'id':'in:0','side':'input','pin':'G10','triangle':False}]}]}
  return spec,model
 def test_component_uses_selected_source_triangle(self):
  spec,model=self.fixture();forms.copy_port_decorations(spec,model)
  self.assertIs(spec['boxes'][0]['ports'][0]['triangle'],True)
 def test_ordinary_canonical_triangle_is_not_replaced(self):
  spec,model=self.fixture();model['portions']['B1'].pop('_reviewed_component')
  forms.copy_port_decorations(spec,model);self.assertIs(spec['boxes'][0]['ports'][0]['triangle'],False)
 def test_unknown_triangle_is_not_cast_to_false(self):
  spec,model=self.fixture();model['portions']['B1']['_inputs'][0]['triangle']=None
  with self.assertRaisesRegex(ValueError,'not established'):forms.copy_port_decorations(spec,model)
 def test_supplement_cannot_change_source_triangle(self):
  spec,model=self.fixture();claim=copy.deepcopy(spec['boxes'][0]['ports'][0])
  overlay={'reviewed_portions':{'B1':{'ports':[claim]}}}
  with self.assertRaisesRegex(ValueError,'triangle differs'):forms.copy_port_decorations(spec,model,overlay)
 def test_selected_triangle_needs_typed_terminal_witness(self):
  spec,model=self.fixture();model['portions']['B1']['_inputs'][0]['source_triangle_observations']=[]
  with self.assertRaisesRegex(ValueError,'typed terminal witness'):forms.copy_port_decorations(spec,model)
 def test_ordinary_profile_only_does_not_change_accepted_port_marks(self):
  spec,model=self.fixture();model['portions']['B1'].pop('_reviewed_component')
  model['portions']['B1']['_source_notation_variants']=[{'page':'XX001','node':'AA','ports':[]}]
  model['portions']['B1']['_inputs'][0]['pin_symbols']={'prefix':[],'suffix':['✲']}
  before=copy.deepcopy(spec['boxes']);forms.decorate_definition(spec,model)
  self.assertEqual(before,spec['boxes']);self.assertTrue(spec['source_notation_profiles'])
 def test_supplement_exact_triangle_is_accepted(self):
  spec,model=self.fixture();claim=copy.deepcopy(spec['boxes'][0]['ports'][0]);claim['triangle']=True
  forms.copy_port_decorations(spec,model,{'reviewed_portions':{'B1':{'ports':[claim]}}})
  self.assertIs(spec['boxes'][0]['ports'][0]['triangle'],True)
if __name__=='__main__':unittest.main()

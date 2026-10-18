from copy import deepcopy
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
import os,unittest
import render_composite_card as C
R=Path(os.environ['IBM360ALD_TEST_REPO'])

def model():
 a={'id':'A1','portion':'A1','function':'A','unit':'U03AA','_inputs':[{'id':'i','pin':'B04','triangle':False,'side':'input'}],'_outputs':[{'id':'o','pin':'D07','triangle':False,'side':'output'}]}
 b=deepcopy(a);b.update(id='A2',portion='A2');b['_outputs'][0]['pin']='D10'
 return {'card_type':'1234','portions':{'A1':a,'A2':b},'edges':[],'signal_pins':{'B04':{'input':['A1','A2']},'D07':{'output':['A1']},'D10':{'output':['A2']}},'layout_hints':{'ranks':{'A1':0,'A2':0},'tops':{'A1':14,'A2':24},'first_bank_x':30,'right_margin':20,'row_step':1}}

class InputChannel(unittest.TestCase):
 def test_default_routing_is_identical_to_installed_router(self):
  spec=spec_from_file_location('_unmodified_router',R/'tools/card_ald/render_composite_card.py');old=module_from_spec(spec);spec.loader.exec_module(old)
  a,b=old.prepare(model()),C.prepare(model());self.assertEqual(a[:3],b[:3]);self.assertEqual(a[3].wires,b[3].wires);self.assertEqual(a[3].by_net,b[3].by_net)
 def test_extra_width_grows_input_space_without_changing_ranks_or_tops(self):
  a=C.prepare(model());m=model();m['layout_hints']['input_channel_extra']=8;b=C.prepare(m)
  for part in a[0]:self.assertEqual(b[0][part]['x'],a[0][part]['x']+8);self.assertEqual(b[0][part]['top'],a[0][part]['top'])
  self.assertEqual(b[3].width,a[3].width+8);C.verify(m,b)
 def test_preference_applies_only_to_external_input_only_nets(self):
  m=model();m['layout_hints']['input_channel_vertical_penalty']=12;a=C.prepare(m)
  self.assertEqual(a[3].input_vertical_channels,{'B04':{'right':24,'penalty':12}});C.verify(m,a)
 def test_preference_does_not_change_gate_or_pin_metadata(self):
  m=model();m['layout_hints']['input_channel_vertical_penalty']=12;before=deepcopy(m);C.prepare(m);self.assertEqual(m,before)
 def test_invalid_extra_width_rejected(self):
  for value in(-1,True,1.5,'8'):
   m=model();m['layout_hints']['input_channel_extra']=value
   with self.assertRaisesRegex(ValueError,'nonnegative integer'):C.prepare(m)
 def test_invalid_preference_rejected(self):
  for value in(-1,True,1.5,'12'):
   m=model();m['layout_hints']['input_channel_vertical_penalty']=value
   with self.assertRaisesRegex(ValueError,'nonnegative integer'):C.prepare(m)
if __name__=='__main__':unittest.main()

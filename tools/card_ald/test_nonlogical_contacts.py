"""K contacts retain physical wiring while remaining outside Boolean gates."""
from copy import deepcopy
from pathlib import Path
import json, os, sys, tempfile, unittest
from unittest.mock import patch
ROOT=Path(os.environ.get('IBM360ALD_TEST_REPO',Path(__file__).resolve().parents[2]))
sys.path[:0]=[str(Path(__file__).resolve().parent),str(ROOT/'tools/card_ald')]
import card_source as S, build_card_data as B, audit_card_uses as A, collect_card_variants as V, generate_card as G

def terminal(side,pin,reference,triangle=False,**extra):
 return dict(side=side,pin=pin,reference=reference,triangle=triangle,row=2 if side=='input'else 3,**extra)
def node():
 return dict(id='AA',node='AA',portion='A1',card_type='1234',unit='U03AT',circuit_identifier='U03AT',function='OR',function_label='OR',page='XX001',location='A-A1J6',_instance=('02A-A1','J6'),pins=[terminal('input','B04','AA.IN'),terminal('output','D07','AA.OUT',True),terminal('output','D06','AA.K',False,border_control='K')])
def box():
 return dict(portion='A1',function='OR',circuit_identifier='U03AT',ports=[dict(id='in',side='input',pin='B04',triangle=False,row=2),dict(id='out',side='output',pin='D07',triangle=True,row=3),dict(id='tap',side='output',pin='D06',triangle=False,row=4,contact_role='nonlogical_common',border_control='K')])
class NonlogicalContacts(unittest.TestCase):
 def test_explicit_role_does_not_follow_similar_labels(self):
  self.assertEqual(S.terminal_contact_role({'pin':'KD06'}),'logical')
  for key in ('border_marker','border_control','border_qualifier','printed_qualifier','marker'):
   self.assertEqual(S.terminal_contact_role({key:'K'}),'nonlogical_common')
  self.assertEqual(S.terminal_contact_role({'_border_decorations':[{'kind':'literal-border-mark','glyph':'K'}]}),'nonlogical_common')
  self.assertEqual(S.terminal_contact_role({'border_control':'E'}),'logical')
 def test_current_marker_survives_catalogue_projection(self):
  raw={'pin':'KD06','side':'output','row':4,'triangle':False,'marker':'K'}
  projected={k:v for k,v in raw.items()if k!='marker'}
  S.attach_typed_terminals({'pins':[projected]},{'pins':[raw]})
  self.assertEqual(S.terminal_contact_role(projected),'nonlogical_common');self.assertNotIn('border_control',raw)
 def test_conflicting_declared_role_is_rejected(self):
  with self.assertRaises(ValueError):S.terminal_contact_role({'marker':'K','contact_role':'logical'})
  with self.assertRaises(ValueError):S.terminal_contact_role({'contact_role':'nonlogical_common'})
 def test_net_resolution_retains_contact_and_side_without_logic_driver(self):
  n=node();before=deepcopy(n);r=S.resolve_net_port(n,'AA.K','output')
  self.assertEqual(r['physical_contact'],'D06');self.assertEqual(r['contact_role'],'nonlogical_common');self.assertIsNone(r['logical_side']);self.assertEqual(n,before)
 def derive(self,n=None,nets=None):
  n=node()if n is None else n
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);m=root/'notes/Card-ALD';m.mkdir(parents=True)
   (m/'Manual canonical circuit forms.json').write_text(json.dumps({'circuits':{'U03AT':{'canonical_form':{'primary_function':'OR','all_input_triangles':False,'all_output_triangles':True}}}}))
   flags=[]
   with patch.object(B,'ROOT',root):model,_=B.derive_semantics('1234',{'listing_portions':['A1']},[n],{'XX001':{'nodes':[n],'nets':nets or []}},B.SINGLE_POWER,flags)
  return model,flags
 def test_builder_uses_source_k_polarity_keeps_other_manual_output(self):
  m,f=self.derive();self.assertFalse(f,f);ports={p['pin']:p for p in m['portions']['A1']['_outputs']}
  self.assertTrue(ports['D07']['triangle']);self.assertFalse(ports['D06']['triangle']);self.assertEqual(ports['D06']['contact_role'],'nonlogical_common')
  self.assertEqual(m['edges'],[]);c=B.terminal_components(m);self.assertNotEqual(c['D06'],c['D07'])
 def test_non_k_control_still_obeys_manual(self):
  n=node();n['pins'][-1].pop('border_control');m,f=self.derive(n);self.assertTrue(m['portions']['A1']['_outputs'][0]['triangle']);self.assertFalse(any(p.get('contact_role')for p in m['portions']['A1']['_outputs']))
 def test_missing_and_conflicting_k_source_polarity_hold(self):
  n=node();n['pins'][-1].pop('triangle');m,f=self.derive(n);self.assertTrue(any(x['kind']=='unknown source border polarity'for x in f))
 def test_boolean_equivalence_omits_k_but_preserves_physical_mark_comparison(self):
  n=node();b=box();pairs=A.port_mapping(n['pins'],b)
  n['function']='N';b['function']='AR';b['ports'][0]['triangle']=True;b['ports'][1]['triangle']=False
  # One input OR with inverted output equals an input-inverted one-input AR;
  # use OR versus A, as AR has its own primary-function restriction.
  n['function']='OR';b['function']='A';self.assertTrue(A.equivalent_form(n,b,pairs,True))
  f=A.compare_occurrence(node(),box(),A.expected_forms({'boxes':[box()],'variants':[]})['A1'],{})
  self.assertFalse([x for x in f if x['status']in('discrepancy','source_uncertainty')],f)
  bad=box();bad['ports'][-1]['triangle']=True
  f=A.compare_occurrence(node(),bad,A.expected_forms({'boxes':[bad],'variants':[]})['A1'],{})
  self.assertTrue(any(x['status']=='discrepancy'for x in f),f)
 def test_variants_cannot_change_logical_role(self):
  b=box();n=node();_,_,flags,_=V.observed_form(n,b,{});self.assertFalse(flags,flags)
  b['ports'][-1].pop('border_control');b['ports'][-1].pop('contact_role');_,_,flags,_=V.observed_form(n,b,{})
  self.assertTrue(any(x['field']=='output_contact_role'for x in flags))
 def test_renderer_labels_explicit_contact_without_changing_net_identity(self):
  b=box();b['x']=20;p=b['ports'][-1];self.assertEqual(G.port_label(b,p),(28,4,'D06'))
  p.pop('border_control')
  with self.assertRaises(AssertionError):G.port_label(b,p)
 def test_routing_isolated_right_k_contact_is_exterior_output(self):
  import render_composite_card as C
  m,f=self.derive();geometry=C.prepare(m);self.assertEqual(geometry[2]['D06']['side'],'output');self.assertEqual(geometry[2]['D07']['side'],'output')
  self.assertEqual(next(p for key,p in geometry[1].items()if p['pin']=='D06')['contact_role'],'nonlogical_common')
 def test_routing_k_contact_with_genuine_peer_driver_is_exterior_output(self):
  import render_composite_card as C
  m,f=self.derive();m['portions']['B1']={'id':'B1','portion':'B1','function':'A','unit':'U03AA','_inputs':[],'_outputs':[{'pin':'D06','side':'output','triangle':False,'ref':'D06','row':0}]}
  m['signal_pins']['D06']['output'].append('B1')
  geometry=C.prepare(m);self.assertEqual(geometry[2]['D06']['side'],'output')
 def test_renderer_accepts_isolated_right_k_exterior_output(self):
  spec=G.read(ROOT/'json/Card-ALD/definitions/0141.json')
  for net in spec['nets']:
   terminals=[t for t in net if t.startswith('PORT:')]
   physical=[t for t in net if t.startswith('PIN:')]
   if len(terminals)!=1 or not physical:continue
   _,portion,ident=terminals[0].split(':',2)
   p=next(p for b in spec['boxes']if b['portion']==portion for p in b['ports']if p['id']==ident)
   if p['side']!='output':continue
   p.update(contact_role='nonlogical_common',border_control='K',triangle=False)
   G.validate(spec)
   break
  else:self.fail('Ordinary published fixture lacks an isolated output')
 def test_wiring_role_preserves_exact_same_and_cross_block_contacts(self):
  n=node();sink=dict(id='AB',portion='B1',card_type='1234',location='A-A1J6',pins=[terminal('input','D06','AB.IN')])
  b=box();sb=dict(portion='B1',function='A',ports=[dict(id='in',side='input',pin='D06',triangle=False)])
  spec={'boxes':[b,sb],'nets':[['PORT:A1:tap','PORT:B1:in','PIN:D06'],['PORT:A1:out','PIN:D07'],['PORT:A1:in','PIN:B04']]}
  doc={'page':'XX001','nodes':[n,sink],'nets':[{'driver':'AA.K','declared_physical_output_drivers':['AA.OUT'],'targets':['AB.IN']}]}
  flags,obs=A.audit_wiring('1234',spec,{Path('test.json'):{'document':doc}})
  self.assertFalse(any(x['field']=='multiple_internal_drivers'for x in flags));self.assertTrue(any(x['classification']=='common_nonlogical_contact_link'for x in obs));self.assertNotEqual(set(spec['nets'][0]),set(spec['nets'][1]))
  # Exact manually traced same-block commoning stays explicit, never created
  # merely by the K marker. It has no second Boolean driver.
  spec['nets'][0].append('PORT:A1:out');spec['nets'].pop(1)
  flags,_=A.audit_wiring('1234',spec,{Path('test.json'):{'document':doc}});self.assertFalse(any(x['field']=='multiple_internal_drivers'for x in flags))
if __name__=='__main__':unittest.main()

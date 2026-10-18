"""AR pass-through labels are input-only logical contacts, across all consumers."""
from copy import deepcopy
from pathlib import Path
import json,tempfile,unittest,sys,os
from unittest.mock import patch
PRIVATE=Path(__file__).resolve().parent
ROOT=Path(os.environ.get('IBM360ALD_TEST_REPO',Path(__file__).resolve().parents[2]))
sys.path[:0]=[str(PRIVATE),str(ROOT/'tools/card_ald')]
import card_source as S,build_card_data as B,audit_card_uses as A,collect_card_variants as V

def pin(side,contact,reference,triangle=False):return dict(side=side,pin=contact,reference=reference,triangle=triangle,row=2 if side=='input'else 3)
def ar(label='AR ID'):
 return {'id':'AA','node':'AA','portion':'A1','card_type':'1234','unit':'T06AA','circuit_identifier':'T06AA','function':label,'function_label':label,'page':'XX001','location':'A-A1J6','_instance':('02A-A1','J6'),'pins':[pin('input','B04','AA.IN'),pin('output','B04','AA.PASS'),pin('output','D02','AA.OUT')]}
class InputOnlyAR(unittest.TestCase):
 def test_first_function_and_same_block_identity(self):
  for label in ('AR','AR T','AR ID','  AR ID'):
   n=ar(label);before=deepcopy(n);self.assertEqual(S.ar_input_only_aliases(n),{1:'B04'});self.assertEqual([i for i,p in S.logical_terminal_items(n)],[0,2]);self.assertEqual(n,before)
  self.assertEqual(S.ar_input_only_aliases(ar('A OR')),{})
 def test_distinct_and_nonar_outputs_retained(self):
  n=ar();n['pins'][1]['pin']='B05';self.assertEqual(S.ar_input_only_aliases(n),{})
  n=ar('OR');self.assertEqual(len(S.logical_terminal_items(n)),3)
 def test_output_endpoint_role_is_input_only(self):
  n=ar();r=S.resolve_net_port(n,'AA.PASS','output');self.assertTrue(r['input_only_alias']);self.assertEqual(r['logical_side'],'input');self.assertEqual(r['physical_contact'],'B04')
  self.assertNotIn('input_only_alias',S.resolve_net_port(n,'AA.OUT','output'))
 def derive(self):
  n=ar();sink={'id':'AB','node':'AB','portion':'B1','card_type':'1234','function':'A','function_label':'A','unit':'U03AA','circuit_identifier':'U03AA','page':'XX001','location':'A-A1J6','_instance':n['_instance'],'pins':[pin('input',None,'AB.IN'),pin('output','D04','AB.OUT')]}
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);p=root/'notes/Card-ALD';p.mkdir(parents=True)
   (p/'Manual canonical circuit forms.json').write_text(json.dumps({'circuits':{'T06AA':{'canonical_form':{'primary_function':'AR','all_input_triangles':False,'all_output_triangles':False}},'U03AA':{'canonical_form':{'primary_function':'A','all_input_triangles':False,'all_output_triangles':False}}}}))
   findings=[]
   with patch.object(B,'ROOT',root):model,_=B.derive_semantics('1234',{'listing_portions':['A1','B1']},[n,sink],{'XX001':{'nodes':[n,sink],'nets':[{'id':'alias','driver':'AA.PASS','targets':['AB.IN']}]}},B.SINGLE_POWER,findings)
  return n,sink,model,findings
 def test_builder_fanout_preserved_without_driver(self):
  n,sink,m,flags=self.derive();self.assertFalse(flags,flags);self.assertEqual([p['pin']for p in m['portions']['A1']['_outputs']],['D02']);self.assertEqual(m['edges'],[])
  self.assertEqual(len(m['input_contact_fanouts']),1);nets=B.terminal_components(m);self.assertIn(('A1','input','B04'),nets['B04']);self.assertIn(('B1','input',None),nets['B04']);self.assertFalse(m['signal_pins']['B04'].get('output'))
 def test_audit_and_variant_ignore_only_printed_alias(self):
  n=ar();box={'portion':'A1','function':'AR','circuit_identifier':'T06AA','ports':[{'id':'in','side':'input','pin':'B04','triangle':False,'row':2},{'id':'out','side':'output','pin':'D02','triangle':False,'row':3}]}
  spec={'boxes':[box],'variants':[]};flags=A.compare_occurrence(n,box,A.expected_forms(spec)['A1'],{})
  self.assertFalse([f for f in flags if f['status']in('discrepancy','source_uncertainty')],flags);self.assertTrue(any(f['field']=='input_only_AR_contact'for f in flags))
  form,obs,missing,ignored=V.observed_form(n,box,{})
  self.assertFalse(missing,missing);self.assertEqual(set(obs),{'function','in','out'});self.assertEqual(len(ignored),1);self.assertEqual(ignored[0]['physical_pin'],'B04')
 def test_audit_fanout_is_not_output_driver(self):
  n,sink,m,flags=self.derive();spec={'boxes':[{'portion':'A1','function':'AR','ports':[{'id':'in','side':'input','pin':'B04','triangle':False},{'id':'out','side':'output','pin':'D02','triangle':False}]},{'portion':'B1','function':'A','ports':[{'id':'in','side':'input','pin':None,'triangle':False},{'id':'out','side':'output','pin':'D04','triangle':False}]}],'nets':[['PIN:B04','PORT:A1:in','PORT:B1:in'],['PIN:D02','PORT:A1:out'],['PIN:D04','PORT:B1:out']]}
  doc={'page':'XX001','nodes':[n,sink],'nets':[{'id':'alias','driver':'AA.PASS','targets':['AB.IN']}]};f,obs=A.audit_wiring('1234',spec,{Path('test.json'):{'document':doc}});self.assertFalse(f,f);self.assertEqual(obs[0]['classification'],'input_contact_fanout');self.assertEqual(obs[0]['driver']['side'],'input')
 def test_distinct_contact_installation_strap_does_not_merge_input_nets(self):
  n=ar();sink={'id':'AB','portion':'B1','card_type':'1234','location':'A-A1J6','pins':[pin('input','B05','AB.IN')]}
  spec={'boxes':[{'portion':'A1','function':'AR','ports':[{'id':'in','side':'input','pin':'B04','triangle':False}]},{'portion':'B1','function':'A','ports':[{'id':'in','side':'input','pin':'B05','triangle':False}]}],'nets':[['PIN:B04','PORT:A1:in'],['PIN:B05','PORT:B1:in']]}
  f,observations=A.audit_wiring('1234',spec,{Path('test.json'):{'document':{'page':'XX001','nodes':[n,sink],'nets':[{'driver':'AA.PASS','targets':['AB.IN']}]}}})
  self.assertFalse(f);self.assertEqual(observations[0]['classification'],'input_contact_installation_wire');self.assertEqual(observations[0]['driver']['side'],'input')
 def test_missing_fanout_is_still_a_discrepancy(self):
  n=ar();sink={'id':'AB','portion':'B1','card_type':'1234','location':'A-A1J6','pins':[pin('input',None,'AB.IN')]};spec={'boxes':[{'portion':'A1','function':'AR','ports':[{'id':'in','side':'input','pin':'B04','triangle':False}]},{'portion':'B1','function':'A','ports':[{'id':'in','side':'input','pin':None,'triangle':False}]}],'nets':[['PIN:B04','PORT:A1:in'],['PORT:B1:in']]}
  f,obs=A.audit_wiring('1234',spec,{Path('test.json'):{'document':{'page':'XX001','nodes':[n,sink],'nets':[{'driver':'AA.PASS','targets':['AB.IN']}]}}});self.assertTrue(any(x['field']=='input_contact_fanout'for x in f))
 def test_routing_keeps_two_distinct_anonymous_input_fanouts(self):
  import render_composite_card as C
  # Derive and route two aliases into separate anonymous inputs of one combiner.
  a=ar();b=ar('AR T');b.update(id='AB',node='AB',portion='A2')
  b['pins']=[pin('input','B05','AB.IN'),pin('output','B05','AB.PASS'),pin('output','D04','AB.OUT')]
  target={'id':'AC','node':'AC','portion':'AA','card_type':'1234','function':'A','function_label':'A','unit':'U03AA','circuit_identifier':'U03AA','page':'XX001','location':'A-A1J6','_instance':a['_instance'],'pins':[pin('input',None,'AC.IN1'),pin('input',None,'AC.IN2'),pin('output','D05','AC.OUT')]}
  target['pins'][1]['row']=3
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);directory=root/'notes/Card-ALD';directory.mkdir(parents=True)
   (directory/'Manual canonical circuit forms.json').write_text(json.dumps({'circuits':{'T06AA':{'canonical_form':{'primary_function':'AR','all_input_triangles':False,'all_output_triangles':False}},'U03AA':{'canonical_form':{'primary_function':'A','all_input_triangles':False,'all_output_triangles':False}}}}))
   flags=[]
   with patch.object(B,'ROOT',root):model,_=B.derive_semantics('1234',{'listing_portions':['A1','A2','AA']},[a,b,target],{'XX001':{'nodes':[a,b,target],'nets':[{'driver':'AA.PASS','targets':['AC.IN1']},{'driver':'AB.PASS','targets':['AC.IN2']}]}},B.SINGLE_POWER,flags)
  self.assertFalse(flags,flags);self.assertFalse(model['edges']);self.assertEqual(len(model['input_contact_fanouts']),2)
  positions,ports,exterior,router=C.prepare(model)
  targets=[(k,p)for k,p in ports.items()if k[0]=='AA'and k[1]=='input']
  self.assertEqual(len(targets),2);self.assertEqual({p['net']for k,p in targets},{'B04','B05'});self.assertEqual(len({p['point']for k,p in targets}),2)
  self.assertFalse([k for k,p in ports.items()if k[1]=='output'and p['net']in('B04','B05')])
 def test_renderer_rejects_duplicate_ar_contact(self):
  import generate_card as G
  # Inject an invalid AR alias into a valid ordinary definition. This remains
  # valid regression coverage after 3379 itself has been corrected/published.
  spec=G.read(ROOT/'json/Card-ALD/definitions/0141.json')
  box=next(b for b in spec['boxes']if any(p.get('pin')and p['side']=='input'for p in b['ports']))
  source=next(p for p in box['ports']if p.get('pin')and p['side']=='input')
  box['function']='AR ID';alias={'id':'injected-alias','pin':source['pin'],'side':'output','triangle':False,'row':box['top']+3};box['ports'].append(alias)
  stale='PORT:'+box['portion']+':injected-alias';net=next(n for n in spec['nets']if 'PIN:'+source['pin']in n);net.append(stale)
  with self.assertRaisesRegex(AssertionError,'input-only'):G.validate(spec)
  box['ports'].remove(alias)
  with self.assertRaises(AssertionError):G.validate(spec)
if __name__=='__main__':unittest.main()

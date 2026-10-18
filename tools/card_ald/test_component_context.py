"""Independent fail-closed fixtures for passive occurrence-only K certificates."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,os,sys,tempfile,unittest
ROOT=Path(os.environ.get('IBM360ALD_TEST_REPO','D:/Github/IBM360/ibm360ald'))
sys.path[:0]=[str(Path(__file__).resolve().parent),str(ROOT/'tools/card_ald')]
import card_source as S,component_context as C
S.configure(ROOT)
from pages import normalize_page
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
class PassiveContextTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  def node(name,site,K):
   return {'id':name,'card_type':'7777','portion':'A1','function':'SW','unit':'S61ZZ','location':site,'row':2 if name=='AA'else 9,'column':50,'source_reviewed':True,
    'pins':[{'side':'input','pin':'B02','reference':name+'.B02','row':3 if name=='AA'else 10,'triangle':False},
     {'side':'output','pin':'B03','reference':name+'.B03','row':4 if name=='AA'else 11,'triangle':False,**({'border_marker':'K'}if K else{})}]}
  self.raw={'page':'ZZ001','source_reviewed':True,'nodes':[node('AA','A-A1A1',False),node('AB','A-A1A2',True)],
   'nets':[{'id':'installation','driver':'AA.B03','targets':[],'additional_source_drivers':['AB.B03'],'source_reviewed':True}]}
  manual=self.root/'fixture manual.pdf';manual.write_bytes(b'Explicit unit-test passive component authority fixture, not a production manual.')
  self.authority={'schema':'reviewed-component-forms-v3','card_parts':{'5807777':{'card_width':'SINGLE CARD','supply_connection_inference_allowed':False}},
   'circuits':{'S61ZZ':{'printed_function':'SW','approved_source_form':True,'authority':'Explicit fixture authority',
    C.CAPABILITY:{'schema':C.CAPABILITY_SCHEMA,'passive_component':True,'component_class':'passive_fixture','marker':'K',
     'requires_plain_same_portion':True,'requires_explicit_page_common_net':True,'intrinsic_connection_inference_allowed':False,
     'complete_K_variant_policy':'hold_until_renderer_support','manual_evidence':[{'path':str(manual),'sha256':sha(manual)}]}}}}
  self.build()
 def tearDown(self):self.temp.cleanup()
 def build(self):
  self.path=self.root/'json/ZZ/ZZ001.json';self.doc=normalize_page(self.raw,'json/ZZ/ZZ001.json','1')['data'];write(self.path,self.doc)
  write(self.root/'notes/Source status.json',{'schema':'ald-current-source-checkpoint-v1','records':[{'repository':{'json':{'path':'json/ZZ/ZZ001.json','sha256':sha(self.path)}}}]})
  self.models={'ZZ001':S.view(self.doc,self.root)}
  self.bindings={'ZZ001':{'path':'json/ZZ/ZZ001.json','sha256':sha(self.path)}}
  self.catalog={'card_type':'7777','full_part_numbers_observed':['5807777'],'physical_card_widths_observed':['SINGLE CARD'],'diagram_occurrences':[
   {'page':'ZZ001','node':n['id'],'node_pointer':'/nodes/'+str(i),'portion':n['portion'],'circuit_identifier':n['unit'],'source_reviewed':True,'pins':deepcopy(n['pins'])}
   for i,n in enumerate(self.models['ZZ001']['nodes'])]}
  self.authority_path=self.root/'json/Card-ALD/component-forms.json';write(self.authority_path,self.authority)
 def run_context(self):return C.apply_context(self.root,self.catalog,self.models,self.bindings)
 def kport(self):return self.models['ZZ001']['nodes'][1]['pins'][1]
 def held(self):
  r=self.run_context();self.assertFalse(r['proofs']);self.assertTrue(r['holds'],r);self.assertEqual(S.intrinsic_contact_role(self.kport()),'nonlogical_common');return r
 def test_generic_valid_source_is_not_card_or_page_specific(self):
  before=self.path.read_bytes();r=self.run_context();self.assertEqual(len(r['proofs']),1);self.assertEqual(r['holds'],[])
  p=r['proofs'][0];self.assertEqual(p['page'],'ZZ001');self.assertEqual(p['pin'],'B03');self.assertEqual(p['component_capability']['component_class'],'passive_fixture')
  self.assertEqual(self.path.read_bytes(),before);self.assertFalse(p['intrinsic_connection_inference_applied']);self.assertEqual(p['model_binding']['path'],'json/ZZ/ZZ001.json')
 def test_only_runtime_role_is_projected_raw_K_unchanged(self):
  r=self.run_context();p=self.kport();self.assertEqual(S.terminal_contact_role(p),'nonlogical_common');self.assertEqual(S.intrinsic_contact_role(p),'logical')
  self.assertEqual(p['border_marker'],'K');self.assertEqual(self.catalog['diagram_occurrences'][1]['pins'][1]['_occurrence_net_role'],r['proofs'][0])
 def test_disabled_capability_is_exact_noop(self):
  del self.authority['circuits']['S61ZZ'][C.CAPABILITY];write(self.authority_path,self.authority)
  before=deepcopy((self.models,self.catalog));self.bindings={};r=self.run_context();self.assertEqual(r,{'proofs':[],'holds':[]});self.assertEqual((self.models,self.catalog),before)
 def test_missing_authority_has_no_capabilities_or_effect(self):
  self.authority_path.unlink();before=deepcopy((self.models,self.catalog));self.assertEqual(self.run_context(),{'proofs':[],'holds':[]});self.assertEqual((self.models,self.catalog),before)
 def test_K_only_retains_current_nonlogical_policy(self):
  self.raw['nodes'][0]['pins'][1]['border_marker']='K';self.build();r=self.run_context();self.assertEqual(r,{'proofs':[],'holds':[]});self.assertEqual(S.intrinsic_contact_role(self.kport()),'nonlogical_common')
 def test_plain_only_retains_current_policy(self):
  self.raw['nodes'][1]['pins'][1].pop('border_marker');self.build();self.assertEqual(self.run_context(),{'proofs':[],'holds':[]})
 def test_other_portion_plain_is_not_a_same_portion_witness(self):
  self.raw['nodes'][0]['portion']='B1';self.build();self.assertEqual(self.run_context(),{'proofs':[],'holds':[]})
 def test_missing_explicit_commoning_holds(self):
  self.raw['nets'][0]['additional_source_drivers']=[];self.build();self.held()
 def test_wrong_target_does_not_prove_K_commoning(self):
  self.raw['nets'][0]['additional_source_drivers']=['AA.B03'];self.build();self.held()
 def test_K_named_origin_cannot_name_itself(self):
  self.raw['nets'][0]['driver']='AB.B03';self.build();self.held()
 def test_origin_must_have_exact_physical_contact(self):
  extra=deepcopy(self.raw['nodes'][0]);extra['id']='AC';extra['location']='A-A1A3'
  for p in extra['pins']:p['reference']=p['reference'].replace('AA.','AC.')
  self.raw['nodes'].append(extra);self.raw['nodes'][0]['pins'][1]['pin']=None;self.build();self.held()
 def test_origin_alias_to_AR_input_is_not_an_output_proof(self):
  self.raw['nodes'].append({'id':'AC','card_type':'9999','portion':'A1','unit':'T06AA','function':'AR','location':'A-A1A3','source_reviewed':True,'pins':[{'side':'input','pin':'D04','row':18,'triangle':False},{'side':'output','pin':'D04','reference':'AC.D04','row':19,'triangle':False}]})
  self.raw['nets'][0]['driver']='AC.D04';self.build();self.catalog['diagram_occurrences']=self.catalog['diagram_occurrences'][:2];self.held()
 def test_wrong_binding_holds(self):self.bindings['ZZ001']['sha256']='0'*64;self.held()
 def test_hash_not_owned_by_accepted_checkpoint_holds(self):
  write(self.root/'notes/Source status.json',{'schema':'ald-current-source-checkpoint-v1','records':[]});self.held()
 def test_runtime_physical_reading_cannot_override_source(self):self.kport()['pin']='B04';self.held()
 def test_source_object_review_is_required(self):self.raw['nodes'][1]['source_reviewed']=False;self.build();self.held()
 def test_page_net_review_is_required(self):self.raw['nets'][0]['source_reviewed']=False;self.build();self.held()
 def test_capability_requires_bound_manual(self):
  self.authority['circuits']['S61ZZ'][C.CAPABILITY]['manual_evidence']=[];self.build();self.held()
 def test_passive_class_cannot_be_inferred_from_function_name(self):
  self.authority['circuits']['S61ZZ'][C.CAPABILITY]['passive_component']=False;self.build();self.held()
 def test_wrong_circuit_in_runtime_holds(self):self.models['ZZ001']['nodes'][1]['unit']='S61ZY';self.held()
 def test_two_page_nets_for_same_K_terminal_are_ambiguous(self):
  self.raw['nets'].append({**deepcopy(self.raw['nets'][0]),'id':'second'});self.build();self.held()
 def test_K_polarity_conflict_holds(self):self.raw['nodes'][1]['pins'][1]['triangle']=True;self.build();self.held()
 def test_revalidation_failure_removes_old_runtime_certificate(self):
  self.assertTrue(self.run_context()['proofs']);self.bindings['ZZ001']['sha256']='0'*64;self.held();self.assertNotIn('_occurrence_net_role',self.kport())
 def test_revoked_capability_removes_old_runtime_certificate(self):
  self.assertTrue(self.run_context()['proofs']);del self.authority['circuits']['S61ZZ'][C.CAPABILITY];write(self.authority_path,self.authority)
  self.assertEqual(self.run_context(),{'proofs':[],'holds':[]});self.assertNotIn('_occurrence_net_role',self.kport());self.assertEqual(S.intrinsic_contact_role(self.kport()),'nonlogical_common')
 def test_forged_JSON_proof_is_not_registered(self):
  p=self.kport();p['_occurrence_net_role']={'role':'commoned_nonorigin','side':'output','pin':'B03','terminal_id':p['_terminal_id'],'context_seal':'0'*64}
  self.assertEqual(S.intrinsic_contact_role(p),'nonlogical_common')
 def test_registered_proof_cannot_be_copied_to_foreign_page_identical_local_terminal(self):
  self.assertTrue(self.run_context()['proofs']);original=self.kport()
  foreign_doc=deepcopy(self.doc);foreign_doc['page']['page']='YY999'
  foreign=S.view(foreign_doc,self.root)['nodes'][1]['pins'][1]
  self.assertEqual((foreign['_terminal_id'],S.terminal_contact(foreign),foreign['side']),(original['_terminal_id'],S.terminal_contact(original),original['side']))
  foreign['_occurrence_net_role']=deepcopy(original['_occurrence_net_role'])
  self.assertIsNone(S.occurrence_net_role(foreign));self.assertEqual(S.intrinsic_contact_role(foreign),'nonlogical_common')
 def test_registered_proof_cannot_be_copied_to_foreign_card_identical_local_terminal(self):
  self.assertTrue(self.run_context()['proofs']);foreign_node=deepcopy(self.models['ZZ001']['nodes'][1]);foreign_node['card_type']='8888'
  self.assertIsNone(S.occurrence_net_role(foreign_node['pins'][1]))
 def test_old_checkpoint_invalidates_existing_registered_object(self):
  self.assertTrue(self.run_context()['proofs']);path=self.root/'notes/Source status.json';data=json.loads(path.read_text());data['test_epoch']='new';write(path,data)
  self.assertIsNone(S.occurrence_net_role(self.kport()));self.assertEqual(S.intrinsic_contact_role(self.kport()),'nonlogical_common')
 def test_changed_source_bytes_invalidate_existing_registered_object(self):
  self.assertTrue(self.run_context()['proofs']);self.path.write_bytes(self.path.read_bytes()+b'\n')
  self.assertIsNone(S.occurrence_net_role(self.kport()));self.assertEqual(S.intrinsic_contact_role(self.kport()),'nonlogical_common')
 def test_view_drops_serialized_source_certificate(self):
  self.assertTrue(self.run_context()['proofs']);saved=deepcopy(self.doc)
  saved['objects'][1]['terminals'][1]['source_literals']['_occurrence_net_role']=deepcopy(self.kport()['_occurrence_net_role'])
  foreign=S.view(saved,self.root)['nodes'][1]['pins'][1]
  self.assertNotIn('_occurrence_net_role',foreign);self.assertIsNone(S.occurrence_net_role(foreign))
 def test_intrinsic_nets_are_never_created_or_changed(self):
  before=deepcopy(self.models['ZZ001']['nets']);r=self.run_context();self.assertTrue(r['proofs']);self.assertEqual(before,self.models['ZZ001']['nets']);self.assertFalse(r['proofs'][0]['rendered_K_variant_support'])
if __name__=='__main__':unittest.main()

from copy import deepcopy
from pathlib import Path
import sys,unittest,tempfile,json,hashlib
sys.path[:0]=[str(Path(__file__).resolve().parent)]
import card_source as S
import collect_card_variants as V

def raw():
    return {'side':'output','pin':'KB09','triangle':False,'border_control':'K','_terminal_id':'nodes:7/t:1',
            '_pin_number':'B09','_pin_number_status':'observed'}
def proof():
    return {'role':'commoned_nonorigin','side':'output','pin':'B09','terminal_id':'nodes:7/t:1',
            'page':'ZZ001','node':'AA','circuit_identifier':'S61AY',
            'model_binding':{'path':'json/ZZ/ZZ001.json','sha256':'1'*64},'net_index':0,'net_origin':'AB.D13'}

class OccurrenceRole(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.model=self.root/'json/ZZ/ZZ001.json';self.model.parent.mkdir(parents=True);self.model.write_text('{}',encoding='utf-8')
        self.checkpoint=self.root/'notes/Source status.json';self.checkpoint.parent.mkdir()
        self.checkpoint.write_text(json.dumps({'schema':'ald-current-source-checkpoint-v1','records':[{'repository':{'json':{'path':'json/ZZ/ZZ001.json','sha256':S.digest(self.model)}}}]}),encoding='utf-8')
        self.authority=self.root/'authority.json';self.authority.write_text('{}',encoding='utf-8')
        self.validator=self.root/'tools/card_ald/card_source.py';self.validator.parent.mkdir(parents=True);self.validator.write_bytes(Path(S.__file__).read_bytes())
        self.manual=Path(self.temp.name)/'registered manual.pdf';self.manual.write_bytes(b'%PDF-1.4\nExact source fixture\n')
        self.manual_registry=self.root/'notes/Card-ALD/Manual canonical circuit forms.json';self.manual_registry.parent.mkdir(parents=True)
        self.manual_registry.write_text(json.dumps({'schema':'manual-canonical-circuit-forms-v1','manual':str(self.manual),'manual_sha256':S.digest(self.manual)}),encoding='utf-8')
        self.current_proof={**proof(),'model_binding':{'path':'json/ZZ/ZZ001.json','sha256':S.digest(self.model)},
                            'source_checkpoint':{'path':str(self.checkpoint),'sha256':S.digest(self.checkpoint)},
                            'component_authority':{'path':str(self.authority),'sha256':S.digest(self.authority)},
                            'validator':{'path':str(self.validator),'sha256':S.digest(self.validator)},
                            'component_capability':{'manual_evidence':[{'path':str(self.manual),'sha256':S.digest(self.manual),'pdf_pages_1based':[1]}]}}
    def tearDown(self):self.temp.cleanup()
    def cert(self,p):return S.register_occurrence_net_role(self.current_proof,p,self.root)
    def test_foreign_page_same_local_id_and_pin_cannot_copy_certificate(self):
        original=raw();original['_occurrence_net_role']=self.cert(original)
        foreign=deepcopy(original) # Another page can have the identical nodes:7/t:1 and B09.
        self.assertEqual(foreign['_terminal_id'],original['_terminal_id']);self.assertEqual(S.terminal_contact(foreign),'B09')
        self.assertIsNone(S.occurrence_net_role(foreign));self.assertEqual(S.intrinsic_contact_role(foreign),'nonlogical_common')
        S.project_occurrence_net_role(original,foreign,page='ZZ002',node='AA',model_binding=self.current_proof['model_binding'])
        self.assertIsNone(S.occurrence_net_role(foreign))
    def test_stale_checkpoint_reuse_revokes_existing_and_new_registration(self):
        p=raw();p['_occurrence_net_role']=self.cert(p)
        old=deepcopy(p['_occurrence_net_role']);self.checkpoint.write_text(self.checkpoint.read_text()+' ',encoding='utf-8')
        self.assertIsNone(S.occurrence_net_role(p))
        with self.assertRaises(ValueError):S.register_occurrence_net_role(old,raw(),self.root)
    def test_changed_source_model_revokes_context_even_before_checkpoint_refresh(self):
        p=raw();p['_occurrence_net_role']=self.cert(p);self.model.write_text('{"changed":true}',encoding='utf-8')
        self.assertIsNone(S.occurrence_net_role(p))
    def test_revoked_authority_cannot_reuse_registered_certificate(self):
        p=raw();p['_occurrence_net_role']=self.cert(p);self.authority.write_text('{"revoked":true}',encoding='utf-8')
        self.assertIsNone(S.occurrence_net_role(p))
    def test_explicit_same_source_projection_is_allowed(self):
        p=raw();p['_occurrence_net_role']=self.cert(p);clone=deepcopy(p)
        S.project_occurrence_net_role(p,clone,page='ZZ001',node='AA',model_binding=self.current_proof['model_binding'])
        self.assertIsNotNone(S.occurrence_net_role(clone))
    def test_serialized_source_certificate_is_removed_by_uniform_view(self):
        p=raw();p['_occurrence_net_role']=self.cert(p)
        source={'page':'ZZ002','nodes':[{'id':'AA','card_type':'7777','portion':'A1','pins':[deepcopy(p)]}]}
        view=S.view(source,self.root)
        self.assertNotIn('_occurrence_net_role',view['nodes'][0]['pins'][0])
    def test_complete_card_k_witness_is_a_real_coverage_hold(self):
        witness={'source_pages':['ZZ001'],'location':'02A-A1A1','unobserved_portions_kept_canonical':[],
                 'fields_not_inferred':[{'field':'occurrence_net_role','profile_only':True}]}
        self.assertEqual(V.complete_k_context_hold(witness)['field'],'complete_K_context_unsupported')
    def test_partial_card_k_context_remains_notes_only(self):
        witness={'source_pages':['ZZ001'],'location':'02A-A1A1','unobserved_portions_kept_canonical':['E2'],
                 'fields_not_inferred':[{'field':'occurrence_net_role','profile_only':True}]}
        self.assertIsNone(V.complete_k_context_hold(witness))
    def test_k_only_role_is_unchanged(self):
        p=raw();self.assertEqual(S.terminal_contact_role(p),'nonlogical_common');self.assertEqual(S.intrinsic_contact_role(p),'nonlogical_common')
    def test_source_json_cannot_register_a_certificate(self):
        p=raw();p['_occurrence_net_role']={**proof(),'context_seal':'2'*64};self.assertIsNone(S.occurrence_net_role(p));self.assertEqual(S.intrinsic_contact_role(p),'nonlogical_common')
    def test_validated_context_does_not_modify_raw_k_role(self):
        p=raw();p['_occurrence_net_role']=self.cert(p)
        self.assertEqual(S.terminal_contact_role(p),'nonlogical_common');self.assertFalse(S.logical_gate_terminal(p));self.assertEqual(S.intrinsic_contact_role(p),'logical')
    def test_changed_model_hash_invalidates_registered_certificate(self):
        p=raw();p['_occurrence_net_role']=self.cert(p);p['_occurrence_net_role']['model_binding']['sha256']='3'*64
        self.assertIsNone(S.occurrence_net_role(p));self.assertEqual(S.intrinsic_contact_role(p),'nonlogical_common')
    def test_certificate_cannot_move_to_another_pin(self):
        p=raw();p['_occurrence_net_role']=self.cert(p);p['_pin_number']='B08'
        self.assertIsNone(S.occurrence_net_role(p))
    def test_certificate_cannot_move_to_another_terminal(self):
        p=raw();p['_occurrence_net_role']=self.cert(p);p['_terminal_id']='nodes:8/t:1'
        self.assertIsNone(S.occurrence_net_role(p))
    def test_profile_only_k_is_never_a_complete_renderable_glyph_variant(self):
        p=raw();p['_occurrence_net_role']=self.cert(p)
        node={'id':'AA','unit':'S61AY','function':'SW','pins':[{'side':'input','pin':'D11','triangle':False},p]}
        box={'portion':'B1','function':'SW','circuit_identifier':'S61AY','ports':[
            {'id':'input:1','side':'input','pin':'D10','row':1,'triangle':False},
            {'id':'input:2','side':'input','pin':'D11','row':2,'triangle':False},
            {'id':'output:3','side':'output','pin':'B09','row':3,'triangle':False}]}
        form,observed,missing,ignored=V.observed_form(node,box,{})
        self.assertFalse([x for x in missing if x['field']=='output_contact_role'])
        self.assertEqual(observed['output:3']['occurrence_net_role']['role'],'commoned_nonorigin')
        self.assertTrue([x for x in missing if x.get('profile_only')is True])
        self.assertEqual(box['ports'][-1]['side'],'output');self.assertNotIn('contact_role',box['ports'][-1])

if __name__=='__main__':unittest.main()

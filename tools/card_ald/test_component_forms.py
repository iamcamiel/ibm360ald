"""Focused reviewed-component authority and caption-routing checks."""
import copy,json,tempfile,unittest
from pathlib import Path
import component_forms as forms
import render_composite_card as router

class ComponentForms(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.path=self.root/'component-forms.json'
        self.profile={'card_width':'DOUBLE CARD','printed_function':'CS','approved_source_form':True,'authority':'Direct human printed-form approval','power_contacts':{},'power_contact_role':'not_established','contact_banks':'BDGJ','applicable_part_numbers':['5801125']}
        self.doc={'schema':'reviewed-component-forms-v2','circuits':{'S06AT':self.profile}}
        self.observations=[{'circuit_identifier':'S06AT','function_label':'CS'}]
    def tearDown(self):self.temp.cleanup()
    def select(self):
        self.path.write_text(json.dumps(self.doc),encoding='utf-8')
        return forms.reviewed_components(self.root,self.path,self.observations,{'DOUBLE CARD'},{'DOUBLE CARD'},['5801125'])
    def test_explicit_unknown_power_is_not_inferred(self):
        profiles,binding=self.select();self.assertEqual(profiles['S06AT']['power_contacts'],{});self.assertEqual(len(binding['sha256']),64)
    def test_mechanical_scope_is_exact(self):
        self.profile['card_width']='SINGLE CARD'
        with self.assertRaisesRegex(ValueError,'mechanical'):self.select()
    def test_primary_label_must_match(self):
        self.observations[0]['function_label']='A'
        with self.assertRaisesRegex(ValueError,'primary function'):self.select()
    def test_secondary_label_is_not_primary(self):
        self.observations[0]['function_label']='CS FL';self.assertTrue(self.select()[0])
    def test_approval_required(self):
        self.profile['approved_source_form']=False
        with self.assertRaisesRegex(ValueError,'authorized'):self.select()
    def test_part_scope_is_exact(self):
        self.profile['applicable_part_numbers']=['5801124']
        with self.assertRaisesRegex(ValueError,'part-number'):self.select()
    def test_unknown_power_status_required(self):
        self.profile['power_contact_role']='ordinary_slt'
        with self.assertRaisesRegex(ValueError,'status'):self.select()
    def test_uncovered_circuit_leaves_ordinary_eligibility_unchanged(self):
        self.observations[0]['circuit_identifier']='U03AA';self.assertEqual(self.select(),({},None))
    def test_bad_contact_is_rejected(self):
        self.profile['power_contacts']={'E03':'+3V'}
        with self.assertRaisesRegex(ValueError,'power contacts'):self.select()
    def test_no_old_preview_authority(self):
        self.doc['schema']='source-bound-component-preview-authority-v1'
        with self.assertRaisesRegex(ValueError,'Unsupported'):self.select()
    def test_contradicting_component_powers_rejected(self):
        other=copy.deepcopy(self.profile);other['power_contacts']={'D03':'+3V'};other['printed_function']='C'
        self.doc['circuits']['S61DG']=other;self.observations.append({'circuit_identifier':'S61DG','function_label':'C'})
        with self.assertRaisesRegex(ValueError,'disagree'):self.select()
    def test_literal_secondary_variants_are_preserved(self):
        models={'ED001':{'nodes':[{'id':'AA','row':2,'column':50}],'printed_labels':[{'row':4,'column':51,'text':'001'}]},'ED002':{'nodes':[{'id':'AA','row':2,'column':50}],'printed_labels':[{'row':4,'column':51,'text':'002'}]}}
        labels=forms.source_labels([{'page':p,'node':'AA'}for p in models],models)
        self.assertEqual([x['text']for x in labels['interior_line_2']],['001','002'])
    def test_caption_blocks_are_spaced_and_caption_cells_reserved(self):
        nodes={}
        for portion,inp,out in [('A1','B02','B04'),('A2','B03','B05')]:
            nodes[portion]={'portion':portion,'function':'A','unit':'U03AA','above_block_caption':'SENSE AMP','_inputs':[{'pin':inp,'triangle':False}], '_outputs':[{'pin':out,'triangle':False}]}
        model={'portions':nodes,'signal_pins':{pin:{}for pin in ['B02','B03','B04','B05']},'edges':[],'layout_hints':{'row_step':1,'ranks':{'A1':0,'A2':0},'tops':{'A1':14,'A2':21},'first_bank_x':20,'right_margin':20}}
        positions,ports,exterior,routing=router.prepare(model)
        self.assertGreaterEqual(positions['A2']['top'],positions['A1']['top']+8)
        for pos in positions.values():
            cells={(x,pos['top']-1)for x in range(pos['x'],pos['x']+9)}
            self.assertTrue(cells<=routing.blocked)
            self.assertFalse(cells&set(routing.wires))
        self.assertTrue(router.verify(model,(positions,ports,exterior,routing)))

class SupplyTieEvidence(unittest.TestCase):
    def setUp(self):
        import build_card_data
        self.builder=build_card_data
        self.ground={'id':'AM','kind':'service','function':'SERV✲','unit':'GND','card_type':'','portion':'','source_reviewed':True,'non_card_evidence':'Printed non-card ground terminal','pins':[{'pin':'D08','side':'output','row':12}]}
    def test_reviewed_noncard_ground_is_explicit_authority(self):
        result=self.builder.annotation_supply_driver({'AM':self.ground},{'AM.D08'},{'D08':'GROUND'})
        self.assertEqual(result['level'],'GROUND')
    def test_real_card_is_not_an_annotation(self):
        self.ground['card_type']='0141';self.ground['portion']='A1'
        self.assertIsNone(self.builder.annotation_supply_driver({'AM':self.ground},{'AM.D08'},{'D08':'GROUND'}))
    def test_unreviewed_or_multidriver_ground_is_not_assumed(self):
        self.ground['source_reviewed']=False
        self.assertIsNone(self.builder.annotation_supply_driver({'AM':self.ground},{'AM.D08'},{'D08':'GROUND'}))
        self.ground['source_reviewed']=True
        self.assertIsNone(self.builder.annotation_supply_driver({'AM':self.ground},{'AM.D08','XX.D08'},{'D08':'GROUND'}))
    def test_power_name_alone_is_insufficient(self):
        self.assertIsNone(self.builder.annotation_supply_driver({'AM':self.ground},{'AM.D08'},{'D08':'+3V'}))
    def derive(self,second_undriven_occurrence=False):
        node={'id':'AA','card_type':'0529','portion':'F1','function':'SW','unit':'S61AY','pins':[{'side':'input','pin':None,'row':12},{'side':'output','pin':'D06','row':12}]}
        obs={'page':'FA541','node':'AA','portion':'F1','function_label':'SW','circuit_identifier':'S61AY','pins':copy.deepcopy(node['pins']),'_instance':('02B-A4',('H7',))}
        models={'FA541':{'nodes':[self.ground,node],'nets':[{'id':'ground','driver':'AM.D08','targets':['AA.']}]}}
        observations=[obs]
        if second_undriven_occurrence:
            observations.append(dict(copy.deepcopy(obs),page='FA542'))
            models['FA542']={'nodes':[copy.deepcopy(node)],'nets':[]}
        catalog={'listing_portions':['F1'],'_reviewed_component_forms':{'S61AY':{'printed_function':'SW','power_contact_role':'reviewed_special','contact_banks':'BD'}}}
        with tempfile.TemporaryDirectory()as td:
            previous=self.builder.ROOT
            try:
                self.builder.ROOT=Path(td);issues=[]
                model,_=self.builder.derive_semantics('0529',catalog,observations,models,{'D08':'GROUND'},issues)
            finally:self.builder.ROOT=previous
        return model,issues
    def test_source_proved_supply_tie_does_not_invent_internal_wire(self):
        model,issues=self.derive()
        self.assertEqual(model['edges'],[])
        self.assertEqual(model['portions']['F1']['_inputs'],[])
        self.assertEqual(len(model['source_supply_ties']),1)
        self.assertFalse(any(x['kind']=='observed pinless ports have no reconstructed internal edge'for x in issues))
    def test_undriven_use_of_same_portion_remains_unresolved(self):
        model,issues=self.derive(True)
        self.assertEqual(len(model['source_supply_ties']),1)
        self.assertTrue(any(x['kind']=='observed pinless ports have no reconstructed internal edge'for x in issues))

class CurrentSpecialRoundtrip(unittest.TestCase):
    """A published supplement cannot replace verified component display facts."""
    @classmethod
    def setUpClass(cls):
        import os,build_card_data
        cls.builder=build_card_data
        cls.root=Path(os.environ.get('ALD_TEST_REPO',Path(__file__).resolve().parents[2]))
        cls.authority=Path(os.environ.get('ALD_TEST_COMPONENT_AUTHORITY',cls.root/'json/Card-ALD/component-forms.json'))
        if not (cls.root/'json/Card types current/1524.json').is_file()or not cls.authority.is_file():
            raise unittest.SkipTest('Current accepted source corpus is not present')
    def fixture(self,card):
        spec,report=self.builder.build(card,root=self.root,component_authority_path=self.authority)
        self.assertIsNotNone(spec)
        overlay={'schema':'reviewed-card-build-overrides-v1','card_type':card,
            'power_contacts':copy.deepcopy(spec['power_contacts']),
            'source_bindings':copy.deepcopy(report['provenance']['source_bindings']),
            'reviewed_portions':{b['portion']:{'function':b['function'],'unit':b['circuit_identifier'],
                'ports':[{k:v for k,v in p.items()if k!='row'}for p in b['ports']]}for b in spec['boxes']},
            'reviewed_nets':copy.deepcopy(spec['nets']),
            'layout':{k:copy.deepcopy(spec[k])for k in ('canvas','wiring','exterior_pins','annotations')},
            'approved_variants':copy.deepcopy(spec['variants'])}
        overlay['layout']['boxes']=[{k:copy.deepcopy(v)for k,v in b.items()if k in ('portion','x','top','height','ports','compact_termination')}for b in spec['boxes']]
        for key in ('component_power_authority','box_captions','symbol_standard','header'):
            if key in spec:overlay[key]=copy.deepcopy(spec[key])
        return spec,overlay
    def rebuilt(self,card,overlay):
        with tempfile.TemporaryDirectory()as td:
            path=Path(td)/'override.json';path.write_text(json.dumps(overlay,ensure_ascii=False),encoding='utf-8')
            return self.builder.build(card,root=self.root,overrides_path=path,component_authority_path=self.authority)
    def test_sense_amp_caption_and_unknown_power_roundtrip(self):
        import generate_card
        first,overlay=self.fixture('1524');second,report=self.rebuilt('1524',overlay)
        self.assertIsNotNone(second,report['uncertainties'])
        self.assertEqual(generate_card.build(first)[0],generate_card.build(second)[0])
        self.assertEqual(second['component_power_authority']['role'],'not_established')
        self.assertEqual(len(second['box_captions']),4)
    def test_reserved_system_contact_authority_roundtrip(self):
        import generate_card
        first,overlay=self.fixture('0529');second,report=self.rebuilt('0529',overlay)
        self.assertIsNotNone(second,report['uncertainties'])
        self.assertEqual(generate_card.build(first)[0],generate_card.build(second)[0])
        self.assertEqual(second['component_power_authority']['source_contact_role'],'reserved_system_contact_positions')
        self.assertEqual(len(report['derived_model']['source_supply_ties']),10)
    def test_supplement_cannot_assign_unknown_power(self):
        _,overlay=self.fixture('1524');overlay['power_contacts']={'D03':'+3V'}
        with self.assertRaisesRegex(ValueError,'power contacts differ'):self.rebuilt('1524',overlay)
    def test_supplement_cannot_replace_source_caption(self):
        _,overlay=self.fixture('1524');overlay['box_captions'][0]['text']='GUESS'
        spec,report=self.rebuilt('1524',overlay)
        self.assertIsNone(spec)
        self.assertTrue(any('box_captions differs'in x.get('detail','')for x in report['uncertainties']))

if __name__=='__main__':unittest.main()

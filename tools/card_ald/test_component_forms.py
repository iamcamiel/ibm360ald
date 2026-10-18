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

class PortDecorationAuthority(unittest.TestCase):
    def fixture(self):
        semantic={'side':'input','pin':'B04','border_symbol':'X','source_edge_decorations':[
            {'terminal_id':'nodes:3/t:0','border_symbol':'X','border_decorations':[{'kind':'literal-border-mark','glyph':'X'}]}]}
        model={'portions':{'A1':{'_inputs':[semantic],'_outputs':[]}}}
        spec={'boxes':[{'portion':'A1','ports':[{'id':'input:1','side':'input','pin':'B04','triangle':False,'row':16}]}]}
        return spec,model
    def star(self,model):
        symbols={'prefix':[],'suffix':['✲']}
        source={'prefix':[],'suffix':[{'mark_id':'star:0','marks':[{'literal':'✲'}]}],
            'unplaced':[],'selected_presentation':{'prefix_mark_ids':[],
                'suffix_mark_ids':['star:0'],'unplaced_mark_ids':[]}}
        p=model['portions']['A1']['_inputs'][0]
        p['pin_symbols']=symbols
        p['source_pin_symbol_observations']=[{'terminal_id':'nodes:3/t:0',
            'pin_symbols':copy.deepcopy(symbols),'source_symbols':source}]
    def test_selected_typed_star_is_separate_from_physical_contact(self):
        spec,model=self.fixture();self.star(model)
        forms.copy_port_decorations(spec,model)
        port=spec['boxes'][0]['ports'][0]
        self.assertEqual(port['pin'],'B04')
        self.assertEqual(port['pin_symbols'],{'prefix':[],'suffix':['✲']})
        self.assertEqual(port['border_symbol'],'X')
    def test_known_source_symbol_variants_keep_an_exact_baseline_witness(self):
        spec,model=self.fixture();self.star(model)
        port=model['portions']['A1']['_inputs'][0]
        plain=copy.deepcopy(port['source_pin_symbol_observations'][0])
        plain['terminal_id']='nodes:4/t:0';plain['pin_symbols']={'prefix':[],'suffix':[]}
        plain['source_symbols']={'prefix':[],'suffix':[],'unplaced':[],
            'selected_presentation':{'prefix_mark_ids':[],'suffix_mark_ids':[],'unplaced_mark_ids':[]}}
        port['source_pin_symbol_observations'].append(plain)
        forms.copy_port_decorations(spec,model)
        self.assertEqual(spec['boxes'][0]['ports'][0]['pin_symbols'],{'prefix':[],'suffix':['✲']})

    def test_current_notation_profiles_are_preserved_idempotently(self):
        spec,model=self.fixture()
        node=model['portions']['A1'];node['_source_notation_baseline_witness']={'page':'ED001','node':'AA'}
        node['_source_notation_variants']=[{'page':'ED002','node':'AB','symbols':{'B04':{'prefix':[],'suffix':['✲']}}}]
        forms.copy_port_decorations(spec,model)
        expected=copy.deepcopy(spec['source_notation_profiles'])
        forms.copy_port_decorations(spec,model)
        self.assertEqual(spec['source_notation_profiles'],expected)
        self.assertEqual(expected[0]['source_variants'],node['_source_notation_variants'])

    def test_literal_suffix_does_not_invent_intrinsic_star(self):
        spec,model=self.fixture();model['portions']['A1']['_inputs'][0]['printed_pin']='B04✲'
        forms.copy_port_decorations(spec,model)
        self.assertNotIn('pin_symbols',spec['boxes'][0]['ports'][0])
    def test_supplement_cannot_drop_selected_intrinsic_star(self):
        spec,model=self.fixture();self.star(model)
        overlay={'reviewed_portions':{'A1':{'ports':[{'id':'input:1','side':'input','pin':'B04','border_symbol':'X'}]}}}
        with self.assertRaisesRegex(ValueError,'pin_symbols differs'):forms.copy_port_decorations(spec,model,overlay)

    def test_exact_typed_mark_does_not_change_geometry_or_contact(self):
        spec,model=self.fixture();before=copy.deepcopy(spec)
        forms.copy_port_decorations(spec,model)
        before['boxes'][0]['ports'][0]['border_symbol']='X'
        self.assertEqual(spec,before)
    def test_literal_suffix_is_not_source_edge_authority(self):
        spec,model=self.fixture();model['portions']['A1']['_inputs'][0]['source_edge_decorations']=[]
        with self.assertRaisesRegex(ValueError,'typed source'):forms.copy_port_decorations(spec,model)
    def test_duplicate_anonymous_ports_remain_valid_without_mark(self):
        spec,model=self.fixture();model['portions']['A1']['_inputs']=[{'side':'input','pin':None},{'side':'input','pin':None}]
        forms.copy_port_decorations(spec,model)
        self.assertNotIn('border_symbol',spec['boxes'][0]['ports'][0])
    def test_overlay_stable_id_cannot_claim_another_contact(self):
        spec,model=self.fixture();overlay={'reviewed_portions':{'A1':{'ports':[{'id':'input:1','side':'input','pin':'B05','border_symbol':'X'}]}}}
        with self.assertRaisesRegex(ValueError,'stable layout ID'):forms.copy_port_decorations(spec,model,overlay)


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
    def test_typed_special_border_symbols_survive_default_overlay(self):
        import generate_card
        expected={
            '1124':{(p,'input','B04')for p in ('A2','A3','A4','A5','A6','A7','A8','A9','AA','AB','AC')},
            '1524':{('A1','input','B10'),('A1','input','B08'),('A1','output','G09'),
                    ('B1','input','D07'),('B1','input','D10'),('B1','output','J09'),
                    ('C1','input','B05'),('C1','input','D05'),('C1','output','J13'),
                    ('D1','input','B13'),('D1','input','D13'),('D1','output','G13')}}
        for card,witnesses in expected.items():
            with self.subTest(card=card):
                first,overlay=self.fixture(card)
                marked={(b['portion'],p['side'],p['pin'])for b in first['boxes']for p in b['ports']if p.get('border_symbol')=='X'}
                self.assertEqual(marked,witnesses)
                second,report=self.rebuilt(card,overlay)
                self.assertIsNotNone(second,report['uncertainties'])
                self.assertEqual(first['boxes'],second['boxes'])
                self.assertEqual(first['nets'],second['nets'])
                self.assertEqual(generate_card.build(first)[0],generate_card.build(second)[0])
    def test_supplement_cannot_drop_current_typed_border_symbol(self):
        _,overlay=self.fixture('1124')
        port=next(p for n in overlay['reviewed_portions'].values()for p in n['ports']if p.get('border_symbol')=='X')
        del port['border_symbol']
        spec,report=self.rebuilt('1124',overlay)
        self.assertIsNone(spec)
        self.assertTrue(any('border_symbol differs'in x.get('detail','')for x in report['uncertainties']))

    def test_standard_heading_special_power_roundtrip(self):
        import generate_card
        for card in ('0536','0611','0709'):
            with self.subTest(card=card):
                first,overlay=self.fixture(card)
                overlay['header']={'schema':'card-ald-header-v1','part_number':'580'+card,
                    'card_width':'SINGLE CARD','reviewed_occurrences':0,'reviewed_pages':0,
                    'provisional_forms':[],'symbol_standard':'PRINTED ALD FORMS'}
                overlay['layout']['annotations']=[a for a in overlay['layout']['annotations']
                    if a['row']>=first['canvas']['header_rows']]
                second,report=self.rebuilt(card,overlay)
                self.assertIsNotNone(second,report['uncertainties'])
                self.assertTrue(all(a['row']>=second['canvas']['header_rows']for a in second['annotations']))
                self.assertEqual(second['header']['symbol_standard'],'PRINTED ALD FORMS')
                first['header']=copy.deepcopy(second['header'])
                first['annotations']=copy.deepcopy(overlay['layout']['annotations'])
                self.assertEqual(generate_card.build(first)[0],generate_card.build(second)[0])
                self.assertEqual(first['component_power_authority'],second['component_power_authority'])

    def test_supplement_cannot_assign_unknown_power(self):
        _,overlay=self.fixture('1524');overlay['power_contacts']={'D03':'+3V'}
        with self.assertRaisesRegex(ValueError,'power contacts differ'):self.rebuilt('1524',overlay)
    def test_supplement_cannot_replace_source_caption(self):
        _,overlay=self.fixture('1524');overlay['box_captions'][0]['text']='GUESS'
        spec,report=self.rebuilt('1524',overlay)
        self.assertIsNone(spec)
        self.assertTrue(any('box_captions differs'in x.get('detail','')for x in report['uncertainties']))

if __name__=='__main__':unittest.main()

"""Whole-witness symbol variants keep contacts, circuits and routes fixed."""
from copy import deepcopy
from pathlib import Path
import json,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(1,'D:/Github/IBM360/ibm360ald/tools/card_ald')
import card_source as S
import build_card_data as B
import collect_card_variants as C
import audit_card_uses as A

def typed(pin,side='input',star=False,edge=None):
    symbols={'prefix':[],'suffix':([{'mark_id':'s','marks':[{'literal':'✲'}]}] if star else []),'unplaced':[],
        'selected_presentation':{'prefix_mark_ids':[],'suffix_mark_ids':['s'] if star else [],'unplaced_mark_ids':[]}}
    decorations=[{'kind':'triangle','glyph':None,'observed_value':False}]
    if edge:decorations.append({'kind':'literal-border-mark','glyph':edge,'observed_value':edge})
    return {'pin':pin,'side':side,'row':1,'triangle':False,'_pin_number':pin,'_pin_number_status':'observed',
        '_terminal_id':'nodes:0/t:'+pin,'_symbols':symbols,'_border_decorations':decorations}

class SymbolVariants(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='D:/Github/IBM360/tmp');self.root=Path(self.temp.name)
        (self.root/'json/XX').mkdir(parents=True)
        self.box={'portion':'A1','function':'A','circuit_identifier':'U03AA','ports':[
            {'id':'in','side':'input','pin':'B04','row':1,'triangle':False},
            {'id':'out','side':'output','pin':'D06','row':3,'triangle':False}]}
        self.spec={'card_type':'1234','boxes':[self.box],'power_contacts':{},'variants':[]}
        self.path=self.root/'definition.json';self.path.write_text(json.dumps(self.spec))
    def tearDown(self):self.temp.cleanup()
    def page(self,name,star=False,edge=None):
        node={'id':'AA','source_reviewed':True,'location':'A-A1J6','card_type':'1234','portion':'A1','unit':'U03AA','function':'A',
            'pins':[{'pin':'B04','side':'input','row':1,'triangle':False,'border_marker':edge},
                    {'pin':'D06✲' if star else 'D06','side':'output','row':3,'triangle':False}]}
        (self.root/'json/XX'/f'{name}.json').write_text(json.dumps({'page':name,'source_reviewed':True,'nodes':[node]}))
    def test_complete_star_and_x_profile_is_source_witnessed(self):
        self.page('XX001',True,'X');r=C.collect('1234',self.path,self.root,publication_policy='complete-witnesses')
        self.assertEqual(r['counts']['complete_field_observation_witnesses'],1)
        override=r['variants'][0]['variant_definition']['box_overrides']['A1']
        self.assertEqual(override['port_symbols'],{'out':{'prefix':[],'suffix':['✲']}})
        self.assertEqual(override['border_symbols'],{'in':'X'})
        self.assertNotIn('port_triangles',override)
    def test_distinct_whole_card_patterns_are_not_combined_per_port(self):
        self.page('XX001',True);self.page('XX011',False,'X')
        r=C.collect('1234',self.path,self.root,publication_policy='complete-witnesses')
        self.assertEqual(r['counts']['conflicting_physical_card_sites'],1)
        self.assertEqual(len(r['variants']),2)
        for v in r['variants']:
            self.assertEqual(v['complete_witnesses'],1)
            o=v['variant_definition']['box_overrides']['A1']
            self.assertFalse('port_symbols' in o and 'border_symbols' in o)
    def test_audit_requires_declared_symbol_variant_even_when_boolean_form_matches(self):
        node={'function':'A','unit':'U03AA','pins':[typed('B04'),typed('D06','output',star=True)]}
        findings=A.compare_occurrence(node,self.box,A.expected_forms(self.spec)['A1'],{})
        self.assertTrue(any(f['status']=='discrepancy' for f in findings))
        self.spec['variants']=[{'number':1,'box_overrides':{'A1':{'port_symbols':{'out':{'prefix':[],'suffix':['✲']}}}}}]
        findings=A.compare_occurrence(node,self.box,A.expected_forms(self.spec)['A1'],{})
        self.assertFalse(any(f['status'] in ('discrepancy','source_uncertainty') for f in findings))
        self.assertTrue(any(f.get('variant_number')==1 for f in findings))
        self.spec['boxes'][0]['ports'][1]['pin_symbols']={'prefix':[],'suffix':['✲']}
        self.spec['variants']=[{'number':2,'box_overrides':{'A1':{'port_symbols':{'out':{'prefix':[],'suffix':[]}}}}}]
        node['pins'][1]=typed('D06','output')
        findings=A.compare_occurrence(node,self.box,A.expected_forms(self.spec)['A1'],{})
        self.assertFalse(any(f['status'] in ('discrepancy','source_uncertainty') for f in findings))
        self.assertTrue(any(f.get('variant_number')==2 for f in findings))

    def test_unknown_intrinsic_placement_is_a_hold_and_not_canonical_fill(self):
        port=typed('D06','output')
        port['_symbols']['unplaced']=[{'mark_id':'u','marks':[{'literal':'✲'}]}]
        node={'function':'A','unit':'U03AA','pins':[typed('B04'),port]}
        findings=A.compare_occurrence(node,self.box,A.expected_forms(self.spec)['A1'],{})
        self.assertTrue(any(f['status']=='source_uncertainty' and f['field']=='typed_symbols' for f in findings))
        form,observed,unmapped,ignored=C.observed_form(node,self.box,{})
        self.assertTrue(any('Unresolved typed source symbol' in m['reason'] for m in unmapped))
        self.assertNotIn('out',observed)

    def test_partial_profile_applies_only_to_exact_current_source_context(self):
        witness={'page':'XX001','node':'AA','node_pointer':'/nodes/0',
            'model_binding':{'path':'json/XX/XX001.json','sha256':'a'*64},'complete_portion_contacts':False,
            'conflicting_source_fields':False,'ports':[{'side':'output','pin':'D06',
                'pin_symbols':{'prefix':[],'suffix':['✲']},'border_symbol':None}]}
        self.spec['source_notation_profiles']=[{'portion':'A1','source_variants':[witness]}]
        node={'id':'AA','function':'A','unit':'U03AA','_source_page':'XX001','_source_pointer':'/nodes/0',
            '_source_model_binding':deepcopy(witness['model_binding']),'pins':[typed('B04'),typed('D06','output',star=True)]}
        forms=A.expected_forms(self.spec)['A1']
        good=A.compare_occurrence(node,self.box,forms,{})
        self.assertFalse(any(f['status'] in ('discrepancy','source_uncertainty') for f in good))
        self.assertTrue(any(f.get('source_notation_witness')==witness for f in good))
        self.assertEqual(self.spec['variants'],[])
        for field,value in [('_source_page','XX011'),('id','AB'),('_source_pointer','/nodes/1'),
            ('_source_model_binding',{'path':'json/XX/XX001.json','sha256':'b'*64})]:
            other=deepcopy(node);other[field]=value
            flags=A.compare_occurrence(other,self.box,forms,{})
            self.assertTrue(any(f['status']=='discrepancy' for f in flags),field)
    def test_builder_baseline_is_one_observed_pattern_not_union_of_stars(self):
        occurrences=[]
        for page,stars in [('XX001',(True,False)),('XX011',(False,True))]:
            occurrences.append({'page':page,'node':'AA','node_pointer':'/nodes/0','portion':'A1','circuit_identifier':'U03AA',
                'function_label':'A','_instance':('02A-A1','J6'),'pins':[typed('B04',star=stars[0]),typed('B05',star=stars[1])]})
        issues=[]
        with patch.object(B,'ROOT',self.root):
            model,_=B.derive_semantics('1234',{'listing_portions':['A1']},occurrences,{'XX001':{'nets':[]},'XX011':{'nets':[]}},B.SINGLE_POWER,issues)
        node=model['portions']['A1'];ports={p['pin']:p for p in node['_inputs']}
        self.assertEqual(ports['B04']['pin_symbols'],{'prefix':[],'suffix':['✲']})
        self.assertNotIn('pin_symbols',ports['B05'])
        self.assertEqual(node['_source_notation_baseline_witness']['page'],'XX001')
        self.assertEqual(len(node['_source_notation_variants']),2)
        self.assertFalse(any('symbol' in i['kind'] for i in issues))

if __name__=='__main__':unittest.main()

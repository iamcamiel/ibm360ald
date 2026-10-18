"""Uniform physical identities and explicitly reviewed pinless annotations."""
from copy import deepcopy
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(1,'D:/Github/IBM360/ibm360ald/tools/card_ald')
import card_source as C
import build_card_data as B

class TypedCardTerminals(unittest.TestCase):
    def typed(self,label,pin,side='output',**extra):
        return {'pin':label,'side':side,'row':12,'triangle':False,
            '_pin_number':pin,'_pin_number_status':'observed' if pin else 'unparsed-or-control',
            '_terminal_id':'nodes:0/t:0','_symbols':{'prefix':[],'suffix':[],'unplaced':[],
                'selected_presentation':{'prefix_mark_ids':[],'suffix_mark_ids':[],'unplaced_mark_ids':[]}},**extra}

    def test_typed_k_and_x_contacts_are_not_invalid_pin_letters(self):
        for label,pin in [('KD06','D06'),('B04X','B04')]:
            p=self.typed(label,pin,reference='AA.'+label)
            self.assertEqual(C.terminal_contact(p),pin)
            resolution=C.resolve_net_port({'id':'AA','pins':[p]},'AA.'+label,'output')
            self.assertEqual((resolution['status'],resolution['physical_contact']),('numbered',pin))
            self.assertEqual(resolution['raw_port']['_symbols'],p['_symbols'])

    def test_attach_preserves_literals_symbols_and_only_matching_source_slots(self):
        current=self.typed('KD06','D06');occ={'pins':[{k:v for k,v in current.items() if not k.startswith('_')}]}
        before=deepcopy(occ);C.attach_typed_terminals(occ,{'pins':[current]})
        self.assertEqual(occ['pins'][0]['pin'],'KD06');self.assertEqual(occ['pins'][0]['_symbols'],current['_symbols'])
        other=deepcopy(before);other['pins'][0]['row']=13;C.attach_typed_terminals(other,{'pins':[current]})
        self.assertNotIn('_pin_number',other['pins'][0])

    def test_reviewed_wire_control_is_pinless_only_for_exact_literal_slot_and_side(self):
        port=self.typed('L',None,'input',reference='AA.L.12')
        self.assertFalse(C.pinless_terminal(port))
        proof={'role':'anonymous-input-wire-annotation','literal':'L','terminal_id':port['_terminal_id'],
               'model_binding':{'path':'json/XX.json','sha256':'a'*64}}
        port['_reviewed_pinless_control']=proof
        self.assertTrue(C.pinless_terminal(port))
        r=C.resolve_net_port({'id':'AA','pins':[port]},'AA.L.12','input')
        self.assertEqual(r['status'],'pinless');self.assertEqual(r['raw_port']['pin'],'L')
        for key,value in [('side','output'),('pin','E'),('_terminal_id','nodes:1/t:0'),('source_unknown_pin',True)]:
            wrong=deepcopy(port);wrong[key]=value;self.assertFalse(C.pinless_terminal(wrong))

    def test_explicit_unknown_is_never_rescued_by_normalized_candidate(self):
        self.assertIsNone(C.terminal_contact(self.typed('B04','B04',source_unknown_pin=True)))

    def test_edge_x_comes_only_from_typed_border_and_conflicting_marks_stay_held(self):
        p=self.typed('B04X','B04','input')
        self.assertIsNone(C.terminal_border_symbol(p))
        p['_border_decorations']=[{'kind':'literal-border-mark','glyph':'X','observed_value':'X'}]
        self.assertEqual(C.terminal_border_symbol(p),'X')
        self.assertEqual(C.terminal_contact(p),'B04')
        for extra in ({'kind':'literal-border-mark','glyph':'K'},
                      {'kind':'triangle','glyph':None,'observed_value':True}):
            wrong=deepcopy(p);wrong['_border_decorations'].append(extra)
            with self.assertRaises(ValueError):C.terminal_border_symbol(wrong)

    def test_selected_pin_star_keeps_placement_and_does_not_duplicate_edge_x(self):
        p=self.typed('B04','B04');p['_symbols']={'prefix':[],'suffix':[{'mark_id':'s','marks':[{'literal':'✲'}]}],
            'unplaced':[],'selected_presentation':{'prefix_mark_ids':[],'suffix_mark_ids':['s'],'unplaced_mark_ids':[]}}
        self.assertEqual(C.terminal_pin_symbols(p),{'prefix':[],'suffix':['✲']})
        p['_border_decorations']=[{'kind':'literal-border-mark','glyph':'X'}]
        p['_symbols']['suffix'][0]['marks'].append({'literal':'X'})
        self.assertEqual(C.terminal_pin_symbols(p),{'prefix':[],'suffix':['✲']})
        p['_symbols']['suffix'][0]['marks'].extend([{'literal':'T'},{'literal':'8'}])
        self.assertEqual(C.terminal_pin_symbols(p),{'prefix':[],'suffix':['✲']})
        p['_symbols']['selected_presentation'].update(suffix_mark_ids=[],unplaced_mark_ids=['s'])
        with self.assertRaises(ValueError):C.terminal_pin_symbols(p)

    def test_semantic_x_keeps_physical_identity_and_exact_source_observations_separate(self):
        p=self.typed('B04','B04','input',_border_decorations=[{'kind':'literal-border-mark','glyph':'X','observed_value':'X'}])
        obs={'page':'XX001','node':'AA','portion':'A1','circuit_identifier':'T06CF','function_label':'PS',
             '_instance':('02A-A1','J6'),'pins':[p]}
        with tempfile.TemporaryDirectory(dir='D:/Github/IBM360/tmp') as temp,patch.object(B,'ROOT',Path(temp)):
            model,_=B.derive_semantics('1234',{'listing_portions':['A1']},[obs],{'XX001':{'nets':[]}},B.SINGLE_POWER,[])
        semantic=model['portions']['A1']['_inputs'][0]
        self.assertEqual((semantic['pin'],semantic['border_symbol'],semantic['triangle']),('B04','X',False))
        self.assertEqual(semantic['source_edge_decorations'][0]['terminal_id'],p['_terminal_id'])

    def test_semantic_contact_union_uses_typed_identity(self):
        pin=self.typed('KD06','D06')
        obs={'page':'XX001','node':'AA','portion':'A1','circuit_identifier':'U03AA','function_label':'A',
             '_instance':('02A-A1','J6'),'pins':[pin]}
        with tempfile.TemporaryDirectory(dir='D:/Github/IBM360/tmp') as temp,patch.object(B,'ROOT',Path(temp)):
            issues=[];model,_=B.derive_semantics('1234',{'listing_portions':['A1']},[obs],{'XX001':{'nets':[]}},B.SINGLE_POWER,issues)
        self.assertIn('D06',model['signal_pins'])
        self.assertFalse([i for i in issues if i['kind']=='unresolved physical/control label'])

if __name__=='__main__':unittest.main()

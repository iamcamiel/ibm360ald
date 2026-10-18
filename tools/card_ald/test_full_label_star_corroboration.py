from copy import deepcopy
from pathlib import Path
import json,os,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import card_source as S
ROOT=Path(os.environ.get('IBM360ALD_TEST_REPO',Path(__file__).resolve().parents[2]))

def port(side='suffix',contact='B02'):
    label=contact+'✲'if side=='suffix'else'✲'+contact
    star={'mark_id':'m:0','marks':[{'literal':'✲','meaning_status':'uninterpreted','order':0}]}
    full={'mark_id':'m:1','marks':[{'literal':c,'meaning_status':'uninterpreted','order':i}for i,c in enumerate(label)]}
    selected={'observation_id':'label:0','prefix_mark_ids':[],'suffix_mark_ids':[],'unplaced_mark_ids':[]}
    selected[side+'_mark_ids']=['m:0']
    annotation={'observation_id':'mark-field:0','prefix_mark_ids':[],'suffix_mark_ids':[],'unplaced_mark_ids':['m:1']}
    return {'pin':label,'printed_annotation':label,'_pin_number':contact,
            '_symbols':{'prefix':[star]if side=='prefix'else[],'suffix':[star]if side=='suffix'else[],
                        'unplaced':[full],'selected_presentation':selected,'observations':[deepcopy(selected),annotation]}}

class FullLabelCorroboration(unittest.TestCase):
    def test_exact_suffix_preserves_source(self):
        p=port();before=deepcopy(p)
        self.assertEqual(S.terminal_pin_symbols(p),{'prefix':[],'suffix':['✲']});self.assertEqual(p,before)
    def test_exact_prefix(self):self.assertEqual(S.terminal_pin_symbols(port('prefix')),{'prefix':['✲'],'suffix':[]})
    def hold(self,p):
        with self.assertRaises(ValueError):S.terminal_pin_symbols(p)
    def test_different_contact(self):
        p=port();p['_pin_number']='D02';self.hold(p)
    def test_annotation_not_same_literal(self):
        p=port();p['printed_annotation']='B03✲';self.hold(p)
    def test_normalized_contact_clone_keeps_typed_source_label(self):
        p=port();p['pin']='B02';self.assertEqual(S.terminal_pin_symbols(p),{'prefix':[],'suffix':['✲']})
    def test_projected_catalogue_keeps_exact_typed_mark_field(self):
        p=port();del p['printed_annotation'];self.assertEqual(S.terminal_pin_symbols(p),{'prefix':[],'suffix':['✲']})
    def test_component_evidence_retains_exact_known_contact(self):
        p=port();minimal={'_symbols':p['_symbols'],'_pin_number':'B02','_pin_number_status':'observed'};self.assertEqual(S.terminal_pin_symbols(minimal),{'prefix':[],'suffix':['✲']})
    def test_extra_control_letter(self):
        p=port();p['_symbols']['unplaced'][0]['marks'].append({'literal':'T','meaning_status':'uninterpreted','order':4});self.hold(p)
    def test_second_star(self):
        p=port();p['_symbols']['unplaced'][0]['marks'].append({'literal':'✲','meaning_status':'uninterpreted','order':4});self.hold(p)
    def test_other_label_does_not_become_annotation(self):
        p=port();p['_symbols']['observations'][1]['observation_id']='label:1';self.hold(p)
    def test_unplaced_label_order_is_not_guessed(self):
        p=port();p['_symbols']['unplaced'][0]['marks'][1]['order']=3;self.hold(p)
    def test_placed_prefix_suffix_conflict(self):
        p=port();p['_symbols']['observations'].append({'observation_id':'label:2','prefix_mark_ids':['m:0'],'suffix_mark_ids':[]});self.hold(p)
    def test_unplaced_only_label_still_holds(self):
        p=port();p['_symbols']['selected_presentation']['suffix_mark_ids']=[];self.hold(p)
    def test_same_full_label_in_different_mark_group_stays_ambiguous(self):
        p=port();g=deepcopy(p['_symbols']['unplaced'][0]);g['mark_id']='m:2';p['_symbols']['unplaced'].append(g);self.hold(p)
    def test_actual_km811_km821_five_labels(self):
        expected={('KM811','BG','B02'),('KM811','BC','D09'),('KM811','BE','D07'),('KM811','BF','D10'),('KM821','AN','D10')}
        seen=set()
        for page in ('KM811','KM821'):
            paths=[p for p in(ROOT/'json').rglob(page+'*.json')if p.parent.name!='Card types current']
            self.assertEqual(len(paths),1);doc=S.read(paths[0],ROOT)
            for n in doc['nodes']:
                for p in n.get('pins',[]):
                    key=(page,n.get('id'),S.physical_contact(p.get('pin')))
                    if key not in expected or p.get('side')!='output':continue
                    before=deepcopy(p);self.assertEqual(S.terminal_pin_symbols(p),{'prefix':[],'suffix':['✲']});self.assertEqual(p,before);seen.add(key)
        self.assertEqual(seen,expected)

if __name__=='__main__':unittest.main()

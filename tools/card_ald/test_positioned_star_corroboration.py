from copy import deepcopy
from pathlib import Path
import os,sys,unittest
ROOT=Path(os.environ.get('IBM360ALD_TEST_REPO',Path(__file__).resolve().parents[2]))
sys.path[:0]=[str(Path(__file__).resolve().parent),str(ROOT/'tools/card_ald')]
import card_source as S

def port(side='suffix'):
 def group(key):return {'mark_id':key,'marks':[{'literal':'✲','meaning_status':'uninterpreted','order':0}]}
 selected={'observation_id':'label:0','prefix_mark_ids':[],'suffix_mark_ids':[],'unplaced_mark_ids':[]};selected[side+'_mark_ids']=['m:0']
 annotation={'observation_id':'mark-field:0','prefix_mark_ids':[],'suffix_mark_ids':[],'unplaced_mark_ids':['m:1']}
 return {'pin':'D13✲','_symbols':{'prefix':[group('m:0')]if side=='prefix'else [],'suffix':[group('m:0')]if side=='suffix'else [],'unplaced':[group('m:1')],'selected_presentation':selected,'observations':[deepcopy(selected),annotation]}}
class PositionedStarCorroboration(unittest.TestCase):
 def test_exact_suffix_repeat_preserves_both_source_observations(self):
  p=port();old=deepcopy(p);self.assertEqual(S.terminal_pin_symbols(p),{'prefix':[],'suffix':['✲']});self.assertEqual(p,old)
 def test_exact_prefix_repeat(self):self.assertEqual(S.terminal_pin_symbols(port('prefix')),{'prefix':['✲'],'suffix':[]})
 def test_unplaced_only_still_holds(self):
  p=port();p['_symbols']['selected_presentation']['suffix_mark_ids']=[]
  with self.assertRaises(ValueError):S.terminal_pin_symbols(p)
 def test_contradictory_literal_placement_holds(self):
  p=port();p['_symbols']['observations'].append({'observation_id':'label:2','prefix_mark_ids':['m:0'],'suffix_mark_ids':[]})
  with self.assertRaises(ValueError):S.terminal_pin_symbols(p)
 def test_two_placed_stars_holds(self):
  p=port();p['_symbols']['selected_presentation']['suffix_mark_ids']=['m:0','m:0']
  with self.assertRaises(ValueError):S.terminal_pin_symbols(p)
 def test_unplaced_full_label_is_not_a_corroborating_annotation(self):
  p=port();p['_symbols']['observations'][1]['observation_id']='label:1'
  with self.assertRaises(ValueError):S.terminal_pin_symbols(p)
 def test_ambiguous_two_unplaced_stars_holds(self):
  p=port();g=deepcopy(p['_symbols']['unplaced'][0]);g['mark_id']='m:2';p['_symbols']['unplaced'].append(g)
  with self.assertRaises(ValueError):S.terminal_pin_symbols(p)
 def test_compound_unplaced_mark_holds(self):
  p=port();p['_symbols']['unplaced'][0]['marks'].append({'literal':'T','order':1})
  with self.assertRaises(ValueError):S.terminal_pin_symbols(p)
 def test_selected_unplaced_observation_still_holds(self):
  p=port();p['_symbols']['selected_presentation']=p['_symbols']['observations'][1]
  with self.assertRaises(ValueError):S.terminal_pin_symbols(p)
 def test_actual_rf701_twelve_raw_labels(self):
  paths=[p for p in(ROOT/'json').rglob('RF701*.json')if p.parent.name!='Card types current'];self.assertEqual(len(paths),1)
  d=S.read(paths[0],ROOT);outputs=[p for n in d['nodes']if n.get('card_type')=='0611'for p in n.get('pins',[])if p.get('side')=='output'and'✲'in str(p.get('pin'))]
  self.assertEqual(len(outputs),12)
  for p in outputs:self.assertEqual(S.terminal_pin_symbols(p),{'prefix':[],'suffix':['✲']})
if __name__=='__main__':unittest.main()

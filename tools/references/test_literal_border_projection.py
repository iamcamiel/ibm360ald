"""Literal straight borders and explicit physical contacts survive source projection."""
from copy import deepcopy
from pathlib import Path
import os,sys,unittest
ROOT=Path(os.environ.get('IBM360ALD_TEST_REPO',Path(__file__).resolve().parents[2]))
sys.path[:0]=[str(ROOT/'tools/card_ald'),str(ROOT/'tools/normalization'),str(ROOT/'tools/references')]
import card_source as S
import build_current_card_catalog as Catalog
from pages import normalize_page
class LiteralBorderProjection(unittest.TestCase):
 def test_typed_straight_border_is_false(self):
  port={'_border_decorations':[{'kind':'literal-border-mark','glyph':'│','observed_value':'│'}]}
  self.assertIs(S.wedge(port),False)
 def test_typed_straight_and_triangle_conflict_is_unknown(self):
  port={'_border_decorations':[{'kind':'literal-border-mark','glyph':'│'},{'kind':'triangle','observed_value':True}]}
  self.assertIsNone(S.wedge(port))
 def test_unrecognized_or_missing_border_remains_unknown(self):
  self.assertIsNone(S.wedge({'_border_decorations':[]}));self.assertIsNone(S.wedge({}))
 def test_legacy_border_glyph_and_triangle_conflict(self):
  self.assertIs(S.wedge({'border_glyph':'│'}),False)
  self.assertIs(S.wedge({'border_glyph':'◺'}),True)
  self.assertIsNone(S.wedge({'border_glyph':'│','triangle':True}))
 def test_explicit_contact_projection_keeps_original_literal_pin(self):
  raw={'side':'input','physical_pin':'D12','printed_label':'D12','border_glyph':'│','row':68};before=deepcopy(raw);p=Catalog.pin_record(raw)
  self.assertIsNone(p['pin']);self.assertEqual(p['printed_pin'],'D12');self.assertEqual(p['physical_pin_candidate'],'D12');self.assertEqual(raw,before)
 def test_explicit_contact_keeps_printed_star_separate(self):
  raw={'side':'output','physical_pin':'D10','printed_label':'D10✲','border_glyph':'◺'};p=Catalog.pin_record(raw)
  self.assertIsNone(p['pin']);self.assertEqual(p['printed_pin'],'D10✲');self.assertEqual(p['physical_pin_candidate'],'D10')
 def test_explicit_conflicting_contact_stays_unresolved(self):
  for raw in ({'pin':'D12','physical_pin':'D10'},{'physical_pin':'D12','printed_label':'D10'}):
   p=Catalog.pin_record(raw);self.assertIsNone(p['physical_pin_candidate']);self.assertEqual(p['physical_pin_parse_status'],'conflicting physical contact fields')
 def test_explicit_null_pin_is_not_filled_from_a_mirror(self):
  p=Catalog.pin_record({'pin':None,'physical_pin':'D12','printed_label':'D12'})
  self.assertIsNone(p['pin']);self.assertIsNone(p['physical_pin_candidate']);self.assertEqual(p['physical_pin_parse_status'],'unlabeled')
 def test_existing_exact_and_star_suffix_projection_is_unchanged(self):
  self.assertEqual(Catalog.pin_record({'pin':'B04'})['physical_pin_parse_status'],'exact')
  self.assertEqual(Catalog.pin_record({'pin':'B04✲'})['physical_pin_parse_status'],'asterisk suffix')
 def test_uniform_roundtrip_preserves_two_source_presentations(self):
  raw={'page':'XX001','source_reviewed':True,'nodes':[{'id':'AA','card_type':'3308','portion':'J1','function':'N','unit':'U03AF','pins':[{'side':'input','physical_pin':'D12','printed_label':'D12','border_glyph':'│','row':68},{'side':'output','physical_pin':'D10','printed_label':'D10✲','border_glyph':'◺','row':68}]}]};before=deepcopy(raw)
  uniform=normalize_page(raw,'json/XX001 TEST.json','1')['data'];node=S.view(uniform)['nodes'][0]
  self.assertEqual([S.terminal_contact(p)for p in node['pins']],['D12','D10']);self.assertEqual([S.wedge(p)for p in node['pins']],[False,True]);self.assertEqual(S.terminal_pin_symbols(node['pins'][1]),{'prefix':[],'suffix':['✲']});self.assertEqual(raw,before)
if __name__=='__main__':unittest.main()


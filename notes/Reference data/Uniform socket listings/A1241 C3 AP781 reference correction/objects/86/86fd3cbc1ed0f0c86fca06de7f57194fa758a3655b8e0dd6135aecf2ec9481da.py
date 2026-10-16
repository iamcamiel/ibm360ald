from copy import deepcopy
import unittest
from prepare_a1241_reference_addendum import fix_json

class ReferenceScope(unittest.TestCase):
 def setUp(self):self.record={'board':'02B-D1','sockets':['C3'],'card_type':'3388','part_number':'5803388','references':[{'ALD_page':'AP781','printed_portions':['A1','B1']},{'ALD_page':'AP741','printed_portions':['F1','H1']}]}
 def test_exact_group_only_and_input_unchanged(self):
  before={'records':[deepcopy(self.record)]};saved=deepcopy(before);after,changes=fix_json(before)
  self.assertEqual(before,saved);self.assertEqual(changes[0]['pointer'],'/records/0/references/1/ALD_page');self.assertEqual(len(changes),1)
  self.assertEqual(after['records'][0]['references'][1]['ALD_page'],'AP781');self.assertEqual(after['records'][0]['references'][0],self.record['references'][0])
 def test_other_site_untouched(self):
  before={'records':[dict(self.record,board='02A-D1'),dict(self.record,sockets=['C4'])]};after,changes=fix_json(before);self.assertEqual(after,before);self.assertEqual(changes,[])
 def test_mixed_portion_group_refused(self):
  record=deepcopy(self.record);record['references'][1]['printed_portions'].append('G1')
  with self.assertRaisesRegex(ValueError,'group unexpectedly'):fix_json({'records':[record]})
 def test_part_type_untouched(self):
  after,changes=fix_json({'board':'02B-D1','records':[dict(self.record)]});r=after['records'][0];self.assertEqual((r['part_number'],r['card_type']),('5803388','3388'))
 def test_bucket_moves_only_two_exact_entries(self):
  entries=[{'kind':'card portion','board':'02B-D1','sockets':['C3'],'card_type':'3388','part_number':'5803388','portion':p}for p in['F1','H1']];other=dict(entries[0],sockets=['C4']);before={'ALD_pages':{'AP741':entries+[other],'AP781':[dict(entries[0],portion='A1')]}};after,changes=fix_json(before)
  self.assertEqual(after['ALD_pages']['AP741'],[other]);self.assertEqual(after['ALD_pages']['AP781'][1:],entries);self.assertEqual(changes[0]['count'],2)
 def test_histories_not_traversed(self):
  before={'records':[deepcopy(self.record)],'history':[deepcopy(self.record)],'firm_resolution_application':deepcopy(self.record)};after,changes=fix_json(before);self.assertEqual(after['history'],before['history']);self.assertEqual(after['firm_resolution_application'],before['firm_resolution_application'])
 def test_type_predecessor_required(self):
  with self.assertRaisesRegex(ValueError,'already have'):fix_json({'records':[dict(self.record,card_type='3368')]})
 def test_idempotent_after_resolution(self):
  after,_=fix_json({'records':[deepcopy(self.record)]});again,changes=fix_json(after);self.assertEqual(again,after);self.assertEqual(changes,[])

if __name__=='__main__':unittest.main()

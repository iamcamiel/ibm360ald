from copy import deepcopy
import unittest
from prepare_a1241_addendum import fix_json


class ExactSite(unittest.TestCase):
    def setUp(self):
        self.record={'board':'02B-D1','sockets':['C3'],'part_number':'5803368','card_type':'3368'}

    def test_exact_site_only_and_source_input_unchanged(self):
        a=deepcopy(self.record);b=dict(self.record,sockets=['C4']);c=dict(self.record,board='02A-D1')
        before={'records':[a,b,c],'firm_resolution_application':{'old':deepcopy(a)}};saved=deepcopy(before)
        after,changes=fix_json(before)
        self.assertEqual(before,saved)
        self.assertEqual(after['records'][0]['part_number'],'5803388')
        self.assertEqual(after['records'][0]['card_type'],'3388')
        self.assertEqual(after['records'][1:],before['records'][1:])
        self.assertEqual(after['firm_resolution_application'],before['firm_resolution_application'])
        self.assertEqual(len(changes),2)

    def test_inherited_board_and_position_suffix_are_explicit(self):
        row=deepcopy(self.record);row.pop('board');row['sockets']=['C3T']
        after,changes=fix_json({'board':'02B-D1','records':[row]})
        self.assertEqual(after['records'][0]['card_type'],'3388');self.assertEqual(len(changes),2)

    def test_no_double_socket_inference(self):
        after,changes=fix_json({'records':[dict(self.record,sockets=['C3','C4'])]})
        self.assertEqual(changes,[])

    def test_buckets_do_not_move_and_history_is_immutable(self):
        before={'ALD_pages':{'AP741':[deepcopy(self.record)]},'history':[deepcopy(self.record)]}
        after,changes=fix_json(before)
        self.assertEqual(set(after['ALD_pages']),{'AP741'})
        self.assertEqual(after['history'],before['history'])
        self.assertEqual({c['pointer']for c in changes},{'/ALD_pages/AP741/0/part_number','/ALD_pages/AP741/0/card_type'})

    def test_unexpected_actual_card_is_not_overwritten(self):
        with self.assertRaisesRegex(ValueError,'Unexpected current C3 card type'):
            fix_json({'records':[dict(self.record,card_type='3308')]})

    def test_already_correct_is_not_rewritten(self):
        after,changes=fix_json({'records':[dict(self.record,card_type='3388',part_number='5803388')]})
        self.assertEqual(changes,[])


if __name__=='__main__':unittest.main()

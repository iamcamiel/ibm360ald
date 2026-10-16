from copy import deepcopy
import unittest
from prepare_rf081_addendum import fix_rf_json


class RFExactScope(unittest.TestCase):
    def setUp(self):
        self.card={'board':'02A-E1','sockets':['F5'],'kind':'single_card','card_type':'0512',
            'references':[{'ALD_page':'RF091','printed_portions':['C1']},{'ALD_page':'RF091','printed_portions':['B1']}],
            'printed_lines':['RF091 C1','B11 RF091BH4','RF091 B1']}

    def test_exact_card_portion_and_literal_only(self):
        data={'records':[deepcopy(self.card)]};old=deepcopy(data);after,changes=fix_rf_json(data)
        self.assertEqual(data,old);r=after['records'][0]
        self.assertEqual(r['references'][0]['ALD_page'],'RF081')
        self.assertEqual(r['references'][1]['ALD_page'],'RF091')
        self.assertEqual(r['printed_lines'],['RF081 C1','B11 RF091BH4','RF091 B1'])
        self.assertEqual(len(changes),2)

    def test_wrong_board_socket_or_type_stays_unchanged(self):
        cards=[dict(self.card,board='02B-E1'),dict(self.card,sockets=['F6']),dict(self.card,card_type='0514')]
        data={'records':cards};after,changes=fix_rf_json(data)
        self.assertEqual(after,data);self.assertEqual(changes,[])

    def test_unrelated_connector_pin_bucket_is_retained(self):
        card={'kind':'card portion','board':'02A-E1','sockets':['F5'],'card_type':'0512','portion':'C1'}
        connector={'kind':'connector pin','board':'02A-E1','sockets':['N6'],'pin':'B11','ALD_reference':'RF091BH4'}
        other={'kind':'card portion','board':'02A-E1','sockets':['F5'],'card_type':'0512','portion':'B1'}
        data={'ALD_pages':{'RF091':[card,connector,other],'RF081':[{'existing':True}]},'history':deepcopy(card)}
        after,changes=fix_rf_json(data)
        self.assertEqual(after['ALD_pages']['RF091'],[connector,other])
        self.assertEqual(after['ALD_pages']['RF081'],[{'existing':True},card])
        self.assertEqual(after['history'],data['history']);self.assertEqual(changes[0]['count'],1)

    def test_same_page_continuation_requires_explicit_primary(self):
        continuation={'board':'02A-E1','socket':'F5','kind':'continuation','continues_socket':'F5',
                      'references':[{'ALD_page':'RF091','printed_portions':['C1']}]}
        alone={'sockets':[continuation]};after,changes=fix_rf_json(alone)
        self.assertEqual(after,alone);self.assertEqual(changes,[])
        data={'sockets':[deepcopy(self.card),continuation]};after,changes=fix_rf_json(data)
        self.assertEqual(after['sockets'][1]['references'][0]['ALD_page'],'RF081')

    def test_bare_unassigned_bucket_keeps_connector(self):
        card={'kind':'card portion','board':'02A-E1','sockets':['F5'],'card_type':'0512','portion':'C1'}
        connector={'kind':'connector pin','board':'02A-E1','sockets':['N6'],'pin':'B11','ALD_reference':'RF091BH4'}
        after,changes=fix_rf_json({'RF091':[card,connector]})
        self.assertEqual(after['RF091'],[connector]);self.assertEqual(after['RF081'],[card])

    def test_inherited_source_board_is_bound(self):
        card=deepcopy(self.card);card.pop('board')
        after,changes=fix_rf_json({'board':'02A-E1','sockets':[card]})
        self.assertEqual(after['sockets'][0]['references'][0]['ALD_page'],'RF081')

    def test_histories_never_walked(self):
        data={'history':[deepcopy(self.card)],'review_metadata_snapshot':deepcopy(self.card)}
        self.assertEqual(fix_rf_json(data),(data,[]))


if __name__=='__main__':unittest.main()

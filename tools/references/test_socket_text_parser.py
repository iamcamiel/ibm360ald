import unittest
from socket_text_parser import column_spans,parse_listings


class SourceTextParser(unittest.TestCase):
    def page(self,left,middle=None,right=None,scan='1',page='A1111-01'):
        # Three real columns represented by two interior rules; pure parser
        # accepts three repeated rules, so add a fourth empty column here.
        cols=[left,middle or [],right or [],[]];height=max(map(len,cols))+3
        lines=[]
        for row in range(height):lines.append('│'.join((c[row] if row<len(c) else '').ljust(39) for c in cols))
        return {'page':page,'scan_id':scan,'board':'02A-A1','lines':lines}
    def test_outer_spans_are_not_dropped(self):
        p=self.page(['A2 SINGLE CARD','   5803308 3308','      MA905 A1'],right=['G2 SINGLE CARD','   5800141 0141','      KT755 A1'])
        self.assertEqual(len(column_spans(p['lines'])),4)
        r=parse_listings([p]);self.assertEqual([x['sockets'] for x in r['records']],[['A2'],['G2']])
    def test_top_title_does_not_hide_last_column(self):
        p=self.page(['A2 SINGLE CARD',' 5803308 3308'],right=['G2 SINGLE CARD',' 5800141 0141'])
        p['lines'].insert(0,'SOLID LOGIC DESIGN AUTOMATION'.ljust(120)+'SOCKET LISTING PAGE01')
        self.assertEqual(len(parse_listings([p])['records']),2)
    def test_dot_filled_reference_rows_keep_original_evidence(self):
        p=self.page(['A2 SINGLE CARD','   5803308 3308','........MA905...A1.B1','................C1.D1'])
        r=parse_listings([p])['records'][0];self.assertEqual(r['references'][0]['portions'],['A1','B1','C1','D1'])
        self.assertIn('........MA905',r['references'][0]['evidence'][0]['literal'])
    def test_indented_first_column_header(self):
        p=self.page(['        A2 SINGLE CARD','           5803308 3308','               MA905 A1'])
        self.assertEqual(parse_listings([p])['records'][0]['sockets'],['A2'])
    def test_double_card_second_socket_is_occupied(self):
        p=self.page(['A2 DOUBLE CARD','A3','   5804191 4191','      AP211 03 07'])
        self.assertEqual(parse_listings([p])['records'][0]['sockets'],['A2','A3'])
    def test_cross_column_continuation(self):
        p=self.page(['A2 SINGLE CARD'],['   5803308 3308','      MA905 A1 B1'])
        r=parse_listings([p])['records'][0];self.assertEqual(r['card_type'],'3308');self.assertEqual(len({s['column'] for s in r['source_spans']}),2)
    def test_cross_page_continuation_keeps_header_ownership(self):
        a=self.page([],right=['A2 SINGLE CARD'],scan='1');b=self.page(['A2 5803308 3308','      MA905 A1'],scan='2',page='A1111-02')
        r=parse_listings([a,b])['records'][0];self.assertEqual(r['header_source']['scan_id'],'1');self.assertEqual(r['card_type'],'3308')
    def test_connector_reference_not_card_portion(self):
        p=self.page(['A2 CABL 5802425','   ZA011 AA','   GOES TO 02B-A1J6','   A2 B04 MA905AA4'])
        r=parse_listings([p])['records'][0];self.assertEqual(r['connector_listing'],'ZA011');self.assertEqual(r['wire_code'],'AA');self.assertEqual(r['references'],[]);self.assertEqual(r['pins'][0]['pin'],'B04')
    def test_unused_portions_are_not_used_references(self):
        p=self.page(['A2 SINGLE CARD',' 5803308 3308','      MA905 A1',' UNUSED PORTIONS','      B C D'])
        r=parse_listings([p])['records'][0];self.assertEqual(r['unused_portions'],['B','C','D']);self.assertEqual(r['references'][0]['portions'],['A1'])
    def test_source_spans_reconstruct_every_semantic_row(self):
        p=self.page(['A2 SINGLE CARD',' 5803308 3308','      MA905 A1']);r=parse_listings([p])['records'][0]
        for span in r['source_spans']:self.assertEqual(p['lines'][span['row']][span['column']:span['column']+len(span['literal'])],span['literal'])
    def test_conflicting_values_remain_explicit_and_unselected(self):
        p=self.page(['A2 SINGLE CARD',' 5803308 3308',' 5803309 3309'])
        r=parse_listings([p]);self.assertIsNone(r['records'][0]['card_type']);self.assertTrue(any(x['kind']=='conflicting_printed_field' for x in r['issues']))
    def test_orphan_data_is_reported(self):
        p=self.page(['      MA905 A1'])
        self.assertTrue(any(x['kind']=='orphan_significant_line' for x in parse_listings([p])['issues']))


if __name__=='__main__':unittest.main()

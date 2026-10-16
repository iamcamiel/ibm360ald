from copy import deepcopy
import unittest
from socket_ald_pin_audit import audit_pins


def record(key='r1', board='02A-A1', sockets=None, card='3308', kind='single_card'):
    return dict(id=key, board=board, sockets=sockets or ['J6'], card_type=card, kind=kind,
                header_source={'scan_id':'61','row':1,'column':0,'literal':'J6 SINGLE CARD'})


def wrapper(pin='B02', location='A-A1J6', card='3308', **extra):
    node=dict(id='AA',location=location,card_type=card,portion='A1',function='A',
              pins=[dict(pin=pin,side='input',**extra)])
    return dict(scan_id='1',page='MA905',model_path='json/MA/MA905.json',node_pointer='/nodes/0',node=node)


class PinAuditTests(unittest.TestCase):
    def audit(self, records, nodes, **kwargs):
        original=deepcopy((records,nodes))
        result=audit_pins(records,nodes,**kwargs)
        self.assertEqual((records,nodes),original)
        return result

    def test_exact_site_and_wrapper_attribution(self):
        result=self.audit([record()], [wrapper()])
        row=result['results'][0]
        self.assertEqual(row['status'],'valid');self.assertEqual(row['node_pointer'],'/nodes/0')
        self.assertEqual(row['width_resolution']['source'],'exact_physical_site')
        self.assertEqual(row['width_resolution']['listing_record_ids'],['r1'])
        self.assertEqual(result['listing_width_evidence'][0]['header_source']['scan_id'],'61')

    def test_site_width_wins_over_card_type_width_elsewhere(self):
        records=[record(card='4633',kind='double_card'),record('r2',board='02B-E1',card='3308')]
        row=self.audit(records,[wrapper('G02')])['results'][0]
        self.assertEqual(row['width_resolution']['kind'],'double');self.assertEqual(row['status'],'valid')

    def test_double_card_second_socket_suffix_alias(self):
        row=self.audit([record(sockets=['K6','K7'],card='4191',kind='DOUBLE CARD')],
                       [wrapper('J13',location='02A-A1K7T',card='4191')])['results'][0]
        self.assertEqual(row['width_resolution']['kind'],'double');self.assertEqual(row['status'],'valid')

    def test_unlisted_or_unreadable_site_unanimous_fallback(self):
        for location in ['A-A1N7','A-A1�6']:
            row=self.audit([record()],[wrapper(location=location)])['results'][0]
            self.assertEqual(row['width_resolution']['source'],'card_type_consensus')
            self.assertEqual(row['width_resolution']['kind'],'single')

    def test_site_conflict_does_not_fallback(self):
        result=self.audit([record(),record('r2',kind='double_card')],[wrapper('G02')])
        self.assertEqual(result['results'][0]['status'],'width_conflict')
        self.assertFalse(result['results'][0]['range_checked']);self.assertTrue(result['issues'])

    def test_card_type_conflict_unclassified(self):
        row=self.audit([record(),record('r2',board='02B-A1',kind='double_card')],
                       [wrapper('J02',location='A-A1N7')])['results'][0]
        self.assertEqual(row['status'],'width_conflict');self.assertIsNone(row['width_resolution']['kind'])

    def test_exact_connector_suppresses_slt_fallback(self):
        records=[record(kind='connector'),record('r2',board='02B-E1')]
        row=self.audit(records,[wrapper('A99')])['results'][0]
        self.assertEqual(row['width_resolution']['status'],'non_slt_site')
        self.assertEqual(row['status'],'unknown_kind');self.assertEqual(row['severity'],'info')

    def test_unknown_listing_kind_not_inferred(self):
        row=self.audit([record(kind='unspecified')],[wrapper('G02')])['results'][0]
        self.assertEqual(row['width_resolution']['status'],'site_kind_unresolved')
        self.assertFalse(row['range_checked'])

    def test_aliases_controls_supply_and_mirrors(self):
        source=wrapper('OUT',printed_pin='D06')
        source['node']['pins'] += [dict(pin='2',side='input'),dict(pin=None,side='input'),
            dict(pin='8D03',side='input'),dict(pin='LB08',side='input'),
            dict(pin='D05',printed_pin='D09',side='input')]
        rows=self.audit([record()],[source])['results']
        self.assertEqual([row['status'] for row in rows],['valid','control','pinless','supply_contact','valid','mirror_conflict'])
        self.assertEqual(rows[4]['physical_contact'],'B08')

    def test_definition_checks_off_by_default(self):
        definitions={'3308':dict(card_type='3308',boxes=[dict(portion='A1',ports=[dict(pin='D04',side='input')])])}
        row=self.audit([record()],[wrapper('B02')],definitions=definitions)['results'][0]
        self.assertEqual(row['status'],'valid');self.assertTrue(row['definition_available']);self.assertFalse(row['definition_checked'])
        row=self.audit([record()],[wrapper('B02')],definitions=definitions,check_definitions=True)['results'][0]
        self.assertEqual(row['status'],'definition_discrepancy')

    def test_no_width_inference_from_four_digit_card_number(self):
        row=self.audit([],[wrapper('U12')])['results'][0]
        self.assertEqual(row['status'],'unknown_kind');self.assertFalse(row['range_checked'])

    def test_literal_board_units_remain_distinct(self):
        records=[record(board='01A-A1',kind='double_card'),record('r2',board='02A-A1')]
        row=self.audit(records,[wrapper('G02')])['results'][0]
        self.assertEqual(row['status'],'invalid_letter')
        self.assertEqual(row['width_resolution']['listing_record_ids'],['r2'])

    def test_conflicting_card_mirrors_prevent_fallback(self):
        source=wrapper(location='A-A1N7');source['node']['printed_card_portion']='4191A1'
        row=self.audit([record()],[source])['results'][0]
        self.assertEqual(row['width_resolution']['status'],'card_identity_unresolved')
        self.assertIsNone(row['width_resolution']['kind'])

    def test_malformed_pin_container_is_explicit(self):
        source=wrapper();source['node']['pins']=None
        report=self.audit([record()],[source])
        self.assertEqual(report['results'],[])
        self.assertEqual(report['issues'][0]['status'],'malformed_pin_container')

    def test_local_single_is_used_despite_global_width_conflict(self):
        records=[record(),record('r2',board='02B-E1',kind='double_card')]
        report=self.audit(records,[wrapper('G02')])
        self.assertEqual(report['results'][0]['status'],'invalid_letter')
        self.assertEqual(report['results'][0]['width_resolution']['kind'],'single')
        self.assertEqual(report['issues'][0]['status'],'card_type_width_conflict')

    def test_duplicate_record_ids_refused(self):
        with self.assertRaisesRegex(ValueError,'Duplicate listing record ID'):
            audit_pins([record(),record()],[wrapper()])


if __name__=='__main__':unittest.main()

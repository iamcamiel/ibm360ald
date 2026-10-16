import unittest
from copy import deepcopy

from socket_ald_reverse import audit_reverse


class Reverse(unittest.TestCase):
    def setUp(self):
        self.record = {'id': 'listing:1', 'board': '02B-E1', 'sockets': ['K6', 'K7'],
            'physical_sockets': ['K6', 'K7'], 'kind': 'double_card', 'card_type': '4191',
            'part_number': '5804191', 'unused_portions': [],
            'header_source': {'page': 'A1251-01', 'scan_id': '100', 'row': 2, 'column': 1},
            'source_spans': [{'literal': 'K6 DOUBLE CARD 5804191'}],
            'references': [{'page': 'AP001', 'portions': ['03'],
                'source_spans': [{'literal': 'AP001 03', 'row': 5, 'column': 1}]}]}
        self.wrapper = {'scan_id': '4', 'page': 'AP001', 'model_path': 'json/AP001.json',
            'node_pointer': '/nodes/0', 'node': {'id': 'AA', 'location': 'B-E1K6',
                'card_type': '4191', 'portion': '03', 'printed_card_portion': '419103'}}

    def run_case(self, record=None, wrapper=None, forward=None):
        return audit_reverse([record or self.record], [wrapper or self.wrapper], forward or [])

    def changed(self, **fields):
        w = deepcopy(self.wrapper); w['node'].update(fields); return w

    def test_unhit_exact_retains_reference_evidence(self):
        report = self.run_case(); result = report['results'][0]
        self.assertEqual(result['classification'], 'exact_same_page')
        self.assertEqual(result['exact_matches'][0]['reference_source_spans'], self.record['references'][0]['source_spans'])
        self.assertEqual(result['exact_matches'][0]['listing'], {'id': 'listing:1', 'record_index': 0})
        self.assertEqual(report['listing_evidence']['listing:1']['header_source'], self.record['header_source'])

    def test_forward_exact_hits_only(self):
        match = {'binding': {'model_path': self.wrapper['model_path'], 'node_pointer': '/nodes/0'}}
        r = self.run_case(forward=[{'classification': 'exact', 'matches': [match]}])
        self.assertEqual(r['results'], [])
        self.assertEqual(r['coverage']['forward_exact_hit_nodes'], 1)
        r = self.run_case(forward=[{'classification': 'location_mismatch', 'matches': [], 'candidates': [match]}])
        self.assertEqual(r['coverage']['reverse_examined_nodes'], 1)

    def test_reviewed_overlay_is_separately_counted(self):
        match = {'binding': self.wrapper}
        r = self.run_case(forward=[{'classification': 'reviewed_overlay_exact', 'matches': [match]}])
        self.assertEqual(r['coverage']['reviewed_overlay_hit_nodes'], 1)
        self.assertEqual(r['coverage']['forward_exact_hit_nodes'], 0)

    def test_ordinary_and_overlay_same_node_count_once(self):
        matches = [{'binding': self.wrapper}]
        r = self.run_case(forward=[{'classification': 'exact', 'matches': matches},
            {'classification': 'reviewed_overlay_exact', 'matches': matches}])
        self.assertTrue(r['coverage']['partition_complete'])
        self.assertEqual(r['coverage']['reviewed_overlay_hit_nodes'], 0)

    def test_other_page_is_review_only_not_correction(self):
        w = deepcopy(self.wrapper); w['page'] = 'AP041'
        r = self.run_case(wrapper=w)['results'][0]
        self.assertEqual(r['classification'], 'exact_identity_other_page')
        self.assertFalse(r['source_changes_applied'])

    def test_both_scans_remain_and_multiple_listing_occurrences(self):
        w = deepcopy(self.wrapper); w.update(scan_id='5', model_path='json/AP001-02.json')
        record = deepcopy(self.record); record['id'] = 'listing:2'
        r = audit_reverse([self.record, record], [self.wrapper, w], [])
        self.assertEqual(len(r['results']), 2)
        self.assertTrue(all(len(x['exact_matches']) == 2 for x in r['results']))

    def test_second_socket_and_position_qualifiers(self):
        r = self.run_case(wrapper=self.changed(location='02B-E1K7T'))
        self.assertEqual(r['results'][0]['classification'], 'exact_same_page')

    def test_no_adjacent_socket_inference(self):
        record = deepcopy(self.record); record['sockets'] = ['K6']; record['physical_sockets'] = ['K6']
        r = self.run_case(record=record, wrapper=self.changed(location='B-E1K7'))['results'][0]
        self.assertEqual(r['classification'], 'two_axis_candidates')
        self.assertEqual(r['candidates'][0]['differing_axes'], ['location'])

    def test_frame_number_is_significant(self):
        r = self.run_case(wrapper=self.changed(location='01B-E1K6'))['results'][0]
        self.assertEqual(r['classification'], 'two_axis_candidates')

    def test_unreadable_card_preserved(self):
        w = self.changed(card_type='41�1', printed_card_portion='41�103')
        r = self.run_case(wrapper=w)['results'][0]
        self.assertEqual(r['classification'], 'unresolved_identity')
        self.assertEqual(r['candidates'][0]['unresolved_axes'], ['card_type'])
        self.assertEqual(r['binding']['node']['card_type'], '41�1')

    def test_conflicting_mirrors_never_exact(self):
        r = self.run_case(wrapper=self.changed(printed_card_portion='463303'))['results'][0]
        self.assertEqual(r['classification'], 'unresolved_identity')
        self.assertEqual(r['exact_matches'], [])
        self.assertIn('conflicting_card_type', r['issues'])

    def test_source_page_conflict_never_exact(self):
        w = dict(self.wrapper, source_page_conflict=True)
        r = self.run_case(wrapper=w)['results'][0]
        self.assertEqual(r['classification'], 'unresolved_identity')
        self.assertEqual(r['exact_matches'], [])

    def test_unused_portion_exact_literal_only(self):
        record = deepcopy(self.record); record['unused_portions'] = ['06']
        w = self.changed(portion='06', printed_card_portion='419106')
        self.assertEqual(self.run_case(record=record, wrapper=w)['results'][0]['classification'], 'portion_marked_unused')
        record['unused_portions'] = ['0']
        self.assertEqual(self.run_case(record=record, wrapper=w)['results'][0]['classification'], 'portion_unlisted_at_site')

    def test_site_card_mismatch(self):
        w = self.changed(card_type='4633', printed_card_portion='463303')
        r = self.run_case(wrapper=w)['results'][0]
        self.assertEqual(r['classification'], 'site_card_type_mismatch')
        self.assertEqual(r['candidates'][0]['differing_axes'], ['card_type'])

    def test_no_arbitrary_candidate_selected(self):
        a = deepcopy(self.record); a['card_type'] = '4633'; a['id'] = 'listing:2'
        b = deepcopy(self.record); b['board'] = '02A-E1'; b['id'] = 'listing:3'
        w = self.changed(portion='06', printed_card_portion='419106')
        r = audit_reverse([self.record, a, b], [w], [])['results'][0]
        self.assertEqual(r['classification'], 'portion_unlisted_at_site')
        self.assertEqual(len(r['site_records']), 2)
        self.assertEqual(len(r['candidates']), 1)

    def test_annotation_exclusion_does_not_hide_unresolved_gate(self):
        a = dict(self.wrapper, node_pointer='/nodes/1', node={'id': 'junction', 'function': 'JUNCTION'})
        b = dict(self.wrapper, node_pointer='/nodes/2', node={'id': 'bad', 'function': 'P'})
        c = dict(self.wrapper, node_pointer='/nodes/3', node={'id': 'bad2', 'location': '�'})
        r = audit_reverse([self.record], [self.wrapper, a, b, c], [])
        self.assertEqual(r['classifications']['annotation_excluded'], 1)
        self.assertEqual(r['classifications']['identity_absent'], 1)
        self.assertEqual(r['classifications']['unresolved_identity'], 1)
        self.assertEqual(r['coverage']['reverse_examined_nodes'], 3)
        self.assertTrue(r['coverage']['partition_complete'])

    def test_explicit_non_cards_have_separate_coverage(self):
        examples = [
            {'CAS_box': 'A1', 'address': '0020'},
            {'kind': 'reference table box', 'pins': []},
            {'function': 'OR', 'unit': 'DOT', 'pins': [{'pin': ''}]},
            {'node_kind': 'mechanical', 'field_lines': [{'text': 'SW'}], 'pins': [{'pin': '1C'}]},
            {'node_kind': 'service', 'unit': 'GND', 'pins': [{'pin': 'BUS'}]},
            {'body': ['✲ENTR✲', 'A7015'], 'pins': ['B02']},
        ]
        wrappers = [dict(self.wrapper, node_pointer=f'/nodes/{i}', node=node) for i, node in enumerate(examples)]
        r = audit_reverse([self.record], wrappers, [])
        self.assertEqual(r['classifications'], {'explicit_non_card': 6})
        self.assertEqual(r['coverage']['non_card_excluded_nodes'], 6)
        self.assertEqual(r['coverage']['reverse_examined_nodes'], 0)
        self.assertTrue(r['coverage']['partition_complete'])
        self.assertTrue(all(x['exclusion_reason'] for x in r['results']))

    def test_missing_identity_and_contact_pins_are_not_annotations(self):
        examples = [{}, {'pins': ['B02']}, {'field_lines': [{'text': 'Unknown'}]},
                    {'grid': '1A', 'top_row': 2, 'bottom_row': 8}]
        wrappers = [dict(self.wrapper, node_pointer=f'/nodes/{i}', node=node) for i, node in enumerate(examples)]
        r = audit_reverse([self.record], wrappers, [])
        self.assertEqual(r['classifications'], {'identity_absent': 4})
        self.assertEqual(r['coverage']['annotation_excluded_nodes'], 0)

    def test_card_identity_prevents_non_card_flag_from_hiding_a_block(self):
        w = self.changed(node_kind='dot', unit='DOT')
        self.assertEqual(self.run_case(wrapper=w)['results'][0]['classification'], 'exact_same_page')

    def test_partial_location_does_not_turn_service_or_dot_into_a_card(self):
        examples = [{'function':'OR','unit':'DOT','location':'A-B3'},
                    {'function':'SERV✲','technology':'SYNC','part':'','card':'A-D3F8','location':'6C-AH'},
                    {'function':'INT✲','card_type':'CABL','location':'E-A1B2','entry_block':True},
                    {'function':'OR','location':'B-B4','A1_card_portion_applicable':False},
                    {'function':'A','location':'A-C2','annotation_block':True}]
        wrappers = [dict(self.wrapper,node_pointer=f'/nodes/{i}',node=n) for i,n in enumerate(examples)]
        r = audit_reverse([self.record],wrappers,[])
        self.assertEqual(r['classifications'],{'explicit_non_card':5})

    def test_service_flag_cannot_hide_a_card_or_damaged_card_alias(self):
        for fields in ({'service_element':True},
                       {'function':'SERV✲','card':'41�103','location':'B-E1K6'}):
            w=self.changed(**fields)
            r=self.run_case(wrapper=w)['results'][0]
            self.assertNotEqual(r['classification'],'explicit_non_card')

    def test_duplicate_bindings_and_unknown_forward_binding_fail(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate ALD node'):
            audit_reverse([self.record], [self.wrapper, self.wrapper], [])
        with self.assertRaisesRegex(ValueError, 'unknown node'):
            self.run_case(forward=[{'classification': 'exact', 'matches': [{'binding': {'model_path': 'other', 'node_pointer': '/nodes/0'}}]}])

    def test_duplicate_listing_ids_fail(self):
        with self.assertRaisesRegex(ValueError, 'duplicate listing'):
            audit_reverse([self.record, self.record], [self.wrapper], [])

    def test_inputs_and_returned_proofs_are_detached(self):
        record = deepcopy(self.record); wrapper = deepcopy(self.wrapper)
        r = audit_reverse([record], [wrapper], [])
        self.assertEqual(record, self.record); self.assertEqual(wrapper, self.wrapper)
        r['results'][0]['binding']['node']['id'] = 'changed'
        r['listing_evidence']['listing:1']['source_spans'].clear()
        self.assertEqual(record, self.record); self.assertEqual(wrapper, self.wrapper)


if __name__ == '__main__':
    unittest.main()

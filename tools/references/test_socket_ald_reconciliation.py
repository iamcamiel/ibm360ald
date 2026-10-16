import unittest
from copy import deepcopy

from socket_ald_reconciliation import reconcile_references


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.record = {'id': 'listing:1', 'board': '02B-E1', 'sockets': ['K6', 'K7'],
            'physical_sockets': ['K6', 'K7'], 'kind': 'double_card', 'card_type': '4191',
            'header_source': {'page': 'A1251-01', 'scan_id': '134'},
            'references': [{'page': 'AP413', 'portions': ['03', '06'],
                'source_spans': [{'row': 39, 'column': 141, 'literal': '      AP413 03 06'}]}]}

    def node(self, portion='03', page='AP433', pointer='/nodes/0', **changes):
        return {'model_path': 'json/' + page + '.json', 'model_sha256': 'a' * 64,
            'text_path': 'ALD/' + page + '.txt', 'text_sha256': 'b' * 64,
            'scan_id': '1', 'page': page, 'node_pointer': pointer,
            'node': {'id': 'AA', 'location': 'B-E1K6', 'card_type': '4191',
                'portion': portion, 'printed_card_portion': '4191' + portion, **changes}}

    def forward(self, records=None, status='missing_block'):
        return [{'claim': {'record_id': r['id'], 'reference_index': i, 'portion_index': j},
                 'classification': status} for r in (records or [self.record])
                for i, ref in enumerate(r['references']) for j, _ in enumerate(ref['portions'])]

    def run_case(self, nodes=None, record=None, status='missing_block'):
        records = [record or self.record]
        return reconcile_references(records,
            nodes if nodes is not None else [self.node(), self.node('06', pointer='/nodes/1')],
            self.forward(records, status))

    def test_unique_counterpart_is_link_not_source_correction(self):
        report = self.run_case(); result = report['results'][0]
        self.assertEqual(result['classification'], 'unique_counterpart_page')
        self.assertEqual(result['literal_page'], 'AP413')
        self.assertEqual(result['chosen_counterpart_page'], 'AP433')
        self.assertEqual(result['reference_source_spans'], self.record['references'][0]['source_spans'])
        self.assertFalse(result['source_page_correction_asserted'])
        self.assertFalse(report['source_changes_applied'])
        self.assertEqual(report['counts']['portion_claims'], 2)

    def test_all_portions_required_before_unique_page(self):
        r = self.run_case(nodes=[self.node()])['results'][0]
        self.assertEqual(r['classification'], 'incomplete_counterpart')
        self.assertEqual(r['reason'], 'some_portions_without_exact_witness')
        self.assertEqual(r['portions'][0]['candidate_pages'], ['AP433'])
        self.assertEqual(r['portions'][1]['candidate_pages'], [])
        self.assertIsNone(r['chosen_counterpart_page'])

    def test_no_witness_is_distinct_from_incomplete(self):
        r = self.run_case(nodes=[])['results'][0]
        self.assertEqual(r['classification'], 'no_counterpart')
        self.assertEqual(r['reason'], 'no_exact_witness')

    def test_disjoint_witness_pages_do_not_choose(self):
        r = self.run_case(nodes=[self.node(), self.node('06', 'AP434')])['results'][0]
        self.assertTrue(r['all_portions_supported'])
        self.assertEqual(r['common_candidate_pages'], [])
        self.assertEqual(r['classification'], 'incomplete_counterpart')
        self.assertEqual(r['reason'], 'no_common_page_for_all_portions')
        self.assertIsNone(r['chosen_counterpart_page'])

    def test_intersection_not_union_selects_page(self):
        nodes = [self.node(), self.node('03', 'AP434'), self.node('06', pointer='/nodes/1')]
        r = self.run_case(nodes=nodes)['results'][0]
        self.assertEqual(r['chosen_counterpart_page'], 'AP433')
        self.assertEqual(r['portions'][0]['candidate_pages'], ['AP433', 'AP434'])

    def test_ambiguous_counterparts_preserve_all_nodes_and_pages(self):
        nodes = [self.node(), self.node('06', pointer='/nodes/1'),
                 self.node('03', 'AP434'), self.node('06', 'AP434', '/nodes/1')]
        r = self.run_case(nodes=nodes)['results'][0]
        self.assertEqual(r['classification'], 'ambiguous_counterpart_pages')
        self.assertEqual(r['common_candidate_pages'], ['AP433', 'AP434'])
        self.assertIsNone(r['chosen_counterpart_page'])

    def test_already_verified_prefers_literal_even_if_other_pages_exist(self):
        record = deepcopy(self.record); record['references'][0]['page'] = 'AP433'
        nodes = [self.node(), self.node('06', pointer='/nodes/1'),
                 self.node('03', 'AP434'), self.node('06', 'AP434', '/nodes/1')]
        r = self.run_case(record=record, nodes=nodes, status='multiple_exact')['results'][0]
        self.assertEqual(r['classification'], 'already_verified')
        self.assertEqual(r['chosen_counterpart_page'], 'AP433')
        # Merely trusting an exact flag would hide an unsupported literal page.
        r = self.run_case(nodes=nodes, status='exact')['results'][0]
        self.assertEqual(r['classification'], 'ambiguous_counterpart_pages')

    def test_duplicate_portions_and_distinct_scan_variants_remain(self):
        record = deepcopy(self.record); record['references'][0]['portions'] = ['03', '03']
        second = self.node(pointer='/nodes/1'); second['node']['id'] = 'AB'
        scan = self.node(); scan.update(model_path='json/AP433-02.json', scan_id='2')
        report = self.run_case(record=record, nodes=[self.node(), second, scan])
        r = report['results'][0]
        self.assertEqual(len(r['portions']), 2)
        self.assertTrue(all(len(p['node_evidence_ids']) == 3 for p in r['portions']))
        self.assertEqual(len(report['node_evidence']), 3)
        self.assertEqual(report['counts']['portion_claims'], 2)

    def test_board_alias_and_explicit_double_socket_without_adjacent_guess(self):
        nodes = [self.node(location='02B-E1K7T'), self.node('06', pointer='/nodes/1', location='B-E1K7')]
        self.assertEqual(self.run_case(nodes=nodes)['results'][0]['classification'], 'unique_counterpart_page')
        record = deepcopy(self.record); record['sockets'] = record['physical_sockets'] = ['K6']
        self.assertEqual(self.run_case(record=record, nodes=nodes)['results'][0]['classification'], 'no_counterpart')
        nodes = [self.node(location='01B-E1K6'), self.node('06', pointer='/nodes/1', location='01B-E1K6')]
        self.assertEqual(self.run_case(nodes=nodes)['results'][0]['classification'], 'no_counterpart')

    def test_unknown_and_conflicting_mirrors_cannot_be_exact(self):
        for changes in [{'printed_card_portion': '4191�3'},
                        {'printed_card_portion': '463303'}, {'location': 'B-E1K�'}]:
            with self.subTest(changes=changes):
                r = self.run_case(nodes=[self.node(**changes), self.node('06', pointer='/nodes/1')])
                self.assertEqual(r['results'][0]['classification'], 'incomplete_counterpart')
        record = deepcopy(self.record); record['card_type'] = '41�1'
        self.assertEqual(self.run_case(record=record)['results'][0]['classification'], 'no_counterpart')

    def test_source_page_conflict_and_annotations_not_indexed(self):
        bad = self.node(); bad['source_page_conflict'] = True
        annotation = self.node(pointer='/nodes/2'); annotation['node'] = {'function': 'JUNCTION'}
        report = self.run_case(nodes=[bad, annotation, self.node('06', pointer='/nodes/1')])
        self.assertEqual(report['results'][0]['classification'], 'incomplete_counterpart')
        self.assertEqual(report['counts']['fully_resolved_source_nodes'], 1)
        self.assertEqual(report['counts']['unresolved_or_non_card_source_nodes'], 2)

    def test_forward_claim_coverage_rejects_missing_duplicates_and_unknown(self):
        forward = self.forward()
        with self.assertRaisesRegex(ValueError, 'cover every listed portion'):
            reconcile_references([self.record], [], forward[:1])
        with self.assertRaisesRegex(ValueError, 'duplicate forward claim'):
            reconcile_references([self.record], [], forward + forward[:1])
        bad = deepcopy(forward); bad[0]['claim']['record_id'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            reconcile_references([self.record], [], bad)

    def test_duplicate_record_and_node_keys_fail(self):
        with self.assertRaisesRegex(ValueError, 'duplicate listing record'):
            reconcile_references([self.record, self.record], [], self.forward())
        with self.assertRaisesRegex(ValueError, 'Duplicate source node'):
            self.run_case(nodes=[self.node(), self.node()])
        bad = self.node(); bad.pop('node_pointer')
        with self.assertRaisesRegex(ValueError, 'model_path and node_pointer'):
            self.run_case(nodes=[bad])

    def test_empty_groups_and_no_reference_records_accounted(self):
        record = deepcopy(self.record); record['references'][0]['portions'] = []
        r = self.run_case(record=record)
        self.assertEqual(r['results'][0]['reason'], 'no_listed_portions')
        self.assertEqual(r['counts']['portion_claims'], 0)
        record['references'] = []
        r = self.run_case(record=record)
        self.assertEqual(r['counts']['reference_groups'], 0)
        self.assertTrue(r['counts']['all_claims_accounted'])

    def test_detached_inputs_and_proofs_no_large_pin_array(self):
        records = [deepcopy(self.record)]; nodes = [self.node(), self.node('06', pointer='/nodes/1')]
        nodes[0]['node']['pins'] = [{'pin': 'D04'}]
        before = deepcopy((records, nodes)); report = reconcile_references(records, nodes, self.forward(records))
        self.assertEqual((records, nodes), before)
        report['results'][0]['reference_source_spans'].clear()
        proof = next(iter(report['node_evidence'].values()))
        self.assertNotIn('pins', proof['observed'])
        proof['observed']['id'] = 'changed'
        self.assertEqual((records, nodes), before)


if __name__ == '__main__':
    unittest.main()

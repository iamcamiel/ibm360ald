import unittest
from copy import deepcopy
from socket_ald_matching import match_claim,normalize_identity,normalize_location,prepare_nodes

class Matching(unittest.TestCase):
    def setUp(self):
        self.claim={'page':'AP001','board':'02B-E1','sockets':['K6','K7'],'card_type':'4191','portion':'03'}
        self.node={'scan_id':'1','page':'AP001','model_path':'page.json','node_pointer':'/nodes/0',
                   'node':{'id':'AA','location':'B-E1K6','card_type':'4191','portion':'03','printed_card_portion':'419103'}}
    def result(self,**fields):
        n=deepcopy(self.node);n['node'].update(fields);return match_claim(self.claim,[n])
    def test_exact(self):self.assertEqual(self.result()['classification'],'exact')
    def test_double_second_half(self):self.assertEqual(self.result(location='02B-E1K7T')['classification'],'exact')
    def test_empty_derived_members_do_not_erase_printed_members(self):
        c=dict(self.claim,physical_sockets=[])
        self.assertEqual(match_claim(c,[self.node])['classification'],'exact')
    def test_socket_suffix_only(self):
        self.assertEqual(normalize_location('02A-E1A3B')['sockets'],['A3'])
        self.assertEqual(normalize_location('02A-E1A3T')['board'],'02A-E1')
    def test_unit_is_significant(self):self.assertEqual(self.result(location='01B-E1K6')['classification'],'location_mismatch')
    def test_leading_zero_card(self):
        c=dict(self.claim,card_type='0141',portion='A1');n=deepcopy(self.node);n['node'].update(card_type='0141',portion='A1',printed_card_portion='0141A1')
        self.assertEqual(match_claim(c,[n])['classification'],'exact')
        n['node']['card_type']='141';self.assertEqual(match_claim(c,[n])['classification'],'unresolved_print')
    def test_repeated_real_boxes(self):
        n=deepcopy(self.node);n['node']['id']='AB';n['node_pointer']='/nodes/1'
        r=match_claim(self.claim,[self.node,n]);self.assertEqual(r['classification'],'multiple_exact');self.assertEqual(len(r['matches']),2)
    def test_conflicting_printed_mirror(self):self.assertEqual(self.result(printed_card_portion='463303')['classification'],'unresolved_print')
    def test_unreadable_mirror_prevents_exact(self):self.assertEqual(self.result(printed_card_portion='4191�3')['classification'],'unresolved_print')
    def test_portion_mismatch(self):self.assertEqual(self.result(portion='06',printed_card_portion='419106')['classification'],'portion_mismatch')
    def test_card_mismatch(self):self.assertEqual(self.result(card_type='4633',printed_card_portion='463303')['classification'],'card_type_mismatch')
    def test_no_two_axes_no_guess(self):self.assertEqual(self.result(card_type='4633',portion='A1',printed_card_portion='4633A1')['classification'],'missing_block')
    def test_page_no_fuzzy(self):
        n=deepcopy(self.node);n['page']='AP002';self.assertEqual(match_claim(self.claim,[n])['classification'],'missing_block')
    def test_partial_mask_not_arbitrary_guess(self):
        c=dict(self.claim,card_type='41�1',portion='�3');n=deepcopy(self.node)
        self.assertEqual(match_claim(c,[n])['classification'],'unresolved_print')
        n['node'].update(card_type='4633',portion='B1',printed_card_portion='4633B1')
        self.assertEqual(match_claim(c,[n])['candidates'],[])
    def test_distinct_two_of_three_ambiguous(self):
        a=deepcopy(self.node);a['node'].update(portion='06',printed_card_portion='419106')
        b=deepcopy(self.node);b['node'].update(location='B-E1K5')
        self.assertEqual(match_claim(self.claim,[a,b])['classification'],'ambiguous_candidates')
    def test_split_location_conflicts(self):self.assertEqual(self.result(board='02A-E1')['classification'],'unresolved_print')
    def test_occupied_members_no_neighbor_inference(self):
        c=dict(self.claim,sockets=['K6']);self.assertEqual(match_claim(c,[dict(self.node,node=dict(self.node['node'],location='B-E1K7'))])['classification'],'location_mismatch')
    def test_i_not_omitted(self):
        c=dict(self.claim,portion='I1');n=deepcopy(self.node);n['node'].update(portion='I1',printed_card_portion='4191I1')
        self.assertEqual(match_claim(c,[n])['classification'],'exact')
    def test_no_mutation_and_full_binding(self):
        c,n=deepcopy(self.claim),deepcopy(self.node);r=match_claim(c,[n]);self.assertEqual(c,self.claim);self.assertEqual(n,self.node);self.assertEqual(r['matches'][0]['binding'],self.node)
    def test_annotation_without_identity_is_not_candidate(self):
        n=dict(self.node,node={'id':'junction1','function':'JUNCTION'})
        r=match_claim(self.claim,[n]);self.assertEqual(r['classification'],'missing_block');self.assertEqual(r['candidates'],[])
    def test_source_page_conflict_prevents_exact(self):
        n=dict(self.node,source_page_conflict=True,model_page_literal='AP002')
        r=match_claim(self.claim,[n]);self.assertEqual(r['classification'],'unresolved_print');self.assertEqual(r['matches'],[])
        self.assertEqual(r['coverage_issues'][0]['code'],'source_page_conflict')
    def test_prepared_nodes_preserve_bindings(self):
        n=prepare_nodes([self.node]);r=match_claim(self.claim,n)
        self.assertEqual(r['classification'],'exact');self.assertEqual(r['matches'][0]['binding'],self.node)
        self.assertEqual(n[0]['_socket_matching_identity'],normalize_identity(self.node['node']))

if __name__=='__main__':unittest.main()

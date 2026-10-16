import unittest
from copy import deepcopy
from socket_ald_identity_adapter import adapt_node
from socket_ald_matching import normalize_identity


class Adapter(unittest.TestCase):
    def test_card_alias_derived_without_source_mutation(self):
        n = {'card': '1125AA', 'location': 'C-D2M6', 'unit': 'S16CL'}; old = deepcopy(n)
        view, trail = adapt_node(n)
        self.assertEqual(view['printed_card_portion'], '1125AA')
        self.assertEqual(n, old)
        self.assertEqual(trail['source_fields']['card'], '1125AA')

    def test_za_part_card_and_grid_have_distinct_meanings(self):
        n = {'part': '3312A1', 'card': 'A-D3H7', 'location': '1B-AA', 'technology': 'T06AA'}
        view, trail = adapt_node(n)
        ident = normalize_identity(view)
        self.assertEqual((ident['card_type'], ident['portion']), ('3312', 'A1'))
        self.assertEqual(ident['location']['board'], '02A-D3')
        self.assertEqual(ident['location']['sockets'], ['H7'])
        self.assertEqual(view['unit'], 'T06AA')
        self.assertIn('physical_card_location_replaces_grid_location', trail['rules'])

    def test_known_physical_location_is_not_silently_replaced(self):
        view, trail = adapt_node({'part': '3312A1', 'card': 'A-D3H7', 'location': 'A-D3H6'})
        self.assertEqual(view['location'], 'A-D3H6')
        self.assertIn('conflicting_physical_card_location_alias', view['_identity_adaptation_issues'])

    def test_context_uses_exact_01c_evidence_only(self):
        n = {'card': '1125AA', 'location': 'C-D2M6', 'A1': {'records': [
            {'board': '01C-D2', 'sockets': ['M6', 'M7'], 'card_type': '1125', 'portion': 'AA'}]}}
        view, trail = adapt_node(n); ident = normalize_identity(view)
        self.assertEqual(ident['location']['board'], '01C-D2')
        self.assertEqual(view['location'], '01C-D2M6')
        self.assertEqual(len(trail['proof']), 1)
        self.assertEqual(normalize_identity({'location': 'C-D2M6'})['location']['board'], '02C-D2')

    def test_context_handles_d_without_global_d_alias(self):
        n = {'printed_card_portion': '0709A1', 'location': 'D-D2G6', 'socket_listing_evidence':
             {'board': '01D-D2', 'sockets': ['G6'], 'card_type': '0709', 'portion': 'A1'}}
        view, _ = adapt_node(n)
        self.assertEqual(normalize_identity(view)['location']['board'], '01D-D2')
        self.assertIsNone(normalize_identity({'location': 'D-D2G6'})['location']['board'])

    def test_wrong_socket_or_card_proof_cannot_supply_frame(self):
        for proof in [{'board': '01C-D2', 'sockets': ['M5'], 'card_type': '1125'},
                      {'board': '01C-D2', 'sockets': ['M6'], 'card_type': '1124'},
                      {'board': '01C-D1', 'sockets': ['M6'], 'card_type': '1125'},
                      {'board': '01D-D2', 'sockets': ['M6'], 'card_type': '1125'}]:
            view, trail = adapt_node({'card': '1125AA', 'location': 'C-D2M6', 'socket_listing_evidence': proof})
            self.assertEqual(view['location'], 'C-D2M6')
            self.assertEqual(trail['proof'], [])

    def test_conflicting_context_proofs_not_selected(self):
        n = {'card': '1125AA', 'location': 'C-D2M6', 'A1': {'records': [
            {'board': '01C-D2', 'sockets': ['M6'], 'card_type': '1125'},
            {'board': '02C-D2', 'sockets': ['M6'], 'card_type': '1125'}]}}
        view, trail = adapt_node(n)
        self.assertEqual(view['location'], 'C-D2M6')
        self.assertIn('conflicting_frame_context_proofs', trail['issues'])

    def test_canonical_explicit_frame_not_overwritten(self):
        n = {'card': '1125AA', 'location': '02C-D2M6', 'socket_listing_evidence':
             {'board': '01C-D2', 'sockets': ['M6'], 'card_type': '1125'}}
        view, trail = adapt_node(n)
        self.assertEqual(view['location'], '02C-D2M6'); self.assertEqual(trail['proof'], [])

    def test_mirror_conflicts_preserved(self):
        n = {'card_type': '4633', 'portion': 'A1', 'card': '4191A1', 'location': 'A-D1B2'}
        view, _ = adapt_node(n)
        self.assertIn('conflicting_card_type', normalize_identity(view)['issues'])
        n['printed_card_portion'] = '4633A1'
        view, trail = adapt_node(n)
        self.assertEqual(view['printed_card_portion'], '4633A1')
        self.assertIn('conflicting_printed_card_portion_alias', view['_identity_adaptation_issues'])

    def test_complete_part_number_is_not_portion(self):
        view, trail = adapt_node({'part': '5804191', 'card': 'A-D1B2', 'location': '1A-AA'})
        self.assertNotIn('printed_card_portion', view)
        self.assertEqual(view['location'], '1A-AA')

    def test_unreadable_alias_remains_unresolved(self):
        view, _ = adapt_node({'card': 'C474A3', 'location': 'B-A3M5'})
        self.assertIn('unreadable_or_invalid_card_type', normalize_identity(view)['issues'])

    def test_empty_unknown_fields_are_not_invented(self):
        n = {'location': '1B-AA', 'card': 'unknown', 'part': 'unknown'}
        view, trail = adapt_node(n)
        # A six/seven-letter string can still be a damaged combined label, but
        # no board or socket is fabricated without physical-location syntax.
        self.assertEqual(view['location'], '1B-AA')
        self.assertFalse(any('physical_card_location' in r for r in trail['rules']))


if __name__ == '__main__': unittest.main()

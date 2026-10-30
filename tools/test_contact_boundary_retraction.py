import copy
import unittest
from ald_json_tools.pin_annotations import normalize_annotation_leads
from retract_contact_boundary_findings import OLD_REASON, retract


class ContactBoundaryTests(unittest.TestCase):
    def page(self, side='L', reverse=False, inside=False):
        old, contact = (49, 46) if side == 'L' else (58, 61)
        neighbor = contact + (1 if side == 'L' else -1) if inside else contact
        route = [[old, 5], [neighbor, 5], [neighbor, 2], [30, 2]]
        if reverse:
            route.reverse()
        node = f'blocks/AA/pins/{side}/4'
        return {'blocks': [{'serial': 'AA', 'grid position': '1A', 'pins': [{'side': side, 'line': 4}]}],
                'nets': [{'net number': 'N', 'nodes': [node], 'routing': [route]}],
                'review': {'status': 'partial', 'approved': False, 'unresolved discrepancies': True}}

    def details(self, page, extra=None):
        hold = {'terminal': page['nets'][0]['nodes'][0], 'net': 'N', 'reason': OLD_REASON}
        return {'format questions': [{'code': 'fixed_terminal_slot_layout', 'status': 'unresolved',
                                     'terminals': [hold] + (extra or [])}],
                'uncertainties': [], 'render comparison': {'rendered': True, 'different cells': 0}}

    def cells(self, routes):
        result = set()
        for route in routes:
            for a, b in zip(route, route[1:]):
                self.assertTrue(a[0] == b[0] or a[1] == b[1])
                for x in range(min(a[0], b[0]), max(a[0], b[0])+1):
                    for y in range(min(a[1], b[1]), max(a[1], b[1])+1):
                        result.add((x, y))
        return result

    def test_both_sides_and_route_directions_keep_the_same_wire_graph_with_pin_stub(self):
        for side in ('L', 'R'):
            for reverse in (False, True):
                page = self.page(side, reverse); before = copy.deepcopy(page)
                contact, border = (46, 50) if side == 'L' else (61, 57)
                stub = [[[contact, 5], [border, 5]]]
                changes, holds = normalize_annotation_leads(page)
                self.assertEqual(holds, []); self.assertEqual(len(changes), 1)
                self.assertEqual(self.cells(before['nets'][0]['routing']+stub), self.cells(page['nets'][0]['routing']+stub))
                self.assertEqual(len(page['nets'][0]['routing'][0]), 3)
                self.assertEqual(normalize_annotation_leads(page), ([], []))

    def test_vertical_arrival_at_contact_needs_no_explicit_bend(self):
        for side in ('L', 'R'):
            page = self.page(side); x = 46 if side == 'L' else 61
            page['nets'][0]['routing'] = [[[x, 2], [x, 5]]]
            before = copy.deepcopy(page)
            self.assertEqual(normalize_annotation_leads(page), ([], [])); self.assertEqual(page, before)

    def test_bend_really_inside_slot_stays_flagged_and_unchanged(self):
        for side in ('L', 'R'):
            page = self.page(side, inside=True); before = copy.deepcopy(page)
            changes, holds = normalize_annotation_leads(page)
            self.assertEqual(changes, []); self.assertEqual(holds[0]['reason'], OLD_REASON); self.assertEqual(page, before)
            self.assertEqual(retract(page, self.details(page))[2], [])

    def test_point_annotation_absolute_positions_and_indices_survive_endpoint_removal(self):
        for reverse in (False, True):
            page = self.page(reverse=reverse); net = page['nets'][0]
            net['annotations'] = [{'at': {'polyline': 0, 'point': i}, 'offset': [2, 1], 'text': str(i)} for i in range(4)]
            positions = [[net['routing'][0][a['at']['point']][0]+2, net['routing'][0][a['at']['point']][1]+1] for a in net['annotations']]
            self.assertEqual(normalize_annotation_leads(page)[1], [])
            self.assertEqual(positions, [[net['routing'][0][a['at']['point']][0]+a['offset'][0], net['routing'][0][a['at']['point']][1]+a['offset'][1]] for a in net['annotations']])

    def test_two_point_route_inside_implicit_stub_remains_valid_and_unflagged(self):
        page = self.page(); page['nets'][0]['routing'] = [[[49, 5], [46, 5]]]
        self.assertEqual(normalize_annotation_leads(page), ([], []))
        self.assertEqual(len(page['nets'][0]['routing'][0]), 2)
        self.assertEqual(len(retract(page, self.details(page))[2]), 1)

    def test_retraction_preserves_other_hold_uncertainty_and_exact_history(self):
        page = self.page(); other = {'terminal': 'blocks/OTHER/pins/L/2', 'net': 'X', 'reason': 'Another net'}
        details = self.details(page, [other]); details['uncertainties'] = [{'field': 'X', 'status': 'unresolved'}]
        original = copy.deepcopy((page, details)); changed, review, removed, moves = retract(page, details)
        self.assertEqual(review['format questions'][0]['terminals'], [other]); self.assertTrue(changed['review']['unresolved discrepancies'])
        self.assertEqual(review['uncertainties'], details['uncertainties']); self.assertEqual(len(removed), 1)
        self.assertEqual(review['format question retractions'][0]['retracted findings'], [details['format questions'][0]['terminals'][0]])
        self.assertEqual((page, details), original); self.assertEqual(retract(changed, review)[2:], ([], []))

    def test_last_finding_retracted_clears_flag_without_approval(self):
        page = self.page(); changed, review, removed, moves = retract(page, self.details(page))
        self.assertEqual(review['format questions'], []); self.assertFalse(changed['review']['unresolved discrepancies']); self.assertFalse(changed['review']['approved'])

    def test_converter_flat_question_is_retracted_too(self):
        page = self.page(); d = self.details(page); hold = d['format questions'][0]['terminals'][0]
        d['format questions'] = [{'code': 'annotation_terminal_lead', **hold}]
        changed, review, removed, moves = retract(page, d)
        self.assertEqual(len(removed), 1); self.assertEqual(review['format questions'], [])


if __name__ == '__main__':
    unittest.main()

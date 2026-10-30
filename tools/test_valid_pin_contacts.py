import copy
import unittest

from ald_json_tools.pin_annotations import normalize_annotation_leads
from retract_valid_pin_contact_findings import retract
from page_maintenance import content_digest


class ValidContactTests(unittest.TestCase):
    def page(self, side='L', annotated=True):
        node = f'blocks/AA/pins/{side}/4'
        pin = {'side': side, 'line': 4, 'pin': 'D13'} if annotated else {'side': side, 'line': 4}
        return {'blocks': [{'serial': 'AA', 'grid position': '1A', 'pins': [pin]}],
                'nets': [{'net number': 'N', 'nodes': [node], 'routing': [],
                          'annotations': [{'at': node, 'text': '3'}] if annotated else []}],
                'review': {'approved': False, 'status': 'partial', 'unresolved discrepancies': True}}

    def details(self, page, reason):
        return {'format questions': [{'code': 'fixed_terminal_slot_layout', 'status': 'unresolved',
                   'terminals': [{'terminal': page['nets'][0]['nodes'][0], 'net': 'N', 'reason': reason}]}],
                'render comparison': {'rendered': True, 'different cells': 0}}

    def test_vertical_annotated_endpoint_adds_horizontal_leg_on_both_sides_and_directions(self):
        for side in ('L', 'R'):
            for reverse in (False, True):
                page = self.page(side); net = page['nets'][0]
                old, contact = (45, 46) if side == 'L' else (62, 61)
                route = [[old, 8], [old, 5]]
                if reverse:
                    route.reverse()
                net['routing'] = [route]
                net['annotations'].append({'at': {'polyline': 0, 'point': 1}, 'text': 'NOTE', 'offset': [2, 1]})
                absolute = [route[1][0]+2, route[1][1]+1]
                changes, holds = normalize_annotation_leads(page)
                self.assertEqual(holds, []); self.assertEqual(len(changes), 1)
                expected = [[old, 8], [old, 5], [contact, 5]]
                self.assertEqual(net['routing'][0], list(reversed(expected)) if reverse else expected)
                note = net['annotations'][1]; anchor = net['routing'][0][note['at']['point']]
                self.assertEqual(absolute, [anchor[0]+note['offset'][0], anchor[1]+note['offset'][1]])
                self.assertEqual(normalize_annotation_leads(page), ([], []))

    def test_crossing_exactly_at_contact_preserves_separate_net_and_its_geometry(self):
        for side in ('L', 'R'):
            page = self.page(side, False)
            old, contact, far = (49, 46, 42) if side == 'L' else (58, 61, 65)
            page['nets'][0]['routing'] = [[[old, 5], [far, 5], [far, 2]]]
            crossing = {'net number': 'CROSS', 'nodes': ['elsewhere'], 'routing': [[[contact, 1], [contact, 9]]]}
            page['nets'].append(copy.deepcopy(crossing))
            changes, holds = normalize_annotation_leads(page)
            self.assertEqual(holds, []); self.assertEqual(len(changes), 1)
            self.assertEqual(page['nets'][0]['routing'][0][0], [contact, 5])
            self.assertEqual(page['nets'][1], crossing)

    def test_competing_wire_strictly_inside_changed_interval_stays_flagged(self):
        page = self.page(annotated=False)
        page['nets'][0]['routing'] = [[[49, 5], [40, 5]]]
        page['nets'].append({'net number': 'X', 'nodes': [], 'routing': [[[48, 2], [48, 8]]]})
        before = copy.deepcopy(page)
        changes, holds = normalize_annotation_leads(page)
        self.assertEqual(changes, []); self.assertEqual(page, before)
        self.assertEqual(holds[0]['reason'], 'The changed lead interval is occupied by another net')

    def test_same_net_branch_at_old_annotated_endpoint_is_preserved(self):
        page = self.page('R'); net = page['nets'][0]
        net['routing'] = [[[62, 5], [80, 5]], [[61, 6], [62, 6], [62, 5]]]
        branch = copy.deepcopy(net['routing'][1])
        self.assertEqual(normalize_annotation_leads(page)[1], [])
        self.assertEqual(net['routing'][0], [[61, 5], [80, 5]])
        self.assertEqual(net['routing'][1], branch)

    def test_unannotated_vertical_at_old_inside_slot_does_not_guess_a_route(self):
        page = self.page(annotated=False); page['nets'][0]['routing'] = [[[49, 2], [49, 5]]]
        before = copy.deepcopy(page)
        self.assertEqual(normalize_annotation_leads(page)[0], [])
        self.assertEqual(page, before)

    def test_retraction_preserves_other_findings_and_exact_old_evidence(self):
        page = self.page(); page['nets'][0]['routing'] = [[[45, 8], [45, 5]]]
        details = self.details(page, 'No unique horizontal endpoint at the old terminal presentation boundary')
        other = {'code': 'other', 'detail': 'Still open'}
        details['format questions'].append(other)
        before = copy.deepcopy((page, details))
        updated, result, removed, moves = retract(page, details)
        self.assertEqual(len(removed), 1); self.assertEqual(len(moves), 1)
        self.assertEqual(result['format questions'], [other])
        self.assertEqual(result['format question retractions'][0]['retracted findings'], details['format questions'][0]['terminals'])
        self.assertTrue(updated['review']['unresolved discrepancies'])
        self.assertFalse(updated['review']['approved'])
        self.assertEqual(result['content sha256'], content_digest(updated))
        self.assertEqual((page, details), before)
        self.assertEqual(retract(updated, result)[2:], ([], []))

    def test_flat_converter_finding_retracts_but_ambiguous_owner_does_not(self):
        page = self.page(); page['nets'][0]['routing'] = [[[45, 8], [45, 5]]]
        details = self.details(page, 'No unique horizontal endpoint at the old terminal presentation boundary')
        details['format questions'] = [{'code': 'annotation_terminal_lead', **details['format questions'][0]['terminals'][0]}]
        self.assertEqual(len(retract(page, details)[2]), 1)
        page['nets'].append(copy.deepcopy(page['nets'][0]))
        self.assertEqual(retract(page, details)[2], [])


if __name__ == '__main__':
    unittest.main()

from pathlib import Path
import copy
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert_ald_json as c


class CoordinateRowViewTests(unittest.TestCase):
    def make_pin(self, row=3, observations=None, point=None, border_point=None, side='output'):
        return {
            'terminal_id': 'AA.1', 'side': side,
            'geometry': {'row': row, 'column': 50, 'point': point, 'border_point': border_point},
            'source_literals': {'point': point, 'border_point': border_point},
            'extensions': {'source_observations': observations or []},
            'pin_number': '1'
        }

    def make_block(self):
        return {'geometry': {'row': 16, 'column': 50}}

    def normalize(self, pin):
        instance = object.__new__(c.Converter)
        return instance.normalize_terminal_row(pin, self.make_block(), 'AA')

    def test_local_geometry_with_absolute_observation_becomes_page_row(self):
        pin = self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}])
        evidence = self.normalize(pin)
        self.assertEqual(pin['geometry']['row'], 19)
        self.assertEqual(evidence['basis'], 'block_local_geometry')

    def test_already_absolute_geometry_with_observation_is_preserved(self):
        pin = self.make_pin(row=19, observations=[{'field': 'absolute_row', 'value': 19}])
        evidence = self.normalize(pin)
        self.assertEqual(pin['geometry']['row'], 19)
        self.assertEqual(evidence['basis'], 'absolute_geometry')

    def test_explicit_point_and_border_rows_must_match_absolute_row(self):
        pin = self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}],
                            point=[57, 19], border_point=[57, 19])
        self.normalize(pin)
        for key in ('point', 'border_point'):
            self.assertEqual(pin['geometry'][key][1], 19)

    def test_contradictory_absolute_or_point_rows_are_held(self):
        cases = [
            self.make_pin(observations=[{'field': 'absolute_row', 'value': 20}]),
            self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}], point=[57, 20]),
            self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}, {'field': 'absolute_row', 'value': 19}]),
            self.make_pin(observations=[{'field': 'absolute_row', 'value': None}]),
        ]
        for pin in cases:
            with self.subTest(pin=pin), self.assertRaises(c.ConversionError):
                self.normalize(pin)

    def test_unobserved_local_looking_row_is_not_guessed(self):
        with self.assertRaises(c.ConversionError):
            self.normalize(self.make_pin())

    def test_point_disambiguates_local_geometry_without_absolute_observation(self):
        pin = self.make_pin(point=[57, 19], border_point=[57, 19])
        evidence = self.normalize(pin)
        self.assertEqual(pin['geometry']['row'], 19)
        self.assertEqual(evidence['basis'], 'block_local_geometry')

    def test_row_qualified_routes_and_role_filter_use_page_row_view(self):
        pin = self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}], side='output')
        self.normalize(pin)
        instance = object.__new__(c.Converter)
        instance.object_ids = {'AA': 'AA'}
        node = 'blocks/AA/pins/R/4'
        instance.terminals = {node: pin}
        instance.primary_aliases = {}
        instance.aliases = {}
        self.assertEqual(instance.terminal_candidates('AA.1@19', 'driver'), [node])
        self.assertEqual(instance.terminal_candidates('AA.1@19', 'target'), [])
        self.assertIn((50, 19), instance.recorded_route_anchors(node))


    def test_source_document_geometry_remains_immutable(self):
        from test_converter import source
        source_path = source('AP761')
        raw = source_path.read_bytes()
        source = c.strict_json(raw)
        original = copy.deepcopy(source)
        instance = c.Converter(source, source_path, c.digest(raw))
        self.assertEqual(source, original)
        owner = next(block for block in instance.owners.values() if block['source_literals'].get('printed_id') == 'AA')
        self.assertEqual(owner['terminals'][0]['geometry']['row'], 3)
        interpreted = next(pin for pin in instance.terminals.values() if pin.get('source_literals', {}).get('printed_label') == 'D06')
        self.assertEqual(interpreted['geometry']['row'], 19)


    def test_identical_mirrored_absolute_row_projections_are_one_fact(self):
        pin = self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}])
        pin['source_literals']['source_observations'] = [{'field': 'absolute_row', 'value': 19}]
        self.normalize(pin)
        self.assertEqual(pin['geometry']['row'], 19)

    def test_conflicting_mirrored_absolute_row_projection_is_held(self):
        pin = self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}])
        pin['source_literals']['source_observations'] = [{'field': 'absolute_row', 'value': 20}]
        with self.assertRaises(c.ConversionError):
            self.normalize(pin)

    def test_malformed_observation_containers_are_controlled_holds(self):
        cases = []
        pin = self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}]); pin['extensions'] = None; cases.append(pin)
        pin = self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}]); pin['extensions']['source_observations'] = {}; cases.append(pin)
        pin = self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}]); pin['extensions']['source_observations'] = ['bad']; cases.append(pin)
        pin = self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}]); pin['source_literals'] = None; cases.append(pin)
        pin = self.make_pin(observations=[{'field': 'absolute_row', 'value': 19}]); pin['source_literals']['source_observations'] = 'bad'; cases.append(pin)
        for pin in cases:
            with self.subTest(pin=pin), self.assertRaises(c.ConversionError):
                self.normalize(pin)


if __name__ == '__main__':
    unittest.main()

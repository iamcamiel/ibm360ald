"""Cabinet numbers must come from explicit labels or unambiguous listings."""
import unittest
from build_card_data import parse_location


class CabinetScopeTests(unittest.TestCase):
    def test_listed_cabinet_disambiguates_abbreviation(self):
        self.assertEqual(parse_location('D-D2K6', [('01D-D2', 'K6')]), ('01D-D2', 'K6'))
        self.assertEqual(parse_location('C-A2D6', [('01C-A2', 'D6')]), ('01C-A2', 'D6'))

    def test_two_matching_cabinets_remain_ambiguous(self):
        self.assertIsNone(parse_location('A-A1J6', [('01A-A1', 'J6'), ('02A-A1', 'J6')]))

    def test_unlisted_unknown_cabinet_is_not_guessed(self):
        self.assertIsNone(parse_location('D-D2K6', [('01D-D2', 'K7')]))

    def test_explicit_cabinet_is_preserved(self):
        self.assertEqual(parse_location('01D-D2K6'), ('01D-D2', 'K6'))
        self.assertEqual(parse_location('02A-A1J6T'), ('02A-A1', 'J6'))

    def test_existing_ordinary_aliases_remain_supported(self):
        self.assertEqual(parse_location('A-A1J6'), ('02A-A1', 'J6'))

    def test_position_suffix_is_not_part_of_socket(self):
        self.assertEqual(parse_location('D-D2K6B', [('01D-D2', 'K6')]), ('01D-D2', 'K6'))

    def test_unreadable_characters_do_not_match(self):
        self.assertIsNone(parse_location('D-�2K6', [('01D-D2', 'K6')]))


if __name__ == '__main__':
    unittest.main()

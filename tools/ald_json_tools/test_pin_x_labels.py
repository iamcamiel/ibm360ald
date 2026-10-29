"""Pin-X border coverage regressions; original-page evidence is retained externally."""
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from convert_ald_json import covers_exact_pin_x_suffix

def fixture():
    return ({'column': 47, 'row': 4, 'text': 'B10X'}, {'pin_number': 'B10', 'pin_number_status': 'observed', 'side': 'input', 'geometry': {'point': [46, 4]}, 'source_literals': {'pin': 'B10', 'printed_label': 'B10', 'pin_status': 'observed', 'border_marker': 'X', 'side': 'input'}, 'border_decorations': [{'kind': 'literal-border-mark', 'glyph': 'X', 'observed_value': 'X'}]})

class ExactCoverageUnit(unittest.TestCase):

    def test_exact_suffix_coverage(self):
        label, terminal = fixture()
        self.assertTrue(covers_exact_pin_x_suffix(label, terminal))

    def test_wrong_physical_pin_label_preserved(self):
        label, terminal = fixture()
        label['text'] = 'B11X'
        self.assertFalse(covers_exact_pin_x_suffix(label, terminal))

    def test_wrong_row_preserved(self):
        label, terminal = fixture()
        label['row'] = 5
        self.assertFalse(covers_exact_pin_x_suffix(label, terminal))

    def test_wrong_adjacent_position_preserved(self):
        label, terminal = fixture()
        label['column'] = 48
        self.assertFalse(covers_exact_pin_x_suffix(label, terminal))

    def test_missing_or_mismatched_source_marker_preserved(self):
        label, terminal = fixture()
        terminal['source_literals'].pop('border_marker')
        self.assertFalse(covers_exact_pin_x_suffix(label, terminal))
        label, terminal = fixture()
        terminal['border_decorations'][0]['glyph'] = 'K'
        self.assertFalse(covers_exact_pin_x_suffix(label, terminal))

    def test_source_pin_disagreement_preserved(self):
        label, terminal = fixture()
        terminal['source_literals']['printed_label'] = 'B11'
        self.assertFalse(covers_exact_pin_x_suffix(label, terminal))

    def test_star_or_bare_marker_is_not_pin_x_suffix(self):
        label, terminal = fixture()
        label['text'] = 'B10✲X'
        self.assertFalse(covers_exact_pin_x_suffix(label, terminal))
        label, terminal = fixture()
        label['text'] = 'X'
        self.assertFalse(covers_exact_pin_x_suffix(label, terminal))

    def test_non_input_side_preserved(self):
        label, terminal = fixture()
        terminal['side'] = 'output'
        self.assertFalse(covers_exact_pin_x_suffix(label, terminal))

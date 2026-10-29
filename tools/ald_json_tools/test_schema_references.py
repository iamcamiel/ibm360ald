"""Reference grammar regressions: python -m unittest discover -s tools/ald_json_tools -p test_schema_references.py."""
import json
from pathlib import Path
import re
import unittest


class ReferenceSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = Path(__file__).resolve().parents[2] / 'schema/ALD_v4.json'
        cls.definitions = json.loads(schema.read_text(encoding='utf-8'))['$defs']

    def matches(self, definition, value):
        return re.fullmatch(self.definitions[definition]['pattern'], value) is not None

    def test_printed_zero_output_reference_is_not_terminal_line_zero(self):
        for reference in ('WA641AA0', 'WA641AA9', 'AP011BJ5', 'WA641AA10'):
            self.assertTrue(self.matches('net number', reference), reference)
            for side in ('inputs', 'outputs'):
                self.assertTrue(self.matches('node', side + '/' + reference), reference)
        self.assertTrue(self.matches('node', 'blocks/AA/pins/R/10'))
        self.assertFalse(self.matches('node', 'blocks/AA/pins/R/0'))
        self.assertFalse(self.matches('node', 'blocks/AA/pins/L/0'))

    def test_zero_exception_does_not_admit_malformed_or_zero_line_anchors(self):
        for reference in ('WA641AA00', 'WA641AA09', 'WA641AA-1',
                          'WA641AAL0-strap', 'WA641AAL0-unused'):
            self.assertFalse(self.matches('net number', reference), reference)
            self.assertFalse(self.matches('node', 'inputs/' + reference), reference)
        for kind in ('strap', 'unused', 'gnd', '+3v', 'no-source'):
            self.assertTrue(self.matches('net number', 'WA641AAL10-' + kind))


if __name__ == '__main__':
    unittest.main()

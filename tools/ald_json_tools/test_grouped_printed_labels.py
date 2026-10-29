"""Grouped semantic-label preservation and incomplete-output guards."""
import sys,ast,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import convert_ald_json as C
text=Path(C.__file__).read_text(encoding="utf8")

class GroupedLabelTests(unittest.TestCase):

    def fixture(self):
        return {'drive': [{'native_reviewed': True, 'origin': 'ED011AA4', 'signal': 'DRIVE', 'polarity': 'even'}], 'inputs': [{'native_reviewed': False, 'origin': 'ED011AB4', 'selection': 0, 'signal': 'SELECT 00', 'suffix': 'GATE D', 'text': 'SELECT 00 GATE D'}], 'outputs': [{'designation': 'AH4', 'destination': 'ED010', 'gate': 'AH', 'native_reviewed': True, 'signal': 'DRIVE'}]}

    def test_unknown_group_missing_group_coordinates_rejected(self):
        for change in ('extra', 'missing', 'coordinates'):
            v = self.fixture()
            if change == 'extra':
                v['other'] = []
            elif change == 'missing':
                v.pop('drive')
            else:
                v['inputs'][0]['row'] = 10
            with self.assertRaises(C.ConversionError):
                C.structured_printed_label_groups(v)

    def test_bad_group_or_record_types_rejected(self):
        for bad in ({}, None, 'drive', 1):
            v = self.fixture()
            v['drive'] = bad
            with self.assertRaises(C.ConversionError):
                C.structured_printed_label_groups(v)
        v = self.fixture()
        v['outputs'] = [None]
        with self.assertRaises(C.ConversionError):
            C.structured_printed_label_groups(v)

    def test_selection_bool_negative_and_noninteger_rejected(self):
        for bad in (True, -1, '0', None):
            v = self.fixture()
            v['inputs'][0]['selection'] = bad
            with self.assertRaises(C.ConversionError):
                C.structured_printed_label_groups(v)

    def test_review_markers_and_text_integrity_checked(self):
        for group, key, bad in [('drive', 'native_reviewed', 1), ('drive', 'polarity', 'left'), ('inputs', 'text', 'SELECT 01 GATE D'), ('outputs', 'signal', '')]:
            v = self.fixture()
            v[group][0][key] = bad
            with self.assertRaises(C.ConversionError):
                C.structured_printed_label_groups(v)

    def test_external_copy_preserves_orders_types_and_history(self):
        v = self.fixture()
        v['inputs'] *= 2
        before = copy.deepcopy(v)
        rv = {'conversion evidence': {}, 'uncertainties': [{'status': 'unresolved', 'field': 'retained'}], 'inherited review': {'user_approved': True}}
        self.assertEqual(C.structured_printed_label_groups(v), [])
        C.attach_grouped_label_evidence(rv, v)
        self.assertEqual(rv['conversion evidence']['source printed label groups'], before)
        self.assertEqual(v, before)
        rv['conversion evidence']['source printed label groups']['inputs'][0]['text'] = 'changed'
        self.assertEqual(v, before)
        self.assertEqual(rv['uncertainties'], [{'status': 'unresolved', 'field': 'retained'}])
        self.assertEqual(rv['inherited review'], {'user_approved': True})

    def test_legacy_labels_pass_through_without_new_external_field(self):
        value = [{'row': 1, 'column': 2, 'text': 'SIGNAL'}]
        rv = {'conversion evidence': {}}
        self.assertIs(C.structured_printed_label_groups(value), value)
        C.attach_grouped_label_evidence(rv, value)
        self.assertEqual(rv, {'conversion evidence': {}})

class ProjectionHoldTests(unittest.TestCase):

    def fixture(self):
        return {'drive': [], 'inputs': [], 'outputs': [{'designation': 'AH4', 'destination': 'ED010', 'gate': 'AH', 'native_reviewed': True, 'signal': 'DRIVE'}]}

    def test_unplaced_output_is_explicit_technical_uncertainty(self):
        v = self.fixture()
        hold = C.grouped_output_projection_issue(v)
        self.assertEqual(hold['field'], 'outputs')
        self.assertEqual(hold['kind'], 'missing')
        self.assertEqual(hold['status'], 'unresolved')
        self.assertIn('unfinished converter projection', hold['detail'])

    def test_no_output_records_do_not_make_hold(self):
        for v in ([], {'drive': [], 'inputs': [], 'outputs': []}):
            self.assertIsNone(C.grouped_output_projection_issue(v))

    def test_legacy_located_outputs_unchanged(self):
        self.assertIsNone(C.grouped_output_projection_issue([{'row': 10, 'column': 242, 'text': 'AH4'}]))

    def test_full_source_records_remain_unmutated(self):
        v = self.fixture()
        original = copy.deepcopy(v)
        C.grouped_output_projection_issue(v)
        self.assertEqual(v, original)

    def test_independent_hold_values(self):
        v = self.fixture()
        a = C.grouped_output_projection_issue(v)
        a['status'] = 'resolved'
        self.assertEqual(C.grouped_output_projection_issue(v)['status'], 'unresolved')

    def test_hold_precedes_model_flag_and_content_digest(self):
        convert = next((m for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == 'Converter' for m in n.body if isinstance(m, ast.FunctionDef) and m.name == 'convert'))
        body = ast.unparse(convert)
        self.assertLess(body.index('self.issues.append(grouped_output_hold)'), body.index("'unresolved discrepancies': bool(self.issues or self.gaps)"))
        self.assertLess(body.index('self.issues.append(grouped_output_hold)'), body.index('content_digest(data)'))

    def test_actual_cli_status_expression_cannot_report_clean_even_with_identical_text_and_other_history_resolved(self):
        tree = ast.parse(text)
        expr = next((n for n in ast.walk(tree) if isinstance(n, ast.IfExp) and isinstance(n.body, ast.Constant) and (n.body.value == 'converted with findings')))
        review = {'uncertainties': [{'status': 'resolved'}, C.grouped_output_projection_issue(self.fixture())], 'format questions': []}
        env = {'comparison': {'different cells': 0}, 'review': review, 'rendered': 'same'}
        self.assertEqual(eval(compile(ast.Expression(expr), '<exact CLI status>', 'eval'), env), 'converted with findings')

if __name__=="__main__":unittest.main()

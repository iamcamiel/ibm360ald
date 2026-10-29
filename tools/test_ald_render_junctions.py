"""Wire glyph regression checks for the browser and standalone renderers."""
import copy
import importlib.util
from pathlib import Path
import unittest


TOOLS = Path(__file__).resolve().parent
RENDERERS = [TOOLS / 'ald_render.py', TOOLS / 'ald_json_tools/ald_render.py']
WORKSPACE_RENDERER = TOOLS.parents[1] / 'ald_json_tools/ald_render.py'
if WORKSPACE_RENDERER.is_file():
    RENDERERS.append(WORKSPACE_RENDERER)


def page(routes):
    return {
        'page': {'page': 'ZZ001', 'title': ['WIRE TEST'], 'date': '01-01-66',
                 'machine': '2065', 'log': '1', 'frame': '1', 'p/n': '1',
                 'ibm division': 'DPD', 'next block': '1'},
        'blocks': [], 'inputs': [], 'outputs': [],
        'nets': [{'net number': f'ZZ001AA{i}', 'nodes': [], 'routing': lines}
                 for i, lines in enumerate(routes)],
    }


class WireGlyphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderers = []
        for index, path in enumerate(RENDERERS):
            spec = importlib.util.spec_from_file_location(f'wire_renderer_{index}', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls.renderers.append((path, module))

    def check(self, routes, expected, ending='\n', trim=False):
        document = page(routes)
        before = copy.deepcopy(document)
        for path, renderer in self.renderers:
            with self.subTest(renderer=str(path), routes=routes):
                result = renderer.render_page(document, trim_trailing_spaces=trim,
                                              line_ending=ending).decode('utf-8')
                self.assertEqual(result.splitlines()[20][100], expected)
                self.assertFalse(set(result) & set('├┤┬┴'))
                self.assertEqual(document, before)

    def test_all_four_t_shapes_from_overlaid_routes_are_diamonds(self):
        # Different nets exercise the direction table, rather than the existing
        # same-net branch detector. Only the displayed glyph changes.
        for dx in (-1, 1):
            self.check([[[[100, 18], [100, 22]]],
                        [[[100, 20], [100 + 2 * dx, 20]]]], '◇')
        for dy in (-1, 1):
            self.check([[[[98, 20], [102, 20]]],
                        [[[100, 20], [100, 20 + 2 * dy]]]], '◇')

    def test_same_net_branch_remains_a_diamond(self):
        self.check([[[[100, 18], [100, 22]], [[98, 20], [100, 20]]]], '◇')

    def test_separate_net_crossing_remains_a_cross(self):
        self.check([[[[98, 20], [102, 20]]], [[[100, 18], [100, 22]]]], '┼')

    def test_corners_and_straight_wires_are_unchanged(self):
        for dx, dy, glyph in ((1, 1, '┌'), (-1, 1, '┐'),
                              (1, -1, '└'), (-1, -1, '┘')):
            self.check([[[[100 + dx * 2, 20], [100, 20],
                           [100, 20 + dy * 2]]]], glyph)
        self.check([[[[98, 20], [102, 20]]]], '─')
        self.check([[[[100, 18], [100, 22]]]], '│')

    def test_diamond_with_trimmed_crlf_output(self):
        self.check([[[[100, 18], [100, 22]]], [[[98, 20], [100, 20]]]],
                   '◇', ending='\r\n', trim=True)

    def test_literal_annotations_emit_diamonds_without_changing_source(self):
        document = page([[[[98, 20], [102, 20]]]])
        document['nets'][0]['annotations'] = [
            {'at': {'polyline': 0, 'point': 0}, 'offset': [0, 1],
             'text': '├┤┬┴'}]
        before = copy.deepcopy(document)
        for path, renderer in self.renderers:
            with self.subTest(renderer=str(path)):
                result = renderer.render_page(document).decode('utf-8')
                self.assertEqual(result.splitlines()[21][98:102], '◇◇◇◇')
                self.assertFalse(set(result) & set('├┤┬┴'))
                self.assertEqual(document, before)


if __name__ == '__main__':
    unittest.main()

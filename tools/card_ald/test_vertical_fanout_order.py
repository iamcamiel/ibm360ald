"""Synthetic one-track fanout tests, including a pinless internal driver."""
from copy import deepcopy
import unittest

from equivalent_input_order import _obstacles
from render_composite_card import DIRS, OPPOSITE, Router, verify
from vertical_fanout_order import optimize


def fixture(shared_input=False, exposed_output=False):
    positions = {'S': {'x': 12, 'top': 14, 'height': 7}}
    positions.update({name: {'x': 60, 'top': row - 3, 'height': 7}
                      for name, row in [('A', 17), ('B', 31), ('C', 45)]})
    if shared_input:
        positions.pop('S')
    model = {'card_type': '9999', 'portions': {name: {'function': 'A'} for name in positions},
             'signal_pins': {'B02': {}} if shared_input else ({'B03': {}} if exposed_output else {}),
             'layout_hints': {'row_step': 1}}
    ports = {(name, 'input', 'in'): {'point': (56 if shared_input and name == 'A' else 59, row),
             'pin': 'B02' if shared_input and name == 'A' else None,
             'triangle': name == 'B', 'net': 'N', 'id': 'in-' + name}
             for name, row in [('A', 17), ('B', 31), ('C', 45)]}
    if not shared_input:
        ports['S', 'output', 'out'] = {'point': (23 if exposed_output else 20, 17),
                                      'pin': 'B03' if exposed_output else None,
                                      'triangle': True, 'net': 'N', 'id': 'source'}
    exterior = {'B02': {'side': 'input', 'row': 17, 'net': 'N'}} if shared_input else {}
    if exposed_output:
        exterior['B03'] = {'side': 'output', 'row': 10, 'net': 'N'}
    blocked, clearance, reserved, _ = _obstacles(positions, ports, exterior, 90)
    router = Router(90, 60, blocked, reserved,
                    {(x+d, y) for x, y in clearance for d in range(-2, 3)}, clearance)
    start = (3 if shared_input else (23 if exposed_output else 20), 17)
    segments = [(start, ports['A', 'input', 'in']['point']),
                ((30, 17), (30, 24)), ((30, 24), (40, 24)),
                ((40, 24), (40, 38)), ((40, 31), (59, 31)),
                ((40, 38), (50, 38)), ((50, 38), (50, 45)), ((50, 45), (59, 45))]
    if exposed_output:
        segments += [((26, 17), (26, 10)), ((26, 10), (86, 10))]
    for a, b in segments:
        dx = (b[0] > a[0]) - (b[0] < a[0]); dy = (b[1] > a[1]) - (b[1] < a[1])
        direction = DIRS.index((dx, dy))
        while a != b:
            q = a[0] + dx, a[1] + dy
            router.wires[a].setdefault('N', set()).add(direction)
            router.wires[q].setdefault('N', set()).add(OPPOSITE[direction])
            router.by_net['N'].update((a, q)); a = q
    for key, p in ports.items():
        router.virtual_endpoint_directions[p['point']]['N'].add(0 if key[1] == 'input' else 2)
    if shared_input:
        router.virtual_endpoint_directions[start]['N'].add(2)
    if exposed_output:
        router.virtual_endpoint_directions[86, 10]['N'].add(0)
    geometry = positions, ports, exterior, router
    verify(model, geometry)
    return model, geometry


class VerticalFanoutTests(unittest.TestCase):
    def test_internal_pinless_staircase_becomes_one_bus(self):
        model, geometry = fixture(); original = deepcopy(geometry)
        result, report = optimize(model, geometry)
        self.assertTrue(report['accepted'])
        self.assertLess(report['after']['bends'], report['before']['bends'])
        vertical = {x for (x, y), layers in result[3].wires.items()
                    if layers.get('N', set()) & {1, 3}}
        self.assertEqual(len(vertical), 1)
        self.assertEqual(result[:3], original[:3])
        self.assertEqual(dict(geometry[3].wires), dict(original[3].wires))
        self.assertEqual(sum(len(v['N']) for v in result[3].wires.values() if 'N' in v)//2,
                         len(result[3].by_net['N'])-1)

    def test_shared_exterior_input_is_eligible(self):
        model, geometry = fixture(True); result, report = optimize(model, geometry)
        self.assertTrue(report['accepted']); self.assertEqual(result[2], geometry[2])
        self.assertEqual(result[1], geometry[1])

    def test_multiple_drivers_are_not_consolidated(self):
        model, geometry = fixture()
        geometry[1]['S', 'output', 'duplicate'] = dict(geometry[1]['S', 'output', 'out'])
        result, report = optimize(model, geometry)
        self.assertFalse(report['accepted']); self.assertIs(result, geometry)

    def test_fixed_exterior_output_and_foreign_net_preserved(self):
        model, geometry = fixture(exposed_output=True)
        router = geometry[3]
        router.route('foreign', (3, 53), {(86, 53)})
        foreign = {p: set(ds['foreign']) for p, ds in router.wires.items() if 'foreign' in ds}
        result, report = optimize(model, geometry)
        self.assertTrue(report['accepted'])
        self.assertEqual(result[2], geometry[2])
        self.assertEqual(foreign, {p: set(ds['foreign']) for p, ds in result[3].wires.items() if 'foreign' in ds})
        self.assertIn((86, 10), result[3].by_net['N'])


if __name__ == '__main__':
    unittest.main()

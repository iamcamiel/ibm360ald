"""Independent private transaction fixtures; no canonical repository writes."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

WORK = Path('D:/Github/IBM360')
TOOLS = WORK / 'ibm360ald/tools/card_ald'
sys.path.insert(0, str(TOOLS))
import adopt_card_layout as adoption

BASE = WORK / 'tmp/ald-text/ald/card-data/serialization-fix-history'
checks = []


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='adoption-fixture-', dir=BASE)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.source = self.root.parent / 'candidates'; self.source.mkdir()
        self.candidates = []
        self.expected = {}
        self.preflight_cards = []
        self.default_cards = []
        for card in ('1111', '2222'):
            old = {'card_type': card, 'boxes': [{'portion': '01', 'circuit_identifier': 'U61AP',
                    'function': 'R T1', 'ports': [{'id': 'in', 'side': 'input', 'pin': 'B02',
                    'triangle': False, 'row': 10}], 'x': 20, 'top': 7, 'height': 7}],
                    'nets': [['PIN:B02', 'PORT:01:in']], 'power_contacts': {'D08': 'GROUND'},
                    'variants': [], 'canvas': {'width': 40, 'height': 25, 'header_rows': 4},
                    'wiring': {'value': 'old'}, 'exterior_pins': [], 'annotations': [],
                    'canonical_line_ending': 'LF', 'provenance': {}}
            candidate = deepcopy(old)
            candidate['boxes'][0]['compact_termination'] = {'point': [15, 10], 'label_width': 8}
            candidate['wiring']['value'] = 'approved'
            path = self.source / (card + '.json'); self.json(path, candidate)
            self.candidates.append((card, path)); self.expected[card] = candidate
            self.json(self.root / f'json/Card-ALD/definitions/{card}.json', old)
            self.json(self.root / f'json/Card-ALD/build-overrides/{card}.json', {'source_bindings': []})
            self.write(self.root / f'Card-ALD/{card}.txt', b'old text')
        self.support = self.source / 'support'; self.write(self.support, b'frozen support')
        self.review = self.source / 'review.json'
        self.json(self.review, {'passed': True, 'failures': [],
                  'candidate_bindings': [{'path': str(p), 'sha256': self.hash(p)} for _, p in self.candidates],
                  'supporting_files': [{'path': str(self.support), 'sha256': self.hash(self.support)}]})
        self.publisher = self.root / 'tools/card_ald/adopt_card_layout.py'
        self.write(self.publisher, (TOOLS / 'adopt_card_layout.py').read_bytes())
        self.write(self.root / 'csv/Card-ALD/Notation variants.csv', b'old index')
        self.write(self.root / 'notes/Card-ALD/Universal card diagrams publication.json', b'old inventory')
        self.write(self.root / 'notes/Card-ALD/1111 drawing provenance.json', b'old provenance')
        self.start = self.snapshot()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, raw):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)

    def json(self, path, value):
        self.write(path, json.dumps(value).encode())

    def hash(self, path):
        return sha256(path.read_bytes()).hexdigest()

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for folder in ('Card-ALD', 'json', 'csv', 'notes') for p in (self.root / folder).rglob('*')
                if p.is_file() and '/history/' not in p.as_posix() and '/Accepted layouts/' not in p.as_posix()}

    def record(self, spec, *args):
        card = spec['card_type']
        for relative in (f'json/Card-ALD/{card}.json', f'notes/Card-ALD/{card} drawing provenance.json',
                         f'notes/Card-ALD/{card} diagram publication receipt.json',
                         f'notes/Card-ALD/Generation/{card}.json', 'csv/Card-ALD/Notation variants.csv',
                         'notes/Card-ALD/Universal card diagrams publication.json'):
            self.write(self.root / relative, ('updated ' + card).encode())

    def render(self, spec):
        return {spec['card_type'] + '.txt': json.dumps({k: spec[k] for k in
                 ('boxes', 'wiring', 'canvas', 'nets', 'variants', 'power_contacts')}, sort_keys=True).encode()}, {'compact_terminations': 1}

    def builder(self, card, overrides_path=None):
        if overrides_path is not None:
            self.preflight_cards.append(card); overlay = json.loads(Path(overrides_path).read_text())
        else:
            self.default_cards.append(card)
            overlay = json.loads((self.root / f'json/Card-ALD/build-overrides/{card}.json').read_text())
        result = deepcopy(self.expected[card])
        for field in ('canvas', 'wiring', 'exterior_pins', 'annotations'):
            result[field] = overlay['layout'][field]
        for box, placement in zip(result['boxes'], overlay['layout']['boxes']):
            assert box['compact_termination'] == placement['compact_termination']
        return result, {'private': overrides_path is not None}

    def run_adopt(self, builder=None, write=None):
        with patch.object(adoption, 'ROOT', self.root), patch.object(adoption, '__file__', str(self.publisher)), \
             patch.object(adoption, 'build', self.render), patch.object(adoption.build_card_data, 'build', builder or self.builder), \
             patch.object(adoption, 'record_generation', self.record), \
             patch.object(adoption, 'write_protected', write or adoption.write_protected):
            return adoption.adopt(self.candidates, self.review)

    def test_success_persists_source_acceptance_and_compact_data(self):
        result = self.run_adopt()
        self.assertTrue(result['published']); self.assertEqual(self.preflight_cards, ['1111', '2222'])
        self.assertEqual(self.default_cards, ['1111', '2222'])
        for card, source in self.candidates:
            overlay = json.loads((self.root / f'json/Card-ALD/build-overrides/{card}.json').read_text())
            self.assertEqual(overlay['layout']['boxes'][0]['compact_termination'], self.expected[card]['boxes'][0]['compact_termination'])
            for binding in overlay['source_bindings']:
                self.assertEqual(self.hash(self.root / binding['path']), binding['sha256'])
        checks.append({'check': 'success and persistent accepted evidence', 'passed': True})

    def test_stale_support_rejects_before_any_write(self):
        self.write(self.support, b'changed')
        with self.assertRaises(AssertionError):
            self.run_adopt()
        self.assertEqual(self.snapshot(), self.start)
        self.assertFalse((self.root / 'notes/Card-ALD/history').exists())
        self.assertFalse((self.root / 'notes/Card-ALD/Generation/Accepted layouts').exists())
        checks.append({'check': 'stale binding rejected before any repository write', 'passed': True})

    def test_second_preflight_mismatch_never_writes_canonical(self):
        def bad(card, overrides_path=None):
            result, report = self.builder(card, overrides_path)
            if card == '2222': result['wiring'] = {'value': 'wrong'}
            return result, report
        with self.assertRaises(AssertionError): self.run_adopt(builder=bad)
        self.assertEqual(self.snapshot(), self.start); self.assertFalse(self.default_cards)
        checks.append({'check': 'all candidates privately preflight before canonical writes', 'passed': True})

    def test_later_default_failure_rolls_back_every_candidate(self):
        def bad(card, overrides_path=None):
            if card == '2222' and overrides_path is None: raise RuntimeError('injected second publication failure')
            return self.builder(card, overrides_path)
        with self.assertRaises(RuntimeError): self.run_adopt(builder=bad)
        self.assertEqual(self.snapshot(), self.start)
        checks.append({'check': 'later publication failure rolls back canonical bytes', 'passed': True})

    def test_final_batch_receipt_failure_rolls_back(self):
        original = adoption.write_protected
        def bad(path, raw):
            if path.name == 'Batch publication receipt.json': raise OSError('injected final receipt failure')
            return original(path, raw)
        with self.assertRaises(OSError): self.run_adopt(write=bad)
        self.assertEqual(self.snapshot(), self.start)
        checks.append({'check': 'final batch receipt failure rolls back canonical bytes', 'passed': True})

    def test_repeated_success_has_distinct_history(self):
        self.run_adopt(); self.run_adopt()
        self.assertEqual(len(list((self.root / 'notes/Card-ALD/history').iterdir())), 2)
        self.assertEqual(len(list((self.root / 'notes/Card-ALD/Generation/Accepted layouts').iterdir())), 2)
        checks.append({'check': 'successive publications use distinct exclusive history directories', 'passed': True})

    def test_semantics_variants_nets_and_power_rejected(self):
        path = self.candidates[0][1]
        original = deepcopy(self.expected['1111'])
        edits = [lambda s: s['boxes'][0].update(circuit_identifier='U61AC'),
                 lambda s: s['boxes'][0]['ports'][0].update(pin='B04'),
                 lambda s: s['boxes'][0]['ports'][0].update(triangle=True),
                 lambda s: s.update(nets=[]), lambda s: s.update(variants=[{'id': 'new'}]),
                 lambda s: s.update(power_contacts={})]
        for edit in edits:
            candidate = deepcopy(original); edit(candidate); self.json(path, candidate)
            review = json.loads(self.review.read_text()); review['candidate_bindings'][0]['sha256'] = self.hash(path)
            self.json(self.review, review)
            with self.assertRaises(AssertionError): self.run_adopt()
            self.assertEqual(self.snapshot(), self.start)
            self.assertFalse((self.root / 'notes/Card-ALD/history').exists())
        checks.append({'check': 'six circuit/port/polarity/net/variant/power mutations rejected before publication', 'passed': True})


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TransactionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {'schema': 'independent-card-adoption-transaction-review-v1',
               'publisher': {'path': str(TOOLS / 'adopt_card_layout.py'),
                             'sha256': sha256((TOOLS / 'adopt_card_layout.py').read_bytes()).hexdigest()},
               'tests_run': result.testsRun, 'checks': checks,
               'passed': result.wasSuccessful(),
               'failures': [str(test) + ': ' + text for test, text in result.failures + result.errors],
               'canonical_repository_untouched': True}
    (BASE / 'Adoption transaction independent review.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    sys.exit(not result.wasSuccessful())

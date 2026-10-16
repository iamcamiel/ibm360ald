"""Small isolated fixtures; never edits real diagrams or review ledgers."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import source_review as sr
HERE = Path(__file__).resolve().parent


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE)
        self.base = Path(self.temp.name)
        self.ledger = self.base / 'answers.json'
        sr.ledger_init(self.ledger, 'fixture')
        sr.ledger_record(self.ledger, question={'question_id': 'one', 'text': 'What is printed?'})

    def tearDown(self):
        assert self.base.resolve().is_relative_to(HERE)
        self.temp.cleanup()

    def test_literal_normalized_and_correction_history_survive(self):
        sr.ledger_record(self.ledger, question_id='one', raw=' b08\n', normalized='B08', response_id='first')
        sr.ledger_record(self.ledger, question_id='one', raw='B09 actually', normalized='B09', response_id='second')
        data = sr.read_json(self.ledger)
        answers = [e for e in data['events'] if e['kind'] == 'answer']
        self.assertEqual(answers[0]['raw'], ' b08\n')
        self.assertEqual(answers[0]['normalized'], 'B08')
        self.assertEqual(len(answers), 2)
        self.assertEqual(sr.verify_ledger(data)['responses'], 2)
        self.assertEqual(len(list((self.base / 'answers.json.history').glob('*.json'))), 3)

    def test_retry_id_does_not_duplicate_answer(self):
        args = dict(question_id='one', raw='B08', response_id='retry')
        first = sr.ledger_record(self.ledger, **args)
        self.assertEqual(first, sr.ledger_record(self.ledger, **args))
        with self.assertRaises(ValueError):
            sr.ledger_record(self.ledger, question_id='one', raw='B09', response_id='retry')

    def test_stale_revision_never_overwrites_new_response(self):
        sr.ledger_record(self.ledger, question_id='one', raw='first', expected_revision=1)
        with self.assertRaises(ValueError):
            sr.ledger_record(self.ledger, question_id='one', raw='second', expected_revision=1)
        self.assertEqual(sr.verify_ledger(sr.read_json(self.ledger))['responses'], 1)

    def test_tampered_raw_answer_detected(self):
        sr.ledger_record(self.ledger, question_id='one', raw='B08')
        data = sr.read_json(self.ledger);data['events'][-1]['raw'] = 'B09'
        with self.assertRaises(ValueError):sr.verify_ledger(data)

    def test_failed_atomic_answer_write_retains_previous_ledger(self):
        before = self.ledger.read_bytes();replace = sr.os.replace
        def fail_current(source, destination):
            if Path(destination) == self.ledger:raise OSError('simulated replace failure')
            return replace(source, destination)
        with patch.object(sr.os, 'replace', side_effect=fail_current):
            with self.assertRaises(OSError):sr.ledger_record(self.ledger, question_id='one', raw='B08', response_id='durable')
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(sr.ledger_record(self.ledger, question_id='one', raw='B08', response_id='durable')['responses'], 1)

    def test_question_cannot_claim_unrecorded_answer(self):
        with self.assertRaises(ValueError):
            sr.ledger_record(self.ledger, question={'question_id': 'two', 'text': 'Question', 'latest_response_id': 'fake'})

    def test_concurrent_cli_writers_record_both_responses(self):
        processes = []
        with sr.locked(self.ledger.with_name(self.ledger.name + '.lock')):
            for answer in ['first response', 'second response']:
                processes.append(subprocess.Popen([sys.executable, str(HERE / 'source_review.py'), 'record-answer',
                    str(self.ledger), '--question-id', 'one', '--raw', answer, '--response-id', answer],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
            time.sleep(0.2)
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, stderr.decode('utf8'))
        data = sr.read_json(self.ledger)
        self.assertEqual({e['raw'] for e in data['events'] if e['kind'] == 'answer'}, {'first response', 'second response'})


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE)
        self.base = Path(self.temp.name);self.target = self.base / 'canonical';self.target.mkdir()
        fonts = [os.environ.get('SOURCE_REVIEW_TEST_FONT', ''), 'C:/Windows/Fonts/consola.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf']
        font = next((Path(x) for x in fonts if x and Path(x).is_file()), None)
        if font is None:self.skipTest('Set SOURCE_REVIEW_TEST_FONT to a monospaced TTF fixture font')
        self.source = self.base / 'original.tif';self.source.write_bytes(b'original TIFF fixture')
        self.text = self.target / 'PAGE.txt'
        self.text.write_bytes(('\r\n'.join(['ABCD'.ljust(12), '│X──────│'.ljust(12), ''.ljust(12), ''.ljust(12)]) + '\r\n').encode('utf8'))
        self.model = self.target / 'PAGE.json';self.model.write_bytes(sr.encode({'nodes': [{'id': 'alias', 'printed_id': 'AA', 'function': 'OR', 'unit': 'U03AF'}], 'untouched': {'truth': True}}).replace(b'\n', b'\r\n'))
        self.notes = self.target / 'PAGE notes.txt';self.notes.write_bytes(b'Before notes\r\n')
        self.config = {'font': sr.binding(font), 'width': 96, 'height': 64, 'font_size': 12,
                       'cell_width': 8, 'row_height': 16, 'origin': [0, 0], 'anchor': 'lt'}
        self.preview = self.target / 'PAGE.png';self.preview.write_bytes(sr.render_preview(self.text.read_bytes(), self.config, self.base))
        self.prior = {k: sr.binding(p) for k, p in [('txt', self.text), ('json', self.model), ('notes', self.notes), ('preview', self.preview)]}
        self.intent = {'schema': sr.INTENT, 'review_id': 'generic-fixture', 'card_type': '9876', 'target_root': str(self.target),
                       'unresolved_questions': [], 'evidence': [], 'pages': [{'page': 'PAGE', 'model_schema': 'ald-page-nodes-v1',
                       'source': sr.binding(self.source), 'prior_quartet': self.prior, 'grid': {'width': 12, 'height': 4},
                       'cell_edits': [{'row': 0, 'column': 1, 'before': 'B', 'after': 'Z'}],
                       'json_patches': [{'pointer': '/nodes/0/function', 'before': 'OR', 'after': 'A'}],
                       'notes_append': 'Literal source check.', 'preview_config': self.config}]}
        self.intent_path = self.base / 'intent.json';self.stage = self.base / 'stage'

    def tearDown(self):
        assert self.base.resolve().is_relative_to(HERE)
        self.temp.cleanup()
    def save_intent(self):self.intent_path.write_bytes(sr.encode(self.intent))
    def create(self):self.save_intent();return sr.create_stage(self.intent_path, self.stage)
    def acceptance(self, manifest=None):
        manifest = manifest or self.stage / 'manifest.json'
        path = self.base / 'independent.json'
        path.write_bytes(sr.encode({'schema': 'source-review-independent-acceptance-v1', 'passed': True, 'failures': [],
                                    'manifest_sha256': sr.digest(manifest.read_bytes()), 'reviewer': 'Independent fixture reviewer',
                                    'independent_review': True, 'unresolved_questions': [], 'accepted_pages': ['PAGE']}))
        return path

    def test_stage_publish_and_idempotence_preserve_scan_and_unrelated_model(self):
        source = self.source.read_bytes();old = self.text.read_bytes()
        result = self.create();self.assertEqual(result['phase'], 'staged');self.assertEqual(self.text.read_bytes(), old)
        acceptance = self.acceptance();first = sr.publish(self.stage / 'manifest.json', acceptance)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertIn(b'AZCD', self.text.read_bytes());self.assertEqual(self.text.read_bytes().count(b'\r\n'), 4)
        self.assertEqual(sr.read_json(self.model)['nodes'][0]['printed_id'], 'AA')
        self.assertEqual(sr.read_json(self.model)['untouched'], {'truth': True})
        self.assertTrue(sr.publish(self.stage / 'manifest.json', acceptance)['idempotent_retry'])
        self.assertEqual(sr.verify_stage(self.stage / 'manifest.json', 'published')['phase'], 'published')

    def test_variable_width_edit_refused_before_stage_creation(self):
        self.intent['pages'][0]['cell_edits'][0]['after'] = 'ZZ'
        with self.assertRaises(ValueError):self.create()
        self.assertFalse(self.stage.exists())

    def test_stale_tiff_binding_refused(self):
        self.source.write_bytes(b'changed TIFF')
        with self.assertRaises(ValueError):self.create()
        self.assertFalse(self.stage.exists())

    def test_wrong_preview_baseline_refused(self):
        self.intent['pages'][0]['preview_config']['origin'] = [1, 0]
        self.intent['pages'][0]['preview_config']['width'] = 100
        with self.assertRaises(ValueError):self.create()
        self.assertFalse(self.stage.exists())

    def test_unknown_intent_schema_and_uncertain_intent_refused(self):
        self.intent['unresolved_questions'] = ['pending']
        with self.assertRaises(ValueError):self.create()
        self.intent['unresolved_questions'] = [];self.intent['schema'] = 'unknown'
        with self.assertRaises(ValueError):self.create()

    def test_wrong_json_preimage_refused(self):
        self.intent['pages'][0]['json_patches'][0]['before'] = 'AR'
        with self.assertRaises(ValueError):self.create()

    def test_json_boolean_not_numeric_preimage(self):
        with self.assertRaises(ValueError):
            sr.patch_model({'nodes': [], 'flag': True}, [{'pointer': '/flag', 'before': 1, 'after': False}])

    def test_json_pointer_escapes_and_nonoverlapping_scope(self):
        model = {'nodes': [], 'a/b': {'~value': 'before'}}
        after = sr.patch_model(model, [{'pointer': '/a~1b/~0value', 'before': 'before', 'after': 'after'}])
        self.assertEqual(after['a/b']['~value'], 'after');self.assertEqual(model['a/b']['~value'], 'before')
        with self.assertRaises(ValueError):
            sr.patch_model(model, [{'pointer': '/a~1b', 'before': model['a/b'], 'after': {}}, {'pointer': '/a~1b/~0value', 'op': 'add', 'after': 'x'}])

    def test_undeclared_json_candidate_change_detected_even_with_updated_hash(self):
        self.create();manifest = sr.read_json(self.stage / 'manifest.json');record = manifest['records'][0]
        path = Path(record['staged_quartet']['json']['path']);data = sr.read_json(path);data['untouched']['truth'] = False
        path.write_bytes(sr.encode(data));record['staged_quartet']['json'] = sr.binding(path)
        (self.stage / 'manifest.json').write_bytes(sr.encode(manifest))
        with self.assertRaises(ValueError):sr.verify_stage(self.stage / 'manifest.json')

    def test_undeclared_txt_or_line_ending_change_detected(self):
        self.create();manifest = sr.read_json(self.stage / 'manifest.json');record = manifest['records'][0]
        path = Path(record['staged_quartet']['txt']['path']);path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
        record['staged_quartet']['txt'] = sr.binding(path);(self.stage / 'manifest.json').write_bytes(sr.encode(manifest))
        with self.assertRaises(ValueError):sr.verify_stage(self.stage / 'manifest.json')

    def test_publish_requires_independent_exact_manifest_acceptance(self):
        self.create();path = self.acceptance();acceptance = sr.read_json(path);acceptance['manifest_sha256'] = '0' * 64
        path.write_bytes(sr.encode(acceptance));before = self.text.read_bytes()
        with self.assertRaises(ValueError):sr.publish(self.stage / 'manifest.json', path)
        self.assertEqual(self.text.read_bytes(), before)

    def test_changed_live_preimage_prevents_any_publication(self):
        self.create();acceptance = self.acceptance();self.notes.write_bytes(b'new independent notes')
        before = self.text.read_bytes()
        with self.assertRaises(ValueError):sr.publish(self.stage / 'manifest.json', acceptance)
        self.assertEqual(self.text.read_bytes(), before)

    def test_incomplete_publication_journal_requires_explicit_reconciliation(self):
        self.create();acceptance = self.acceptance();(self.stage / 'publication-in-progress.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):sr.publish(self.stage / 'manifest.json', acceptance)

    def test_legacy_stage_verify_requires_existing_acceptance_and_never_publishes(self):
        self.create();manifest = sr.read_json(self.stage / 'manifest.json');manifest['schema'] = sr.LEGACY
        path = self.stage / 'legacy-manifest.json';path.write_bytes(sr.encode(manifest));acceptance = self.acceptance(path)
        with self.assertRaises(ValueError):sr.verify_stage(path)
        proof = sr.verify_stage(path, acceptance=acceptance)
        self.assertEqual(proof['phase'], 'staged')
        self.assertIn('legacy_has_no_declarative_patch_list', proof['checks'][0]['json_patch_scope'])
        with self.assertRaises(ValueError):sr.publish(path, acceptance)

    def test_stage_cannot_be_inside_targets_or_reused(self):
        self.save_intent()
        with self.assertRaises(ValueError):sr.create_stage(self.intent_path, self.target / 'stage')
        self.create()
        with self.assertRaises(ValueError):sr.create_stage(self.intent_path, self.stage)


if __name__ == '__main__':unittest.main(verbosity=2)

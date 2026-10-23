"""Experiment plumbing tests use artificial ink and never personal samples."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from scripts import run_handwriting_experiment as experiment


def fixture(root):
    bank = {'schema_version': 1, 'reviewed': True, 'source_sha256': 'synthetic', 'glyphs': {}, 'words': {}}
    for index, char in enumerate('ab012+%=.'):
        path = root / f'g{index}.png'
        image = Image.new('L', (8, 16), 255)
        ImageDraw.Draw(image).line((1, 14, 3, 2, 6, 14), fill=0, width=2)
        image.save(path)
        bank['glyphs'][char] = {'file': path.name, 'sha256': experiment.digest(path), 'baseline': 14, 'advance': 10}
    bank['words']['ab'] = dict(bank['glyphs']['a'])
    path = root / 'bank.json'
    experiment.write_json(path, bank)
    return path


class ExperimentWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bank_dir = self.root / 'bank'
        self.bank_dir.mkdir()
        self.bank = fixture(self.bank_dir)
        self.suite = self.root / 'suite.json'
        experiment.write_json(self.suite, {'cases': [{'id': 'new-words', 'text': 'ba ab\n1+1=2 0.1%'}]})

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_cases_preflight_before_output_created(self):
        experiment.write_json(self.suite, {'cases': [{'id': 'good', 'text': 'ab'}, {'id': 'bad', 'text': 'ba!'}]})
        output = self.root / 'result'
        with self.assertRaisesRegex(ValueError, 'Unsupported characters in bad'):
            experiment.run_experiment(self.bank, None, self.suite, output, modes=('reference',))
        self.assertFalse(output.exists())

    def test_existing_directory_and_unsafe_or_duplicate_ids_rejected(self):
        output = self.root / 'output'
        output.mkdir()
        (output / 'manifest.json').write_text('preserve me')
        with self.assertRaisesRegex(ValueError, 'never overwritten'):
            experiment.preflight(self.bank, None, self.suite, output, ('reference',), 42)
        self.assertEqual((output / 'manifest.json').read_text(), 'preserve me')
        for ids in (['../escape'], ['CON'], ['case', 'CASE']):
            experiment.write_json(self.suite, {'cases': [{'id': item, 'text': 'ab'} for item in ids]})
            with self.assertRaises(ValueError):
                experiment.preflight(self.bank, None, self.suite, self.root / 'new', ('reference',), 42)

    def test_html_escapes_case_title_text_and_image_attributes(self):
        suite = {'cases': [{'id': 'case', 'title': '<script>alert(1)</script>', 'text': '<img src=x onerror=alert(2)> & "quotes"'}]}
        output = experiment.review_html(suite, ('reference',), {'case/reference/page-001.png': 'hash'})
        self.assertNotIn('<script>', output)
        self.assertNotIn('<img src=x', output)
        self.assertIn('&lt;script&gt;', output)
        self.assertIn('&lt;img src=x', output)
        self.assertIn('case/reference/page-001.png', output)
        self.assertIn('Accuracy and similarity are unverified', output)

    def test_overlap_diagnostics_do_not_claim_blind_validation(self):
        report = experiment.diagnostics({'text': 'Ab ba ab 12'}, {'words': {'ab': {}}},
                                        {'training_words': ['ab'], 'pairs': {'ab': [1, 1]}, 'excluded_words': ['ba']}, ['ab'])
        self.assertEqual(report['training_word_matches'], ['ab'])
        self.assertEqual(report['words_not_in_training'], ['ba'])
        self.assertEqual(report['pairs_not_observed_directly_in_training'], ['ba'])
        self.assertEqual(report['requested_exclusions_still_in_training'], ['ab'])
        self.assertIn('not blind', report['interpretation'])

    def test_snapshot_replay_and_fingerprint_are_path_independent(self):
        def render(folder, request, preferences):
            self.assertEqual(request['expected_input_hashes'],
                             {'reference_bank_sha256': experiment.digest(request['reference_bank'])})
            # No PDF authoring in plumbing tests. Compare a deterministic stand-in
            # artifact; the rendering modules have separate pixel/baseline tests.
            experiment.write_json(folder / 'generated.json', {'text': request['text'], 'seed': request['seed']})
        first = self.root / 'first'
        with patch.object(experiment, 'render_case', side_effect=render):
            one = experiment.run_experiment(self.bank, None, self.suite, first, modes=('reference',), snapshot=True)
            moved = self.root / 'relocated'
            shutil.copytree(first, moved)
            shutil.rmtree(self.bank_dir)
            two = experiment.run_experiment(moved / 'inputs/bank/bank.json', None, moved / 'suite.json',
                                            self.root / 'second', modes=('reference',))
        self.assertEqual(one['run_fingerprint'], two['run_fingerprint'])
        self.assertEqual(one['artifact_sha256'], two['artifact_sha256'])
        self.assertEqual(one['status'], 'needs-human-review')
        self.assertEqual(one['validation']['writer_similarity'], 'unverified')
        self.assertEqual(one['replay_inputs']['bank'], 'inputs/bank/bank.json')

    def test_input_change_between_cases_rejects_mixed_run(self):
        from web.runtime.vatr_worker import verify_request_inputs
        experiment.write_json(self.suite, {'cases': [{'id': 'first', 'text': 'ab'}, {'id': 'second', 'text': 'ba'}]})
        original_hash = experiment.digest(self.bank)
        calls = []

        def render(folder, request, preferences):
            calls.append(request)
            self.assertEqual(request['expected_input_hashes']['reference_bank_sha256'], original_hash)
            verify_request_inputs(request)
            # Simulate a concurrent refit after the first case has rendered.
            with self.bank.open('a', encoding='utf-8') as stream:
                stream.write('\n')

        output = self.root / 'changed-input'
        with patch.object(experiment, 'render_case', side_effect=render):
            with self.assertRaisesRegex(ValueError, 'changed after this job was queued'):
                experiment.run_experiment(self.bank, None, self.suite, output, modes=('reference',))
        self.assertEqual(len(calls), 2)
        self.assertEqual(json.loads((output / 'manifest.json').read_text())['status'], 'failed')

    def test_failed_render_is_recorded_and_cannot_be_overwritten(self):
        output = self.root / 'failure'
        with patch.object(experiment, 'render_case', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
                experiment.run_experiment(self.bank, None, self.suite, output, modes=('reference',))
        record = json.loads((output / 'manifest.json').read_text())
        self.assertEqual(record['status'], 'failed')
        with self.assertRaisesRegex(ValueError, 'never overwritten'):
            experiment.run_experiment(self.bank, None, self.suite, output, modes=('reference',))


if __name__ == '__main__':
    unittest.main()

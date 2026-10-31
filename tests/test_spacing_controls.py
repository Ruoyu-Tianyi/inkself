"""Spacing preference validation and persistence use synthetic sample fixtures."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from web import app as web
from web.runtime.spacing import DEFAULTS, PRESETS, normalize_spacing
from tests.test_math_renderer import fixture


class SpacingValidation(unittest.TestCase):
    def test_presets_and_overrides_have_unambiguous_saved_names(self):
        self.assertEqual(normalize_spacing(), {'preset': 'natural', **DEFAULTS})
        for name, values in PRESETS.items():
            self.assertEqual(normalize_spacing({'preset': name}), {'preset': name, **values})
        custom = normalize_spacing({'preset': 'compact', 'word': 1.7})
        self.assertEqual(custom['preset'], 'custom')
        self.assertEqual(custom['word'], 1.7)
        self.assertEqual(custom['line'], PRESETS['compact']['line'])
        custom['word'] = .5
        self.assertEqual(normalize_spacing({'preset': 'compact'})['word'], .8)

    def test_invalid_inputs_fail_instead_of_becoming_silent_defaults(self):
        for value in [[], 'natural', {'preset': []}, {'preset': 'unknown'}, {'unknown': 1},
                      {'word': True}, {'word': '1.2'}, {'word': float('nan')},
                      {'word': float('inf')}, {'letter': 0}, {'line': 5},
                      {'baseline': -1}, {'variation': 2.01}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_spacing(value)


class SpacingPreferenceAPI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pid = 'e' * 32
        folder = self.root / 'profiles' / self.pid
        bank = folder / 'reference-bank'
        bank.mkdir(parents=True)
        fixture(bank)
        web.write(folder / 'profile.json', {
            'id': self.pid, 'name': 'Synthetic spacing', 'status': 'ready',
            'created_at': '2026-01-01', 'sample_sha256': 'synthetic-math',
            'sample': {'lines': []}, 'selected_lines': [], 'preferences': {},
            'reference_bank': 'reference-bank/bank.json',
        })
        self.store = patch.object(web, 'DATA', self.root)
        self.store.start()
        self.submit = patch.object(web.POOL, 'submit')
        self.worker = self.submit.start()
        self.client = TestClient(web.app)
        self.client.__enter__()
        self.headers = {'X-Inkself-Token': self.client.get('/api/session').json()['token']}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.submit.stop()
        self.store.stop()
        self.temp.cleanup()

    def queue(self, **options):
        return self.client.post('/api/jobs', headers=self.headers, json={
            'profile_id': self.pid, 'text': 'Result 123', 'render_mode': 'reference', **options,
        })

    def test_legacy_requests_receive_compatible_spacing_defaults(self):
        response = self.queue()
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()['preferences']['spacing'], normalize_spacing())

    def test_settings_roundtrip_to_worker_profile_history_and_assignment(self):
        spacing = {'preset': 'relaxed', 'letter': 1.4, 'number': 1.6, 'baseline': 1.8}
        response = self.queue(spacing=spacing)
        self.assertEqual(response.status_code, 202, response.text)
        first = response.json()
        expected = normalize_spacing(spacing)
        folder = self.root / 'jobs' / first['id']
        self.assertEqual(web.read(folder / 'request.json')['spacing'], expected)
        self.assertEqual(web.read(self.root / 'profiles' / self.pid / 'profile.json')['preferences']['spacing'], expected)
        saved = copy.deepcopy(first['preferences'])
        second = self.queue(text='Result $x_1=12$', layout_mode='assignment',
                            math_enabled=True, allow_supplemental_math=True,
                            spacing={'preset': 'compact'})
        self.assertEqual(second.status_code, 202, second.text)
        self.assertEqual(second.json()['preferences']['spacing'], normalize_spacing({'preset': 'compact'}))
        history = self.client.get('/api/jobs/' + first['id']).json()
        self.assertEqual(history['preferences'], saved)
        request = web.read(self.root / 'jobs' / second.json()['id'] / 'request.json')
        self.assertEqual(request['spacing'], normalize_spacing({'preset': 'compact'}))
        self.assertEqual(request['layout_mode'], 'assignment')

    def test_bad_spacing_rejected_before_any_job_or_preference_change(self):
        for settings in [{'preset': 'bogus'}, {'number': 10}, {'word': True},
                         {'variation': '1'}, {'letter': .1}, {'typo': 1}]:
            with self.subTest(settings=settings):
                response = self.queue(spacing=settings)
                self.assertEqual(response.status_code, 422, response.text)
        self.worker.assert_not_called()
        self.assertEqual(list((self.root / 'jobs').glob('*')), [])
        profile = web.read(self.root / 'profiles' / self.pid / 'profile.json')
        self.assertEqual(profile['preferences'], {})


if __name__ == '__main__':
    unittest.main()

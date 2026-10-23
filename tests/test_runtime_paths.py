"""Desktop storage and worker dispatch never depend on the installed Python."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web import runtime_paths as paths


class RuntimePaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.tmp.cleanup()

    def frozen(self):
        return patch.multiple(sys, frozen=True, _MEIPASS=str(self.root / 'resources'),
                              executable=str(self.root / 'Inkself.exe'), create=True)

    def test_source_defaults_keep_project_paths(self):
        with patch.object(sys, 'frozen', False, create=True):
            root = Path(paths.__file__).resolve().parents[1]
            self.assertEqual(paths.resource_root(), root)
            self.assertEqual(paths.data_root(), root / '.local/web-data')
            self.assertEqual(paths.model_root(), root / '.local/vendor/vatrpp')
            self.assertEqual(paths.model_probe_path(), root / '.local/model-probe.json')
            suffix = '.local/model-env/Scripts/python.exe' if os.name == 'nt' else '.local/model-env/bin/python'
            self.assertEqual(paths.model_python(), root / suffix)

    def test_frozen_resources_and_portable_writable_paths_are_separate(self):
        with self.frozen():
            self.assertEqual(paths.resource_root(), self.root / 'resources')
            self.assertEqual(paths.data_root(), self.root / 'data')
            self.assertEqual(paths.model_root(), self.root / 'models/vatrpp')
            self.assertEqual(paths.model_probe_path(), self.root / 'models/model-probe.json')
            self.assertIsNone(paths.model_python())

    def test_environment_overrides_are_resolved_in_source_and_desktop_modes(self):
        expected = {name: self.root / value for name, value in {
            'INKSELF_DATA': 'owner-data', 'INKSELF_MODEL_DIR': 'external-model',
            'INKSELF_MODEL_PYTHON': 'external-python.exe'}.items()}
        with patch.dict(os.environ, {name: str(value) for name, value in expected.items()}):
            for frozen in [False, True]:
                with patch.object(sys, 'frozen', frozen, create=True):
                    self.assertEqual(paths.data_root(), expected['INKSELF_DATA'])
                    self.assertEqual(paths.model_root(), expected['INKSELF_MODEL_DIR'])
                    self.assertEqual(paths.model_python(), expected['INKSELF_MODEL_PYTHON'])

    def test_frozen_local_workers_reenter_executable_without_python_switches(self):
        request = self.root / 'job/request.json'
        with self.frozen():
            for mode in ['reference', 'learned-habits']:
                self.assertEqual(paths.worker_command(request, mode),
                                 [str(self.root / 'Inkself.exe'), '--worker', str(request)])

    def test_source_worker_keeps_python_script_command(self):
        request = self.root / 'request.json'
        with patch.object(sys, 'frozen', False, create=True):
            for mode in sorted(paths.RENDERERS):
                self.assertEqual(paths.worker_command(request, mode),
                    [str(paths.model_python()), str(paths.resource_root() / 'web/runtime/vatr_worker.py'), str(request)])

    def test_neural_desktop_worker_requires_explicit_external_python(self):
        request = self.root / 'request.json'
        with self.frozen():
            for mode in ['model', 'model-calibrated']:
                with self.assertRaisesRegex(RuntimeError, 'INKSELF_MODEL_PYTHON'):
                    paths.worker_command(request, mode)
            external = self.root / 'external/python.exe'
            with patch.dict(os.environ, {'INKSELF_MODEL_PYTHON': str(external)}):
                self.assertEqual(paths.worker_command(request, 'model'),
                    [str(external), str(self.root / 'resources/web/runtime/vatr_worker.py'), str(request)])
            with self.assertRaisesRegex(ValueError, 'Unknown'):
                paths.worker_command(request, 'unsupported')

    def test_session_exposes_only_supplied_instance_identity(self):
        from web import app as web_app
        self.assertIsNone(web_app.session()['instance_id'])
        with patch.dict(os.environ, {'INKSELF_INSTANCE_ID': 'desktop-instance-test'}):
            response = web_app.session()
            self.assertEqual(response['instance_id'], 'desktop-instance-test')
            self.assertEqual(response['mode'], 'local-single-owner')

    def test_bundled_neural_worker_needs_no_external_python(self):
        request=self.root/'request.json'
        worker=self.root/'ai-runtime/InkselfAI.exe'
        worker.parent.mkdir();worker.write_bytes(b'fixture')
        with self.frozen():
            self.assertEqual(paths.model_worker(),worker)
            self.assertEqual(paths.worker_command(request,'model'),[str(worker),'--worker',str(request)])
            self.assertEqual(paths.worker_command(request,'model',python=self.root/'legacy/python.exe'),
                [str(self.root/'legacy/python.exe'),str(self.root/'resources/web/runtime/vatr_worker.py'),str(request)])

    def test_installed_storage_stays_outside_program_files(self):
        (self.root/'installed-mode.json').write_text('{"mode":"installed"}')
        with self.frozen(),patch.dict(os.environ,{'LOCALAPPDATA':str(self.root/'LocalData')}):
            self.assertEqual(paths.data_root(),self.root/'LocalData/Inkself/data')
            self.assertEqual(paths.model_root(),self.root/'LocalData/Inkself/data/models/vatrpp')


if __name__ == '__main__':
    unittest.main()

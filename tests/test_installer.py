"""Installer safety tests use tiny synthetic bundles; no compiler is executed."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_installer as installer

REAL_MODEL_MANIFEST = installer.MODEL_MANIFEST


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def checksums(root):
    records = [f'{installer.sha256(path)}  {path.relative_to(root).as_posix()}'
               for path in sorted(root.rglob('*')) if path.is_file() and path.name != 'SHA256SUMS.txt']
    (root / 'SHA256SUMS.txt').write_text('\n'.join(records) + '\n', encoding='utf-8')


def fixture(root, *, ai=False):
    root.mkdir(parents=True)
    (root / '_internal').mkdir()
    (root / 'licenses' / 'python').mkdir(parents=True)
    (root / ('InkselfAI.exe' if ai else 'Inkself.exe')).write_bytes(b'synthetic executable')
    (root / '_internal' / 'runtime.dll').write_bytes(b'synthetic runtime')
    (root / 'licenses' / 'python' / 'LICENSE.txt').write_text('Synthetic license')
    (root / 'THIRD_PARTY_NOTICES.txt').write_text('Synthetic dependency notices')
    write(root / 'build-manifest.json', {'application': 'InkselfAI' if ai else 'Inkself', 'includes_model_assets': False})
    checksums(root)
    return root


def model_fixture(root, names=None):
    files = {'model.safetensors': b'synthetic weights', 'config.json': b'{}',
             'files/unifont.pickle': b'synthetic prototype', 'files/english_words.txt': b'word',
             'models/model.py': b'# synthetic model', 'README.md': b'Synthetic upstream notice'}
    if names is not None:
        files = {name: ('Synthetic asset: ' + name).encode() for name in names}
    for name, value in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    write(root / 'download-manifest.json', {'repo': installer.MODEL_REPO, 'revision': installer.MODEL_REVISION,
          'files': [[name, hashlib.sha256(value).hexdigest()] for name, value in files.items()]})
    spec = {'schema_version': 1, 'repository': installer.MODEL_REPO, 'revision': installer.MODEL_REVISION,
            'files': [{'path': name, 'size': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
                      for name, value in files.items()]}
    return root, spec


class InstallerSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.app = fixture(self.root / 'Core 应用')
        self.ai = fixture(self.root / 'AI runtime', ai=True)
        self.model, self.model_spec = model_fixture(self.root / 'test model')
        self.model_manifest = self.root / 'pinned-model-assets.json'
        write(self.model_manifest, self.model_spec)
        self.manifest_patch = patch.object(installer, 'MODEL_MANIFEST', self.model_manifest)
        self.manifest_patch.start()
        self.compiler = self.root / 'ISCC.exe'
        self.compiler.write_bytes(b'synthetic compiler placeholder')
        self.output = self.root / 'setup output'

    def tearDown(self):
        self.manifest_patch.stop()
        self.tmp.cleanup()

    def test_license_inventory_does_not_copy_package_code_or_caches(self):
        from scripts.build_desktop import license_file
        self.assertTrue(license_file('package/licenses/LICENSE.txt'))
        self.assertTrue(license_file('package.dist-info/licenses/MIT'))
        self.assertFalse(license_file('packaging/licenses/__init__.py'))
        self.assertFalse(license_file('packaging/licenses/__pycache__/__init__.cpython-311.pyc'))

    def test_first_party_license_files_are_preserved_in_payload(self):
        for name in ('LICENSE','NOTICE.txt','COMMERCIAL-LICENSE.md'):
            (self.app/name).write_text('Synthetic project notice',encoding='utf-8')
        checksums(self.app)
        names={item['relative'] for item in installer.installer_payload(self.app)}
        self.assertTrue({'LICENSE','NOTICE.txt','COMMERCIAL-LICENSE.md'}.issubset(names))

    def test_core_allowlist_includes_runtime_notices_checksums_and_marker(self):
        records = installer.installer_payload(self.app)
        names = {item['relative'] for item in records}
        self.assertTrue({'Inkself.exe', '_internal/runtime.dll', 'licenses/python/LICENSE.txt',
                         'SHA256SUMS.txt', 'THIRD_PARTY_NOTICES.txt', 'installed-mode.json'}.issubset(names))
        include = installer.files_include(records)
        self.assertNotIn('recursesubdirs', include.lower())
        self.assertNotIn('Source: "*', include)
        self.assertTrue(all(item['component'] != 'model' for item in records))

    def test_ai_runtime_destination_and_offline_model_retention(self):
        records = installer.installer_payload(self.app, self.ai, self.model)
        ai_exe = next(item for item in records if item['relative'] == 'InkselfAI.exe')
        self.assertEqual(ai_exe['destination'], r'{app}\ai-runtime')
        models = [item for item in records if item['component'] == 'model']
        self.assertTrue(models)
        self.assertTrue(all(item['preserve_on_uninstall'] for item in models))
        lines = [line for line in installer.files_include(records).splitlines() if 'models\\vatrpp' in line]
        self.assertTrue(all('uninsneveruninstall' in line for line in lines))
        self.assertTrue(all('onlyifdoesntexist' not in line for line in lines))
        self.assertTrue(any('README.md' in line for line in lines))

    def test_offline_installer_covers_all_49_runtime_assets_and_is_ready(self):
        from web import model_setup
        actual = json.loads(REAL_MODEL_MANIFEST.read_text(encoding='utf-8'))
        names = [item['path'] for item in actual['files']]
        self.assertEqual(len(names), 49)
        model, spec = model_fixture(self.root / 'full synthetic model', names)
        write(self.model_manifest, spec)
        records = installer.installer_payload(self.app, self.ai, model)
        models = [item for item in records if item['component'] == 'model']
        self.assertTrue(set(names).issubset(item['relative'] for item in models))
        self.assertIn('train.py', {item['relative'] for item in models})
        installed = self.root / 'installed data' / 'models' / 'vatrpp'
        for item in models:
            target = installed / item['relative']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item['source'], target)
        with patch.object(model_setup, 'MANIFEST', self.model_manifest):
            self.assertTrue(model_setup.assets_ready(installed))
        self.assertEqual(json.loads((installed / 'inkself-verified-assets.json').read_text()), spec)

    def test_model_without_legacy_download_manifest_uses_same_pinned_assets(self):
        (self.model / 'download-manifest.json').unlink()
        _, files = installer.verified_model(self.model)
        self.assertTrue({item['path'] for item in self.model_spec['files']}.issubset(files))
        self.assertIn('inkself-verified-assets.json', files)

    def test_omitted_non_runtime_script_is_still_rejected_by_full_manifest(self):
        extra = {'path': 'train.py', 'size': 1, 'sha256': hashlib.sha256(b'x').hexdigest()}
        self.model_spec['files'].append(extra)
        write(self.model_manifest, self.model_spec)
        with self.assertRaisesRegex(ValueError, 'missing'):
            installer.verified_model(self.model)

    def test_private_directories_rejected_even_when_empty_or_checksummed(self):
        for name in ('data', 'config', 'logs', 'models', 'profiles', '.local'):
            with self.subTest(name=name):
                directory = self.app / name
                directory.mkdir()
                with self.assertRaisesRegex(ValueError, 'Private runtime directory'):
                    installer.installer_payload(self.app)
                directory.rmdir()
        write(self.app / '_internal' / 'profile.json', {'name': 'Synthetic private profile'})
        checksums(self.app)
        with self.assertRaisesRegex(ValueError, 'Private profile'):
            installer.installer_payload(self.app)

    def test_unknown_files_and_weights_are_not_silently_packaged(self):
        (self.app / 'secret.txt').write_text('synthetic secret')
        checksums(self.app)
        with self.assertRaisesRegex(ValueError, 'allowlist'):
            installer.installer_payload(self.app)
        (self.app / 'secret.txt').unlink()
        checksums(self.app)
        (self.ai / '_internal' / 'weight.pth').write_bytes(b'synthetic weight')
        checksums(self.ai)
        with self.assertRaisesRegex(ValueError, 'weights'):
            installer.installer_payload(self.app, self.ai)

    def test_release_tampering_and_incomplete_checksum_coverage_are_rejected(self):
        (self.app / 'Inkself.exe').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            installer.installer_payload(self.app)
        checksums(self.app)
        (self.app / '_internal' / 'extra.dll').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'cover every'):
            installer.installer_payload(self.app)

    def test_missing_notices_invalid_model_and_unsafe_model_paths_are_rejected(self):
        (self.app / 'THIRD_PARTY_NOTICES.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'complete release'):
            installer.installer_payload(self.app)
        with self.assertRaisesRegex(ValueError, 'requires --ai-runtime'):
            installer.installer_payload(self.ai, model=self.model)
        manifest_path = self.model / 'download-manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['files'].append(['../private.txt', None])
        write(manifest_path, manifest)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            installer.verified_model(self.model)

    def test_reparse_points_and_iss_path_injection_are_rejected(self):
        class Info:
            st_mode = 0o40755
            st_file_attributes = 0x400
        with patch.object(Path, 'lstat', return_value=Info()):
            with self.assertRaisesRegex(ValueError, 'reparse'):
                installer._ordinary(self.app)
        for name in ('file*', 'file?', 'file\nSource: "*"', 'file"quoted'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'control characters'):
                    installer._safe_iss_literal(name)
        self.assertEqual(installer._safe_iss_literal('braces{literal}'), 'braces{{literal}')

    def test_existing_installer_is_never_overwritten(self):
        self.output.mkdir()
        setup = self.output / 'Inkself-Setup.exe'
        setup.write_bytes(b'preserve this existing setup')
        with patch.object(installer.subprocess, 'run') as compiler:
            with self.assertRaises(FileExistsError):
                installer.build_installer(self.app, compiler=self.compiler, output=self.output)
            compiler.assert_not_called()
        self.assertEqual(setup.read_bytes(), b'preserve this existing setup')

    def test_build_publishes_manifest_without_private_source_paths(self):
        seen = {}
        def fake_compile(command, **kwargs):
            seen['command'] = command
            directory = Path(next(arg.split('=', 1)[1] for arg in command if arg.startswith('/DBuildOutput=')))
            include = Path(next(arg.split('=', 1)[1] for arg in command if arg.startswith('/DFileListPath=')))
            seen['include'] = include.read_text(encoding='utf-8-sig')
            (directory / 'Inkself-Setup.exe').write_bytes(b'synthetic compiled setup')
        with patch.object(installer.subprocess, 'run', side_effect=fake_compile):
            setup = installer.build_installer(self.app, compiler=self.compiler, output=self.output, ai_runtime=self.ai)
        self.assertEqual(setup.read_bytes(), b'synthetic compiled setup')
        receipt = json.loads(setup.with_suffix('.manifest.json').read_text())
        self.assertTrue(receipt['includes_ai_runtime'])
        self.assertFalse(receipt['includes_model_assets'])
        self.assertNotIn(str(self.root), json.dumps(receipt))
        self.assertIn('installed-mode.json', seen['include'])
        self.assertEqual(receipt['sha256'], installer.sha256(setup))
        self.assertTrue(setup.with_suffix('.exe.sha256').is_file())

    def test_input_change_during_compile_does_not_publish_setup(self):
        def fake_compile(command, **kwargs):
            directory = Path(next(arg.split('=', 1)[1] for arg in command if arg.startswith('/DBuildOutput=')))
            (directory / 'Inkself-Setup.exe').write_bytes(b'synthetic setup')
            (self.app / 'Inkself.exe').write_bytes(b'changed while compiling')
        with patch.object(installer.subprocess, 'run', side_effect=fake_compile):
            with self.assertRaisesRegex(ValueError, 'changed during compilation'):
                installer.build_installer(self.app, compiler=self.compiler, output=self.output)
        self.assertFalse((self.output / 'Inkself-Setup.exe').exists())

    def test_output_cannot_modify_input_bundle(self):
        with self.assertRaisesRegex(ValueError, 'outside all input'):
            installer.build_installer(self.app, compiler=self.compiler, output=self.app / 'new setup')
        self.assertFalse((self.app / 'new setup').exists())

    def test_template_is_per_user_and_never_deletes_user_data(self):
        template = installer.TEMPLATE.read_text(encoding='utf-8')
        self.assertIn('PrivilegesRequired=lowest', template)
        self.assertIn(r'DefaultDirName={localappdata}\Programs\Inkself', template)
        self.assertIn('Flags: uninsneveruninstall', template)
        self.assertNotIn('[UninstallDelete]', template)
        self.assertNotIn('[InstallDelete]', template)
        self.assertNotIn('[Registry]', template)
        self.assertIn('ButtonInstall=安装', template)
        self.assertIn(r'compiler:Languages\ChineseSimplified.isl', template)
        self.assertNotIn('compiler:Default.isl', template)
        self.assertIn('WelcomeLabel1=欢迎安装 Inkself', template)
        self.assertIn('FinishedHeadingLabel=Inkself 安装完成', template)
        self.assertEqual(json.loads(installer.INSTALLED_MODE.read_text())['mode'], 'installed')


if __name__ == '__main__':
    unittest.main()

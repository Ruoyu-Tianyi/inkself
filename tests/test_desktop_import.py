"""Desktop migration fixtures are synthetic and never use personal samples."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.import_desktop_profiles import import_profiles


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def fixture(root, pid='a' * 32, *, ready=True, with_bank=True):
    folder = root / 'profiles' / pid
    sample = folder / 'sample'
    sample.mkdir(parents=True)
    (sample / 'normalized.png').write_bytes(b'synthetic normalized sample')
    (sample / 'line-000.png').write_bytes(b'synthetic line sample')
    profile = {'id': pid, 'name': 'Synthetic writer', 'created_at': '2026-01-01T00:00:00Z',
               'status': 'ready' if ready else 'needs-review', 'sample_sha256': 'f' * 64,
               'sample': {'lines': [{'file': 'line-000.png', 'width': 20, 'height': 10}]},
               'selected_lines': [0] if ready else [], 'preferences': {'size': 16}}
    if with_bank:
        bank_dir = folder / 'bank'
        bank_dir.mkdir()
        image = bank_dir / 'a.png'
        image.write_bytes(b'synthetic glyph')
        bank = {'schema_version': 1, 'reviewed': True, 'source_sha256': 'f' * 64,
                'glyphs': {'a': {'file': 'a.png', 'sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                                  'baseline': 8, 'advance': 10}}, 'words': {}}
        write(bank_dir / 'bank.json', bank)
        profile['reference_bank'] = 'bank/bank.json'
        profile['habit_model'] = 'habit.json'
        write(folder / 'habit.json', {'schema_version': 1, 'source_sha256': 'f' * 64,
                                    'bank_sha256': hashlib.sha256((bank_dir / 'bank.json').read_bytes()).hexdigest()})
    write(folder / 'profile.json', profile)
    return folder, profile


class DesktopImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source, self.target = self.root / 'old data', self.root / 'desktop 数据'
        self.folder, self.profile = fixture(self.source)

    def tearDown(self):
        self.tmp.cleanup()

    def test_imports_only_profiles_and_preserves_relative_references(self):
        write(self.source / 'jobs' / ('d' * 32) / 'request.json', {'output': 'C:/old/private/path'})
        (self.source / 'private.log').write_text('synthetic private log')
        result = import_profiles(self.source, self.target)
        self.assertEqual(result, {'imported': ['a' * 32], 'skipped': [], 'imported_count': 1, 'skipped_count': 0})
        copied = self.target / 'profiles' / ('a' * 32)
        self.assertEqual(json.loads((copied / 'profile.json').read_text()), self.profile)
        self.assertTrue((copied / 'bank' / 'a.png').is_file())
        self.assertEqual([p.name for p in self.target.iterdir()], ['profiles'])
        self.assertEqual([p.name for p in copied.parent.iterdir()], ['a' * 32])

    def test_existing_id_is_skipped_without_overwriting(self):
        import_profiles(self.source, self.target)
        copied = self.target / 'profiles' / ('a' * 32) / 'profile.json'
        original = copied.read_bytes()
        self.profile['name'] = 'New source name'
        write(self.folder / 'profile.json', self.profile)
        result = import_profiles(self.source, self.target)
        self.assertEqual(result['skipped'], ['a' * 32])
        self.assertEqual(result['imported_count'], 0)
        self.assertEqual(copied.read_bytes(), original)

    def test_needs_review_profile_without_reference_bank_is_valid(self):
        fixture(self.source, 'b' * 32, ready=False, with_bank=False)
        self.assertEqual(import_profiles(self.source, self.target)['imported_count'], 2)

    def test_validates_all_profiles_before_creating_target(self):
        other, profile = fixture(self.source, 'b' * 32)
        profile['status'] = 'unknown'
        write(other / 'profile.json', profile)
        with self.assertRaisesRegex(ValueError, 'Invalid profile metadata'):
            import_profiles(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_rejects_traversal_and_absolute_paths(self):
        for field, path in [('reference_bank', '../outside.json'), ('habit_model', 'C:\\private\\habit.json'),
                            ('reference_bank', '/private/bank.json'), ('habit_model', 'habit.json:stream')]:
            with self.subTest(field=field, path=path):
                profile = dict(self.profile, **{field: path})
                write(self.folder / 'profile.json', profile)
                with self.assertRaises(ValueError):
                    import_profiles(self.source, self.target)
                self.assertFalse(self.target.exists())

    def test_sample_line_and_nested_bank_references_cannot_escape(self):
        self.profile['sample']['lines'][0]['file'] = '../profile.json'
        write(self.folder / 'profile.json', self.profile)
        with self.assertRaises(ValueError):
            import_profiles(self.source, self.target)
        self.profile['sample']['lines'][0]['file'] = 'line-000.png'
        write(self.folder / 'profile.json', self.profile)
        bank_path = self.folder / 'bank' / 'bank.json'
        bank = json.loads(bank_path.read_text())
        bank['glyphs']['a']['file'] = '../../outside.png'
        write(bank_path, bank)
        with self.assertRaises(ValueError):
            import_profiles(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_corrupt_json_missing_assets_and_bad_selection_are_rejected(self):
        for value in [None, [], {'id': 'wrong'}, dict(self.profile, selected_lines=[True]),
                      dict(self.profile, selected_lines=[7]), dict(self.profile, selected_lines=[])]:
            with self.subTest(value=value):
                write(self.folder / 'profile.json', value)
                with self.assertRaises(ValueError):
                    import_profiles(self.source, self.target)
        write(self.folder / 'profile.json', self.profile)
        (self.folder / 'sample' / 'normalized.png').unlink()
        with self.assertRaises(ValueError):
            import_profiles(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_rejects_symbolic_links_even_when_pointing_inside_profile(self):
        link = self.folder / 'linked-sample.png'
        try:
            link.symlink_to(self.folder / 'sample' / 'normalized.png')
        except OSError:
            self.skipTest('Creating Windows symlinks needs developer mode or permission.')
        try:
            with self.assertRaisesRegex(ValueError, 'Symbolic links'):
                import_profiles(self.source, self.target)
            self.assertFalse(self.target.exists())
        finally:
            link.unlink()

    def test_windows_reparse_points_are_rejected(self):
        from scripts import import_desktop_profiles as module
        class Info:
            st_mode = 0o40755
            st_file_attributes = 0x400
        with patch.object(Path, 'lstat', return_value=Info()):
            with self.assertRaisesRegex(ValueError, 'reparse points'):
                module._no_link(self.folder)

    def test_failed_copy_never_publishes_partial_profile(self):
        from scripts import import_desktop_profiles as module
        def broken_copy(source, staging, **kwargs):
            (staging / 'partial.txt').write_text('partial')
            raise OSError('Simulated interrupted copy')
        with patch.object(module.shutil, 'copytree', side_effect=broken_copy):
            with self.assertRaisesRegex(OSError, 'interrupted copy'):
                import_profiles(self.source, self.target)
        self.assertEqual(list((self.target / 'profiles').iterdir()), [])

    def test_checksum_mismatch_and_target_inside_source_are_rejected(self):
        (self.folder / 'bank' / 'a.png').write_bytes(b'changed synthetic ink')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            import_profiles(self.source, self.target)
        self.assertFalse(self.target.exists())
        with self.assertRaisesRegex(ValueError, 'outside the source profiles'):
            import_profiles(self.source, self.folder / 'recursive target')


if __name__ == '__main__':
    unittest.main()

import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/personal-handwriting/scripts/profile.py'
spec = importlib.util.spec_from_file_location('profile_cli', SCRIPT)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class Profiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = self.root / 'store'
    def tearDown(self): self.tmp.cleanup()

    def test_create_duplicate_and_traversal(self):
        profile = p.create(self.store, 'writer-1', 'Writer')
        self.assertEqual(profile['status'], 'reference-only')
        with self.assertRaises(FileExistsError): p.create(self.store, 'writer-1', 'Other')
        for value in ['../escape', 'a/b', '.', 'A', '-a', 'a-', 'x' * 65]:
            with self.assertRaises(ValueError): p.create(self.store, value, 'Bad')

    def test_sample_copy_dedup_and_pairing(self):
        p.create(self.store, 'writer', 'Writer')
        image = self.root / 'sample.png'; image.write_bytes(b'synthetic test bytes, not a handwriting sample')
        transcription = self.root / 'text.txt'; transcription.write_text('abc 012', encoding='utf-8')
        p.add_sample(self.store, 'writer', image, 'freeform')
        data = p.add_sample(self.store, 'writer', image, 'freeform', transcription)
        self.assertEqual(len(data['samples']), 1)
        record = data['samples'][0]
        self.assertEqual((self.store / 'writer' / record['path']).read_bytes(), image.read_bytes())
        self.assertEqual((self.store / 'writer' / record['transcript_path']).read_text(encoding='utf-8'), 'abc 012')
        transcription.write_text('different', encoding='utf-8')
        with self.assertRaises(ValueError): p.add_sample(self.store, 'writer', image, 'freeform', transcription)

    def test_invalid_transcript_has_no_sample_side_effect(self):
        p.create(self.store, 'writer', 'Writer')
        image = self.root / 'sample.jpg'; image.write_bytes(b'test')
        transcript = self.root / 'bad.txt'; transcript.write_bytes(b'\xff\xfe\xff')
        with self.assertRaises(UnicodeError): p.add_sample(self.store, 'writer', image, 'freeform', transcript)
        self.assertEqual(p.load(self.store, 'writer')[1]['samples'], [])
        self.assertFalse((self.store / 'writer/samples').exists())

    def test_update_validation_preserves_existing_data(self):
        p.create(self.store, 'writer', 'Writer')
        original = p.load(self.store, 'writer')[1]
        for value in [{'font_size_pt': 999}, {'seed': True}, {'line_spacing': float('nan')},
                      {'unexpected': 1}, {'missing_glyph': 'silent'}, {'ink_color': 'blue'}]:
            with self.assertRaises(ValueError): p.update(self.store, 'writer', value)
        self.assertEqual(p.load(self.store, 'writer')[1], original)
        updated = p.update(self.store, 'writer', {'font_size_pt': 14, 'seed': 7})
        self.assertEqual(updated['preferences']['seed'], 7)
        self.assertEqual(updated['preferences']['ink_color'], original['preferences']['ink_color'])

if __name__ == '__main__': unittest.main()

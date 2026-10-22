"""Synthetic end-to-end fixtures; these are NOT real personal handwriting."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'engines/glyphs/scripts/handwriting.py'
spec = importlib.util.spec_from_file_location('personal_engine', SCRIPT)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


def filled_sheet(manifest_path, pdf_path, output, angle=0, perspective=False, empty=False, skip=()):
    m = e.read_json(manifest_path)
    document = e.pdfium.PdfDocument(str(pdf_path))
    pages = []
    for index, page in enumerate(document):
        image = page.render(scale=200/72).to_pil().convert('RGB')
        if not empty:
            draw = e.ImageDraw.Draw(image)
            for cell in m['pages'][index]['cells']:
                if cell['char'] in skip: continue
                x, y, w, h = cell['box']
                font = e.ImageFont.truetype(e.font_path(), round((24 + cell['variant']) * 200/72))
                draw.text(((x + w*.16)*200/72, cell['baseline']*200/72), cell['char'],
                          font=font, fill=(25, 46, 90), anchor='ls')
        if perspective:
            data = e.np.array(image)
            height, width = data.shape[:2]
            source = e.np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
            target = e.np.float32([[45, 22], [width-25, 0], [width-1, height-35], [0, height-1]])
            matrix = e.cv2.getPerspectiveTransform(source, target)
            data = e.cv2.warpPerspective(data, matrix, (width, height), borderValue=(255,255,255))
            gradient = e.np.linspace(.78, 1, height).reshape(height, 1, 1)
            data = e.np.clip(data.astype(float)*gradient, 0, 255).astype('uint8')
            image = e.Image.fromarray(data)
        if angle: image = image.rotate(angle, expand=True, fillcolor='white')
        path = Path(output).with_name(Path(output).stem + f'-{index+1}.png')
        image.save(path); pages.append(path)
        page.close()
    document.close()
    return pages


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = self.root / 'store'
        e.profiles.create(self.store, 'writer', 'Synthetic test writer')
        self.template = self.root / 'template.pdf'
        self.manifest = self.root / 'template.json'
        e.make_template(self.template, characters='ABCabc0123+-=÷%', variants=3)

    def tearDown(self): self.tmp.cleanup()

    def extract(self, **options):
        scans = filled_sheet(self.manifest, self.template, self.root/'scan.png', **options)
        return e.extract(self.store, 'writer', self.manifest, scans)

    def ready(self):
        self.extract()
        e.review(self.store, 'writer', True)
        text = self.root/'input.json'
        text.write_text(json.dumps({'blocks': [
            {'type':'heading','text':'ABC'},
            {'type':'paragraph','runs':[{'text':'abc 0123 + 3 = 3 ÷ 1 23%'},
                {'text':'a','subscript':True},{'text':'2','superscript':True}]}]}), encoding='utf-8')
        return text

    def test_template_and_extract(self):
        result = self.extract()
        self.assertEqual(result['glyphs'], 15)
        self.assertEqual(result['variants'], 45)
        self.assertEqual(result['missing'], [])
        self.assertEqual(result['rejected_slots'], [])
        self.assertTrue(Path(result['contact_sheet']).is_file())
        with self.assertRaises(ValueError): e.load_library(self.store, 'writer')
        self.assertEqual(e.profiles.load(self.store, 'writer')[1]['status'], 'reference-only')

    def test_review_render_and_visible_validation(self):
        text = self.ready()
        output = self.root/'output.pdf'
        result = e.render(self.store, 'writer', text, output)
        checks = e.validate_output(result['report'], self.root/'rendered')
        self.assertEqual(checks['status'], 'passed')
        report = e.read_json(result['report'])
        self.assertEqual(''.join(x['char'] for x in report['glyph_trace']), 'ABCabc0123+3=3÷123%a2')
        svg = e.ET.parse(report['svg'][0])
        self.assertEqual(len(svg.findall('.//{http://www.w3.org/2000/svg}image')), report['glyph_count'])
        self.assertTrue((self.root/'rendered/page-001.png').exists())
        with self.assertRaises(ValueError): e.render(self.store, 'writer', text, output)

    def test_missing_glyph_fails_without_output(self):
        text = self.ready()
        text = self.root/'missing.txt'
        text.write_text('ABCz', encoding='utf-8')
        self.assertEqual(e.coverage(self.store, 'writer', text)['missing'], ['z'])
        with self.assertRaisesRegex(ValueError, 'Missing glyphs'):
            e.render(self.store, 'writer', text, self.root/'missing.pdf')
        self.assertFalse((self.root/'missing.pdf').exists())

    def test_extreme_slants_wrap_without_clipping(self):
        self.ready()
        source = self.root/'slant.txt'
        source.write_text('ABC abc 0123 +-= ' * 60, encoding='utf-8')
        for slant in (-20, 20):
            result = e.render(self.store, 'writer', source, self.root/f'slant{slant}.pdf', overrides={'slant_deg': slant})
            self.assertEqual(e.validate_output(result['report'])['status'], 'passed')

    def test_preview_cannot_bypass_review(self):
        self.extract()
        source = self.root/'preview.txt'
        source.write_text('ABC', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'reviewed library'):
            e.render(self.store, 'writer', source, self.root/'unreviewed.pdf', preview=True)

    def test_blank_sheet_does_not_activate_library(self):
        with self.assertRaisesRegex(ValueError, 'No usable ink'):
            self.extract(empty=True)
        self.assertNotIn('active_library', e.profiles.load(self.store, 'writer')[1])

    def test_rotated_and_perspective_shadowed_sheet(self):
        result = self.extract(angle=90, perspective=True)
        self.assertEqual(result['glyphs'], 15)
        self.assertEqual(result['missing'], [])

    def test_full_alphabet_hollow_letters_do_not_become_markers(self):
        path = self.root/'full.pdf'
        e.make_template(path)
        scans = filled_sheet(path.with_suffix('.json'), path, self.root/'full-scan.png', angle=90, perspective=True)
        result = e.extract(self.store, 'writer', path.with_suffix('.json'), scans)
        self.assertEqual(result['missing'], [])
        self.assertEqual(result['glyphs'], len(e.DEFAULT_CHARS))

    def test_missing_character_is_reported(self):
        result = self.extract(skip=('C',))
        self.assertEqual(result['missing'], ['C'])
        self.assertEqual(len(result['rejected_slots']), 3)

    def test_wrong_manifest_rejected(self):
        scans = filled_sheet(self.manifest, self.template, self.root/'scan.png')
        other = self.root/'other.pdf'
        e.make_template(other, characters='xyz', variants=2)
        with self.assertRaisesRegex(ValueError, 'Wrong template'):
            e.extract(self.store, 'writer', other.with_suffix('.json'), scans)

    def test_deterministic_render_and_no_preference_mutation(self):
        text = self.ready()
        before = e.profiles.load(self.store, 'writer')[1]['preferences']
        a = e.render(self.store, 'writer', text, self.root/'a.pdf', seed=31)
        b = e.render(self.store, 'writer', text, self.root/'b.pdf', seed=31)
        ra, rb = e.read_json(a['report']), e.read_json(b['report'])
        self.assertEqual(ra['glyph_trace'], rb['glyph_trace'])
        self.assertEqual(ra['pdf_sha256'], rb['pdf_sha256'])
        self.assertEqual(e.profiles.load(self.store, 'writer')[1]['preferences'], before)

    def test_tampered_glyph_and_pdf_fail(self):
        text = self.ready()
        result = e.render(self.store, 'writer', text, self.root/'out.pdf')
        with open(result['pdf'], 'ab') as stream: stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            e.validate_output(result['report'])
        _, _, folder, library = e.load_library(self.store, 'writer')
        glyph = library['glyphs']['A'][0]
        (folder/glyph['file']).write_bytes(b'not an image')
        with self.assertRaisesRegex(ValueError, 'Glyph file changed'):
            e.render(self.store, 'writer', text, self.root/'new.pdf', overrides={'glyph_variation':0})

    def test_many_pages_and_invalid_runs(self):
        text = self.ready()
        text = self.root/'many.txt'
        text.write_text(('ABC abc 0123\n'*110), encoding='utf-8')
        result = e.render(self.store, 'writer', text, self.root/'many.pdf')
        self.assertGreater(result['pages'], 1)
        e.validate_output(result['report'])
        text = self.root/'invalid.json'
        text.write_text(json.dumps({'runs':[{'text':'a','subscript':True,'superscript':True}]}), encoding='utf-8')
        with self.assertRaises(ValueError): e.read_document(text)

    def test_manifest_path_escape_is_rejected(self):
        manifest = e.read_json(self.manifest)
        manifest['pages'][0]['cells'][0]['box'][0] = -100
        self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'outside'):
            e.extract(self.store, 'writer', self.manifest, [self.template])


if __name__ == '__main__': unittest.main()

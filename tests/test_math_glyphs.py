"""Synthetic supplemental-glyph checks; no claims of writer similarity."""
import hashlib
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from web.runtime.math_glyphs import SUPPORTED_GLYPHS, supplemental_glyph


class SupplementalMathGlyphs(unittest.TestCase):
    def test_every_supported_shape_is_nonempty_padded_and_honest(self):
        required = set('αβγδεζηθικλμνξοπρστυφχψωϵϑϕϱςΓΔΘΛΞΠΣΥΦΨΩ()[]{}√∑∏∫∞±≤≥≠∈∂∇·|/\\→')
        self.assertFalse(required - SUPPORTED_GLYPHS)
        for char in sorted(SUPPORTED_GLYPHS):
            with self.subTest(character=char):
                image, baseline, meta = supplemental_glyph(char, {'glyphs':{}}, 3)
                pixels = np.asarray(image)
                self.assertEqual(image.mode, 'L')
                self.assertTrue(np.any(pixels < 150))
                self.assertTrue(np.all(pixels[[0,-1],:] == 255))
                self.assertTrue(np.all(pixels[:,[0,-1]] == 255))
                self.assertTrue(math.isfinite(baseline))
                self.assertEqual(meta['origin'], 'supplemental')
                self.assertTrue(meta['handwriting_not_learned'])
                self.assertEqual(meta['references'], [])

    def test_repeatable_paths_and_scale_do_not_involve_random_fonts(self):
        for char in 'απΣ√∫∑()→':
            first, b1, meta1 = supplemental_glyph(char, {'glyphs':{}}, 3)
            again, b2, meta2 = supplemental_glyph(char, {'glyphs':{}}, 3)
            small, native_base, _ = supplemental_glyph(char, {'glyphs':{}}, 1)
            self.assertEqual(first.tobytes(), again.tobytes())
            self.assertEqual((b1,meta1), (b2,meta2))
            self.assertEqual(first.size, (small.width*3, small.height*3))
            self.assertEqual(b1, native_base)

    def test_matches_sample_size_and_bounds_estimated_stroke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = Image.new('L', (12,15), 255)
            ImageDraw.Draw(sample).line((3,2,5,11,9,2), fill=20, width=2)
            path = root/'n.png';sample.save(path)
            record = {'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'baseline':12}
            bank = {'_root':root,'glyphs':{'n':record}}
            _,_,meta = supplemental_glyph('α', bank)
            self.assertEqual(meta['style_geometry']['x_height'],10)
            self.assertTrue(.9 <= meta['style_geometry']['stroke_width'] <= 1.7)
            self.assertEqual(meta['style_references'],[record['sha256']])

    def test_greek_alias_records_its_actual_source_and_remains_supplemental(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = Image.new('L', (12,15), 255)
            ImageDraw.Draw(sample).ellipse((2,2,9,12), outline=20, width=2)
            path=root/'o.png';sample.save(path)
            record={'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'baseline':13}
            image, baseline, meta=supplemental_glyph('ο', {'_root':root,'glyphs':{'o':record}})
            self.assertEqual(meta['source_latin'],'o')
            self.assertTrue(meta['handwriting_not_learned'])
            self.assertEqual(baseline,15)
            expected = sample.resize((36,45),Image.Resampling.LANCZOS)
            self.assertEqual(image.crop((6,6,42,51)).tobytes(),expected.tobytes())

    def test_unknown_characters_and_invalid_raster_scales_are_rejected(self):
        for value in ('🙂', '中文', 'a', '', None):
            with self.assertRaises(ValueError): supplemental_glyph(value, {'glyphs':{}})
        for scale in (0,9,1.5,True):
            with self.assertRaises(ValueError): supplemental_glyph('α', {'glyphs':{}}, scale)


if __name__ == '__main__':
    unittest.main()

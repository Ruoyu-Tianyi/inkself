"""Structural math keeps a personal pen width without claiming learned shapes."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np
from PIL import Image, ImageDraw

from web.runtime.math_strokes import draw_fence, draw_radical, estimate_style


STYLE = {'stroke_px':4.2, 'shade':30, 'slant':.08, 'em_height':96, 'style_references':[]}


def max_stroke(image):
    mask = (np.asarray(image) < 170).astype('uint8')
    return float(cv2.distanceTransform(mask, cv2.DIST_L2, 5).max()) * 2


class MathematicalStrokes(unittest.TestCase):
    def assert_padded(self, image):
        pixels = np.asarray(image)
        self.assertTrue(np.any(pixels < 170))
        self.assertTrue(np.all(pixels[[0, -1], :] == 255))
        self.assertTrue(np.all(pixels[:, [0, -1]] == 255))

    def test_all_fences_keep_pen_width_across_heights_and_complete_strokes(self):
        for char in '()[]{}|':
            measures = []
            for height in (40, 96, 220, 480):
                with self.subTest(char=char, height=height):
                    image, metadata = draw_fence(char, height, STYLE)
                    self.assert_padded(image)
                    self.assertEqual(metadata['stroke_px'], STYLE['stroke_px'])
                    measures.append(max_stroke(image))
                    mask = np.asarray(image) < 170
                    rows = np.where(mask)[0]
                    self.assertLess(rows.min(), 11)
                    self.assertGreater(rows.max(), height-11)
                    self.assertGreaterEqual(rows.max()-rows.min(),height-2)
                    # A delimiter is one complete gesture, including both hooks.
                    self.assertEqual(cv2.connectedComponents(mask.astype('uint8'), 8)[0]-1, 1)
            self.assertLess(max(measures), min(measures)*1.35 + 1)
            self.assertLess(max(measures), STYLE['stroke_px']*1.65 + 1)

    def test_repeatable_variants_are_smooth_distinct_and_style_stable(self):
        before = copy.deepcopy(STYLE)
        for char in '([{':
            first, metadata = draw_fence(char, 160, STYLE, seed=19, occurrence=4)
            again, repeated_metadata = draw_fence(char, 160, STYLE, seed=19, occurrence=4)
            self.assertEqual((first.size, first.tobytes()), (again.size, again.tobytes()))
            self.assertEqual(metadata, repeated_metadata)
            signatures = set()
            for occurrence in range(6):
                image, info = draw_fence(char, 160, STYLE, seed=19, occurrence=occurrence)
                signatures.add(hashlib.sha256(image.tobytes()).hexdigest())
                self.assertEqual(info['stroke_px'], STYLE['stroke_px'])
            self.assertGreaterEqual(len(signatures), 5)
        self.assertEqual(STYLE, before)

    def test_captured_delimiter_has_priority_and_does_not_inflate_pen_width(self):
        source = Image.new('L', (32, 90), 255)
        ImageDraw.Draw(source).line([(27,5),(8,7),(5,78),(23,84)], fill=20, width=4)
        before = source.tobytes()
        for height in (65, 220, 520):
            image, metadata = draw_fence('[', height, STYLE, source=source)
            self.assert_padded(image)
            self.assertEqual(metadata['method'], 'reviewed-delimiter-centreline')
            self.assertLess(max_stroke(image), STYLE['stroke_px']*1.8)
        self.assertEqual(source.tobytes(), before)

    def test_radical_leaves_content_and_long_tall_index_rectangles_clear(self):
        for body_size, index_size in [((35, 45), None), ((200, 180),(25,20)), ((20,30),(320,110))]:
            with self.subTest(body=body_size, index=index_size):
                image, (x,y), index_xy, metadata = draw_radical(body_size,index_size,STYLE,seed=33,occurrence=2)
                self.assert_padded(image)
                pixels = np.asarray(image)
                self.assertTrue(np.all(pixels[y:y+body_size[1], x:x+body_size[0]] == 255),
                                'The continuous overbar and hook cannot cover the radicand.')
                self.assertLess(x+body_size[0], image.width)
                self.assertLess(y+body_size[1], image.height)
                if index_size:
                    ix, iy = index_xy
                    self.assertTrue(np.all(pixels[iy:iy+index_size[1], ix:ix+index_size[0]] == 255))
                    self.assertLess(ix+index_size[0], image.width)
                    self.assertLess(iy+index_size[1], image.height)
                self.assertEqual(metadata['method'], 'continuous-radical-gesture')
                self.assertEqual(cv2.connectedComponents((pixels < 170).astype('uint8'),8)[0]-1, 1)

    def test_radical_variation_is_reproducible_and_not_a_fixed_rule(self):
        first = draw_radical((140,80),(20,18),STYLE,seed=7,occurrence=1)
        again = draw_radical((140,80),(20,18),STYLE,seed=7,occurrence=1)
        self.assertEqual((first[0].size,first[0].tobytes(),first[1:]),
                         (again[0].size,again[0].tobytes(),again[1:]))
        changed = draw_radical((140,80),(20,18),STYLE,seed=7,occurrence=2)
        self.assertNotEqual(first[0].tobytes(),changed[0].tobytes())
        self.assertLess(max_stroke(first[0]),STYLE['stroke_px']*2.1)

    def test_sample_geometry_is_bounded_and_empty_bank_has_safe_defaults(self):
        self.assertAlmostEqual(estimate_style({'glyphs':{}})['stroke_px'],3.9)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = Image.new('L',(12,28),255)
            ImageDraw.Draw(image).line((3,3,6,25),fill=40,width=2)
            image.save(root/'1.png')
            bank = {'_root':root,'glyphs':{'1':{'file':'1.png','sha256':'example'}}}
            style = estimate_style(bank)
            self.assertTrue(2.7 <= style['stroke_px'] <= 6.6)
            self.assertEqual(style['shade'],40)
            self.assertEqual(style['style_references'],['example'])


if __name__ == '__main__':
    unittest.main()

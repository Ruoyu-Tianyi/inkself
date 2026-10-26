"""Digit diversity must remain deterministic and preserve sample topology."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from test_symbol_style import fixture
from web.runtime.digit_style import numeric_token, render_digit, digit_gap
from web.runtime.symbol_style import topology, symbol_token

class DigitStyle(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.bank=fixture(Path(self.tmp.name))

    def test_repeated_digits_vary_but_seed_reproduces(self):
        image,meta=numeric_token(self.bank,'88888888',42,3)
        other,again=numeric_token(self.bank,'88888888',42,3)
        self.assertEqual(image.tobytes(),other.tobytes())
        self.assertEqual(meta,again)
        self.assertGreater(len(set(meta['digit_gaps_px'])),4)
        self.assertGreater(len({tuple(v['offset_px']) for v in meta['digit_variants']}),3)
        self.assertNotEqual(image.tobytes(),numeric_token(self.bank,'88888888',43,3)[0].tobytes())

    def test_digits_keep_holes_and_white_borders(self):
        for digit in '0123456789':
            expected=topology(render_digit(self.bank,digit,42,0)[0])
            for occurrence in range(12):
                image,_,meta=render_digit(self.bank,digit,42,occurrence)
                self.assertEqual(topology(image),expected)
                array=np.asarray(image)
                self.assertTrue(np.all(array[[0,-1],:]==255))
                self.assertTrue(np.all(array[:,[0,-1]]==255))
                self.assertEqual(meta['source_sha256'],self.bank['glyphs'][digit]['sha256'])

    def test_decimal_percent_and_reference_control(self):
        _,meta=numeric_token(self.bank,'100.25%',42,9)
        self.assertEqual(len(meta['digit_variants']),5)
        self.assertEqual(len(meta['symbol_variants']),2)
        self.assertTrue(meta['symbol_variants'][-1]['canvas_guard_passed'])
        self.assertFalse(symbol_token(self.bank,'123')[1]['digit_variants'])
        self.assertTrue(all(.8<=digit_gap(42,4,i)<=4.3 for i in range(100)))

    def test_math_digits_and_mixed_text_follow_same_variation(self):
        from test_habit_model import fixture as habit_fixture
        from web.runtime.habit_model import fit_habits,align_words,habit_token
        from web.runtime.math_renderer import render_math
        from web.runtime.math_syntax import parse_math
        root=Path(self.tmp.name)/'habit';root.mkdir()
        bank=habit_fixture(root);model=fit_habits(bank,align_words(bank))
        a,meta=habit_token(bank,model,'a1122',42,1)
        self.assertEqual(len(meta['digit_variants']),4)
        first=render_math(parse_math('11112222'),bank,model,42,1)[0]
        same=render_math(parse_math('11112222'),bank,model,42,1)[0]
        other=render_math(parse_math('11112222'),bank,model,42,2)[0]
        self.assertEqual(first.tobytes(),same.tobytes())
        self.assertNotEqual(first.tobytes(),other.tobytes())

"""Synthetic math layout checks; no personal source ink or PDF generation."""
import copy
import hashlib
import json
from pathlib import Path
import string
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

from web.runtime.math_renderer import render_math
from web.runtime.math_syntax import parse_math
from web.runtime.reference_renderer import load_bank


def fixture(root):
    bank = {'schema_version': 1, 'reviewed': True, 'source_sha256': 'synthetic-math',
            'glyphs': {}, 'words': {}, 'letter_width_scale': .8}
    for index, char in enumerate(string.ascii_letters + string.digits + '+-=/'):
        image = Image.new('L', (12, 20), 255)
        ImageDraw.Draw(image).line((2, 17, 3 + index % 3, 3, 9, 17), fill=20, width=2)
        path = root / f'char-{index}.png'
        image.save(path)
        bank['glyphs'][char] = {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                'baseline': 18, 'advance': 14}
    path = root / 'bank.json';path.write_text(json.dumps(bank), encoding='utf-8')
    return load_bank(path)


def ink_count(image):
    return int(np.count_nonzero(np.asarray(image) < 170))


class MathematicalLayout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name)
        self.bank = fixture(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def render(self, expression, **options):
        return render_math(parse_math(expression), self.bank, **options)

    def assert_clear_bounds(self, image, metadata):
        pixels = np.asarray(image)
        self.assertTrue(np.any(pixels < 170))
        self.assertTrue(np.all(pixels[[0, -1], :] == 255))
        self.assertTrue(np.all(pixels[:, [0, -1]] == 255))
        self.assertGreaterEqual(metadata['baseline'], 0)
        self.assertLessEqual(metadata['baseline'], image.height)
        self.assertEqual(metadata['em_height'], 96)

    def test_nested_subscript_and_superscript_preserve_ast_and_glyphs(self):
        source = r'x_{i_j}^{2}'
        image, metadata = self.render(source)
        self.assert_clear_bounds(image, metadata)
        self.assertEqual(metadata['math_ast'], parse_math(source))
        self.assertEqual([item['glyph'] for item in metadata['math_glyphs']], list('xij2'))
        plain, _ = self.render('x')
        self.assertGreater(image.height, plain.height)
        self.assertGreater(image.width, plain.width)
        self.assertEqual(metadata['supplemental_math_glyphs'], [])

    def test_fraction_has_separated_numerator_rule_and_denominator(self):
        image, metadata = self.render(r'\frac{12}{34}')
        self.assert_clear_bounds(image, metadata)
        mask = np.asarray(image) < 170
        row = int(np.argmax(mask.sum(axis=1)))
        self.assertGreater(np.count_nonzero(mask[row]), image.width * .7)
        self.assertGreater(np.count_nonzero(mask[:row - 2]), 0)
        self.assertGreater(np.count_nonzero(mask[row + 3:]), 0)
        self.assertEqual([item['glyph'] for item in metadata['math_glyphs']], list('1234'))

    def test_radical_uses_structural_hook_without_supplementing_glyph(self):
        image, metadata = self.render(r'\sqrt[3]{x^2+y^2}')
        self.assert_clear_bounds(image, metadata)
        self.assertEqual(metadata['supplemental_math_glyphs'], [])
        self.assertCountEqual([item['glyph'] for item in metadata['math_glyphs']], list('x2+y23'))
        body, _ = self.render('x^2+y^2')
        self.assertGreater(image.width, body.width)
        self.assertGreater(image.height, body.height)

    def test_nested_fences_scale_to_fraction_body_and_retain_reading_ast(self):
        expression = r'\left[\left(\frac{x+1}{y}\right)\right]'
        image, metadata = self.render(expression, allow_supplemental=True)
        self.assert_clear_bounds(image, metadata)
        self.assertEqual(metadata['math_ast'], parse_math(expression))
        self.assertEqual(set(metadata['supplemental_math_glyphs']), set('[]()'))
        bare, _ = self.render(r'\frac{x+1}{y}')
        self.assertGreater(image.width, bare.width)
        self.assertGreater(image.height, bare.height)
        self.assertCountEqual([item['glyph'] for item in metadata['math_glyphs']], list('[(x+1y)]'))

    def test_sum_and_integral_place_limits_above_and_below_operator(self):
        for command in ('sum', 'int', 'prod'):
            with self.subTest(command=command):
                bare, _ = self.render('\\' + command, allow_supplemental=True)
                image, metadata = self.render('\\' + command + '_{i=1}^{n}', allow_supplemental=True)
                self.assert_clear_bounds(image, metadata)
                self.assertGreater(image.height, bare.height + 20)
                self.assertGreater(metadata['baseline'], 10)
                self.assertEqual(metadata['math_ast']['children'][0]['base']['limits'], True)
                self.assertEqual([item['glyph'] for item in metadata['math_glyphs']][1:], list('i=1n'))

    def test_greek_supplement_is_explicit_deterministic_and_not_personal(self):
        ast = parse_math(r'\alpha+\beta=\Gamma')
        image, metadata = render_math(ast, self.bank, seed=27, variant=3, allow_supplemental=True)
        again, again_metadata = render_math(ast, self.bank, seed=27, variant=3, allow_supplemental=True)
        self.assertEqual((image.size, image.tobytes()), (again.size, again.tobytes()))
        self.assertEqual(metadata, again_metadata)
        self.assertEqual(metadata['supplemental_math_glyphs'], sorted('αβΓ'))
        self.assertEqual([item['glyph'] for item in metadata['math_glyphs']], list('α+β=Γ'))
        for item in metadata['math_glyphs']:
            self.assertEqual(item['source'], 'supplemental' if item['glyph'] in 'αβΓ' else 'personal')
        self.assertIn('not learned', metadata['limits'])

    def test_missing_glyphs_fail_without_silent_substitution(self):
        with self.assertRaisesRegex(ValueError, 'missing.*α'):
            self.render(r'\alpha+x')
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.render('(x)')
        with self.assertRaisesRegex(ValueError, 'Unsupported supplemental'):
            self.render('☃', allow_supplemental=True)

    def test_render_does_not_modify_ast_bank_or_source_files(self):
        ast = parse_math(r'\sqrt{\alpha^2+x^2}')
        ast_before, bank_before = copy.deepcopy(ast), copy.deepcopy(self.bank)
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.root.iterdir()}
        render_math(ast, self.bank, allow_supplemental=True)
        self.assertEqual(ast, ast_before)
        self.assertEqual(self.bank, bank_before)
        self.assertEqual(hashes, {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.root.iterdir()})

    def test_personal_adapter_and_symbol_occurrences_remain_repeatable(self):
        model = {'allographs': {}, 'pairs': {}, 'family_pairs': {},
                 'width_coefficients': [.8, 0, 0, 0, 0, 0, 0],
                 'height_coefficients': [.8, 0, 0, 0, 0, 0, 0],
                 'width_residual_std': .05, 'baseline_slopes': [-.02, .02],
                 'observations': 40, 'connector_bow_px': 0, 'limits': 'Synthetic adapter.'}
        before = copy.deepcopy(model)
        ast = parse_math('x_1+2=x^2')
        image, metadata = render_math(ast, self.bank, model=model, seed=7, variant=9)
        again, again_metadata = render_math(ast, self.bank, model=model, seed=7, variant=9)
        self.assertEqual((image.size, image.tobytes()), (again.size, again.tobytes()))
        self.assertEqual(metadata, again_metadata)
        self.assertEqual(model, before)
        self.assertEqual([item['glyph'] for item in metadata['math_glyphs']], list('x1+2=x2'))
        self.assert_clear_bounds(image, metadata)

    def test_long_root_index_is_not_clipped_to_radical_body_width(self):
        index = '123456789012345'
        image, metadata = self.render(r'\sqrt[' + index + ']{x}')
        index_image, _ = self.render(index)
        self.assert_clear_bounds(image, metadata)
        self.assertGreaterEqual(image.width, round((index_image.width - 12) * .55))
        self.assertEqual(len(metadata['math_glyphs']), len(index) + 1)

    def test_tall_subscript_and_superscript_do_not_overwrite_each_other(self):
        script = r'\frac{\frac{1}{2}}{\frac{3}{4}}'
        base, _ = self.render('x')
        upper, _ = self.render('x^{' + script + '}')
        lower, _ = self.render('x_{' + script + '}')
        combined, metadata = self.render('x_{' + script + '}^{' + script + '}')
        self.assert_clear_bounds(combined, metadata)
        expected = ink_count(upper) + ink_count(lower) - ink_count(base)
        self.assertGreaterEqual(ink_count(combined), expected * .98,
                                'Combined scripts must not erase each other or the base.')


if __name__ == '__main__':
    unittest.main()

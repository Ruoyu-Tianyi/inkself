"""Synthetic symbol checks: topology and provenance, not handwriting similarity."""
import copy
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from web.runtime.reference_renderer import load_bank, reference_token
from web.runtime.symbol_style import SCALE, SYMBOLS, render_symbol, symbol_token, topology


def _save_glyph(root, bank, char, image, baseline):
    path = root / f'g-{ord(char):04x}.png'
    image.save(path)
    bank['glyphs'][char] = {
        'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'baseline': baseline, 'advance': image.width + 2,
    }


def fixture(root):
    bank = {'schema_version': 1, 'reviewed': True, 'source_sha256': 'synthetic-symbol-sample',
            'glyphs': {}, 'words': {}, 'spacing_px': 2, 'letter_width_scale': .7}
    for char in '0123456789':
        image = Image.new('L', (17, 25), 255)
        draw = ImageDraw.Draw(image)
        if char == '1':
            draw.line((6, 6, 9, 3, 9, 21), fill=0, width=2)
        else:
            draw.ellipse((3, 3, 13, 21), outline=0, width=2)
            if char in '2356789':
                draw.line((4, 12, 12, 12), fill=0, width=1)
        _save_glyph(root, bank, char, image, 22)

    # Intentionally oversized: separate loops and an excessively heavy diagonal.
    image = Image.new('L', (36, 46), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 3, 12, 15), outline=0, width=2)
    draw.ellipse((23, 29, 33, 41), outline=0, width=2)
    draw.line((27, 4, 10, 40), fill=0, width=6)
    _save_glyph(root, bank, '%', image, 42)

    for char in '+-=×÷':
        image = Image.new('L', (18, 22), 255)
        draw = ImageDraw.Draw(image)
        if char == '=':
            draw.line((2, 7, 15, 7), fill=0, width=2)
            draw.line((2, 15, 15, 15), fill=0, width=2)
        elif char == '×':
            draw.line((3, 5, 14, 17), fill=0, width=2)
            draw.line((14, 5, 3, 17), fill=0, width=2)
        else:
            draw.line((2, 11, 15, 11), fill=0, width=2)
            if char == '+':
                draw.line((9, 4, 9, 18), fill=0, width=2)
            if char == '÷':
                draw.ellipse((8, 2, 10, 4), fill=0)
                draw.ellipse((8, 18, 10, 20), fill=0)
        _save_glyph(root, bank, char, image, 21)

    _save_glyph(root, bank, '.', Image.new('L', (1, 1), 0), 1)
    for char in ',;:?!':
        image = Image.new('L', (12, 24), 255)
        draw = ImageDraw.Draw(image)
        if char in ',;':
            draw.line((6, 18, 6, 20, 4, 23), fill=0, width=2)
        if char in ';:':
            draw.ellipse((5, 7, 7, 9), fill=0)
        if char == ':':
            draw.ellipse((5, 18, 7, 20), fill=0)
        if char == '?':
            draw.arc((2, 2, 10, 12), 180, 360, fill=0, width=2)
            draw.line((10, 7, 6, 14), fill=0, width=2)
            draw.ellipse((5, 19, 7, 21), fill=0)
        if char == '!':
            draw.line((6, 2, 6, 15), fill=0, width=2)
            draw.ellipse((5, 19, 7, 21), fill=0)
        _save_glyph(root, bank, char, image, 21)
    path = root / 'bank.json'
    path.write_text(json.dumps(bank), encoding='utf-8')
    return load_bank(path)


def components(image):
    mask = (np.asarray(image) < 170).astype('uint8')
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    return mask, labels, stats[1:count]


def holes(image):
    ink = np.asarray(image) < 170
    background = (~np.pad(ink, 1)).astype('uint8')
    # Background includes the connected outer white canvas; other regions are holes.
    return cv2.connectedComponents(background, connectivity=8)[0] - 2


def ink_height(image):
    rows = np.where(np.any(np.asarray(image) < 170, axis=1))[0]
    return int(rows[-1] - rows[0] + 1) if len(rows) else 0


def diagonal_thickness(image):
    _, _, stats = components(image)
    diagonal = max(stats, key=lambda row: int(row[cv2.CC_STAT_HEIGHT]))
    return diagonal[cv2.CC_STAT_AREA] / math.hypot(diagonal[cv2.CC_STAT_WIDTH], diagonal[cv2.CC_STAT_HEIGHT])


class SymbolStyle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bank = fixture(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_occurrence_and_index_are_exactly_repeatable(self):
        self.assertEqual(SCALE, 3)
        self.assertEqual(SYMBOLS, frozenset('%+-=×÷.,;:?!'))
        for char in sorted(SYMBOLS):
            with self.subTest(char=char):
                a, baseline_a, metadata_a = render_symbol(self.bank, char, seed=71, occurrence=4, index=2)
                b, baseline_b, metadata_b = render_symbol(self.bank, char, seed=71, occurrence=4, index=2)
                self.assertEqual(a.mode, 'L')
                self.assertEqual((a.size, a.tobytes()), (b.size, b.tobytes()))
                self.assertEqual(baseline_a, baseline_b)
                self.assertTrue(math.isfinite(baseline_a))
                self.assertEqual(metadata_a, metadata_b)

    def test_repetition_has_several_visible_variants(self):
        for char in '%=+':
            with self.subTest(char=char):
                variants = set()
                for occurrence in range(12):
                    image, _, _ = render_symbol(self.bank, char, seed=42, occurrence=occurrence)
                    variants.add((image.size, image.tobytes()))
                self.assertGreaterEqual(len(variants), 4)

    def test_oversized_percent_is_normalized_without_losing_loops_or_diagonal(self):
        with Image.open(self.root / self.bank['glyphs']['%']['file']) as opened:
            source = opened.convert('L')
        with Image.open(self.root / self.bank['glyphs']['0']['file']) as opened:
            digit = opened.convert('L')
        self.assertEqual(len(components(source)[2]), 3)
        self.assertEqual(holes(source), 2)
        for occurrence in range(6):
            with self.subTest(occurrence=occurrence):
                image, _, _ = render_symbol(self.bank, '%', seed=42, occurrence=occurrence)
                self.assertEqual(len(components(image)[2]), 3)
                self.assertEqual(holes(image), 2)
                self.assertLess(ink_height(image) / SCALE, ink_height(source))
                self.assertLessEqual(ink_height(image) / SCALE, ink_height(digit) * 1.65)
                self.assertLess(diagonal_thickness(image) / SCALE, diagonal_thickness(source))

    def test_equal_bars_and_division_dots_remain_separate(self):
        for char, expected in [('=', 2), ('÷', 3)]:
            for occurrence in range(8):
                with self.subTest(char=char, occurrence=occurrence):
                    image, _, _ = render_symbol(self.bank, char, seed=42, occurrence=occurrence)
                    self.assertEqual(len(components(image)[2]), expected)

    def test_one_pixel_period_remains_visible_and_no_symbol_touches_border(self):
        for char in sorted(SYMBOLS):
            for occurrence in (0, 3, 11):
                with self.subTest(char=char, occurrence=occurrence):
                    image, _, _ = render_symbol(self.bank, char, seed=42, occurrence=occurrence)
                    pixels = np.asarray(image)
                    self.assertTrue(np.any(pixels < 170))
                    self.assertTrue(np.all(pixels[[0, -1], :] == 255))
                    self.assertTrue(np.all(pixels[:, [0, -1]] == 255))

    def test_assets_records_and_reference_rendering_are_unchanged(self):
        original_bank = copy.deepcopy(self.bank)
        original_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.root.iterdir()}
        reference_before, metadata_before = reference_token(self.bank, '10%=1+0.', prefer_words=False)
        for char in sorted(SYMBOLS):
            render_symbol(self.bank, char, seed=91, occurrence=5, index=1)
        reference_after, metadata_after = reference_token(self.bank, '10%=1+0.', prefer_words=False)
        self.assertEqual(self.bank, original_bank)
        self.assertEqual(original_hashes, {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.root.iterdir()})
        self.assertEqual((reference_before.size, reference_before.tobytes()), (reference_after.size, reference_after.tobytes()))
        self.assertEqual(metadata_before, metadata_after)

    def test_tiny_punctuation_survives_actual_a4_token_resampling(self):
        # The token canvas phase matters: isolated glyph resizing is insufficient.
        # Count ink components only; this does not measure writer similarity.
        for text, expected_components in [('1.1', 3), ('1:1', 4)]:
            for occurrence in range(8):
                image, metadata = symbol_token(self.bank, text, seed=42, occurrence=occurrence)
                self.assertEqual(metadata['em_height'], 96)
                for size in (10, 16, 26):
                    with self.subTest(text=text, occurrence=occurrence, size=size):
                        factor = max(24, int(size * 1240 / 595.2756 * 1.4)) / 96
                        resized = image.resize((max(1, round(image.width * factor)), max(1, round(image.height * factor))), Image.Resampling.LANCZOS)
                        self.assertEqual(topology(resized)[0], expected_components)
                        # A separate dark punctuation component must still exist
                        # between the digit components, even for a one-pixel dot.
                        _, _, stats = components(resized)
                        ordered = sorted(stats, key=lambda stat: int(stat[cv2.CC_STAT_LEFT]))
                        middle = ordered[1:-1]
                        self.assertEqual(len(middle), expected_components - 2)
                        self.assertTrue(all(stat[cv2.CC_STAT_AREA] >= 1 for stat in middle))

    def test_percent_canvas_guard_preserves_final_size_topology_and_digit_prefix(self):
        for text in ('1%', '75%'):
            first_size = None
            digit_prefix = None
            prefix_advance = 0
            for char in text[:-1]:
                record = self.bank['glyphs'][char]
                with Image.open(self.root / record['file']) as source:
                    prefix_advance += max(record['advance'], source.width + 1)
            for occurrence in range(8):
                image, metadata = symbol_token(self.bank, text, seed=42, occurrence=occurrence)
                entry = next(record for record in metadata['symbol_variants'] if record['character'] == '%')
                with self.subTest(text=text, occurrence=occurrence):
                    self.assertIs(entry['canvas_guard_passed'], True)
                    attempt = entry['variation_attempt']
                    percent, percent_baseline, _ = render_symbol(
                        self.bank, '%', seed=42, occurrence=occurrence, index=len(text) - 1,
                        attempt=attempt if isinstance(attempt, int) else 0,
                        variation=isinstance(attempt, int),
                    )
                    px = round((4 + prefix_advance - entry['left_padding']) * SCALE)
                    py = round(metadata['baseline'] - percent_baseline * SCALE)
                    layer = Image.new('L', image.size, 255)
                    layer.paste(percent, (px, py))
                    self.assertEqual(topology(layer), (3, 2))
                    current_prefix = np.asarray(image)[:, :px].copy()
                    if first_size is None:
                        first_size, digit_prefix = image.size, current_prefix
                    self.assertEqual(image.size, first_size)
                    np.testing.assert_array_equal(current_prefix, digit_prefix)
                    for size in (10, 16, 26):
                        with self.subTest(size=size):
                            factor = max(24, int(size * 1240 / 595.2756 * 1.4)) / 96
                            dimensions = (max(1, round(layer.width * factor)), max(1, round(layer.height * factor)))
                            small_layer = layer.resize(dimensions, Image.Resampling.LANCZOS)
                            self.assertEqual(topology(small_layer), (3, 2))


if __name__ == '__main__':
    unittest.main()

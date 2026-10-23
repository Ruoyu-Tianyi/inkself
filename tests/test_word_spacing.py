"""Synthetic boundary evidence; no owner handwriting or similarity claims."""
import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from web.runtime.word_spacing import fit_word_spacing, sample_word_gaps, validate_word_spacing


def reviewed_fixture(root, gap_rows=None, omit=None):
    gap_rows = gap_rows or [[5, 9, 6, 14, 8, 11], [12, 7, 10, 6, 15, 9], [7, 10, 13, 6, 8, 11]]
    bank = {"reviewed": True, "source_sha256": "synthetic", "words": {}}
    lines = []
    for row, gaps in enumerate(gap_rows):
        x = 4
        image = Image.new("L", (500, 40), 255)
        draw = ImageDraw.Draw(image)
        for index in range(len(gaps) + 1):
            name = f"word-{row}-{index}"
            draw.rectangle((x, 5, x + 17, 30), fill=0)
            if omit != (row, index):
                bank["words"][name] = {"source": {"row": row, "box": [x, 0, x + 18, 40]}}
            x += 18 + (gaps[index] if index < len(gaps) else 0)
        file = f"line-{row:03}.png"
        image.save(root / file)
        lines.append({"file": file})
    return bank, lines


class WordSpacing(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_reviewed_source_gaps_fit_distribution_in_em_not_character_width(self):
        bank, lines = reviewed_fixture(self.root)
        model = fit_word_spacing(bank, self.root, lines)
        self.assertEqual(model["method"], "reviewed-word-boxes")
        self.assertEqual(model["confidence"], "high")
        self.assertEqual(model["observations"], 18)
        self.assertAlmostEqual(model["mean"], sum([5, 9, 6, 14, 8, 11, 12, 7, 10, 6, 15, 9, 7, 10, 13, 6, 8, 11]) / 18 / 32)
        bank["glyphs"] = {"a": {"advance": 1000}}
        bank["letter_width_scale"] = .4
        self.assertEqual(model, fit_word_spacing(bank, self.root, lines))

    def test_partial_transcript_cannot_turn_omitted_word_into_a_space(self):
        bank, lines = reviewed_fixture(self.root, omit=(0, 2))
        model = fit_word_spacing(bank, self.root, lines)
        self.assertEqual(model["observations"], 16)
        self.assertGreaterEqual(model["rejected_pairs"], 1)
        self.assertLessEqual(max(model["distribution"]), 15 / 32)

    def test_selected_rows_and_outside_paths_are_not_fit(self):
        bank, lines = reviewed_fixture(self.root)
        model = fit_word_spacing(bank, self.root, lines, selected_lines=[1, 2])
        self.assertEqual(model["observations"], 12)
        self.assertEqual(model["source_rows"], 2)
        bad = copy.deepcopy(lines)
        bad[0]["file"] = "../untrusted.png"
        self.assertEqual(fit_word_spacing(bank, self.root, bad)["observations"], 12)

    def test_word_boxes_without_source_image_do_not_prove_adjacency(self):
        bank, _ = reviewed_fixture(self.root)
        model = fit_word_spacing(bank)
        self.assertEqual(model["method"], "conservative-default")
        self.assertEqual(model["confidence"], "none")
        self.assertEqual(model["observations"], 0)
        self.assertIn("not a learned", model["limits"])

    def test_two_separated_image_gap_groups_are_explicit_low_confidence(self):
        lines = []
        for row in range(3):
            image = Image.new("L", (550, 40), 255)
            draw = ImageDraw.Draw(image)
            x = 3
            for word in range(7):
                for char in range(4):
                    draw.rectangle((x, 5, x + 3, 30), fill=0)
                    x += 6
                x += 8 + word % 3
            file = f"estimate-{row}.png"
            image.save(self.root / file)
            lines.append({"file": file})
        model = fit_word_spacing(sample_dir=self.root, sample_lines=lines)
        self.assertEqual(model["method"], "image-gap-estimate")
        self.assertEqual(model["confidence"], "low")
        self.assertEqual(model["observations"], 18)
        self.assertIn("not recognized", model["limits"])

    def test_uniform_letter_gaps_are_ambiguous_and_cannot_be_learned_as_spaces(self):
        bank, lines = reviewed_fixture(self.root, [[6] * 8, [6] * 8])
        # Unreviewed coordinate labels are never accepted as word evidence.
        bank["reviewed"] = False
        model = fit_word_spacing(bank, self.root, lines)
        self.assertEqual(model["method"], "conservative-default")
        self.assertEqual(model["observations"], 0)

    def test_sampling_reproducible_varied_bounded_and_correlated(self):
        bank, lines = reviewed_fixture(self.root)
        model = fit_word_spacing(bank, self.root, lines)
        model["lag_correlation"] = .5
        a = sample_word_gaps(model, 1000, seed=38)
        self.assertEqual(a, sample_word_gaps(model, 1000, seed=38))
        self.assertNotEqual(a, sample_word_gaps(model, 1000, seed=39))
        self.assertNotEqual(a, sample_word_gaps(model, 1000, seed=38, paragraph=1))
        self.assertGreater(len(set(round(value, 3) for value in a)), 80)
        self.assertGreater(min(a), 0)
        self.assertLessEqual(max(a), model["max_gap"])
        self.assertGreater(np.corrcoef(a[:-1], a[1:])[0, 1], .3)
        self.assertAlmostEqual(np.mean(a), model["mean"], delta=.025)

    def test_uniform_reviewed_sample_gets_small_explicit_prior_variation(self):
        bank, lines = reviewed_fixture(self.root, [[8] * 8, [8] * 8])
        model = fit_word_spacing(bank, self.root, lines)
        self.assertEqual(model["std"], 0)
        self.assertEqual(model["variation_origin"], "bounded-natural-variation-prior")
        self.assertGreater(np.std(sample_word_gaps(model, 100)), 0)
        self.assertLess(np.std(sample_word_gaps(model, 100)), .04)

    def test_one_punctuation_observation_does_not_establish_context_habit(self):
        bank, lines = reviewed_fixture(self.root)
        key = next(iter(bank["words"]))
        bank["words"][key + "."] = bank["words"].pop(key)
        model = fit_word_spacing(bank, self.root, lines)
        self.assertNotIn("after-pause", model["context_adjustments"])
        contexts = [{"left": "a.", "right": "B"}] * 10
        self.assertEqual(sample_word_gaps(model, 10), sample_word_gaps(model, 10, contexts=contexts))

    def test_repeated_pause_context_uses_sample_evidence_with_shrinkage(self):
        bank, lines = reviewed_fixture(self.root, [[14, 5, 14, 5, 14, 5], [14, 5, 14, 5, 14, 5]])
        for name in list(bank["words"]):
            if int(name.rsplit("-", 1)[1]) in (0, 2, 4):
                bank["words"][name + "."] = bank["words"].pop(name)
        model = fit_word_spacing(bank, self.root, lines)
        context = model["context_adjustments"]["after-pause"]
        self.assertEqual(context["observations"], 6)
        self.assertGreater(context["factor"], 1)
        self.assertLessEqual(context["factor"], 1.25)
        plain = sample_word_gaps(model, 10)
        pause = sample_word_gaps(model, 10, contexts=[{"left": "End.", "right": "Next"}] * 10)
        for a, b in zip(plain, pause):
            self.assertAlmostEqual(b / a, context["factor"])

    def test_invalid_models_and_generation_limits_rejected(self):
        base = fit_word_spacing()
        for key, value in [("mean", float("nan")), ("std", -1), ("lag_correlation", 1),
                           ("distribution", [float("inf")]), ("min_gap", -.1),
                           ("measurement_resolution", float("nan")), ("variation_origin", "unsupported"),
                           ("observations", float("inf")), ("quantiles", {"0.5": float("nan")})]:
            model = copy.deepcopy(base)
            model[key] = value
            with self.assertRaises(ValueError):
                validate_word_spacing(model)
        with self.assertRaises(ValueError):
            sample_word_gaps(base, 200001)
        with self.assertRaises(ValueError):
            sample_word_gaps(base, 1, contexts=[])
        with self.assertRaises(ValueError):
            sample_word_gaps(base, True)
        self.assertEqual(sample_word_gaps(base, 0), [])

    def test_reference_bank_and_sample_source_must_match(self):
        bank, lines = reviewed_fixture(self.root)
        with self.assertRaisesRegex(ValueError, "source does not match"):
            fit_word_spacing(bank, self.root, lines, source_sha256="another-sample")


if __name__ == "__main__":
    unittest.main()

"""Conservative sample-derived word gaps and reproducible writing rhythm.

Reviewed word coordinates are useful only when the source line confirms there
is no omitted ink between them. Image-only segmentation is deliberately a
lower-confidence estimate: a large letter gap must not become a learned space.
All public gap values are fractions of an em, independent of glyph widths.
"""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image


VERSION = "sample-word-spacing-1"
MIN_GAP = .12
MAX_GAP = 1.1
_METHODS = {"reviewed-word-boxes", "image-gap-estimate", "conservative-default"}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _ink(image):
    """Discard isolated scan specks without joining disconnected letters."""
    import cv2
    pixels = np.asarray(image.convert("L")) < 170
    count, labels, stats, _ = cv2.connectedComponentsWithStats(pixels.astype("uint8"), 8)
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] < 3:
            pixels[labels == label] = False
    return pixels


def _load_lines(sample_dir, sample_lines, selected_lines):
    if sample_dir is None or not isinstance(sample_lines, list):
        return {}
    root = Path(sample_dir).resolve()
    selected = set(range(len(sample_lines))) if selected_lines is None else {
        value for value in selected_lines if isinstance(value, int) and not isinstance(value, bool)
    }
    result = {}
    for index, record in enumerate(sample_lines[:24]):
        if index not in selected or not isinstance(record, dict) or not isinstance(record.get("file"), str):
            continue
        path = (root / record["file"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            continue
        with Image.open(path) as image:
            if image.width > 10000 or image.height > 2048 or image.width * image.height > 4000000:
                continue
            result[index] = _ink(image)
    return result


def _context(left, right):
    left = str(left).rstrip()
    if left.endswith((".", "?", "!", ";", ":")):
        return "after-pause"
    if left.endswith(","):
        return "after-comma"
    return "ordinary"


def _reviewed_observations(bank, lines, em_height):
    rows = defaultdict(list)
    for text, record in bank.get("words", {}).items():
        source = record.get("source") if isinstance(record, dict) else None
        if not isinstance(source, dict):
            continue
        row, box = source.get("row"), source.get("box")
        if not isinstance(row, int) or isinstance(row, bool) or row not in lines:
            continue
        if not isinstance(box, list) or len(box) != 4 or not all(_finite(v) for v in box):
            continue
        left, top, right, bottom = box
        image = lines[row]
        if not (0 <= left < right <= image.shape[1] and 0 <= top < bottom <= image.shape[0]):
            continue
        rows[row].append((float(left), float(right), str(text)))
    observations, rejected = [], 0
    for row, boxes in sorted(rows.items()):
        boxes.sort()
        for sequence, (left, right) in enumerate(zip(boxes, boxes[1:])):
            gap = right[0] - left[1]
            ratio = gap / em_height
            # A partially transcribed bank can omit a whole word or number.
            # Check the full source strip, not just either annotated box height.
            start, end = math.ceil(left[1]), math.floor(right[0])
            if not MIN_GAP <= ratio <= MAX_GAP or start >= end or np.any(lines[row][:, start:end]):
                rejected += 1
                continue
            observations.append((row, float(ratio), _context(left[2], right[2]), sequence))
    return observations, rejected


def _empty_runs(ink):
    occupied = np.any(ink, axis=0)
    indexes = np.flatnonzero(occupied)
    if not len(indexes):
        return []
    # Crop off page/crop margins; only internal blank runs can be word gaps.
    blank = ~occupied[indexes[0]:indexes[-1] + 1]
    boundaries = np.flatnonzero(np.diff(np.r_[False, blank, False]))
    return [int(end - start) for start, end in zip(boundaries[::2], boundaries[1::2]) if end - start >= 2]


def _image_observations(lines):
    candidates, heights = [], {}
    for row, ink in sorted(lines.items()):
        ys = np.where(ink)[0]
        if not len(ys):
            continue
        # Full ascender/descender extent, never average character width. The
        # .9 proportion is a declared generic em-height prior, not a learned one.
        em = (int(ys.max()) - int(ys.min()) + 1) / .9
        heights[row] = em
        candidates.extend((row, gap / em, sequence) for sequence, gap in enumerate(_empty_runs(ink)))
    if len(candidates) < 12 or len(heights) < 2:
        return []
    values = np.asarray([value for _, value, _ in candidates])
    logs = np.log(values)
    centers = np.quantile(logs, [.2, .8])
    for _ in range(24):
        labels = np.abs(logs[:, None] - centers).argmin(axis=1)
        if any(np.count_nonzero(labels == group) < 3 for group in (0, 1)):
            return []
        updated = np.array([logs[labels == group].mean() for group in (0, 1)])
        if np.allclose(centers, updated):
            break
        centers = updated
    small, large = values[labels == 0], values[labels == 1]
    # Demand two separated populations. Uniformly spaced alphabet/word rows,
    # or ambiguous broad distributions, cannot establish word boundaries.
    if (np.median(large) < .18 or np.median(small) > .16 or
            np.median(large) / np.median(small) < 2.8 or
            np.quantile(large, .1) < 1.5 * np.quantile(small, .9) or
            len(large) / len(values) > .6):
        return []
    return [(row, float(ratio), "ordinary", sequence) for (row, ratio, sequence), label in zip(candidates, labels)
            if label == 1 and MIN_GAP <= ratio <= MAX_GAP]


def fit_word_spacing(bank=None, sample_dir=None, sample_lines=None, selected_lines=None,
                     source_sha256=None, em_height=32):
    """Return a JSON-serializable spacing model; never require OCR or the target text.

    ``sample_lines`` is profile.sample.lines; each file is relative to sample_dir.
    Reviewed ``bank.words[*].source`` coordinates use the source crop's pixels.
    Native bank em_height defaults to the renderer's established 32 pixels.
    """
    if not _finite(em_height) or not 8 <= em_height <= 512:
        raise ValueError("Invalid source em height.")
    bank = bank or {}
    if not isinstance(bank, dict):
        raise ValueError("Invalid source reference bank.")
    if source_sha256 and bank.get("source_sha256") and source_sha256 != bank["source_sha256"]:
        raise ValueError("Word-spacing source does not match the reference bank.")
    lines = _load_lines(sample_dir, sample_lines, selected_lines)
    observations, rejected = _reviewed_observations(bank, lines, float(em_height)) if bank.get("reviewed") is True else ([], 0)
    method = "reviewed-word-boxes"
    if len(observations) < 5:
        observations = _image_observations(lines)
        method = "image-gap-estimate"
    if len(observations) < 5:
        observations = []
        method = "conservative-default"
    values = np.asarray([value for _, value, _, _ in observations], dtype=float)
    measured = bool(len(values))
    distribution = sorted(float(value) for value in values) if measured else [.20, .25, .29, .32, .35, .40, .46]
    if len(distribution) > 256:
        distribution = np.quantile(distribution, np.linspace(0, 1, 256)).tolist()
    mean = float(values.mean()) if measured else .32
    std = float(values.std()) if measured else .065
    row_values = defaultdict(list)
    context_values = defaultdict(list)
    for row, value, context, sequence in observations:
        row_values[row].append((sequence, value))
        context_values[context].append(value)
    previous, following = [], []
    for row in row_values.values():
        for left, right in zip(row, row[1:]):
            if right[0] == left[0] + 1:
                previous.append(left[1]); following.append(right[1])
    correlation, rhythm_origin = .25, "conservative-prior"
    if len(previous) >= 12 and np.std(previous) > .01 and np.std(following) > .01:
        correlation = float(np.clip(np.corrcoef(previous, following)[0, 1], -.15, .55))
        rhythm_origin = "observed-adjacent-gaps"
    contexts = {}
    # Pause effects need repeated evidence; single punctuation examples never
    # establish a habit. Shrink small groups toward the overall writer mean.
    for context, group in context_values.items():
        if context == "ordinary" or len(group) < 5:
            continue
        factor = 1 + (float(np.mean(group)) / mean - 1) * len(group) / (len(group) + 8)
        contexts[context] = {"factor": float(np.clip(factor, .8, 1.25)), "observations": len(group)}
    confidence = ("high" if len(values) >= 16 and len(row_values) >= 2 else "moderate") if method == "reviewed-word-boxes" else ("low" if measured else "none")
    return {
        "schema_version": 1, "version": VERSION, "method": method, "confidence": confidence,
        "source_sha256": source_sha256 or bank.get("source_sha256"),
        "bank_sha256": bank.get("_manifest_sha256"),
        "source_line_ink_hashes": {str(row): hashlib.sha256(ink.tobytes()).hexdigest() for row, ink in sorted(lines.items())},
        "observations": len(values), "source_rows": len(row_values), "rejected_pairs": rejected,
        "unit": "em", "mean": mean, "std": std,
        "quantiles": {str(q): float(np.quantile(distribution, q)) for q in (.1, .25, .5, .75, .9)},
        "distribution": distribution,
        "min_gap": MIN_GAP, "max_gap": MAX_GAP,
        "measurement_resolution": 1 / float(em_height) if method == "reviewed-word-boxes" else 0.,
        "lag_correlation": correlation, "rhythm_origin": rhythm_origin,
        "variation_origin": "observed" if measured and std >= mean * .06 else "bounded-natural-variation-prior",
        "context_adjustments": contexts,
        "sampling_note": "Empirical quantiles with bounded subpixel dequantization; rhythm is identified separately as observed or a conservative prior.",
        "limits": ("Reviewed source gaps; no stroke timing is inferred." if method == "reviewed-word-boxes" else
                   "Image-only gap clusters and generic em calibration; word boundaries are not recognized." if measured else
                   "No reliable word-boundary evidence; bounded generic spacing, not a learned personal habit."),
    }


def validate_word_spacing(model):
    """Reject malformed persisted models before using them in layout."""
    if not isinstance(model, dict) or model.get("schema_version") != 1 or model.get("version") != VERSION or model.get("method") not in _METHODS:
        raise ValueError("Invalid word-spacing model.")
    for name in ("mean", "std", "min_gap", "max_gap", "lag_correlation", "measurement_resolution"):
        if not _finite(model.get(name)):
            raise ValueError("Invalid word-spacing statistics.")
    if not (MIN_GAP <= model["min_gap"] <= model["mean"] <= model["max_gap"] <= MAX_GAP and
            0 <= model["std"] <= MAX_GAP and -.15 <= model["lag_correlation"] <= .55 and
            0 <= model["measurement_resolution"] <= .125):
        raise ValueError("Word-spacing statistics are out of bounds.")
    distribution = model.get("distribution")
    if (not isinstance(distribution, list) or not 1 <= len(distribution) <= 256 or
            any(not _finite(value) or not MIN_GAP <= value <= MAX_GAP for value in distribution)):
        raise ValueError("Invalid word-spacing distribution.")
    if (model.get("variation_origin") not in {"observed", "bounded-natural-variation-prior"} or
            model.get("rhythm_origin") not in {"conservative-prior", "observed-adjacent-gaps"}):
        raise ValueError("Invalid word-spacing evidence label.")
    if model.get("unit") != "em" or model.get("confidence") not in {"high", "moderate", "low", "none"}:
        raise ValueError("Invalid word-spacing evidence metadata.")
    for name in ("observations", "source_rows", "rejected_pairs"):
        value = model.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 200000:
            raise ValueError("Invalid word-spacing evidence count.")
    quantiles = model.get("quantiles")
    if (not isinstance(quantiles, dict) or set(quantiles) != {str(q) for q in (.1, .25, .5, .75, .9)} or
            any(not _finite(value) or not MIN_GAP <= value <= MAX_GAP for value in quantiles.values())):
        raise ValueError("Invalid word-spacing quantiles.")
    adjustments = model.get("context_adjustments", {})
    if not isinstance(adjustments, dict) or len(adjustments) > 8:
        raise ValueError("Invalid word-spacing contexts.")
    for key, entry in adjustments.items():
        if (key not in {"after-pause", "after-comma"} or not isinstance(entry, dict) or
                not _finite(entry.get("factor")) or not .8 <= entry["factor"] <= 1.25 or
                isinstance(entry.get("observations"), bool) or not isinstance(entry.get("observations"), int) or
                not 5 <= entry["observations"] <= 200000):
            raise ValueError("Invalid word-spacing context adjustment.")
    return model


def sample_word_gaps(model, count, seed=42, paragraph=0, contexts=None):
    """Generate bounded em ratios with correlated, seed-reproducible variation.

    ``contexts`` optionally supplies one {left, right} text pair per boundary.
    The sequence is sampled once before line wrapping, so a wrap does not change
    later spaces and repeated exports remain reproducible.
    """
    validate_word_spacing(model)
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 200000:
        raise ValueError("Invalid word-gap count.")
    if contexts is not None and len(contexts) != count:
        raise ValueError("Word-gap contexts must match the boundary count.")
    digest = hashlib.sha256(f"{VERSION}:{seed}:{paragraph}".encode()).digest()
    rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))
    values = np.sort(model["distribution"])
    positions = np.linspace(0, 1, len(values))
    correlation = model["lag_correlation"]
    z = float(rng.normal())
    result = []
    for index in range(count):
        z = correlation * z + math.sqrt(1 - correlation ** 2) * float(rng.normal())
        rank = .5 * (1 + math.erf(z / math.sqrt(2)))
        gap = float(np.interp(rank, positions, values))
        gap += model["measurement_resolution"] * float(rng.uniform(-.35, .35))
        # A tiny flat-sample prior avoids mechanical repetition while explicitly
        # retaining its non-learned origin. Never amplify a varied real sample.
        if model["variation_origin"] == "bounded-natural-variation-prior":
            gap += model["mean"] * .07 * z
        if contexts is not None:
            record = contexts[index]
            if not isinstance(record, dict):
                raise ValueError("Invalid word-gap context.")
            context = _context(record.get("left", ""), record.get("right", ""))
            gap *= model.get("context_adjustments", {}).get(context, {}).get("factor", 1.)
        result.append(float(np.clip(gap, model["min_gap"], model["max_gap"])))
    return result

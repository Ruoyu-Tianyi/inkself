"""Explicit supplemental mathematical glyphs, never claimed as learned writing.

The reviewed sample can set scale, stroke darkness, and a bounded slant. Shapes
come from the small, auditable vector vocabulary below; no font, model, network,
or hidden substitution is used. These glyphs require the caller's explicit opt-in.
"""
import math
import re
import statistics

import numpy as np
from PIL import Image, ImageDraw

from .reference_renderer import _image


DESIGN_VERSION = 1

# Absolute SVG-like M/L/Q/C commands. Native design baseline is y=24 and the
# lowercase x-height is 14. Open curves are intentional pen strokes.
_PATHS = {
    'α': ("M14 12 C9 7 2 11 3 18 C4 25 10 25 13 18 L15 10 M14 15 C12 22 15 25 18 22",),
    'β': ("M4 31 L5 10 C5 -1 16 0 15 8 C14 12 9 14 5 14 M6 14 C15 8 21 16 16 22 C13 26 8 24 5 23",),
    'γ': ("M1 11 C5 7 9 16 10 24 C11 29 9 34 7 32 C4 29 12 18 17 10",),
    'δ': ("M13 3 C5 0 4 5 10 10 C22 19 11 29 4 22 C-2 16 6 9 14 12",),
    'ε': ("M15 11 C7 6 1 14 9 16 M9 16 C-2 18 5 28 15 22",),
    'ζ': ("M2 5 C8 7 13 7 17 4 M17 5 C10 11 -3 18 5 23 C8 25 16 22 14 29 C13 32 9 33 7 30",),
    'η': ("M2 11 L3 24 M3 16 C8 5 16 8 15 17 L13 32",),
    'θ': ("M9 3 C-1 5 -1 25 8 25 C17 25 20 5 12 3 C11 2 10 2 9 3 M2 14 C6 16 12 15 17 13",),
    'ι': ("M6 10 L4 20 C3 25 7 25 11 22",),
    'κ': ("M4 10 L3 24 M4 18 L15 10 M6 16 C11 17 10 23 16 24",),
    'λ': ("M3 3 C7 1 9 7 11 14 L16 24 M11 14 L3 25",),
    'μ': ("M4 11 L1 32 M4 13 L3 21 C5 28 12 23 14 11 M14 12 L13 21 C13 25 16 25 19 22",),
    'ν': ("M2 10 C5 9 3 20 7 24 C12 21 15 16 16 10",),
    'ξ': ("M3 3 C8 7 12 6 16 3 M14 6 C2 8 1 14 12 14 M12 14 C1 17 1 23 10 23 C16 23 17 28 11 32",),
    'ο': ("M10 10 C1 8 0 21 6 24 C14 28 21 13 14 10 C13 9 11 9 10 10",),
    'π': ("M1 12 C6 9 12 10 20 10 M6 11 L4 24 M15 11 L14 21 C14 25 18 25 21 22",),
    'ρ': ("M2 32 L5 14 C9 5 19 9 16 18 C14 26 6 26 4 20",),
    'σ': ("M11 11 C2 8 0 21 6 24 C14 28 19 17 13 12 M11 11 C15 12 19 11 22 10",),
    'τ': ("M1 12 C7 9 14 10 20 10 M11 11 L9 20 C8 25 13 25 16 22",),
    'υ': ("M3 10 C4 14 -1 23 7 24 C16 25 19 11 14 10",),
    'φ': ("M10 10 C1 8 -1 22 7 24 C17 28 22 13 15 10 C13 9 11 9 10 10 M14 3 L7 32",),
    'χ': ("M2 9 C9 10 10 24 16 26 M17 9 C12 12 7 24 1 29",),
    'ψ': ("M3 10 C3 15 1 23 9 24 C17 24 20 13 18 10 M12 4 L7 32",),
    'ω': ("M4 10 C-1 15 0 25 6 24 C10 23 11 17 10 15 M10 15 C7 23 12 26 16 23 C22 19 22 11 18 10",),
    'ϵ': ("M16 11 C5 7 0 13 2 19 C4 26 12 26 17 22 M2 17 L12 17",),
    'ϑ': ("M10 3 C1 4 0 25 9 25 C17 25 21 12 16 9 C12 7 10 14 16 15 C22 17 24 11 23 8",),
    'ϕ': ("M10 10 C1 8 -1 22 7 24 C17 28 22 13 15 10 C13 9 11 9 10 10 M13 3 L8 32",),
    'ϱ': ("M2 32 L5 14 C9 5 19 9 16 18 C14 26 6 26 4 20 M3 26 C1 34 10 36 13 29",),
    'ς': ("M16 11 C7 6 -1 15 4 21 C7 24 15 23 14 29 C13 33 8 33 6 31",),
    'Α': ("M1 24 L11 3 L19 24 M6 16 L15 16",),
    'Β': ("M3 24 L5 3 L11 3 C22 3 20 13 10 13 L4 13 M10 13 C23 12 22 24 10 24 L3 24",),
    'Γ': ("M3 24 L5 3 L19 3",),
    'Δ': ("M1 24 L12 3 L21 24 L1 24",),
    'Ε': ("M20 3 L5 3 L3 24 L19 24 M4 13 L16 13",),
    'Ζ': ("M3 3 L22 3 L1 24 L21 24",),
    'Η': ("M4 3 L2 24 M20 3 L18 24 M3 13 L19 13",),
    'Θ': ("M11 3 C-1 2 -2 25 10 25 C24 26 26 2 11 3 M5 14 L19 14",),
    'Ι': ("M4 3 L16 3 M10 3 L8 24 M2 24 L14 24",),
    'Κ': ("M4 3 L2 24 M20 3 L3 16 M9 11 L20 24",),
    'Λ': ("M1 24 L12 3 L21 24",),
    'Μ': ("M2 24 L5 3 L13 18 L22 3 L22 24",),
    'Ν': ("M2 24 L4 3 L20 24 L22 3",),
    'Ξ': ("M2 3 L23 3 M5 13 L20 13 M1 24 L22 24",),
    'Ο': ("M11 3 C-1 2 -2 25 10 25 C24 26 26 2 11 3",),
    'Π': ("M1 3 L23 3 M5 3 L3 24 M20 3 L18 24",),
    'Ρ': ("M3 24 L5 3 L12 3 C25 3 22 14 10 14 L4 14",),
    'Σ': ("M23 3 L3 3 L13 13 L1 24 L22 24",),
    'Τ': ("M1 3 L24 3 M13 3 L11 24",),
    'Υ': ("M2 3 L12 13 L23 3 M12 13 L10 24",),
    'Φ': ("M11 7 C-2 6 -2 21 10 21 C25 22 27 7 11 7 M14 1 L11 27",),
    'Χ': ("M3 3 L20 24 M22 3 L1 24",),
    'Ψ': ("M3 3 L3 11 C4 24 21 23 23 11 L24 3 M14 1 L11 27",),
    'Ω': ("M1 24 L9 24 C-4 12 3 2 13 3 C27 4 26 17 17 24 L26 24",),
    '(': ("M10 1 C0 8 0 25 8 32",),
    ')': ("M2 1 C12 8 12 25 4 32",),
    '[': ("M10 1 L3 1 L2 32 L9 32",),
    ']': ("M2 1 L9 1 L8 32 L1 32",),
    '{': ("M12 1 C2 0 6 10 5 13 C4 16 1 16 1 17 C5 18 5 18 4 23 C3 29 3 32 11 32",),
    '}': ("M1 1 C11 0 7 10 8 13 C9 16 12 16 12 17 C8 18 8 18 9 23 C10 29 10 32 2 32",),
    '|': ("M5 2 L4 29",),
    '/': ("M1 28 L15 3",),
    '\\': ("M2 3 L15 28",),
    '√': ("M0 18 L4 16 L8 25 L16 3 L28 3",),
    '∑': ("M25 2 L3 2 L15 14 L1 28 L25 28",),
    '∏': ("M1 2 L27 2 M6 2 L4 28 M22 2 L20 28",),
    '∫': ("M16 1 C5 -2 10 12 7 23 C6 30 4 34 0 31",),
    '∞': ("M14 17 C1 1 -5 28 7 23 C15 21 17 8 24 10 C35 13 26 30 18 21 L11 13",),
    '+': ("M1 17 L21 17 M12 7 L11 27",),
    '−': ("M1 17 L21 17",),
    '-': ("M1 17 L17 17",),
    '=': ("M1 12 L21 12 M1 21 L21 21",),
    '±': ("M1 11 L21 11 M12 2 L11 20 M1 26 L21 26",),
    '∓': ("M1 4 L21 4 M1 19 L21 19 M12 10 L11 28",),
    '×': ("M2 8 L18 25 M20 8 L1 25",),
    '÷': ("M1 17 L21 17", "M11 6 L11.2 6.2", "M11 28 L11.2 28.2"),
    '·': ("M5 17 L5.4 17.3",),
    '∘': ("M7 12 C0 11 0 20 6 21 C13 22 15 12 7 12",),
    '≤': ("M21 5 L1 14 L20 22 M1 27 L21 27",),
    '≥': ("M1 5 L21 14 L2 22 M1 27 L21 27",),
    '<': ("M21 6 L1 16 L20 26",),
    '>': ("M1 6 L21 16 L2 26",),
    '≠': ("M1 12 L21 12 M1 21 L21 21 M17 3 L5 29",),
    '≈': ("M1 12 C8 4 14 20 23 11 M1 22 C8 14 14 30 23 21",),
    '≃': ("M1 12 C8 4 14 20 23 11 M1 25 L23 25",),
    '∼': ("M1 17 C8 9 14 25 23 16",),
    '∈': ("M21 5 C-3 3 -4 30 20 27 M1 16 L18 16",),
    '∉': ("M21 5 C-3 3 -4 30 20 27 M1 16 L18 16 M21 1 L4 31",),
    '∂': ("M5 3 C23 -2 21 29 9 25 C-2 22 3 10 14 13 C18 14 17 17 17 17",),
    '∇': ("M1 3 L23 3 L10 26 L1 3",),
    '∅': ("M11 5 C-1 3 -3 26 9 26 C23 27 26 5 11 5 M23 1 L-1 30",),
    '∀': ("M1 3 L11 27 L23 3 M6 16 L17 16",),
    '∃': ("M1 3 L20 3 L18 27 L0 27 M3 15 L19 15",),
    '∝': ("M23 9 C14 8 14 23 7 24 C-4 25 -1 8 7 10 C15 11 16 26 24 23",),
    '∧': ("M1 25 L12 6 L22 25",),
    '∨': ("M1 6 L11 25 L22 6",),
    '¬': ("M1 12 L22 12 L21 24",),
    '∩': ("M1 27 L2 14 C3 0 23 0 22 14 L21 27",),
    '∪': ("M2 4 L1 17 C0 31 20 31 21 17 L22 4",),
    '⊂': ("M22 5 C-4 2 -5 30 21 27",),
    '⊃': ("M1 5 C27 2 28 30 2 27",),
    '⊆': ("M22 3 C-4 0 -5 24 21 21 M1 28 L22 28",),
    '⊇': ("M1 3 C27 0 28 24 2 21 M1 28 L22 28",),
    '→': ("M1 16 L29 16 M20 8 L29 16 L19 24",),
    '←': ("M29 16 L1 16 M10 8 L1 16 L11 24",),
    '↔': ("M1 16 L29 16 M20 8 L29 16 L19 24 M10 8 L1 16 L11 24",),
    '↦': ("M1 8 L1 24 M1 16 L29 16 M20 8 L29 16 L19 24",),
    '⇒': ("M1 12 L24 12 M1 20 L24 20 M19 5 L32 16 L18 27",),
    '⇔': ("M7 12 L25 12 M7 20 L25 20 M20 5 L33 16 L19 27 M13 5 L0 16 L14 27",),
    '′': ("M7 3 L3 12",),
    '″': ("M7 3 L3 12 M14 3 L10 12",),
}

SUPPORTED_GLYPHS = frozenset(_PATHS)
_LATIN_SHAPE_ALIASES = dict(zip('οΑΒΕΖΗΙΚΜΝΟΡΤΥΧ', 'oABEZHIKMNOPTYX'))


def _flatten(path):
    tokens = re.findall(r'[MLQC]|-?\d+(?:\.\d+)?', path)
    result, current, i = [], (0., 0.), 0
    while i < len(tokens):
        command = tokens[i]
        count = {'M': 2, 'L': 2, 'Q': 4, 'C': 6}[command]
        values = [float(n) for n in tokens[i + 1:i + 1 + count]]
        i += count + 1
        if command == 'M':
            result.append([(values[0], values[1])])
            current = result[-1][-1]
            continue
        start = current
        if command == 'L':
            points = [(values[0], values[1])]
        elif command == 'Q':
            points = [((1-t)**2*start[0]+2*(1-t)*t*values[0]+t*t*values[2],
                       (1-t)**2*start[1]+2*(1-t)*t*values[1]+t*t*values[3])
                      for t in np.linspace(0, 1, 25)[1:]]
        else:
            points = [((1-t)**3*start[0]+3*(1-t)**2*t*values[0]+3*(1-t)*t*t*values[2]+t**3*values[4],
                       (1-t)**3*start[1]+3*(1-t)**2*t*values[1]+3*(1-t)*t*t*values[3]+t**3*values[5])
                      for t in np.linspace(0, 1, 33)[1:]]
        result[-1].extend(points)
        current = points[-1]
    return result


def _geometry(bank):
    """Bounded visual matching, without inferring an unseen writer-specific shape."""
    heights, widths, slants, shades, references = [], [], [], [], []
    # Small deterministic selection avoids treating wide, curved glyphs as stems.
    for char in 'aenxo1lIt':
        record = bank.get('glyphs', {}).get(char)
        if record is None:
            continue
        image = _image(bank, record)
        pixels = np.asarray(image)
        yy, xx = np.where(pixels < 180)
        if not len(xx):
            continue
        references.append(record.get('sha256', ''))
        if char in 'aenxo':
            heights.append(int(yy.max() - yy.min() + 1))
        dark = pixels[pixels < 160]
        shades.append(float(np.median(dark if len(dark) else pixels[pixels < 180])))
        mask = pixels < 170
        for row in mask:
            changes = np.diff(np.r_[False, row, False].astype(int))
            runs = np.flatnonzero(changes == -1) - np.flatnonzero(changes == 1)
            widths.extend(float(n) for n in runs if 1 <= n <= max(2, image.height * .22))
        if char in '1lI' and yy.max() - yy.min() > 4:
            slope = float(np.cov(xx, yy, ddof=0)[0, 1] / max(1, np.var(yy)))
            slants.append(-slope)
    return {
        'x_height': float(np.clip(statistics.median(heights) if heights else 13., 8., 22.)),
        'stroke_width': float(np.clip(statistics.median(widths) if widths else 1.3, .9, 1.7)),
        'slant': float(np.clip(statistics.median(slants) if slants else .08, -.12, .24)),
        'shade': round(float(np.clip(statistics.median(shades) if shades else 15., 0., 100.))),
        'style_references': sorted(set(filter(None, references))),
    }


def supplemental_glyph(char, bank, scale=3):
    """Return an L raster, native-pixel baseline and truthful supplemental metadata.

    Callers must opt in before invoking this function. The result does not claim
    that the sample contained the requested symbol, or that its shape was learned.
    A Greek/Latin visual alias may reuse a reviewed Latin outline, with that
    decision recorded separately from its supplemental Greek interpretation.
    """
    if not isinstance(char, str) or char not in SUPPORTED_GLYPHS:
        raise ValueError('Unsupported supplemental mathematical glyph: ' + repr(char))
    if isinstance(scale, bool) or not isinstance(scale, int) or not 1 <= scale <= 8:
        raise ValueError('Supplemental raster scale must be an integer from 1 to 8.')
    meta = {
        'origin': 'supplemental', 'supplemental': True,
        'handwriting_not_learned': True, 'character': char,
        'design_version': DESIGN_VERSION,
        'method': 'curated-math-path-with-sample-geometry',
        'em_height': 32 * scale, 'raster_scale': scale,
        'references': [],
    }
    alias = _LATIN_SHAPE_ALIASES.get(char)
    record = bank.get('glyphs', {}).get(alias) if alias else None
    if record is not None:
        source = _image(bank, record)
        image = Image.new('L', ((source.width + 4) * scale, (source.height + 4) * scale), 255)
        image.paste(source.resize((source.width * scale, source.height * scale), Image.Resampling.LANCZOS), (2 * scale, 2 * scale))
        baseline = float(record['baseline']) + 2
        if not math.isfinite(baseline):
            raise ValueError('Invalid reviewed glyph baseline.')
        meta.update(method='reviewed-latin-outline-for-supplemental-greek', source_latin=alias,
                    style_references=[record.get('sha256', '')])
        return image, baseline, meta
    geometry = _geometry(bank)
    factor = geometry['x_height'] / 14
    paths = [points for path in _PATHS[char] for points in _flatten(path)]
    transformed = [[((x + geometry['slant'] * (24 - y)) * factor, y * factor)
                    for x, y in points] for points in paths]
    coordinates = [point for points in transformed for point in points]
    min_x = min(x for x, _ in coordinates)
    max_x = max(x for x, _ in coordinates)
    min_y = min(y for _, y in coordinates)
    max_y = max(y for _, y in coordinates)
    pad = 2.5
    width = max(5, math.ceil(max_x - min_x + 2 * pad))
    height = max(5, math.ceil(max_y - min_y + 2 * pad))
    # Oversample only for rasterization; returned dimensions remain scale × native.
    draw_scale = scale * 2
    image = Image.new('L', (width * draw_scale, height * draw_scale), 255)
    draw = ImageDraw.Draw(image)
    stroke = max(1, round(geometry['stroke_width'] * draw_scale))
    radius = stroke / 2
    for points in transformed:
        points = [((x - min_x + pad) * draw_scale, (y - min_y + pad) * draw_scale)
                  for x, y in points]
        draw.line(points, fill=geometry['shade'], width=stroke, joint='curve')
        for x, y in (points[0], points[-1]):
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=geometry['shade'])
    image = image.resize((width * scale, height * scale), Image.Resampling.LANCZOS)
    baseline = 24 * factor - min_y + pad
    meta.update(style_geometry={key: value for key, value in geometry.items() if key != 'style_references'},
                style_references=geometry['style_references'])
    return image, float(baseline), meta

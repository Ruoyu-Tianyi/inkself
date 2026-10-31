"""User-selected spacing controls, independent of learned handwriting evidence."""
from __future__ import annotations

import math

VERSION = 'spacing-controls-1'
LIMITS = {
    'letter': (.6, 1.8), 'word': (.5, 2.), 'line': (.8, 1.8),
    'paragraph': (.3, 2.5), 'number': (.6, 1.8), 'symbol': (.6, 1.8),
    'baseline': (0., 2.), 'variation': (0., 2.),
}
DEFAULTS = {key: 1. for key in LIMITS}
PRESETS = {
    'natural': dict(DEFAULTS),
    'neat': {**DEFAULTS, 'line': 1.05, 'baseline': .25, 'variation': .2},
    'compact': {**DEFAULTS, 'letter': .85, 'word': .8, 'line': .9,
                'paragraph': .75, 'number': .9, 'symbol': .9,
                'baseline': .75, 'variation': .7},
    'relaxed': {**DEFAULTS, 'letter': 1.15, 'word': 1.3, 'line': 1.2,
                'paragraph': 1.3, 'number': 1.15, 'symbol': 1.15,
                'baseline': 1.15, 'variation': 1.25},
}


def normalize_spacing(value=None):
    """Resolve a preset and overrides; reject invalid saved or submitted values.

    Omitting settings preserves the previous renderer defaults. Overrides that
    differ from a named preset are labelled custom to keep saved UI state honest.
    """
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - (set(LIMITS) | {'preset'}):
        raise ValueError('间距设置无效：包含未知选项。')
    preset = value.get('preset', 'natural')
    if not isinstance(preset, str) or preset not in (*PRESETS, 'custom'):
        raise ValueError('请选择有效的间距风格。')
    result = dict(PRESETS.get(preset, DEFAULTS))
    for key, (low, high) in LIMITS.items():
        number = value.get(key, result[key])
        if (isinstance(number, bool) or not isinstance(number, (int, float))
                or not math.isfinite(number) or not low <= number <= high):
            raise ValueError(f'间距设置 {key} 必须在 {low:g}–{high:g} 之间。')
        result[key] = float(number)
    if preset in PRESETS and result != PRESETS[preset]:
        preset = 'custom'
    return {'preset': preset, **result}


def adjust_gap(base, mean, settings, kind):
    """Scale a positive gap and its existing deviation from its nominal mean.

    This controls spacing, not glyph size or shape. Callers preserve attachment
    gaps (zero) and enforce their own math/ink collision bounds separately.
    """
    return max(.25, (mean + (base - mean) * settings['variation']) * settings[kind])

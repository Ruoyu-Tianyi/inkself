"""Bounded sample-derived digit variation, not learned stroke dynamics."""
import hashlib
import random

VERSION = 'sample-digits-1'


def digit_gap(seed, occurrence, index):
    """Positive native-pixel spacing with a shared rhythm and local variation."""
    def noise(label):
        key = hashlib.sha256(f'{VERSION}:{seed}:{occurrence}:{label}'.encode()).digest()
        return random.Random(int.from_bytes(key[:8], 'little')).uniform(-1, 1)
    return round(max(.8, min(4.3, 2.4 + .45*noise('rhythm') + 1.05*noise(index))), 3)


def render_digit(bank, char, seed=42, occurrence=0, index=0):
    from .symbol_style import render_symbol
    if char not in '0123456789':
        raise ValueError('Expected an ASCII digit.')
    image, baseline, meta = render_symbol(bank, char, seed, occurrence, index, allow_digit=True)
    meta['version'] = VERSION
    meta['variation_limit'] = 'Bounded source transforms; not additional learned allographs.'
    return image, baseline, meta


def numeric_token(bank, text, seed=42, occurrence=0):
    from .symbol_style import symbol_token
    return symbol_token(bank, text, seed, occurrence, vary_digits=True)

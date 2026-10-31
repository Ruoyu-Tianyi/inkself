"""Bounded, reproducible symbol variation on reviewed personal ink.

This is procedural variation, not inferred pen pressure or newly learned shapes.
Digit variation is opt-in; the reference renderer remains unchanged. Percent components
are not reconstructed, and topology-changing variations fall back to the base.
"""
import hashlib
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .reference_renderer import _image

SCALE = 3
SYMBOLS = frozenset('%+-=×÷.,;:?!')
VERSION = 'bounded-symbols-1'


def standalone_symbol(text):
    """A prose token made only of punctuation/operators, excluding whitespace."""
    return bool(text) and all(not char.isalnum() and not char.isspace() for char in text)


def symbol_gap(base, settings, seed=42, occurrence=0, index=0):
    """Adjust operator/punctuation spacing with bounded opt-in extra rhythm.

    Historical symbol gaps were constant, so the natural (1) setting preserves
    them. Stronger variation adds new deterministic differences between gaps.
    """
    from .spacing import adjust_gap
    if settings['variation']<=1:
        return adjust_gap(base,base,settings,'symbol')
    key=hashlib.sha256(f'symbol-gap:{seed}:{occurrence}:{index}'.encode()).digest()
    noise=np.random.default_rng(int.from_bytes(key[:8],'little')).uniform(-1,1)
    sample=base*(1+.22*max(0,settings['variation']-1)*float(noise))
    return adjust_gap(sample,base,settings,'symbol')


def topology(image):
    mask = (np.asarray(image) < 170).astype('uint8')
    components = cv2.connectedComponents(np.pad(mask, 1), connectivity=8)[0] - 1
    # Four-connected background avoids counting diagonal foreground contacts as
    # a closed loop. The extra padding gives the outside exactly one component.
    holes = cv2.connectedComponents(1 - np.pad(mask, 1), connectivity=4)[0] - 2
    return components, holes


def _mask_parts(image):
    mask = (np.asarray(image) < 170).astype('uint8')
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    return [(labels == i, stats[i]) for i in range(1, count)]


def _loop_width(mask):
    contours, _ = cv2.findContours(mask.astype('uint8'), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    length = sum(cv2.arcLength(c, True) for c in contours) / 2
    return float(mask.sum() / max(length, 1))


def _percent_base(bank, source, baseline):
    high = source.resize((source.width * SCALE, source.height * SCALE), Image.Resampling.LANCZOS)
    original_topology = topology(high)
    detail = {'percent_scale': 1., 'diagonal_rebuilt': False}
    parts = _mask_parts(source)
    # Only repair the unambiguous form: two enclosed loops plus one tall slash.
    loops = [(mask, stat) for mask, stat in parts
             if topology(Image.fromarray(np.where(mask, 0, 255).astype('uint8')))[1] == 1]
    others = [(mask, stat) for mask, stat in parts if not any(mask is m for m, _ in loops)]
    if len(parts) == 3 and len(loops) == 2 and len(others) == 1:
        diagonal, stat = others[0]
        yy, xx = np.where(diagonal)
        if stat[3] >= source.height * .7 and len(np.unique(yy)) > 5:
            correlation = float(np.corrcoef(xx, yy)[0, 1]) if np.std(xx) else 0
            if correlation < -.65:
                rows = np.unique(yy)
                centers = np.array([np.mean(xx[yy == y]) for y in rows])
                centers = np.convolve(np.pad(centers, (1, 1), mode='edge'), [1/3]*3, mode='valid')
                length = float(np.hypot(np.diff(centers), np.diff(rows)).sum())
                target = float(np.clip(np.median([_loop_width(m) for m, _ in loops]) * 1.15, 1.2, 3.))
                if float(diagonal.sum()) / max(length, 1) > target * 1.5:
                    # Preserve the captured centerline, rather than introducing
                    # a font slash. Extra resolution keeps a narrow line smooth.
                    source_array = np.asarray(source).copy()
                    erase = cv2.dilate(diagonal.astype('uint8'), np.ones((3, 3), 'uint8')).astype(bool)
                    source_array[erase] = 255
                    candidate = Image.fromarray(source_array).resize(high.size, Image.Resampling.LANCZOS)
                    stroke = Image.new('L', (source.width * 9, source.height * 9), 255)
                    draw = ImageDraw.Draw(stroke)
                    points = [((float(x)+.5)*9, (float(y)+.5)*9) for x, y in zip(centers, rows)]
                    draw.line(points, fill=30, width=max(1, round(target*9)), joint='curve')
                    radius = target*9/2
                    for x, y in (points[0], points[-1]):
                        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=30)
                    stroke = stroke.resize(high.size, Image.Resampling.LANCZOS)
                    candidate = Image.fromarray(np.minimum(np.asarray(candidate), np.asarray(stroke)))
                    if topology(candidate) == original_topology:
                        high = candidate
                        detail['diagonal_rebuilt'] = True

    digit_heights = []
    for char in '0235689':
        if char in bank['glyphs']:
            mask = np.asarray(_image(bank, bank['glyphs'][char])) < 170
            ys = np.where(mask)[0]
            if len(ys):
                digit_heights.append(int(ys.max() - ys.min() + 1))
    ys = np.where(np.asarray(source) < 170)[0]
    ink_height = int(ys.max() - ys.min() + 1)
    # Oversized source composites should not tower over their adjacent numbers.
    if digit_heights and ink_height > 1.5 * np.median(digit_heights):
        factor = max(.4, 1.3 * float(np.median(digit_heights)) / ink_height)
        candidate = high.resize((max(3, round(high.width*factor)), max(3, round(high.height*factor))), Image.Resampling.LANCZOS)
        if topology(candidate) == original_topology:
            high = candidate
            baseline *= factor
            detail['percent_scale'] = factor
    return high, baseline, detail


def _percent_parts(base, rng):
    """Vary loop placement and slash curvature, while retaining captured ink."""
    if topology(base) != (3, 2):
        return base, False
    output = np.full_like(base, 255)
    yy, xx = np.indices(base.shape, dtype='float32')
    for mask, stat in _mask_parts(base):
        support = cv2.dilate(mask.astype('uint8'), np.ones((5, 5), 'uint8')).astype(bool)
        layer = np.where(support, base, 255).astype('uint8')
        if topology(np.where(mask, 0, 255))[1] == 1:
            center = (float(stat[0]+stat[2]/2), float(stat[1]+stat[3]/2))
            matrix = cv2.getRotationMatrix2D(center, float(rng.uniform(-5, 5)), float(rng.uniform(.94, 1.06)))
            matrix[:, 2] += rng.uniform(-.35, .35, size=2)*SCALE
            layer = cv2.warpAffine(layer, matrix, (base.shape[1], base.shape[0]), flags=cv2.INTER_CUBIC, borderValue=255)
        else:
            t = np.clip((yy-stat[1])/max(1, stat[3]-1), 0, 1)
            bow = float(rng.uniform(-.45, .45))*SCALE*np.sin(np.pi*t)
            layer = cv2.remap(layer, (xx+bow).astype('float32'), yy, cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=255)
        np.minimum(output, layer, out=output)
    return (output, True) if topology(output) == (3, 2) else (base, False)


def render_symbol(bank, char, seed=42, occurrence=0, index=0, attempt=0, variation=True, allow_digit=False):
    """Return high-resolution ink, native baseline, and auditable variation.

    left_padding is excluded from layout_width; compositors must place the ink
    that far left of its logical origin. This preserves digit/symbol spacing.
    """
    if char not in SYMBOLS and not (allow_digit and char in '0123456789'):
        raise ValueError('Only supported punctuation and operators can vary.')
    record = bank['glyphs'][char]
    source = _image(bank, record)
    baseline = float(record['baseline'])
    detail = {}
    if char == '%':
        high, baseline, detail = _percent_base(bank, source, baseline)
    else:
        high = source.resize((source.width*SCALE, source.height*SCALE), Image.Resampling.LANCZOS)
    height, width = high.height, high.width
    padding = 3 * SCALE
    base = np.pad(np.asarray(high), padding, constant_values=255)
    if char in '.:':
        # A one-pixel, low-contrast dot can disappear after A4 downsampling.
        # Add only 1/3 native pixel and deepen its captured ink, preserving gaps.
        base = np.clip(255-(255-base.astype('float32'))*2., 0, 255).astype('uint8')
        base = cv2.erode(base, np.ones((2, 2), 'uint8'))
    expected = topology(base)
    identity = f'{VERSION}:{seed}:{occurrence}:{index}:{char}' + (f':{attempt}' if attempt else '')
    key = hashlib.sha256(identity.encode()).digest()
    rng = np.random.default_rng(int.from_bytes(key[:8], 'little'))
    if char == '%':
        varied_parts, detail['component_variation'] = _percent_parts(base, rng)
    else:
        varied_parts = base
    tiny = char in '.,:;' or min(source.size) <= 2
    angle = 0. if tiny else float(rng.uniform(-3., 3.))
    sx = 1. if tiny else float(rng.uniform(.94, 1.06))
    sy = 1. if tiny else float(rng.uniform(.95, 1.05))
    dx, dy = rng.uniform(-.35, .35, size=2) * SCALE
    if tiny:
        dx, dy = round(float(dx)), round(float(dy))
    radians = math.radians(angle)
    a, b = math.cos(radians)*sx, -math.sin(radians)*sy
    c, d = math.sin(radians)*sx, math.cos(radians)*sy
    cx, cy = padding+(width-1)/2, padding+(height-1)/2
    matrix = np.array([[a, b, cx-a*cx-b*cy+dx], [c, d, cy-c*cx-d*cy+dy]], dtype='float32')
    varied = cv2.warpAffine(varied_parts, matrix, (base.shape[1], base.shape[0]),
                           flags=cv2.INTER_NEAREST if tiny else cv2.INTER_CUBIC, borderValue=255)
    small = Image.fromarray(varied).resize((max(1, round(varied.shape[1]*29/96)), max(1, round(varied.shape[0]*29/96))), Image.Resampling.LANCZOS)
    accepted = variation and topology(varied) == expected and topology(small) == expected and np.all(varied[[0,-1], :] == 255) and np.all(varied[:, [0,-1]] == 255)
    if not accepted:
        varied = base
        if char == '%':
            detail['component_variation'] = False
    meta = {'character': char, 'index': index, 'version': VERSION, 'source_sha256': record['sha256'],
            'left_padding': padding/SCALE, 'layout_width': width/SCALE,
            'angle_degrees': angle if accepted else 0., 'width_scale': sx if accepted else 1.,
            'height_scale': sy if accepted else 1., 'offset_px': [float(dx/SCALE), float(dy/SCALE)] if accepted else [0., 0.],
            'variation_accepted': bool(accepted), **detail}
    return Image.fromarray(varied), baseline+padding/SCALE, meta


def fit_percent_to_canvas(bank, image, meta, canvas_size, position, seed, occurrence):
    """Check the isolated percent at its actual token resampling phase.

    Canvas dimensions/advances never change between candidates, so digit pixels
    cannot change when a percent variation is rejected. Check every UI font size.
    """
    expected = topology(image)
    def legible(candidate):
        layer = Image.new('L', canvas_size, 255)
        layer.paste(candidate, position)
        for size in range(10, 27):
            factor = max(24, int(size*1240/595.2756*1.4))/96
            small = layer.resize((max(1, round(layer.width*factor)), max(1, round(layer.height*factor))), Image.Resampling.LANCZOS)
            if topology(small) != expected:
                return False
        return True
    for attempt in range(13):
        if attempt:
            image, _, meta = render_symbol(bank, '%', seed, occurrence, meta['index'], attempt=attempt)
        if legible(image):
            return image, {**meta, 'canvas_guard_passed': True, 'variation_attempt': attempt}
    image, _, meta = render_symbol(bank, '%', seed, occurrence, meta['index'], variation=False)
    return image, {**meta, 'canvas_guard_passed': legible(image), 'variation_attempt': 'normalized-base'}


def symbol_token(bank, text, seed=42, occurrence=0, vary_digits=False, spacing=None):
    """Compose nonalphabetic tokens without applying letter geometry to digits."""
    from .spacing import normalize_spacing,adjust_gap
    settings=normalize_spacing(spacing)
    pieces = []
    variants = []
    references = []
    digit_variants = []
    digit_gaps = []
    for index, char in enumerate(text):
        record = bank['glyphs'][char]
        source = _image(bank, record)
        if char in SYMBOLS or (vary_digits and char.isascii() and char.isdigit()):
            image, baseline, meta = render_symbol(bank, char, seed, occurrence, index, allow_digit=vary_digits)
            (digit_variants if char.isdigit() else variants).append(meta)
            bearing = meta['left_padding']
            advance = meta['layout_width'] + max(1., float(record.get('advance', source.width+2))-source.width)
        else:
            image = source.resize((source.width*SCALE, source.height*SCALE), Image.Resampling.LANCZOS)
            baseline, bearing = float(record['baseline']), 0.
            advance = max(source.width+1, float(record.get('advance', source.width+2)))
        if index+1 < len(text):
            logical_width=meta['layout_width'] if char in SYMBOLS or (vary_digits and char.isascii() and char.isdigit()) else source.width
            kind='number' if char.isdigit() and text[index+1].isdigit() else 'symbol'
            old_gap=advance-logical_width
            gap=symbol_gap(old_gap,settings,seed,occurrence,index) if kind=='symbol' else adjust_gap(old_gap,old_gap,settings,kind)
            advance=logical_width+gap
        if vary_digits and char.isdigit() and index+1 < len(text) and text[index+1].isdigit():
            from .digit_style import digit_gap
            gap = digit_gap(seed, occurrence, index,settings)
            advance = logical_width+gap
            digit_gaps.append(gap)
        pieces.append((image, baseline, bearing, advance))
        references.append(record['sha256'])
    base = math.ceil(max(p[1] for p in pieces))+4
    height = math.ceil(base+max(im.height/SCALE-b for im,b,_,_ in pieces))+4
    width = math.ceil(sum(p[3] for p in pieces[:-1])+pieces[-1][0].width/SCALE-pieces[-1][2])+8
    result = np.full((height*SCALE, width*SCALE), 255, dtype='uint8')
    x = 4.
    for index,(im, baseline, bearing, advance) in enumerate(pieces):
        px, py = round((x-bearing)*SCALE), round((base-baseline)*SCALE)
        if text[index] == '%':
            entry = next(v for v in variants if v['index'] == index)
            im, checked = fit_percent_to_canvas(bank, im, entry, (width*SCALE, height*SCALE), (px, py), seed, occurrence)
            entry.update(checked)
        area = result[py:py+im.height, px:px+im.width]
        if area.shape != (im.height, im.width):
            raise ValueError('Symbol would exceed its word canvas.')
        np.minimum(area, np.asarray(im), out=area)
        x += advance
    return Image.fromarray(result), {'baseline': base*SCALE, 'em_height': 32*SCALE, 'raster_scale': SCALE,
        'renderer': 'sample-digits-with-bounded-variation' if vary_digits else 'captured-digits-with-symbol-variation', 'references': references,
        'digit_variants': digit_variants, 'digit_gaps_px': digit_gaps,
        'symbol_variants': variants, 'symbol_variation_limit': 'Bounded procedural variation; not learned stroke dynamics.'}

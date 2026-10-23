"""Sample-matched structural strokes with smooth, repeatable pen variation.

These paths describe mathematical structure, not a learned unseen character.
Captured delimiters retain their sampled centreline; absent delimiters use an
explicit supplemental vocabulary. Stroke width never scales with a tall fence.
"""
import hashlib
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .reference_renderer import _image

VERSION = 'sample-matched-math-strokes-1'
FENCES = frozenset('()[]{}|/\\⟨⟩‖')


def estimate_style(bank, scale=3):
    widths, shades, slants, references = [], [], [], []
    for char in '1lIntxen+-=':
        record = bank.get('glyphs', {}).get(char)
        if record is None:
            continue
        pixels = np.asarray(_image(bank, record))
        mask = (pixels < 170).astype('uint8')
        yy, xx = np.where(mask)
        if not len(xx):
            continue
        contours, _ = cv2.findContours(np.pad(mask, 1), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        length = sum(cv2.arcLength(contour, True) for contour in contours) / 2
        if length > 3:
            widths.append(float(mask.sum()) / length)
        shades.append(float(np.median(pixels[pixels < 170])))
        references.append(record.get('sha256', ''))
        if char in '1lI' and np.ptp(yy) > 5:
            slants.append(-float(np.cov(xx, yy, ddof=0)[0, 1]) / max(1, float(np.var(yy))))
    return {
        'stroke_px': float(np.clip(np.median(widths) if widths else 1.3, .9, 2.2)) * scale,
        'shade': int(np.clip(np.median(shades) if shades else 30, 0, 100)),
        'slant': float(np.clip(np.median(slants) if slants else .06, -.12, .20)),
        'em_height': 32 * scale,
        'style_references': sorted(set(filter(None, references))),
    }


def _variation(seed, occurrence, name):
    digest = hashlib.sha256(f'{VERSION}:{seed}:{occurrence}:{name}'.encode()).digest()
    return [(int.from_bytes(digest[i:i + 2], 'little') / 65535) * 2 - 1 for i in range(0, 16, 2)]


def _curve(start, control1, control2, end, count=30):
    return [tuple((1-t)**3 * start[k] + 3*(1-t)**2*t * control1[k]
                  + 3*(1-t)*t*t * control2[k] + t**3 * end[k] for k in (0, 1))
            for t in np.linspace(0, 1, count)]


def _paint(size, paths, style, variation):
    """Vary pressure over whole gestures, rather than perturbing individual dots."""
    aa = 4
    image = Image.new('L', (size[0] * aa, size[1] * aa), 255)
    draw = ImageDraw.Draw(image)
    stroke = style['stroke_px'] * (1 + .035 * variation[4])
    shade = int(np.clip(style['shade'] + 4 * variation[6], 0, 110))
    for path in paths:
        lengths = np.r_[0., np.cumsum([math.dist(a, b) for a, b in zip(path, path[1:])])]
        for index, point in enumerate(path):
            t = lengths[index] / max(1, lengths[-1])
            pressure = .96 + .055 * math.sin(math.pi * t + variation[5] * .5)
            radius = stroke * pressure * aa / 2
            x, y = point[0] * aa, point[1] * aa
            if index:
                previous = path[index - 1]
                draw.line((previous[0]*aa, previous[1]*aa, x, y), fill=shade,
                          width=max(1, round(radius*2)))
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=shade)
    return image.resize(size, Image.Resampling.LANCZOS)


def _thin(mask):
    """Zhang-Suen centreline, retaining the captured gesture's branch topology."""
    ink = np.pad(mask.astype('uint8'), 1)
    for _ in range(max(ink.shape)):
        changed = False
        for stage in (0, 1):
            p2, p3 = ink[:-2, 1:-1], ink[:-2, 2:]
            p4, p5 = ink[1:-1, 2:], ink[2:, 2:]
            p6, p7 = ink[2:, 1:-1], ink[2:, :-2]
            p8, p9 = ink[1:-1, :-2], ink[:-2, :-2]
            ring = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            neighbors = sum(ring[:8])
            transitions = sum((a == 0) & (b == 1) for a, b in zip(ring, ring[1:]))
            first = p2*p4*p6 if stage == 0 else p2*p4*p8
            second = p4*p6*p8 if stage == 0 else p2*p6*p8
            remove = (ink[1:-1, 1:-1] != 0) & (neighbors >= 2) & (neighbors <= 6) & (transitions == 1) & (first == 0) & (second == 0)
            if np.any(remove):
                ink[1:-1, 1:-1][remove] = 0
                changed = True
        if not changed:
            break
    return ink[1:-1, 1:-1]


def _captured_paths(source):
    mask = _thin(np.asarray(source) < 170)
    points = {(int(x), int(y)) for y, x in np.argwhere(mask)}
    adjacency = {point: sorted((point[0]+dx, point[1]+dy) for dx in (-1, 0, 1)
                              for dy in (-1, 0, 1) if (dx or dy) and (point[0]+dx, point[1]+dy) in points)
                 for point in points}
    used, paths = set(), []
    for start in sorted(points, key=lambda point: (len(adjacency[point]) == 2, point[1], point[0])):
        for neighbor in adjacency[start]:
            edge = frozenset((start, neighbor))
            if edge in used:
                continue
            path = [start, neighbor]
            used.add(edge)
            while len(adjacency[path[-1]]) == 2:
                following = next(point for point in adjacency[path[-1]] if point != path[-2])
                edge = frozenset((path[-1], following))
                if edge in used:
                    break
                used.add(edge)
                path.append(following)
            paths.append(path)
    if not paths:
        raise ValueError('Captured mathematical delimiter has no usable stroke.')
    return paths


def draw_fence(char, height, style, seed=42, occurrence=0, source=None):
    """Draw a complete fence at its final height with a sample-sized pen.

    ``source`` is the reviewed outline at the renderer's working resolution.
    Its centreline, including asymmetric hooks, takes priority over generic paths.
    """
    if char not in FENCES or height < 8:
        raise ValueError('Unsupported mathematical fence or height.')
    v = _variation(seed, occurrence, char)
    stroke, em = style['stroke_px'], style['em_height']
    pad = max(6, math.ceil(stroke*.7 + 4))
    height = int(height)
    body_height = height
    if source is not None:
        captured = _captured_paths(source)
        xx = [point[0] for path in captured for point in path]
        yy = [point[1] for path in captured for point in path]
        x0, x1, y0, y1 = min(xx), max(xx), min(yy), max(yy)
        width = max(stroke*1.5, (x1-x0) * np.clip(math.sqrt(body_height/max(1, y1-y0)), .75, 1.45))
        normalized = [[((x-x0)/max(1, x1-x0), (y-y0)/max(1, y1-y0)) for x, y in path] for path in captured]
        method = 'reviewed-delimiter-centreline'
    else:
        width = min(.34*em, max(.14*em, body_height*.15))
        if char in '()':
            normalized = [_curve((.88, 0), (.12, .12), (-.02, .38), (.10, .54))
                          + _curve((.10, .54), (.13, .76), (.48, .97), (.94, 1))[1:]]
        elif char in '[]':
            normalized = [[(.96, .015), (.15, 0), (.10, .965), (1, 1)]]
        elif char in '{}':
            normalized = [_curve((.96, 0), (.20, -.01), (.24, .06), (.27, .19))
                          + _curve((.27, .19), (.32, .33), (.33, .40), (.02, .49))[1:]
                          + _curve((.02, .49), (.33, .53), (.34, .58), (.28, .72))[1:]
                          + _curve((.28, .72), (.17, .93), (.21, 1.01), (.97, 1))[1:]]
        elif char in '|‖':
            width = stroke
            normalized = [[(.5, 0), (.43, 1)]] if char == '|' else [[(0,0),(-.07,1)],[(3,0),(2.93,1)]]
        elif char in '⟨⟩':
            normalized = [[(.95,0),(.05,.50),(.98,1)]]
        else:
            normalized = [[(1, 0), (0, 1)]] if char == '/' else [[(0, 0), (1, 1)]]
        if char in ')]}⟩':
            normalized = [[(1-x, y) for x, y in path] for path in normalized]
        method = 'supplemental-fence-path'
    # Only gesture-level bow and lean vary. The sampled author's pen stays fixed.
    lean = style['slant'] * min(body_height, em) * .22 + v[0] * .65
    paths = [[(x*width*(1+.025*v[1]) + lean*(.5-y) + v[2]*.65*math.sin(math.pi*y),
               y*body_height) for x, y in path] for path in normalized]
    min_x = min(x for path in paths for x, _ in path)
    max_x = max(x for path in paths for x, _ in path)
    paths = [[(x-min_x+pad, y+pad) for x, y in path] for path in paths]
    size = (max(7, math.ceil(max_x-min_x) + pad*2 + 1), height+pad*2+1)
    image = _paint(size, paths, style, v)
    return image, {'method':method, 'stroke_px':stroke, 'top_padding_px':pad,
                   'variation_id':hashlib.sha256(str(v).encode()).hexdigest()[:16]}


def draw_radical(body_size, index_size, style, seed=42, occurrence=0):
    """A continuous hook and overbar, with separate safe space for root indices."""
    bw, bh = body_size
    iw, ih = index_size or (0, 0)
    v = _variation(seed, occurrence, 'radical')
    stroke, em = style['stroke_px'], style['em_height']
    pad = max(4, math.ceil(stroke + 2))
    hook = max(22, round(em*.30))
    clearance = max(7, math.ceil(stroke*1.45))
    index_gap = max(4, math.ceil(stroke))
    # The index sits strictly to the left of the ascending stroke, including
    # unusually wide or tall explicit indices; it can never be overpainted.
    root_x = pad + iw + index_gap if iw else pad
    bar_y = pad + ih*.42 + abs(v[0])*1.2
    body_x = math.ceil(root_x + hook + clearance)
    body_y = math.ceil(bar_y + clearance + stroke*.7)
    bottom = max(body_y + bh, pad + ih) + pad
    top = (root_x+hook, bar_y)
    start = (root_x+1, body_y+bh*.46)
    shoulder = (root_x+hook*.24, body_y+bh*.36)
    toe = (root_x+hook*.56, body_y+bh-stroke*.5)
    rising = _curve(toe, (root_x+hook*.71, body_y+bh*.64),
                    (root_x+hook*.85, bar_y+bh*.05), top, 20)
    end_x = body_x + bw + pad*.2
    # Keep the whole gently bowed overbar above the explicit content clearance.
    bar_end = (end_x, bar_y + v[1]*.85)
    bar = _curve(top, (top[0]+(end_x-top[0])*.32, bar_y+.6*v[2]),
                 (top[0]+(end_x-top[0])*.72, bar_y+.8*v[3]), bar_end, 35)
    paths = [[start, shoulder, toe] + rising[1:] + bar[1:]]
    size = (math.ceil(end_x+pad), math.ceil(bottom))
    image = _paint(size, paths, style, v)
    return image, (body_x, body_y), (pad, pad) if iw else None, {
        'method':'continuous-radical-gesture', 'stroke_px':stroke,
        'content_clearance_px':clearance,
        'variation_id':hashlib.sha256(str(v).encode()).hexdigest()[:16],
    }

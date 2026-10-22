"""Personal glyph sampling, extraction, review and SVG/PDF rendering.

All content is rendered from an explicitly reviewed, local user glyph library.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import random
import statistics
import string
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pypdfium2 as pdfium
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

SPEC = importlib.util.spec_from_file_location('personal_profile', Path(__file__).with_name('profile.py'))
profiles = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profiles)
A4 = (595.2756, 841.8898)
DEFAULT_CHARS = string.ascii_uppercase + string.ascii_lowercase + string.digits + '.,:;!?\'"+-=×÷%()[]/<>¥$πΔ'
MAX_IMAGE_PIXELS = 60_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    profiles.write_json(path, data)


def safe_child(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Stored path escapes its profile.')
    return path


def font_path(explicit=None):
    candidates = [explicit] if explicit else [
        'C:/Windows/Fonts/arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/Library/Fonts/Arial.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf']
    for path in candidates:
        if path and Path(path).is_file():
            return str(Path(path).resolve())
    raise ValueError('A Unicode label font is required; pass --label-font /path/font.ttf.')


def make_template(output, manifest=None, characters=DEFAULT_CHARS, variants=3, label_font=None):
    if type(variants) is not int or not 1 <= variants <= 5:
        raise ValueError('variants must be 1-5.')
    chars = list(dict.fromkeys(characters))
    if not chars or len(chars) > 4096 or any(ch.isspace() or ord(ch) < 32 for ch in chars):
        raise ValueError('Use 1-4096 non-whitespace printable characters.')
    pdfmetrics.registerFont(TTFont('SampleLabels', font_path(label_font)))
    face = pdfmetrics.getFont('SampleLabels').face
    missing = [ch for ch in chars if ord(ch) not in face.charWidths]
    if missing:
        raise ValueError('Label font does not cover: ' + ''.join(missing))
    output = Path(output).resolve()
    manifest = Path(manifest).resolve() if manifest else output.with_suffix('.json')
    if output == manifest:
        raise ValueError('PDF and manifest paths must differ.')
    if output.exists() or manifest.exists():
        raise ValueError('Template outputs already exist; use a new destination.')
    identifier = hashlib.sha256(json.dumps({'chars': chars, 'variants': variants, 'version': 1}, ensure_ascii=False).encode()).hexdigest()[:16]
    width, height = A4
    marks = [[24, 24], [width - 24, 24], [width - 24, height - 24], [24, height - 24]]
    pages = []
    for index, start in enumerate(range(0, len(chars), 32)):
        tag = (int(identifier[:4], 16) << 8) | (index + 1)
        cells = []
        for j, ch in enumerate(chars[start:start + 32]):
            col, row = j % 4, j // 4
            x, y = 43 + col * 127.3, 133 + row * 78
            slot_w = 117.3 / variants
            for v in range(variants):
                cells.append({'char': ch, 'variant': v,
                              'box': [x + 4 + v * slot_w, y + 19, slot_w - 4, 53],
                              'baseline': y + 59})
        pages.append({'page': index + 1, 'tag': tag, 'cells': cells})
    metadata = {'schema_version': 1, 'id': identifier, 'page_size_pt': list(A4),
                'markers': marks, 'tag_box': [208, 21, 3, 8], 'variants': variants,
                'characters': ''.join(chars), 'pages': pages}
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(suffix='.pdf', dir=output.parent)
    os.close(fd)
    try:
        c = canvas.Canvas(temp, pagesize=A4)
        c.setTitle('Inkself glyph sampling sheet')
        for page in pages:
            c.setFont('SampleLabels', 14)
            c.drawString(43, height - 63, 'Inkself glyph samples')
            c.setFont('SampleLabels', 8)
            for k, text in enumerate([
                f"Sheet {page['page']} / {len(pages)}    Template {identifier}",
                'Write the labelled character ONCE in EACH slot. Keep the page markers visible.',
                'Use your normal handwriting. Rest letters on the pale baseline; do not trace labels.',
                'Scan or photograph a full page. Blank or unclear slots will not be accepted.']):
                c.drawString(43, height - 81 - k * 11, text)
            for k, (mx, my) in enumerate(marks):
                c.setFillColorRGB(0, 0, 0)
                c.rect(mx - 7, height - my - 7, 14, 14, stroke=0, fill=1)
                hole = 8 if k == 0 else 4
                c.setFillColorRGB(1, 1, 1)
                c.rect(mx - hole / 2, height - my - hole / 2, hole, hole, stroke=0, fill=1)
            tx, ty, tw, th = metadata['tag_box']
            c.setFillColorRGB(0, 0, 0)
            for bit in range(24):
                if page['tag'] & (1 << (23 - bit)):
                    c.rect(tx + bit * tw, height - ty - th, tw, th, stroke=0, fill=1)
            for j, ch in enumerate(chars[(page['page'] - 1) * 32:page['page'] * 32]):
                x, y = 43 + (j % 4) * 127.3, 133 + (j // 4) * 78
                c.setFillColorRGB(0, 0, 0)
                c.setFont('SampleLabels', 9)
                c.drawString(x + 3, height - y - 12, f'{ch}   U+{ord(ch):04X}')
            c.setLineWidth(.35)
            for cell in page['cells']:
                x, y, w, h = cell['box']
                c.setStrokeColorRGB(.82, .82, .82)
                c.rect(x, height - y - h, w, h, stroke=1, fill=0)
                c.setStrokeColorRGB(.88, .88, .88)
                c.line(x + 2, height - cell['baseline'], x + w - 2, height - cell['baseline'])
            c.showPage()
        c.save()
        os.replace(temp, output)
        atomic_json(manifest, metadata)
    finally:
        if Path(temp).exists(): Path(temp).unlink()
    return {'pdf': str(output), 'manifest': str(manifest), 'pages': len(pages), 'template_id': identifier}


def image_pages(paths, dpi):
    for source in paths:
        source = Path(source).resolve(strict=True)
        if source.suffix.lower() == '.pdf':
            document = pdfium.PdfDocument(str(source))
            try:
                for index in range(len(document)):
                    page = document[index]
                    try:
                        image = page.render(scale=dpi / 72).to_pil().convert('RGB')
                        if image.width * image.height > MAX_IMAGE_PIXELS:
                            raise ValueError('PDF page is too large.')
                        yield source, index + 1, image
                    finally: page.close()
            finally: document.close()
        else:
            with Image.open(source) as image:
                image = image.convert('RGB')
                image.load()
                yield source, 1, image


def locate_markers(gray):
    if min(gray.shape) < 450:
        raise ValueError('Sample image is too small; scan at 150 DPI or higher.')
    threshold = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY_INV, 35, 15)
    contours, hierarchy = cv2.findContours(threshold, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None: raise ValueError('No page markers found.')
    height, width = gray.shape
    found = []
    for i, contour in enumerate(contours):
        child = hierarchy[0][i][2]
        area = cv2.contourArea(contour)
        if child < 0 or area < 45 or area > width * height * .01:
            continue
        polygon = cv2.approxPolyDP(contour, .02 * cv2.arcLength(contour, True), True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if not .7 < w / max(h, 1) < 1.4 or area / (w * h) < .65:
            continue
        cx, cy = x + w / 2, y + h / 2
        if not ((cx < width * .24 or cx > width * .76) and (cy < height * .24 or cy > height * .76)):
            continue
        hole = cv2.contourArea(contours[child]) / area
        if .04 < hole < .65:
            found.append({'center': [cx, cy], 'area': area, 'hole': hole})
    # Keep the largest ring in each physical corner, rejecting handwriting contours.
    corners = []
    for right, bottom in [(False, False), (True, False), (True, True), (False, True)]:
        candidates = [x for x in found if (x['center'][0] > width / 2) == right and (x['center'][1] > height / 2) == bottom]
        if not candidates:
            raise ValueError('All four page markers must be visible; no guessed alignment was applied.')
        corners.append(max(candidates, key=lambda x: x['area']))
    anchor = max(range(4), key=lambda i: corners[i]['hole'])
    if corners[anchor]['hole'] < .22:
        raise ValueError('Orientation marker is unclear.')
    return np.float32([corners[(anchor + i) % 4]['center'] for i in range(4)])


def align_page(image, manifest, dpi):
    rgb = np.array(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    source = locate_markers(gray)
    scale = dpi / 72
    destination = np.float32(manifest['markers']) * scale
    transform = cv2.getPerspectiveTransform(source, destination)
    size = tuple(round(x * scale) for x in manifest['page_size_pt'])
    aligned = cv2.warpPerspective(rgb, transform, size, flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    gray = cv2.cvtColor(aligned, cv2.COLOR_RGB2GRAY)
    paper = cv2.GaussianBlur(gray, (0, 0), 25 * dpi / 200)
    normal = cv2.divide(gray, np.maximum(paper, 1), scale=255)
    tx, ty, tw, th = manifest['tag_box']
    tag = 0
    for bit in range(24):
        x = round((tx + (bit + .5) * tw) * scale)
        y = round((ty + th / 2) * scale)
        value = np.median(normal[max(0, y-1):y+2, max(0, x-1):x+2])
        tag = (tag << 1) | int(value < 170)
    return normal, tag


def validate_manifest(manifest):
    if manifest.get('schema_version') != 1 or not isinstance(manifest.get('pages'), list):
        raise ValueError('Unsupported sampling manifest.')
    if len(manifest['pages']) < 1 or len(manifest['pages']) > 128:
        raise ValueError('Invalid manifest page count.')
    if manifest.get('page_size_pt') != list(A4):
        raise ValueError('Unsupported sample page size.')
    if len(manifest.get('markers', [])) != 4:
        raise ValueError('Manifest must contain four markers.')
    width, height = A4
    for page in manifest['pages']:
        if not isinstance(page.get('tag'), int) or not 0 <= page['tag'] < 2**24:
            raise ValueError('Invalid page tag.')
        for cell in page.get('cells', []):
            x, y, w, h = cell['box']
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in [x, y, w, h, cell['baseline']]):
                raise ValueError('Invalid cell coordinates.')
            if not (0 <= x < x + w <= width and 0 <= y < y + h <= height):
                raise ValueError('Sample cell lies outside the page.')
            if len(cell['char']) != 1 or cell['char'].isspace():
                raise ValueError('Invalid cell character.')


def extract(store, identifier, manifest_path, sources, dpi=200):
    if not 120 <= dpi <= 400: raise ValueError('dpi must be 120-400.')
    manifest = read_json(manifest_path)
    validate_manifest(manifest)
    dest, profile = profiles.load(store, identifier)
    images = []
    total_pixels = 0
    for entry in image_pages(sources, dpi):
        total_pixels += entry[2].width * entry[2].height
        if total_pixels > 90_000_000 or len(images) >= 128:
            raise ValueError('Sampling batch exceeds the image-memory limit; use lower DPI or a smaller template.')
        images.append(entry)
    if len(images) != len(manifest['pages']):
        raise ValueError(f"Expected {len(manifest['pages'])} sample pages, received {len(images)}.")
    library_id = uuid.uuid4().hex
    folder = safe_child(dest, 'libraries/' + library_id)
    folder.mkdir(parents=True, exist_ok=False)
    glyphs, rejected, source_records = {}, [], []
    seen = set()
    scale = dpi / 72


    for source, source_page, image in images:
        normal, tag = align_page(image, manifest, dpi)
        expected = next((p for p in manifest['pages'] if p['tag'] == tag), None)
        if expected is None or tag in seen:
            raise ValueError('Wrong template, duplicate page, or unreadable page tag; extraction was not activated.')
        seen.add(tag)
        source_hash = profiles.digest(source)
        source_records.append({'sha256': source_hash, 'filename': source.name,
                               'source_page': source_page, 'template_page': expected['page']})
        Image.fromarray(normal).save(folder / f"aligned-{expected['page']:03}.png")
        for cell in expected['cells']:
            x, y, w, h = cell['box']
            pad = 2.0
            x0, y0 = round((x + pad) * scale), round((y + pad) * scale)
            x1, y1 = round((x + w - pad) * scale), round((y + h - pad) * scale)
            patch = normal[y0:y1, x0:x1]
            mask = (patch < 170).astype(np.uint8)
            count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
            keep = np.zeros_like(mask)
            for label in range(1, count):
                if stats[label, cv2.CC_STAT_AREA] >= max(2, round(dpi / 100)):
                    keep[labels == label] = 1
            ys, xs = np.where(keep > 0)
            reason = None
            minimum = 12 if cell['char'].isalnum() else 3
            if len(xs) < minimum: reason = 'blank-or-too-little-ink'
            elif min(xs) < 1 or max(xs) >= patch.shape[1] - 2 or min(ys) < 1 or max(ys) >= patch.shape[0] - 2:
                reason = 'touches-slot-boundary'
            if reason:
                rejected.append({'char': cell['char'], 'variant': cell['variant'],
                                 'page': expected['page'], 'reason': reason})
                continue
            left, right = max(0, min(xs) - 2), min(patch.shape[1], max(xs) + 3)
            top, bottom = max(0, min(ys) - 2), min(patch.shape[0], max(ys) + 3)
            left, right, top, bottom = map(int, (left, right, top, bottom))
            alpha = np.clip((255 - patch[top:bottom, left:right].astype(np.float32)) * 1.15, 0, 255)
            alpha *= keep[top:bottom, left:right]
            rgba = np.zeros((*alpha.shape, 4), np.uint8)
            rgba[:, :, 3] = alpha.astype(np.uint8)
            filename = f"u{ord(cell['char']):06x}-v{cell['variant']}.png"
            Image.fromarray(rgba).save(folder / filename)
            record = {'file': filename, 'sha256': profiles.digest(folder / filename),
                      'variant': cell['variant'], 'width_pt': (right - left) / scale,
                      'height_pt': (bottom - top) / scale,
                      'descent_pt': (y0 + bottom) / scale - cell['baseline'],
                      'ascent_pt': cell['baseline'] - (y0 + top) / scale,
                      'source_sha256': source_hash, 'page': expected['page'],
                      'source_box_aligned_px': [x0 + left, y0 + top, right - left, bottom - top]}
            glyphs.setdefault(cell['char'], []).append(record)
    heights = [max(1, g['ascent_pt']) for char, variants in glyphs.items() if char.isalnum() for g in variants]
    if not heights:
        heights = [g['height_pt'] for variants in glyphs.values() for g in variants]
    if not heights:
        raise ValueError('No usable ink was found. Fill in the sampling sheet first.')
    reference = statistics.median(heights)
    for variants in glyphs.values():
        for glyph in variants:
            glyph['advance_pt'] = glyph['width_pt'] + reference * .13
    library = {'schema_version': 1, 'id': library_id, 'status': 'draft', 'created_at': profiles.now(),
               'template_id': manifest['id'], 'template_sha256': profiles.digest(manifest_path),
               'reference_height_pt': reference, 'glyphs': glyphs, 'sources': source_records,
               'rejected_slots': rejected, 'missing': [c for c in manifest['characters'] if c not in glyphs],
               'semantic_validation': 'Label mapping requires visual review; no OCR-based identity claim.'}
    atomic_json(folder / 'library.json', library)
    make_contact(folder, library)
    for source in dict.fromkeys(str(x[0]) for x in images):
        profiles.add_sample(store, identifier, source, 'labeled-sheet')
    dest, profile = profiles.load(store, identifier)
    profile['draft_library'] = library_id
    profile['updated_at'] = profiles.now()
    profiles.write_json(dest / 'profile.json', profile)
    return {'status': 'draft', 'library_id': library_id, 'glyphs': len(glyphs),
            'variants': sum(map(len, glyphs.values())), 'missing': library['missing'],
            'rejected_slots': rejected, 'contact_sheet': str(folder / 'contact.png'),
            'library': str(folder / 'library.json')}


def make_contact(folder, library):
    entries = [(char, glyph) for char, variants in library['glyphs'].items() for glyph in variants]
    columns, tile_w, tile_h = 8, 150, 125
    rows = math.ceil(len(entries) / columns)
    # Split very large libraries into reasonably sized contact pages.
    font = ImageFont.truetype(font_path(), 13)
    contacts = []
    for start in range(0, len(entries), columns * 12):
        batch = entries[start:start + columns * 12]
        image = Image.new('RGB', (columns * tile_w, math.ceil(len(batch) / columns) * tile_h), 'white')
        draw = ImageDraw.Draw(image)
        for i, (char, glyph) in enumerate(batch):
            x, y = i % columns * tile_w, i // columns * tile_h
            draw.text((x + 5, y + 5), f"{char} U+{ord(char):04X} v{glyph['variant'] + 1}", font=font, fill='black')
            with Image.open(folder / glyph['file']) as ink:
                ink = ink.convert('RGBA')
                ink.thumbnail((tile_w - 16, tile_h - 35))
                image.paste(ink, (x + 8, y + 30), ink)
            draw.rectangle((x, y, x + tile_w - 1, y + tile_h - 1), outline='#cccccc')
        name = 'contact.png' if start == 0 else f'contact-{start // (columns * 12) + 1}.png'
        image.save(folder / name)
        contacts.append(name)
    return contacts


def load_library(store, identifier, draft=False):
    dest, profile = profiles.load(store, identifier)
    key = 'draft_library' if draft else 'active_library'
    library_id = profile.get(key)
    if not library_id or not isinstance(library_id, str) or not re_full_id(library_id):
        raise ValueError('No draft library.' if draft else 'No reviewed library. Extract and visually review a sample first.')
    folder = safe_child(dest, 'libraries/' + library_id)
    library = read_json(folder / 'library.json')
    if library.get('id') != library_id or library.get('schema_version') != 1:
        raise ValueError('Inconsistent glyph library.')
    if not draft and library.get('status') != 'reviewed':
        raise ValueError('The active library has not passed visual review.')
    return dest, profile, folder, library


def re_full_id(value):
    return len(value) == 32 and all(ch in '0123456789abcdef' for ch in value)


def review(store, identifier, accept=False):
    dest, profile, folder, library = load_library(store, identifier, draft=True)
    if not accept:
        return {'status': library['status'], 'library': str(folder / 'library.json'),
                'contact_sheets': [str(p) for p in sorted(folder.glob('contact*.png'))],
                'missing': library['missing'], 'rejected_slots': library['rejected_slots'],
                'next': 'Inspect ALL contact sheets and original sample labels; then review --accept.'}
    library['status'] = 'reviewed'
    library['reviewed_at'] = profiles.now()
    library['review_basis'] = 'Caller attested visual inspection of glyph identities and legibility.'
    atomic_json(folder / 'library.json', library)
    profile['active_library'] = library['id']
    profile['status'] = 'glyph-ready'
    profile['updated_at'] = profiles.now()
    profiles.write_json(dest / 'profile.json', profile)
    return {'status': 'glyph-ready', 'library_id': library['id'], 'glyphs': len(library['glyphs']),
            'missing': library['missing']}


def read_document(path):
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError('Document exceeds the 2 MB input limit.')
    if path.suffix.lower() == '.json':
        document = read_json(path)
        if not isinstance(document, dict): raise ValueError('Document must be a JSON object.')
        blocks = document.get('blocks', [{'type': 'paragraph', 'runs': document.get('runs', [])}])
    else:
        blocks = [{'type': 'paragraph', 'text': path.read_text(encoding='utf-8-sig')}]
    if not isinstance(blocks, list) or len(blocks) > 10000:
        raise ValueError('Invalid document blocks.')
    normalized = []
    for block in blocks:
        if not isinstance(block, dict) or block.get('type', 'paragraph') not in ('paragraph', 'heading'):
            raise ValueError('Supported block types: paragraph and heading.')
        source_runs = block.get('runs', [{'text': block.get('text', '')}])
        if not isinstance(source_runs, list): raise ValueError('runs must be an array.')
        runs = []
        for run in source_runs:
            if not isinstance(run, dict) or not isinstance(run.get('text'), str):
                raise ValueError('Each run requires a string text.')
            if any(key not in ('text', 'subscript', 'superscript') for key in run):
                raise ValueError('Unknown run field.')
            for key in ('subscript', 'superscript'):
                if key in run and type(run[key]) is not bool: raise ValueError(key + ' must be boolean.')
            if run.get('subscript') and run.get('superscript'):
                raise ValueError('A run cannot be both subscript and superscript.')
            text = run['text'].replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ')
            if any(ord(ch) < 32 and ch != '\n' for ch in text):
                raise ValueError('Unsupported control characters in text.')
            runs.append({'text': text, 'subscript': run.get('subscript', False),
                         'superscript': run.get('superscript', False)})
        normalized.append({'type': block.get('type', 'paragraph'), 'runs': runs})
    total = sum(len(r['text']) for b in normalized for r in b['runs'])
    if total > 120000: raise ValueError('Document exceeds 120,000 characters.')
    if not any(r['text'].strip() for b in normalized for r in b['runs']):
        raise ValueError('Document is empty.')
    return normalized


def coverage(store, identifier, input_path, draft=False):
    _, _, _, library = load_library(store, identifier, draft=draft)
    blocks = read_document(input_path)
    text = ''.join(r['text'] for b in blocks for r in b['runs'])
    needed = sorted(set(text) - {' ', '\n'})
    missing = [ch for ch in needed if ch not in library['glyphs']]
    return {'status': 'missing-glyphs' if missing else 'covered', 'library_id': library['id'],
            'library_status': library['status'], 'required': len(needed), 'missing': missing,
            'missing_codepoints': [f'U+{ord(ch):04X}' for ch in missing],
            'content_sha256': hashlib.sha256(text.encode()).hexdigest()}


def glyph_image(folder, glyph, ink):
    path = safe_child(folder, glyph['file'])
    if profiles.digest(path) != glyph['sha256']:
        raise ValueError('Glyph file changed after extraction: ' + glyph['file'])
    with Image.open(path) as source:
        source = source.convert('RGBA')
        if source.getchannel('A').getbbox() is None:
            raise ValueError('Glyph has no visible ink: ' + glyph['file'])
        output = Image.new('RGBA', source.size, ink)
        output.putalpha(source.getchannel('A'))
        return output


def plan_layout(blocks, library, preferences):
    rng = random.Random(preferences['seed'])
    width, height = A4
    margin = 43.0
    y = height - 58
    page = 1
    items = []
    text_index = 0
    for block in blocks:
        size = preferences['font_size_pt'] * (1.22 if block['type'] == 'heading' else 1)
        glyph_runs = []
        for run in block['runs']:
            small = run['subscript'] or run['superscript']
            run_size = size * (.72 if small else 1)
            shift = -size * .24 if run['subscript'] else size * .38 if run['superscript'] else 0
            for char in run['text']:
                if char in (' ', '\n'):
                    glyph_runs.append({'char': char, 'advance': size * .40, 'index': text_index})
                else:
                    variants = library['glyphs'][char]
                    glyph = rng.choice(variants) if rng.random() < preferences['glyph_variation'] else variants[0]
                    factor = run_size * .75 / library['reference_height_pt']
                    advance = glyph['advance_pt'] * factor
                    advance *= rng.uniform(1 - preferences['spacing_variation'], 1 + preferences['spacing_variation'])
                    advance = max(advance, (glyph['width_pt'] + abs(math.tan(math.radians(preferences['slant_deg']))) * glyph['height_pt']) * factor + .1)
                    glyph_runs.append({'char': char, 'glyph': glyph, 'scale': factor,
                                       'shift': shift, 'advance': advance, 'index': text_index})
                text_index += 1
        # Wrap at spaces when possible; oversized individual tokens wrap at characters.
        lines, line, advance = [], [], 0.0
        for item in glyph_runs:
            if item['char'] == '\n':
                lines.append(line); line = []; advance = 0; continue
            if line and advance + item['advance'] > width - 2 * margin:
                last_space = next((i for i in range(len(line)-1, -1, -1) if line[i]['char'] == ' '), None)
                if last_space is not None:
                    lines.append(line[:last_space]); line = line[last_space + 1:]
                    advance = sum(i['advance'] for i in line)
                else:
                    lines.append(line); line = []; advance = 0
            if advance + item['advance'] > width - 2 * margin:
                if line: lines.append(line); line = []; advance = 0
                if item['advance'] > width - 2 * margin:
                    raise ValueError('An individual glyph is wider than the printable page.')
            line.append(item); advance += item['advance']
        if line: lines.append(line)
        for line in lines:
            ascent = max([size * .8] + [(i['glyph']['height_pt'] - i['glyph']['descent_pt']) * i['scale'] + i['shift'] for i in line if 'glyph' in i])
            descent = max([size * .25] + [i['glyph']['descent_pt'] * i['scale'] - i['shift'] for i in line if 'glyph' in i])
            jitter = preferences['baseline_jitter_pt']
            if y - descent - jitter < margin:
                page += 1; y = height - margin - ascent - jitter
            if y + ascent + jitter > height - margin:
                y = height - margin - ascent - jitter
            x = margin
            baseline = y + rng.uniform(-jitter, jitter)
            shear = math.tan(math.radians(preferences['slant_deg']))
            for item in line:
                if 'glyph' in item:
                    glyph = item['glyph']; factor = item['scale']
                    w, h = glyph['width_pt'] * factor, glyph['height_pt'] * factor
                    bottom = baseline + item['shift'] - glyph['descent_pt'] * factor
                    shift_x = max(0, -shear * h)
                    left = x + shift_x
                    bbox = [min(left, left + shear*h), bottom,
                            max(left+w, left+w+shear*h), bottom+h]
                    if min(bbox[0], bbox[1]) < margin - .01 or bbox[2] > width - margin + .01 or bbox[3] > height - margin + .01:
                        raise ValueError('Requested size/slant creates an out-of-margin glyph; reduce size or slant.')
                    items.append({'char': item['char'], 'index': item['index'], 'page': page,
                                  'glyph': glyph, 'x': left, 'y': bottom, 'w': w, 'h': h,
                                  'shear': shear, 'bbox': bbox})
                x += item['advance']
            y -= max(size * preferences['line_spacing'], ascent + descent + 2 * jitter + 2)
        y -= size * .55
    return items, page


def render(store, identifier, input_path, output, svg_dir=None, seed=None, overrides=None, preview=False):
    _, profile, folder, library = load_library(store, identifier)
    blocks = read_document(input_path)
    result = coverage(store, identifier, input_path)
    if result['missing']:
        raise ValueError('Missing glyphs: ' + ', '.join(f'{c!r} U+{ord(c):04X}' for c in result['missing']))
    preferences = dict(profile['preferences'])
    if overrides: preferences.update(profiles.validate_preferences(overrides))
    if seed is not None: preferences.update(profiles.validate_preferences({'seed': seed}))
    if preferences['missing_glyph'] != 'error':
        raise ValueError('This renderer supports only faithful glyph rendering. Set missing_glyph to error.')
    items, pages = plan_layout(blocks, library, preferences)
    output = Path(output).resolve()
    if output.suffix.lower() != '.pdf': raise ValueError('Output must end in .pdf.')
    report_path = output.with_suffix('.report.json')
    svg_dir = Path(svg_dir).resolve() if svg_dir else output.with_name(output.stem + '_svg')
    if output.exists() or report_path.exists() or svg_dir.exists():
        raise ValueError('Output already exists; choose a new output path.')
    ink = preferences['ink_color']
    image_cache = {}
    for item in items:
        file = item['glyph']['file']
        if file not in image_cache:
            image = glyph_image(folder, item['glyph'], ink)
            data = io.BytesIO(); image.save(data, format='PNG')
            image_cache[file] = (ImageReader(image), data.getvalue())
    output.parent.mkdir(parents=True, exist_ok=True)
    svg_dir.mkdir(parents=True, exist_ok=False)
    c = canvas.Canvas(str(output), pagesize=A4, invariant=1, pageCompression=1)
    c.setTitle('Inkself glyph document')
    svg_files = []
    for page in range(1, pages + 1):
        svg = ET.Element('svg', {'xmlns': 'http://www.w3.org/2000/svg',
                                'width': f'{A4[0]}pt', 'height': f'{A4[1]}pt',
                                'viewBox': f'0 0 {A4[0]} {A4[1]}'})
        ET.SubElement(svg, 'title').text = 'Inkself glyph document'
        ET.SubElement(svg, 'rect', {'width': str(A4[0]), 'height': str(A4[1]), 'fill': 'white'})
        for item in (i for i in items if i['page'] == page):
            image, data = image_cache[item['glyph']['file']]
            x, y, w, h, sh = [item[k] for k in ('x', 'y', 'w', 'h', 'shear')]
            c.saveState(); c.transform(1, 0, sh, 1, x, y)
            c.drawImage(image, 0, 0, width=w, height=h, mask='auto'); c.restoreState()
            # SVG embeds the exact same image bytes used by PDF, without external references.
            top = A4[1] - y - h
            ET.SubElement(svg, 'image', {'width': str(w), 'height': str(h),
                           'transform': f'matrix(1 0 {-sh} 1 {x+sh*h} {top})',
                           'href': 'data:image/png;base64,' + base64.b64encode(data).decode(),
                           'data-codepoint': f'U+{ord(item["char"]):04X}',
                           'data-source-sha256': item['glyph']['source_sha256']})
        c.showPage()
        svg_path = svg_dir / f'page-{page:03}.svg'
        ET.ElementTree(svg).write(svg_path, encoding='utf-8', xml_declaration=True)
        svg_files.append(str(svg_path))
    c.save()
    trace = [{'char': i['char'], 'index': i['index'], 'page': i['page'], 'bbox': i['bbox'],
              'glyph_file': i['glyph']['file'], 'glyph_sha256': i['glyph']['sha256'],
              'source_sha256': i['glyph']['source_sha256']} for i in items]
    expected = ''.join(r['text'] for b in blocks for r in b['runs'])
    visible = ''.join(i['char'] for i in items)
    if visible != expected.replace(' ', '').replace('\n', ''):
        raise ValueError('Content-to-glyph mapping mismatch.')
    report = {'schema_version': 1, 'engine_version': '1.0.0', 'profile_id': identifier,
              'library_id': library['id'], 'library_status': library['status'],
              'preview': preview, 'preferences': preferences, 'pages': pages,
              'pdf': str(output), 'pdf_sha256': profiles.digest(output), 'svg': svg_files,
              'content_sha256': hashlib.sha256(expected.encode()).hexdigest(),
              'content': expected, 'glyph_count': len(items), 'glyph_trace': trace,
              'validation': {'content_mapping': True, 'layout_bounds': True,
                'visible_glyph_identity': 'Caller-reviewed source glyphs; not independently OCR-verified.',
                'personal_similarity': 'Requires evaluation against the sample owner\'s real handwriting.'}}
    atomic_json(report_path, report)
    return {'pdf': str(output), 'svg_dir': str(svg_dir), 'report': str(report_path),
            'pages': pages, 'glyph_count': len(items), 'preview': preview}


def validate_output(report_path, render_dir=None):
    report = read_json(report_path)
    if report.get('schema_version') != 1: raise ValueError('Unsupported output report.')
    pdf = Path(report['pdf']).resolve(strict=True)
    if profiles.digest(pdf) != report['pdf_sha256']:
        raise ValueError('PDF changed after generation.')
    expected = report['content'].replace(' ', '').replace('\n', '')
    if ''.join(i['char'] for i in report['glyph_trace']) != expected:
        raise ValueError('Glyph trace differs from the expected content.')
    if hashlib.sha256(report['content'].encode()).hexdigest() != report['content_sha256']:
        raise ValueError('Report content hash mismatch.')
    document = pdfium.PdfDocument(str(pdf))
    visible = []
    try:
        if len(document) != report['pages']: raise ValueError('PDF page count mismatch.')
        for i in range(len(document)):
            page = document[i]
            try:
                image = page.render(scale=2).to_pil().convert('RGB')
                gray = np.array(image).mean(axis=2)
                ink = int(np.count_nonzero(gray < 230))
                expected_glyphs = [g for g in report['glyph_trace'] if g['page'] == i+1]
                if expected_glyphs and ink < 5: raise ValueError(f'Page {i+1} contains no visible ink.')
                for g in expected_glyphs:
                    x0, y0, x1, y1 = g['bbox']
                    if not (0 <= x0 < x1 <= A4[0] and 0 <= y0 < y1 <= A4[1]):
                        raise ValueError('Glyph bounds leave the page.')
                    patch = gray[max(0, int((A4[1]-y1)*2)):min(gray.shape[0], math.ceil((A4[1]-y0)*2)),
                                 max(0, int(x0*2)):min(gray.shape[1], math.ceil(x1*2))]
                    if patch.size == 0 or not np.any(patch < 230):
                        raise ValueError(f'No visible ink for glyph {g["index"]} on page {i+1}.')
                if render_dir:
                    dest = Path(render_dir).resolve(); dest.mkdir(parents=True, exist_ok=True)
                    image.save(dest / f'page-{i+1:03}.png')
                visible.append({'page': i+1, 'ink_pixels': ink, 'glyphs': len(expected_glyphs)})
            finally: page.close()
    finally: document.close()
    return {'status': 'passed', 'checks': ['pdf-hash', 'content-to-glyph-trace', 'page-count',
            'page-bounds', 'visible-ink-per-glyph'], 'pages': visible,
            'limit': 'This validates mapping and visible ink, not handwriting similarity or user mislabelling.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', default='.local/profiles')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('template'); p.add_argument('--output', required=True)
    p.add_argument('--manifest'); p.add_argument('--characters', default=DEFAULT_CHARS)
    p.add_argument('--variants', type=int, default=3); p.add_argument('--label-font')
    p = sub.add_parser('extract'); p.add_argument('id'); p.add_argument('--manifest', required=True)
    p.add_argument('--pages', nargs='+', required=True); p.add_argument('--dpi', type=int, default=200)
    p = sub.add_parser('review'); p.add_argument('id'); p.add_argument('--accept', action='store_true')
    p = sub.add_parser('coverage'); p.add_argument('id'); p.add_argument('--input', required=True)
    p.add_argument('--draft', action='store_true')
    p = sub.add_parser('render'); p.add_argument('id'); p.add_argument('--input', required=True)
    p.add_argument('--output', required=True); p.add_argument('--svg-dir'); p.add_argument('--seed', type=int)
    p.add_argument('--preferences'); p.add_argument('--preview', action='store_true')
    p = sub.add_parser('validate'); p.add_argument('--report', required=True); p.add_argument('--render-dir')
    args = parser.parse_args(argv)
    try:
        if args.command == 'template':
            result = make_template(args.output, args.manifest, args.characters, args.variants, args.label_font)
        elif args.command == 'extract': result = extract(args.store, args.id, args.manifest, args.pages, args.dpi)
        elif args.command == 'review': result = review(args.store, args.id, args.accept)
        elif args.command == 'coverage': result = coverage(args.store, args.id, args.input, args.draft)
        elif args.command == 'render':
            result = render(args.store, args.id, args.input, args.output, args.svg_dir, args.seed,
                            read_json(args.preferences) if args.preferences else None, args.preview)
        else: result = validate_output(args.report, args.render_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 3 if result.get('status') == 'missing-glyphs' else 0
    except (ValueError, OSError, KeyError, TypeError, cv2.error) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

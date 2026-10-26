"""Line-first A4 layout with bounded page memory and inspectable placements.

Layout preserves generated item order. It does not validate handwriting, rendered
formula meaning, or textual correctness.
"""
from __future__ import annotations

import json
import hashlib
import math
import re
from pathlib import Path

from PIL import Image, ImageOps

VERSION = 'inkself-document-layout-3'


def _spacing_gaps(items, model, seed):
    from .runtime.word_spacing import sample_word_gaps, validate_word_spacing
    validate_word_spacing(model)
    ratios, group, paragraph = {}, [], 0

    def finish():
        nonlocal group, paragraph
        contexts = [{'left': items[group[pos-1]].get('text','') if pos else '',
                     'right': items[item_index].get('text','')} for pos,item_index in enumerate(group)]
        values = sample_word_gaps(model, len(group), seed=seed, paragraph=paragraph, contexts=contexts)
        ratios.update(zip(group, values))
        group = []
        paragraph += 1

    for index, item in enumerate(items):
        if item.get('newline') or item.get('display_math'):
            finish()
        else:
            group.append(index)
    finish()
    return ratios


def _number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Invalid layout ' + name + '.')
    if positive and value <= 0:
        raise ValueError('Invalid layout ' + name + '.')
    return float(value)


def plan_document(items, preferences, page_w=1240, page_h=1754, margin=90, word_spacing=None):
    """Plan from item dimensions without opening images or authoring a PDF.

    Every drawable item needs width/height; baseline/em_height are optional for
    legacy fixed-height words. Newline items carry no image. Display math is a
    centered, unbreakable line. Coordinates are final raster pixels.
    """
    size = _number(preferences['size'], 'size', True)
    spacing = _number(preferences['line_spacing'], 'line spacing', True)
    if not 0 <= margin < min(page_w, page_h) / 2:
        raise ValueError('Invalid page margins.')
    scale = page_w / 595.2756
    em = max(24, int(size * scale * 1.4))
    leading = max(em + 5, int(size * scale * spacing))
    word_gap = max(1, round(size * scale * .45))
    ratios = _spacing_gaps(items, word_spacing, preferences.get('seed', 42)) if word_spacing is not None else None
    available = page_w - 2 * margin
    capacity = page_h - 2 * margin
    nominal_ascent = round(em * 26 / 32)
    nominal_descent = em - nominal_ascent
    lines, pending, warnings = [], [], []
    paragraph = 0
    pending_width = 0
    display_break_pending = False

    def finish(explicit=False, display=False):
        nonlocal pending, pending_width
        if not pending:
            return
        from .runtime.baseline_rhythm import word_offsets
        offsets=word_offsets([p['width'] for p in pending],[p.get('gap_before',0) for p in pending],em,preferences.get('seed',42),len(lines)) if preferences.get('baseline_variation',True) and not display else [0]*len(pending)
        for piece,dy in zip(pending,offsets):piece['baseline_offset']=dy
        ascent = max(nominal_ascent, max(piece['baseline']-piece['baseline_offset'] for piece in pending))
        descent = max(nominal_descent, max(piece['height']-piece['baseline']+piece['baseline_offset'] for piece in pending))
        height = ascent + descent
        if height > capacity:
            raise ValueError('An item is taller than the printable page; reduce its size.')
        title = ' '.join(str(items[piece['item_index']].get('text', '')) for piece in pending)
        heading = explicit and not display and len(title) <= 100 and bool(re.match(r'^\d+[.)](?:\s|$)', title))
        lines.append({'pieces': pending, 'width': pending_width, 'ascent': ascent,
                      'height': height, 'leading': max(leading, height + 5),
                      'paragraph': paragraph, 'display_math': display, 'heading': heading, 'blank': False})
        pending, pending_width = [], 0

    for index, item in enumerate(items):
        if item.get('newline'):
            if display_break_pending:
                # A display block already ended its own line. Consume the source
                # line break once; a second newline still creates a blank line.
                display_break_pending = False
                continue
            if pending:
                finish(explicit=True)
            else:
                lines.append({'pieces': [], 'width': 0, 'ascent': nominal_ascent, 'height': em,
                              'leading': leading, 'paragraph': paragraph, 'blank': True,
                              'heading': False, 'display_math': False})
                paragraph += 1
            continue
        display_break_pending = False
        width = _number(item['width'], 'image width', True)
        height = _number(item['height'], 'image height', True)
        original_em = _number(item.get('em_height', height), 'em height', True)
        original_baseline = _number(item.get('baseline', height * 26 / 32), 'baseline')
        factor = em / original_em
        piece = {'item_index': index, 'width': max(1, round(width * factor)),
                 'height': max(1, round(height * factor)), 'baseline': round(original_baseline * factor),
                 'effective_scale': 1.0}
        if 'source_image_box' in item:
            piece['source_image_box'] = item['source_image_box']
        if piece['width'] > available:
            if not item.get('display_math'):
                raise ValueError('An item is wider than the printable page; reduce its size or split it.')
            fit_scale = available / piece['width']
            if fit_scale < .65:
                raise ValueError('公式过长，请拆成多行；缩至可打印宽度会小于原字号的 65%。')
            requested_width = piece['width']
            piece.update(width=available, height=max(1, round(piece['height'] * fit_scale)),
                         baseline=round(piece['baseline'] * fit_scale), effective_scale=fit_scale)
            warnings.append({'code': 'display-math-scaled', 'item_index': index,
                             'requested_width': requested_width, 'rendered_width': available,
                             'effective_scale': fit_scale,
                             'message': 'Display formula scaled uniformly to fit the printable width; review its final legibility.'})
        if item.get('display_math'):
            finish()
            paragraph += 1
            pending, pending_width = [piece], piece['width']
            finish(display=True)
            paragraph += 1
            display_break_pending = True
        else:
            gap = max(1, round(ratios[index] * em)) if ratios is not None else word_gap
            if item.get('space_before') is False:
                gap = 0
            piece['gap_before'] = gap if pending else 0
            next_width = pending_width + piece['gap_before'] + piece['width']
            if pending and next_width > available:
                finish()
                piece['gap_before'] = 0
                next_width = piece['width']
            pending.append(piece)
            pending_width = next_width
    finish()
    # Trailing separators do not create empty PDF pages.
    while lines and lines[-1]['blank']:
        lines.pop()

    placements, planned_lines = [], []
    page, y = 1, margin
    bottom = page_h - margin

    def span(group):
        return sum(line['leading'] for line in group[:-1]) + group[-1]['height'] if group else 0

    def new_page():
        nonlocal page, y
        if y != margin:
            page += 1
            y = margin

    def place(line):
        nonlocal y
        line_id = len(planned_lines)
        start_x = (page_w - line['width']) / 2 if line['display_math'] else margin
        baseline_y = y + line['ascent']
        item_indices = []
        x = round(start_x)
        for piece in line['pieces']:
            x += piece.get('gap_before', 0)
            entry = {'item_index': piece['item_index'], 'page': page, 'line': line_id,
                     'x': x, 'y': baseline_y - piece['baseline']+piece['baseline_offset'],
                     'width': piece['width'], 'height': piece['height'], 'baseline': baseline_y+piece['baseline_offset'],
                     'baseline_offset':piece['baseline_offset'],
                     'display_math': line['display_math'], 'effective_scale': piece['effective_scale'],
                     'gap_before': piece.get('gap_before', 0)}
            if 'source_image_box' in piece:
                entry['source_image_box'] = piece['source_image_box']
            placements.append(entry)
            item_indices.append(piece['item_index'])
            x += piece['width']
        planned_lines.append({'line': line_id, 'page': page, 'paragraph': line['paragraph'],
                              'y': y, 'height': line['height'], 'baseline': baseline_y,
                              'item_indices': item_indices, 'heading': line['heading'],
                              'display_math': line['display_math'], 'blank': line['blank']})
        y += line['leading']

    index = 0
    while index < len(lines):
        line = lines[index]
        if line['blank']:
            if y != margin and y + line['height'] <= bottom:
                place(line)
            index += 1
            continue
        if line['heading']:
            following = []
            cursor = index + 1
            meaningful = 0
            while cursor < len(lines) and meaningful < 2:
                candidate = lines[cursor]
                if candidate['heading']:
                    break
                following.append(candidate)
                meaningful += not candidate['blank']
                cursor += 1
            group = [line] + following
            section_end = index + 1
            while section_end < len(lines) and not lines[section_end]['heading']:
                section_end += 1
            section = lines[index:section_end]
            while section and section[-1]['blank']:
                section = section[:-1]
            # Keep a short numbered question together, including its formula and
            # explanation, when the entire block fits on one printable page.
            if span(section) <= capacity:
                group = section
            if span(group) > capacity:
                # A tall formula may make keeping two following lines impossible.
                # Keep the first following content block whenever that smaller
                # group fits, instead of abandoning the heading constraint.
                first_content = next((i for i, candidate in enumerate(following) if not candidate['blank']), None)
                if first_content is not None:
                    group = [line] + following[:first_content + 1]
            if span(group) <= capacity and y + span(group) > bottom:
                new_page()
            if y + line['height'] > bottom:
                new_page()
            place(line)
            index += 1
            continue
        if line['display_math']:
            following = []
            cursor = index + 1
            body_paragraph = None
            while cursor < len(lines):
                candidate = lines[cursor]
                if candidate['heading'] or candidate['display_math']:
                    break
                if candidate['blank']:
                    if body_paragraph is not None:
                        break
                else:
                    if body_paragraph is None:
                        body_paragraph = candidate['paragraph']
                    elif candidate['paragraph'] != body_paragraph:
                        break
                following.append(candidate)
                cursor += 1
            # Separators before the next heading/formula are not an explanation.
            # Do not move an otherwise fitting formula merely to keep blank space.
            while following and following[-1]['blank']:
                following.pop()
            group = [line] + following
            if span(group) > capacity:
                meaningful = 0
                group = [line]
                for candidate in following:
                    group.append(candidate)
                    meaningful += not candidate['blank']
                    if meaningful == 2:
                        break
            previous_content = next((record for record in reversed(planned_lines) if not record['blank']), None)
            follows_heading = bool(previous_content and previous_content['page'] == page and previous_content['heading'])
            if span(group) <= capacity and y + span(group) > bottom:
                if follows_heading:
                    warnings.append({'code': 'formula-explanation-keep-unavoidable',
                                     'item_index': line['pieces'][0]['item_index'],
                                     'message': 'Keeping the formula with its heading prevents keeping the following explanation on this page.'})
                else:
                    new_page()
            if y + line['height'] > bottom:
                new_page()
            place(line)
            index += 1
            continue
        # Treat explicit single newlines as a forced line within the paragraph;
        # blank lines, headings and display formulas delimit pagination groups.
        end = index + 1
        while end < len(lines) and not line['display_math']:
            candidate = lines[end]
            if candidate['paragraph'] != line['paragraph'] or candidate['blank'] or candidate['heading'] or candidate['display_math']:
                break
            end += 1
        group = lines[index:end]
        count = 0
        while count < len(group) and y + span(group[:count + 1]) <= bottom:
            count += 1
        if count == 0:
            new_page()
            continue
        if len(group) > count:
            previous_content = next((record for record in reversed(planned_lines) if not record['blank']), None)
            follows_heading = bool(previous_content and previous_content['page'] == page and
                                   (previous_content['heading'] or previous_content['display_math']))
            if count == 1 and len(group) >= 2 and y != margin and span(group[:2]) <= capacity:
                new_page()
                continue
            if len(group) - count == 1:
                if count >= 3:
                    count -= 1
                elif span(group) <= capacity and y != margin and not follows_heading:
                    new_page()
                    continue
                else:
                    warnings.append({'code': 'widow-orphan-unavoidable', 'item_index': group[0]['pieces'][0]['item_index'],
                                     'message': 'Page dimensions cannot keep two paragraph lines on both sides of this break.'})
        for candidate in group[:count]:
            place(candidate)
        index += count
        if count < len(group):
            new_page()
    return {'schema_version': 2, 'layout_version': VERSION, 'page_width': page_w, 'page_height': page_h, 'margin': margin,
            'pages': page, 'lines': planned_lines, 'placements': placements, 'warnings': warnings}


def _safe_image(folder, filename):
    if not isinstance(filename, str):
        raise ValueError('Invalid generated image path.')
    path = (folder / filename).resolve()
    if path.parent != folder or path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
        raise ValueError('Generated image must be a direct child of the output directory.')
    return path


def compose_document(folder, job, generated):
    """Save one raster page at a time and append it to the PDF."""
    if generated.get('assignment_layout'):
        from .runtime.assignment import compose_assignment
        return compose_assignment(folder,job,generated)
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    folder = Path(folder).resolve()
    from .runtime.word_spacing import fit_word_spacing
    spacing_model = generated.get('word_spacing') or fit_word_spacing()
    items = []
    paths = {}
    for index, item in enumerate(generated['words']):
        if item.get('newline'):
            items.append(dict(item))
            continue
        path = _safe_image(folder, item.get('file'))
        with Image.open(path) as source:
            image = source.convert('L')
            bounds = ImageOps.invert(image).point(lambda value: 255 if value > 45 else 0).getbbox()
            if not bounds:
                raise ValueError('Generated item contains no visible ink.')
            # Remove raster side bearings before measuring visible word gaps.
            # Keep a pixel of safety; height and baseline remain unchanged.
            crop = [max(0, bounds[0] - 1), 0, min(image.width, bounds[2] + 1), image.height]
            items.append({**item, 'width': crop[2] - crop[0], 'height': image.height,
                          'source_image_box': crop, 'image_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        paths[index] = path
    model_info=generated.get('model',{})
    reference_mode=isinstance(model_info,dict) and model_info.get('mode')=='reference'
    plan = plan_document(items, {**job['preferences'], 'baseline_variation':not reference_mode}, word_spacing=spacing_model)
    code = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in (
        ('document_layout.py', Path(__file__)),
        ('word_spacing.py', Path(__file__).parent / 'runtime/word_spacing.py'),
        ('baseline_rhythm.py', Path(__file__).parent / 'runtime/baseline_rhythm.py'))}
    identity = {'version': VERSION, 'code_sha256': code, 'preferences': job['preferences'],
                'word_spacing': spacing_model,
                'text_sha256': hashlib.sha256(job['text'].encode('utf-8')).hexdigest(),
                'items_sha256': hashlib.sha256(json.dumps(items,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()}
    plan['provenance'] = {**identity, 'layout_fingerprint_sha256': hashlib.sha256(
        json.dumps(identity, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
        'padding_policy': 'Horizontal ink bounds plus one safety pixel; original rasters and baselines retained.'}
    ink = job['preferences']['ink']
    if not isinstance(ink, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', ink):
        raise ValueError('Invalid ink color.')
    document = canvas.Canvas(str(folder / 'result.pdf'), pagesize=(595.2756, 841.8898), invariant=1)
    document.setTitle('Inkself handwriting preview - requires human review')
    by_page = {}
    for entry in plan['placements']:
        by_page.setdefault(entry['page'], []).append(entry)
    for page_number in range(1, plan['pages'] + 1):
        page = Image.new('RGB', (plan['page_width'], plan['page_height']), 'white')
        for entry in by_page.get(page_number, []):
            with Image.open(paths[entry['item_index']]) as source:
                word = source.convert('L').crop(entry['source_image_box']).resize((entry['width'], entry['height']), Image.Resampling.LANCZOS)
            page.paste(ImageOps.colorize(word, black=ink, white='white'), (entry['x'], entry['y']))
        filename = folder / f'page-{page_number:03}.png'
        page.save(filename)
        document.drawImage(ImageReader(page), 0, 0, width=595.2756, height=841.8898)
        document.showPage()
        page.close()
    document.save()
    (folder / 'layout.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    report = {'requested_text': job['text'], 'model': generated['model'],
              'validation': {'visible_pages': plan['pages'], 'content_identity': 'not-OCR-verified; human review required',
                             'similarity': 'not evaluated'}, 'words': generated['words'],
              'layout': {'file': 'layout.json', 'warnings': plan['warnings'], 'provenance': plan['provenance']}}
    (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return plan['pages']

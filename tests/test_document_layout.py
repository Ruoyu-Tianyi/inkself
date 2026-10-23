"""Pure layout tests with synthetic dimensions; no personal material or PDFs."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from web.document_layout import compose_document, plan_document


PREFERENCES = {'size': 16, 'line_spacing': 1.6, 'ink': '#263d57'}


def word(text='word', width=100, height=32, baseline=26, **extra):
    return {'text': text, 'file': 'word.png', 'width': width, 'height': height,
            'baseline': baseline, 'em_height': 32, **extra}


def paragraph(count, label='word'):
    items = []
    for index in range(count):
        if index:
            items.append({'newline': True})
        items.append(word(f'{label}{index}'))
    return items


class DocumentLayout(unittest.TestCase):
    def test_sampled_gaps_are_reproducible_and_match_wrap_placements(self):
        from web.runtime.word_spacing import fit_word_spacing
        model=fit_word_spacing()
        items=[word(str(index),width=160) for index in range(150)]
        prefs={**PREFERENCES,'seed':27}
        plan=plan_document(items,prefs,page_h=350,margin=20,word_spacing=model)
        self.assert_bounds_and_order(items,plan)
        self.assertEqual(plan,plan_document(items,prefs,page_h=350,margin=20,word_spacing=model))
        changed=plan_document(items,{**prefs,'seed':28},page_h=350,margin=20,word_spacing=model)
        self.assertNotEqual(plan['placements'],changed['placements'])
        gaps=[p['gap_before'] for p in plan['placements'] if p['gap_before']]
        self.assertGreater(len(set(gaps)),5)
        by_line={}
        for entry in plan['placements']:by_line.setdefault(entry['line'],[]).append(entry)
        for line in by_line.values():
            self.assertEqual(line[0]['gap_before'],0)
            for left,right in zip(line,line[1:]):
                self.assertEqual(right['x']-left['x']-left['width'],right['gap_before'])

    def test_source_adjacent_punctuation_does_not_receive_a_word_gap(self):
        from web.runtime.word_spacing import fit_word_spacing
        items=[word('Value'),word('x',width=20,math=True,space_before=True),
               word('.',width=3,space_before=False),word('Next',space_before=True)]
        plan=plan_document(items,PREFERENCES,word_spacing=fit_word_spacing())
        self.assertEqual(plan['placements'][2]['gap_before'],0)
        self.assertGreater(plan['placements'][1]['gap_before'],0)
        self.assertGreater(plan['placements'][3]['gap_before'],0)
        self.assert_bounds_and_order(items,plan)

    def test_composition_trims_canvas_padding_and_preserves_visible_ink(self):
        import json
        from PIL import ImageDraw
        from web.runtime.word_spacing import fit_word_spacing
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            image=Image.new('L',(100,32),255)
            ImageDraw.Draw(image).rectangle((40,5,58,26),fill=0)
            image.save(folder/'padded.png')
            words=[word(str(i),file='padded.png') for i in range(40)]
            compose_document(folder,{'text':' '.join(str(i) for i in range(40)),
                'preferences':{**PREFERENCES,'seed':17}},
                {'model':{},'words':words,'word_spacing':fit_word_spacing()})
            plan=json.loads((folder/'layout.json').read_text())
            self.assertEqual(plan['provenance']['word_spacing']['method'],'conservative-default')
            self.assertTrue(all(p['source_image_box']==[39,0,60,32] for p in plan['placements']))
            with Image.open(folder/'page-001.png') as page:
                for p in plan['placements']:
                    if p['page']==1:
                        crop=page.crop((p['x'],p['y'],p['x']+p['width'],p['y']+p['height'])).convert('L')
                        self.assertLess(min(crop.getdata()),80)
            self.assert_bounds_and_order(words,plan)

    def assert_bounds_and_order(self, items, plan):
        expected = [index for index, item in enumerate(items) if not item.get('newline')]
        self.assertEqual([entry['item_index'] for entry in plan['placements']], expected)
        margin = plan['margin']
        for entry in plan['placements']:
            self.assertGreaterEqual(entry['x'], margin)
            self.assertGreaterEqual(entry['y'], margin)
            self.assertLessEqual(entry['x'] + entry['width'], plan['page_width'] - margin)
            self.assertLessEqual(entry['y'] + entry['height'], plan['page_height'] - margin)
        by_page = {}
        for line in plan['lines']:
            by_page.setdefault(line['page'], []).append(line)
        for lines in by_page.values():
            for previous, following in zip(lines, lines[1:]):
                self.assertLessEqual(previous['y'] + previous['height'], following['y'])

    def test_long_paragraph_wraps_and_preserves_item_order_without_single_line_tail(self):
        # Width produces several automatically wrapped lines, not only explicit
        # breaks. Geometry and final order are checked over several small pages.
        items = [word(str(index), width=240) for index in range(37)]
        plan = plan_document(items, PREFERENCES, page_h=300, margin=20)
        self.assertGreaterEqual(plan['pages'], 3)
        self.assert_bounds_and_order(items, plan)
        for page in range(1, plan['pages'] + 1):
            self.assertGreaterEqual(sum(line['page'] == page for line in plan['lines']), 2)
        self.assertEqual(plan, plan_document(items, PREFERENCES, page_h=300, margin=20))

    def test_widow_uses_two_lines_and_new_paragraph_does_not_start_with_one(self):
        items = paragraph(6)
        plan = plan_document(items, PREFERENCES, page_h=300, margin=20)
        self.assertEqual([sum(line['page'] == page for line in plan['lines']) for page in (1, 2)], [4, 2])
        items = paragraph(3, 'before') + [{'newline': True}, {'newline': True}] + paragraph(4, 'after')
        plan = plan_document(items, PREFERENCES, page_h=300, margin=20)
        after_indices = {index for index, item in enumerate(items) if item.get('text', '').startswith('after')}
        after = [entry for entry in plan['placements'] if entry['item_index'] in after_indices]
        self.assertEqual({entry['page'] for entry in after}, {2})
        self.assert_bounds_and_order(items, plan)

    def test_numbered_heading_moves_with_following_body(self):
        items = paragraph(3, 'before') + [{'newline': True}, word('13.'), {'newline': True}] + paragraph(4, 'body')
        plan = plan_document(items, PREFERENCES, page_h=300, margin=20)
        heading = next(entry for entry in plan['placements'] if items[entry['item_index']].get('text') == '13.')
        body = [entry for entry in plan['placements'] if items[entry['item_index']].get('text', '').startswith('body')]
        self.assertEqual(heading['page'], 2)
        self.assertTrue(all(entry['page'] == heading['page'] for entry in body[:2]))
        self.assert_bounds_and_order(items, plan)

    def test_heading_is_not_abandoned_when_all_pagination_constraints_cannot_fit(self):
        items = [word('13.'), {'newline': True}] + paragraph(3, 'body')
        plan = plan_document(items, PREFERENCES, page_h=210, margin=20)
        self.assertEqual([entry['page'] for entry in plan['placements']], [1, 1, 1, 2])
        self.assertIn('widow-orphan-unavoidable', [warning['code'] for warning in plan['warnings']])
        self.assert_bounds_and_order(items, plan)

    def test_heading_stays_with_tall_formula_when_two_following_lines_cannot_fit(self):
        items = paragraph(3, 'before') + [{'newline': True}, word('13.'), {'newline': True},
                 word('equation', width=220, height=110, baseline=85, display_math=True), word('explanation')]
        plan = plan_document(items, PREFERENCES, page_h=300, margin=20)
        heading = next(entry for entry in plan['placements'] if items[entry['item_index']].get('text') == '13.')
        formula = next(entry for entry in plan['placements'] if entry['display_math'])
        self.assertEqual(heading['page'], 2)
        self.assertEqual(heading['page'], formula['page'])
        self.assert_bounds_and_order(items, plan)

    def test_tall_inline_formula_changes_whole_line_metrics_and_display_is_centered(self):
        items = [word('before'), word('fraction', width=160, height=96, baseline=70, inline_math=True),
                 {'newline': True}, word('following'),
                 word('display', width=260, height=110, baseline=85, display_math=True), word('after')]
        plan = plan_document(items, PREFERENCES)
        places = {entry['item_index']: entry for entry in plan['placements']}
        self.assertEqual(places[0]['baseline'], places[1]['baseline'])
        self.assertGreaterEqual(places[3]['y'], places[1]['y'] + places[1]['height'])
        display = places[4]
        self.assertLessEqual(abs(display['x'] + display['width'] / 2 - plan['page_width'] / 2), .5)
        self.assertEqual(plan['lines'][display['line']]['item_indices'], [4])
        self.assertTrue(display['display_math'])
        self.assert_bounds_and_order(items, plan)

    def test_display_formula_can_shrink_with_auditable_scale_but_not_below_limit(self):
        items = [word('wide equation', width=900, height=100, baseline=75, display_math=True)]
        plan = plan_document(items, PREFERENCES)
        formula = plan['placements'][0]
        self.assertEqual(formula['width'], plan['page_width'] - 2 * plan['margin'])
        self.assertGreaterEqual(formula['effective_scale'], .65)
        self.assertLess(formula['effective_scale'], 1.)
        self.assertEqual(formula['x'], plan['margin'])
        self.assertEqual(plan['warnings'][0]['code'], 'display-math-scaled')
        self.assertEqual(plan['warnings'][0]['effective_scale'], formula['effective_scale'])
        original_factor = max(24, int(16 * 1240 / 595.2756 * 1.4)) / 32
        self.assertEqual(formula['height'], round(round(100 * original_factor) * formula['effective_scale']))
        self.assert_bounds_and_order(items, plan)
        with self.assertRaisesRegex(ValueError, '公式过长'):
            plan_document([word(width=1600, display_math=True)], PREFERENCES)
        with self.assertRaisesRegex(ValueError, 'wider'):
            plan_document([word(width=900, inline_math=True)], PREFERENCES)

    def test_display_linebreak_consumed_once_and_second_break_keeps_paragraph_gap(self):
        formula = word('formula', width=200, height=50, baseline=40, display_math=True)
        for breaks, expected_blank in ((1, 0), (2, 1)):
            items = [formula] + [{'newline': True}] * breaks + [word('body')]
            plan = plan_document(items, PREFERENCES)
            self.assertEqual(sum(line['blank'] for line in plan['lines']), expected_blank)
            self.assert_bounds_and_order(items, plan)

    def test_display_formula_moves_with_two_explanation_lines(self):
        items = paragraph(3, 'before') + [{'newline': True},
                 word('formula', width=200, height=64, baseline=48, display_math=True),
                 {'newline': True}] + paragraph(2, 'explain')
        plan = plan_document(items, PREFERENCES, page_h=300, margin=20)
        formula = next(entry for entry in plan['placements'] if entry['display_math'])
        explanations = [entry for entry in plan['placements'] if items[entry['item_index']].get('text', '').startswith('explain')]
        self.assertEqual(formula['page'], 2)
        self.assertEqual({entry['page'] for entry in explanations}, {formula['page']})
        self.assert_bounds_and_order(items, plan)

    def test_short_numbered_question_formula_and_explanation_move_as_one_block(self):
        items = paragraph(3, 'before') + [{'newline': True}, word('28.'), {'newline': True},
                 word('intro'), {'newline': True},
                 word('formula', width=200, height=42, baseline=32, display_math=True),
                 {'newline': True}] + paragraph(2, 'explain')
        plan = plan_document(items, PREFERENCES, page_h=330, margin=20)
        question = [entry for entry in plan['placements'] if not items[entry['item_index']].get('text', '').startswith('before')]
        self.assertEqual({entry['page'] for entry in question}, {2})
        self.assertEqual(plan['pages'], 2)
        self.assert_bounds_and_order(items, plan)

    def test_last_formula_does_not_move_just_to_keep_blank_before_next_heading(self):
        items = [word('before'), {'newline': True}, word('4.'), {'newline': True},
                 word('intro'), {'newline': True},
                 word('root', width=200, height=64, baseline=48, display_math=True), {'newline': True},
                 word('integral', width=200, height=64, baseline=48, display_math=True),
                 {'newline': True}, {'newline': True}, word('5.'), {'newline': True}, word('next')]
        plan = plan_document(items, PREFERENCES, page_h=420, margin=20)
        pages = {items[entry['item_index']]['text']: entry['page'] for entry in plan['placements']}
        self.assertEqual({pages[label] for label in ('4.', 'intro', 'root', 'integral')}, {1})
        self.assertEqual(pages['5.'], 2)
        self.assert_bounds_and_order(items, plan)

    def test_legacy_images_blank_paragraph_and_impossible_item(self):
        legacy = {'text': 'legacy', 'file': 'legacy.png', 'width': 80, 'height': 40}
        items = [legacy, {'newline': True}, {'newline': True}, word('last'), {'newline': True}, {'newline': True}]
        plan = plan_document(items, PREFERENCES)
        self.assertEqual(sum(line['blank'] for line in plan['lines']), 1)
        self.assertEqual(plan['pages'], 1)
        self.assert_bounds_and_order(items, plan)
        with self.assertRaisesRegex(ValueError, 'wider'):
            plan_document([word(width=10000)], PREFERENCES)
        with self.assertRaisesRegex(ValueError, 'taller'):
            plan_document([word(height=10000)], PREFERENCES)

    def test_path_escape_and_blank_image_fail_before_pdf_authoring(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'job'
            folder.mkdir()
            Image.new('L', (8, 8), 0).save(root / 'outside.png')
            Image.new('L', (8, 8), 255).save(folder / 'blank.png')
            job = {'text': 'test', 'preferences': PREFERENCES}
            with patch('reportlab.pdfgen.canvas.Canvas') as canvas:
                for filename in ('../outside.png', str(root / 'outside.png'), 'blank.png'):
                    with self.subTest(filename=filename), self.assertRaises(ValueError):
                        compose_document(folder, job, {'model': {}, 'words': [{'file': filename}]})
                canvas.assert_not_called()
            self.assertFalse((folder / 'result.pdf').exists())


if __name__ == '__main__':
    unittest.main()

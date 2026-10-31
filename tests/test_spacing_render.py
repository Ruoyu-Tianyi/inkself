"""Behavioral checks for spacing controls using synthetic ink, not personal samples."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tests.test_assignment import bank_fixture
from tests.test_habit_model import fixture as habit_fixture
from web.document_layout import plan_document
from web.runtime.assignment import Writer, compose_assignment, render_assignment
from web.runtime.digit_style import numeric_token
from web.runtime.habit_model import align_words, fit_habits, habit_token
from web.runtime.math_renderer import render_math
from web.runtime.math_syntax import parse_math
from web.runtime.reference_renderer import reference_token
from web.runtime.spacing import normalize_spacing
from web.runtime.symbol_style import symbol_gap
from web.runtime.vatr_worker import request_input_hashes, verify_request_inputs,renderer_provenance
from web.runtime.word_spacing import fit_word_spacing


class AdjustableSpacingRendering(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bank = bank_fixture(self.root / 'bank')

    def tearDown(self):
        self.temp.cleanup()

    def clear_bounds(self, image):
        pixels = np.asarray(image)
        self.assertTrue(np.all(pixels[[0, -1], :] == 255))
        self.assertTrue(np.all(pixels[:, [0, -1]] == 255))

    def test_reference_default_preserves_captured_word_and_custom_rebuilds(self):
        folder = self.root / 'habit'; folder.mkdir()
        bank = habit_fixture(folder)
        original, meta = reference_token(bank, 'anne')
        explicit, _ = reference_token(bank, 'anne', spacing=normalize_spacing())
        self.assertEqual(meta['renderer'], 'captured-word')
        self.assertEqual(original.tobytes(), explicit.tobytes())
        unrelated,_=reference_token(bank,'anne',spacing={'number':1.8,'symbol':1.8})
        self.assertEqual(original.tobytes(),unrelated.tobytes())
        numeric,_=reference_token(bank,'1212')
        unrelated,_=reference_token(bank,'1212',spacing={'letter':1.8})
        self.assertEqual(numeric.tobytes(),unrelated.tobytes())
        narrow, meta = reference_token(bank, 'anne', spacing={'letter': .6})
        wide, _ = reference_token(bank, 'anne', spacing={'letter': 1.8})
        self.assertNotEqual(meta['renderer'], 'captured-word')
        self.assertLess(narrow.width, wide.width)
        self.assertEqual(len(meta['references']), len('anne'))
        self.clear_bounds(wide)

    def test_habit_letter_and_digit_tracking_change_geometry_without_cropping(self):
        folder = self.root / 'habit'; folder.mkdir()
        bank = habit_fixture(folder)
        model = fit_habits(bank, align_words(bank), excluded={'naen'})
        for text, key in [('anneanne', 'letter'), ('111111', 'number'), ('12+12%', 'symbol')]:
            with self.subTest(key=key):
                narrow, _ = habit_token(bank, model, text, spacing={key: .6})
                wide, _ = habit_token(bank, model, text, spacing={key: 1.8})
                self.assertLess(narrow.width, wide.width)
                self.clear_bounds(narrow); self.clear_bounds(wide)
                repeat, _ = habit_token(bank, model, text, spacing={key: 1.8})
                self.assertEqual(wide.tobytes(), repeat.tobytes())

    def test_new_letter_rhythm_has_no_dip_at_the_natural_default(self):
        folder=self.root/'habit';folder.mkdir()
        bank=habit_fixture(folder)
        model=fit_habits(bank,align_words(bank),excluded={'naen'})
        for renderer in (lambda v:reference_token(bank,'anneanne',prefer_words=False,spacing={'variation':v})[0],
                         lambda v:habit_token(bank,model,'anneanne',spacing={'variation':v})[0]):
            self.assertEqual(renderer(.9).tobytes(),renderer(1).tobytes())
            natural=renderer(1)
            varied=renderer(2)
            self.assertNotEqual(natural.tobytes(),varied.tobytes())

    def test_numeric_spacing_variation_zero_keeps_constant_gaps(self):
        _, fixed = numeric_token(self.bank, '111111111', spacing={'variation': 0, 'number': 1.5})
        _, natural = numeric_token(self.bank, '111111111')
        self.assertEqual(len(set(fixed['digit_gaps_px'])), 1)
        self.assertGreater(len(set(natural['digit_gaps_px'])), 1)
        self.assertAlmostEqual(fixed['digit_gaps_px'][0], 3.6)

    def test_symbol_rhythm_is_reproducible_and_changes_real_math_pixels(self):
        settings=normalize_spacing({'variation':2})
        values=[symbol_gap(3,settings,11,0,index) for index in range(12)]
        self.assertGreater(len(set(values)),5)
        self.assertEqual(values,[symbol_gap(3,settings,11,0,index) for index in range(12)])
        self.assertEqual({symbol_gap(3,normalize_spacing({'variation':0}),11,0,i) for i in range(12)},{3})
        ast=parse_math('1+2=3+4=5+6')
        fixed,_=render_math(ast,self.bank,spacing={'variation':0})
        varied,_=render_math(ast,self.bank,spacing=settings)
        repeated,_=render_math(ast,self.bank,spacing=settings)
        self.assertNotEqual(fixed.tobytes(),varied.tobytes())
        self.assertEqual(varied.tobytes(),repeated.tobytes())
        self.clear_bounds(varied)

    def test_math_spacing_keeps_structure_and_all_glyphs_at_extremes(self):
        ast = parse_math(r'\left(\frac{x_{12}+\alpha}{\sqrt{123}}\right)=123')
        outputs=[]
        for symbol in (.6, 1.8):
            image, meta = render_math(ast, self.bank, allow_supplemental=True,
                                      spacing={'symbol': symbol, 'number': symbol})
            self.assertEqual(meta['math_ast'], ast)
            self.clear_bounds(image)
            outputs.append((image, [g['glyph'] for g in meta['math_glyphs']]))
        self.assertLess(outputs[0][0].width, outputs[1][0].width)
        self.assertEqual(outputs[0][1], outputs[1][1])

    def test_word_line_paragraph_and_baseline_controls_affect_layout(self):
        item={'text':'sample','width':65,'height':32,'baseline':26,'em_height':32}
        items=[dict(item) for _ in range(25)]+[{'newline':True},{'newline':True}]+[dict(item) for _ in range(12)]
        base={'size':16,'line_spacing':1.6,'seed':42}
        model=fit_word_spacing()
        compact=plan_document(items,{**base,'spacing':{'word':.5,'line':.8,'paragraph':.3,'baseline':0}},word_spacing=model)
        loose=plan_document(items,{**base,'spacing':{'word':2,'line':1.8,'paragraph':2.5,'baseline':2}},word_spacing=model)
        self.assertLess(compact['placements'][1]['gap_before'],loose['placements'][1]['gap_before'])
        self.assertEqual({p['baseline_offset'] for p in compact['placements']},{0})
        self.assertGreater(len({p['baseline_offset'] for p in loose['placements']}),1)
        self.assertLess(compact['lines'][1]['y']-compact['lines'][0]['y'],loose['lines'][1]['y']-loose['lines'][0]['y'])
        for plan in (compact,loose):
            for p in plan['placements']:
                self.assertGreaterEqual(p['y'],plan['margin'])
                self.assertLessEqual(p['y']+p['height'],plan['page_height']-plan['margin'])
            for previous,current in zip(plan['lines'],plan['lines'][1:]):
                if previous['page']==current['page']:
                    self.assertGreaterEqual(current['y'],previous['y']+previous['height'])
        # Isolate paragraph spacing from the line/word controls.
        short=[dict(item),{'newline':True},{'newline':True},dict(item)]
        a=plan_document(short,{**base,'spacing':{'paragraph':.3}})
        b=plan_document(short,{**base,'spacing':{'paragraph':2.5}})
        self.assertGreater(b['placements'][-1]['y'],a['placements'][-1]['y'])

    def test_reference_baseline_strength_is_continuous_when_explicit(self):
        text='Alpha beta delta gamma '*12
        spacing=fit_word_spacing()
        old=Writer(self.bank,None,spacing,42,False)
        old.paragraph(text)
        self.assertEqual({v for line in old.baseline_lines for v in line['offsets_px']},{0})
        offsets=[]
        for strength in (0,.5,1,1.5):
            writer=Writer(self.bank,None,spacing,42,False,spacing_options={'baseline':strength})
            writer.paragraph(text)
            offsets.append([abs(v) for line in writer.baseline_lines for v in line['offsets_px']])
        self.assertEqual(set(offsets[0]),{0})
        self.assertGreater(max(offsets[2]),0)
        for previous,current in zip(offsets,offsets[1:]):
            self.assertTrue(all(a<=b for a,b in zip(previous,current)))

    def test_standalone_prose_operator_spacing_and_attached_punctuation(self):
        items=[{'text':text,'width':25,'height':32,'em_height':32} for text in ('12','+','34','word','tail')]
        prefs={'size':16,'line_spacing':1.6,'seed':42}
        small=plan_document(items,{**prefs,'spacing':{'symbol':.6}})
        large=plan_document(items,{**prefs,'spacing':{'symbol':1.8}})
        for i in (1,2):
            self.assertLess(small['placements'][i]['gap_before'],large['placements'][i]['gap_before'])
        self.assertEqual(small['placements'][4]['gap_before'],large['placements'][4]['gap_before'])
        punctuation=[items[0],{**items[1],'text':'.','space_before':False}]
        attached=plan_document(punctuation,{**prefs,'spacing':{'symbol':1.8}})
        self.assertEqual(attached['placements'][1]['gap_before'],0)
        # A complete inline formula is not a standalone prose symbol token.
        formula=[items[0],{**items[1],'text':'+','math':True},items[2]]
        a=plan_document(formula,{**prefs,'spacing':{'symbol':.6}})
        b=plan_document(formula,{**prefs,'spacing':{'symbol':1.8}})
        self.assertEqual([p['gap_before'] for p in a['placements']],[p['gap_before'] for p in b['placements']])
        spacing=fit_word_spacing()
        widths=[]
        for factor in (.6,1.8):
            writer=Writer(self.bank,None,spacing,42,False,spacing_options={'symbol':factor,'baseline':0})
            image=writer.paragraph('12 + 34')
            from PIL import ImageOps
            widths.append(ImageOps.invert(image).getbbox()[2])
        self.assertLess(widths[0],widths[1])

    def test_extreme_variation_keeps_visible_word_boundaries(self):
        from unittest.mock import patch
        settings={'word':.5,'variation':2}
        model=fit_word_spacing()
        items=[{'text':'word','width':35,'height':32,'em_height':32} for _ in range(100)]
        prefs={'size':16,'line_spacing':1.6,'seed':42,'spacing':settings}
        plan=plan_document(items,prefs,word_spacing=model)
        em=max(24,int(16*1240/595.2756*1.4))
        self.assertGreater(len({p['gap_before'] for p in plan['placements']}),2)
        self.assertTrue(all(p['gap_before']>=round(.08*em) for p in plan['placements'] if p['gap_before']))
        attached=plan_document([items[0],{**items[1],'text':'.','space_before':False}],prefs,word_spacing=model)
        self.assertEqual(attached['placements'][1]['gap_before'],0)
        writer=Writer(self.bank,None,model,42,False,spacing_options=settings)
        with patch.object(writer,'join',wraps=writer.join) as join:
            writer.paragraph('Alpha beta gamma delta '*20,em=39)
        gaps=[piece[2] for call in join.call_args_list for piece in call.args[0] if piece[2]]
        self.assertTrue(gaps)
        self.assertTrue(all(gap>=round(.08*39) for gap in gaps))

    def test_assignment_uses_spacing_and_reserves_choice_and_page_bounds(self):
        source='## 1\n1. B\n2. E\n\n## 2\n'+('Alpha beta 123 + 456. '*40)+'\n\nSecond paragraph.'
        folder=self.root/'out';folder.mkdir()
        settings=normalize_spacing({'preset':'relaxed','baseline':2,'variation':2,'paragraph':2.5})
        request={'text':source,'seed':42,'answer_size':16,'spacing':settings}
        meta=render_assignment(request,self.bank,None,fit_word_spacing(),folder)
        self.assertEqual(meta['spacing'],settings)
        compose_assignment(folder,{'preferences':{'ink':'#263d57','spacing':settings}}, {'assignment_layout':meta,'model':{'name':'Synthetic'}})
        layout=json.loads((folder/'layout.json').read_text())
        self.assertEqual(layout['spacing'],settings)
        paragraph_gaps=[p['gap_after'] for p in layout['placements'] if p['role']=='paragraph']
        self.assertTrue(all(gap>12 for gap in paragraph_gaps))
        for p in layout['placements']:
            self.assertGreaterEqual(p['y'],80)
            self.assertLessEqual(p['y']+p['height'],1642)

    def test_queued_spacing_edit_changes_identity_and_is_rejected(self):
        request={'render_mode':'reference','reference_bank':str(self.root/'bank'/'bank.json'),
                 'spacing':normalize_spacing()}
        request['expected_input_hashes']=request_input_hashes(request)
        request['spacing']['word']=1.4
        with self.assertRaisesRegex(ValueError,'changed after.*queued'):
            verify_request_inputs(request)

    def test_reference_math_and_assignment_provenance_covers_spacing_dependencies(self):
        from unittest.mock import patch
        for extra in ({'math_enabled':True},{'layout_mode':'assignment'}):
            request={'render_mode':'reference','text':'x','seed':42,**extra}
            paths=[]
            def digest(path):
                paths.append(Path(path).name)
                return 'synthetic-source'
            with patch('web.runtime.vatr_worker._sha256',side_effect=digest):
                renderer_provenance(request,{})
            self.assertTrue({'spacing.py','math_renderer.py','symbol_style.py','digit_style.py'}.issubset(paths))
            if 'layout_mode' in extra:self.assertIn('markdown_document.py',paths)


if __name__=='__main__':
    unittest.main()

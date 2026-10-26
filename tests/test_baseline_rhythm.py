import unittest
from web.runtime.baseline_rhythm import word_offsets
from web.document_layout import plan_document

class BaselineRhythm(unittest.TestCase):
    def test_reproducible_bounded_and_attached_punctuation(self):
        widths=[80]*30;gaps=[10]*30;gaps[3]=0
        values=word_offsets(widths,gaps,50,42,1)
        self.assertEqual(values,word_offsets(widths,gaps,50,42,1))
        self.assertNotEqual(values,word_offsets(widths,gaps,50,42,2))
        self.assertGreater(len(set(values)),2)
        self.assertTrue(all(abs(v)<=4 for v in values))
        self.assertEqual(values[2],values[3])

    def test_lines_reserve_room_and_do_not_clip_or_overlap(self):
        items=[{'text':'test','width':70,'height':50,'baseline':32,'em_height':40} for _ in range(120)]
        prefs={'size':16,'line_spacing':1.1,'seed':42}
        plan=plan_document(items,prefs)
        self.assertGreater(len({p['baseline_offset'] for p in plan['placements']}),2)
        for p in plan['placements']:
            self.assertGreaterEqual(p['y'],plan['margin'])
            self.assertLessEqual(p['y']+p['height'],plan['page_height']-plan['margin'])
            line=plan['lines'][p['line']]
            self.assertGreaterEqual(p['y'],line['y'])
            self.assertLessEqual(p['y']+p['height'],line['y']+line['height'])
        aligned=plan_document(items,{**prefs,'baseline_variation':False})
        self.assertEqual({p['baseline_offset'] for p in aligned['placements']},{0})

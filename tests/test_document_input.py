"""Content gates reject ambiguous or unreviewed math before queueing a job."""
import unittest
from web.runtime.document_input import prepare_document


class DocumentInput(unittest.TestCase):
    def setUp(self):
        self.bank={'glyphs':{c:{} for c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+-=.'}}

    def test_prose_limit_and_formula_limit_are_separate(self):
        tokens,_=prepare_document('Result $x_{12345678901234567890123456789012345}=1$.',self.bank,True)
        self.assertTrue(any('math' in v for v in tokens))
        with self.assertRaises(ValueError):prepare_document('a'*33,self.bank,True)

    def test_missing_greek_requires_explicit_supplement(self):
        with self.assertRaisesRegex(ValueError,'原稿未采集'):prepare_document(r'$\alpha_i=1$',self.bank,True,False)
        _,missing=prepare_document(r'$\alpha_i=1$',self.bank,True,True)
        self.assertEqual(missing,['α'])

    def test_unrecognized_commands_and_empty_formula_fail_preflight(self):
        for text in ('$$  $$',r'$\input{secret}$',r'$\unknown{x}$','$x_{1$'):
            with self.subTest(text=text),self.assertRaises(ValueError):prepare_document(text,self.bank,True,True)

    def test_math_is_not_silently_enabled(self):
        with self.assertRaises(ValueError):prepare_document('$x_i$',self.bank,False,True)
        tokens,missing=prepare_document('Result x.',self.bank)
        self.assertEqual([v['text'] for v in tokens],['Result','x.']);self.assertEqual(missing,[])


if __name__=='__main__':unittest.main()

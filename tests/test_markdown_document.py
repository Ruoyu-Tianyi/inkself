"""Markdown importer fixtures are generic text; no handwriting files are used."""
import json
import unittest
from unittest.mock import patch

from web.markdown_document import decode_markdown_upload, parse_markdown


class MarkdownDocument(unittest.TestCase):
    def test_headings_formatting_numbered_questions_and_paragraphs(self):
        source = '# Capacity-planning - Part 2\n\n1. **Find capacity.**\n\na. Use *annual demand*.\n\n## Case-study: x < y\nKeep file_name and x_i.'
        result = parse_markdown(source, 'Homework.MD')
        self.assertEqual(result['text'], 'Capacity-planning - Part 2\n\n1. Find capacity.\n\na. Use annual demand.\n\nCase-study: x < y\nKeep file_name and x_i.')
        self.assertEqual(result['summary']['headings'], 2)
        self.assertEqual(result['summary']['list_items'], 1)
        self.assertFalse(result['math_enabled'])
        self.assertEqual(result['source_text'], source)
        json.dumps(result)

    def test_math_preserves_all_delimiters_inequalities_and_nested_notation(self):
        formulas = [r'$x_{i_j}^{2} < y_i$', r'$$\frac{a-b}{\sqrt[3]{x_i}} \geq 0$$',
                    r'\(\alpha_i+\beta_i\)', '\\[\n\\left[\\frac{x}{y}\\right] > 0\n\\]']
        source = '# Model $a-b < c$\n\n' + '\n\n'.join(formulas)
        result = parse_markdown(source)
        self.assertTrue(result['math_enabled'])
        for formula in formulas:
            self.assertIn(formula, result['text'])
        self.assertIn('Model $a-b < c$', result['text'])
        self.assertEqual(result['summary']['math'], 5)
        self.assertEqual(result['summary']['inline_math'], 3)
        self.assertEqual(result['summary']['display_math'], 2)

    def test_math_fences_convert_without_stripping_symbols(self):
        result = parse_markdown('Question 1\n\n```math\n\\frac{x_i-y_i}{2} <= z\n```\n\n~~~latex\n\\alpha_i^2\n~~~~')
        self.assertIn('$$\n\\frac{x_i-y_i}{2} <= z\n$$', result['text'])
        self.assertIn('$$\n\\alpha_i^2\n$$', result['text'])
        self.assertEqual(result['summary']['display_math'], 2)
        self.assertEqual(result['summary']['code_blocks'], 2)

    def test_lists_tasks_and_quotes_keep_visible_contents(self):
        source = '- First\n  * Nested **answer**\n- [x] Check 25%\n- [ ] Review\n\n> Quoted *reason*.\n\nTitle\n====='
        result = parse_markdown(source)
        self.assertIn('- First\n  - Nested answer\n- Done: Check 25%\n- To do: Review', result['text'])
        self.assertIn('Quoted reason.', result['text'])
        self.assertEqual(result['summary']['list_items'], 4)
        self.assertEqual(result['summary']['blockquotes'], 1)
        self.assertEqual(result['summary']['headings'], 1)
        self.assertGreaterEqual(len(result['warnings']), 3)

    def test_tables_become_readable_rows_and_warn(self):
        source = '| **Item** | Value |\n| :--- | ---: |\n| Demand | 25 |\n| Rate | $x_i < 1$ |\n\nEnd.'
        result = parse_markdown(source)
        self.assertEqual(result['text'], 'Item; Value\nDemand; 25\nRate; $x_i < 1$\n\nEnd.')
        self.assertNotIn('|', result['text'])
        self.assertEqual(result['summary']['tables'], 1)
        self.assertEqual(result['summary']['table_rows'], 2)
        self.assertTrue(any('表格' in warning for warning in result['warnings']))
        with self.assertRaisesRegex(ValueError, '列数'):
            parse_markdown('| A | B |\n| --- | --- |\n| only one |')

    def test_links_images_and_autolinks_never_open_destinations(self):
        source = '[visible **answer**](file:///C:/secret.txt)\n![A clear chart](https://invalid.test/chart.png)\n<https://invalid.test/info>\n[notes][ref]\n\n[ref]: ../../private.txt'
        with patch('urllib.request.urlopen', side_effect=AssertionError('No network allowed')):
            result = parse_markdown(source)
        self.assertIn('visible answer\nA clear chart\nhttps://invalid.test/info\nnotes', result['text'])
        self.assertNotIn('secret.txt', result['text'])
        self.assertNotIn('private.txt', result['text'])
        self.assertEqual(result['summary']['links'], 3)
        self.assertEqual(result['summary']['images'], 1)
        self.assertTrue(any('alt' in warning for warning in result['warnings']))
        with self.assertRaisesRegex(ValueError, '替代文字'):
            parse_markdown('![](private.png)')

    def test_escaped_punctuation_entities_and_inline_code_are_literal(self):
        result = parse_markdown(r'\*literal\* and \#tag; file\_name; [brackets]; &lt; 5; `a*b` and \$25.')
        self.assertEqual(result['text'], '*literal* and #tag; file_name; [brackets]; < 5; a*b and $25.')
        self.assertFalse(result['math_enabled'])
        self.assertEqual(result['summary']['inline_code'], 1)
        with_math = parse_markdown(r'Cost \$25 and $x_i=2$; `price $5`.')
        self.assertEqual(with_math['text'], r'Cost \$25 and $x_i=2$; price \$5.')
        self.assertEqual(parse_markdown('First\\\nSecond')['text'], 'First\nSecond')

    def test_nested_link_destinations_and_emphasis(self):
        result = parse_markdown('***both*** and __bold__ and _italic_. [Read](https://example.test/a_(b) "Title")')
        self.assertEqual(result['text'], 'both and bold and italic. Read')
        self.assertEqual(result['summary']['links'], 1)

    def test_strikethrough_warning_requires_a_real_strikethrough(self):
        ordinary = parse_markdown('**Bold answer**, *italic reason* and ***both***.')
        self.assertEqual(ordinary['text'], 'Bold answer, italic reason and both.')
        self.assertFalse(any('删除线' in warning for warning in ordinary['warnings']))
        crossed = parse_markdown('**Answer** with ~~old words~~ retained.')
        self.assertEqual(crossed['text'], 'Answer with old words retained.')
        self.assertEqual(sum('删除线' in warning for warning in crossed['warnings']), 1)

    def test_link_destinations_are_not_parsed_as_math_or_html(self):
        result = parse_markdown('[Read $x_i$](file:///C:/cost$25_(draft).md)\n<https://example.test/cost$25>\n`[literal](target)`')
        self.assertEqual(result['summary']['math'], 1)
        self.assertEqual(result['summary']['links'], 2)
        self.assertEqual(result['text'], 'Read $x_i$\nhttps://example.test/cost\\$25\n[literal](target)')

    def test_html_and_unsupported_code_are_explicit_errors(self):
        for source in ['<script>alert(1)</script>', '<div>Visible</div>', '<!-- secret -->',
                       '```python\nprint(123)\n```', '    print(123)', '[^1]: detail']:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    parse_markdown(source)
        self.assertEqual(parse_markdown('&lt;script&gt;visible&lt;/script&gt;')['text'], '<script>visible</script>')

    def test_unclosed_structures_fail_without_silent_loss(self):
        for source in ['$x_i', '$$x_i$', r'\(x_i', '```math\nx_i', '`a', '[label](missing',
                       '[label][unknown]', '```math\n\n```', '$$ $$']:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    parse_markdown(source)
        with self.assertRaisesRegex(ValueError, '嵌套过深'):
            parse_markdown('[' * 1000 + 'text' + ']' * 1000)

    def test_utf8_bom_newlines_and_original_source_are_preserved(self):
        uploaded = b'\xef\xbb\xbf# Example\r\n\r\nAnswer.'
        decoded = decode_markdown_upload(uploaded, 'test.markdown')
        self.assertEqual(decoded, '# Example\r\n\r\nAnswer.')
        source = '\ufeff# Example\r\n\r\nAnswer.'
        result = parse_markdown(source)
        self.assertEqual(result['text'], 'Example\n\nAnswer.')
        self.assertEqual(result['source_text'], source)

    def test_upload_limits_names_encoding_and_control_characters(self):
        for filename in ['answer.pdf', '../answer.md', 'C:\\answer.md', '.md', 'a.md\n', 'a.md:stream']:
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    decode_markdown_upload(b'Answer', filename)
        with self.assertRaisesRegex(ValueError, 'UTF-8'):
            decode_markdown_upload(b'\xff\xfeA\x00')
        with self.assertRaisesRegex(ValueError, '256 KB'):
            decode_markdown_upload(b'a' * (256 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, '100,000'):
            parse_markdown('a' * 100_001)
        with self.assertRaisesRegex(ValueError, '20,000'):
            parse_markdown('a' * 20_001)
        with self.assertRaisesRegex(ValueError, '控制字符'):
            parse_markdown('Answer\x00data')
        with self.assertRaisesRegex(ValueError, '没有可生成'):
            parse_markdown('   \n\n')


if __name__ == '__main__':
    unittest.main()

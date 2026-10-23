"""Math grammar and resource limits; no external TeX or handwriting data."""
import json
import unittest

from web.runtime.math_syntax import (
    MAX_DEPTH, MathSyntaxError, document_tokens, parse_math, required_glyphs,
)


def first(source):
    return parse_math(source)['children'][0]


class MathSyntax(unittest.TestCase):
    def test_scripts_both_orders_share_the_same_ast(self):
        self.assertEqual(parse_math('x_i^2'), parse_math('x^2_i'))
        script = first('x_i^2')
        self.assertEqual(script['base'], {'type': 'glyph', 'text': 'x'})
        self.assertEqual(script['sub']['text'], 'i')
        self.assertEqual(script['sup']['text'], '2')

    def test_nested_scripts_and_grouped_bases(self):
        nested = first(r'{x+y}_{i_{j+1}}^{n^2}')
        self.assertEqual(nested['base']['type'], 'sequence')
        self.assertEqual(nested['sub']['children'][0]['type'], 'script')
        self.assertEqual(nested['sup']['children'][0]['sup']['text'], '2')
        self.assertEqual(required_glyphs(nested), set('xy+ij1n2'))

    def test_fraction_and_indexed_nested_radical(self):
        node = first(r'\frac{a+b}{\sqrt[3]{x_{i+1}}}')
        self.assertEqual(node['type'], 'fraction')
        radical = node['denominator']['children'][0]
        self.assertEqual(radical['type'], 'radical')
        self.assertEqual(radical['index']['children'][0]['text'], '3')
        self.assertEqual(required_glyphs(node), set('ab+3xi1'))
        self.assertNotIn('√', required_glyphs(node))
        self.assertEqual(first(r'\sqrt{x}')['index'], None)
        self.assertEqual(first(r'\frac12')['denominator']['text'], '2')

    def test_named_operators_and_limits(self):
        expression = parse_math(r'\sum_{i=1}^n x_i+\prod_j y_j+\int_0^1 f(x)')
        self.assertEqual(expression['children'][0]['base'],
                         {'type': 'named_operator', 'name': 'sum', 'text': '∑', 'limits': True})
        for name in ('sin', 'cos', 'tan', 'log', 'ln', 'lim', 'max', 'min'):
            node = first('\\' + name)
            self.assertEqual(node['text'], name)
            self.assertEqual(node['limits'], name in ('lim', 'max', 'min'))
        self.assertEqual(first('∑'), first(r'\sum'))
        self.assertEqual(first('∫'), first(r'\int'))

    def test_literal_fences_and_left_right_scalable_fences(self):
        nested = first('[(x+1)]')
        self.assertEqual((nested['left'], nested['right']), ('[', ']'))
        self.assertEqual(nested['body']['children'][0]['type'], 'fence')
        self.assertEqual(first(r'\left(x+1\right)'), first('(x+1)'))
        node = first(r'\left.\frac{a}{b}\right|_0^1')
        self.assertEqual(node['base']['left'], '')
        self.assertEqual(node['base']['right'], '|')
        braces = first(r'\left\{x\right\}')
        self.assertEqual((braces['left'], braces['right']), ('{', '}'))

    def test_greek_unicode_and_operator_commands(self):
        self.assertEqual(parse_math(r'\alpha+\beta=\Gamma'), parse_math('α+β=Γ'))
        ast = parse_math(r'\theta\varepsilon\varphi\times\cdot\div\pm\leq\geq\neq\infty\to')
        self.assertEqual(required_glyphs(ast), set('θϵϕ×·÷±≤≥≠∞→'))
        self.assertEqual(parse_math(r'\lambda/\pi'), parse_math('λ/π'))

    def test_derivative_gradient_and_membership_aliases(self):
        self.assertEqual(parse_math(r'\frac{\partial f}{\partial x}\approx\nabla f'),
                         parse_math(r'\frac{∂f}{∂x}≈∇f'))
        self.assertEqual(parse_math(r'x\in A+y\notin B'), parse_math('x∈A+y∉B'))
        self.assertEqual(required_glyphs(parse_math(r'\partial\nabla\in\notin\approx')), set('∂∇∈∉≈'))

    def test_text_preserves_spaces_and_literal_scripts(self):
        node = first(r'\text{rate_1 per year}')
        text = ''.join(child['text'] for child in node['children'])
        self.assertEqual(text, 'rate_1 per year')
        self.assertNotIn(' ', required_glyphs(node))
        self.assertEqual(required_glyphs(parse_math(r'\text{cost \$5 and 10\%}')), set('cost$5and10%'))

    def test_roman_labels_retain_math_scripts_and_spaces(self):
        node = first(r'\mathrm{kg m^{-3}}')
        self.assertEqual(node['children'][2], {'type': 'glyph', 'text': ' '})
        self.assertEqual(node['children'][3]['type'], 'script')
        self.assertEqual(required_glyphs(node), set('kgm-3'))

    def test_ast_is_json_serializable_without_execution(self):
        source = r'\frac{\sin(\alpha)}{\sqrt{x^2+y^2}}'
        ast = parse_math(source)
        self.assertEqual(json.loads(json.dumps(ast)), ast)

    def test_missing_arguments_unclosed_groups_and_duplicate_scripts_rejected(self):
        for source in ('', ' ', '{x', 'x}', '(x]', '[x)', 'x)', 'x_', 'x^', '^2',
                       'x^2^3', 'x_i_j', r'\frac{x}', r'\frac{}{2}', r'\sqrt',
                       r'\sqrt[3{x}', r'\left(x', r'x\right)', r'\text{x',
                       r'\mathrm x', chr(92), '$x$', 'x\x00'):
            with self.subTest(source=source), self.assertRaises(MathSyntaxError):
                parse_math(source)

    def test_unknown_commands_files_macros_environments_and_linebreaks_rejected(self):
        for source in (r'\input{secret}', r'\include{secret}', r'\write18{cmd}',
                       r'\def\x{1}', r'\begin{matrix}a&b\end{matrix}', r'x\\y',
                       r'\unsupported{x}', r'\text{\input{secret}}', r'\left\foo x\right)'):
            with self.subTest(source=source), self.assertRaises(MathSyntaxError):
                parse_math(source)

    def test_expression_depth_length_and_node_limits(self):
        parse_math('{' * MAX_DEPTH + 'x' + '}' * MAX_DEPTH)
        with self.assertRaisesRegex(MathSyntaxError, 'nesting'):
            parse_math('{' * (MAX_DEPTH + 1) + 'x' + '}' * (MAX_DEPTH + 1))
        with self.assertRaisesRegex(MathSyntaxError, '2000'):
            parse_math(' ' * 2000 + 'x')
        with self.assertRaisesRegex(MathSyntaxError, 'node budget'):
            parse_math('x' * 1000)
        with self.assertRaises(MathSyntaxError):
            parse_math(None)


class DocumentMathTokens(unittest.TestCase):
    def test_disabled_math_preserves_ordinary_word_and_line_tokenization(self):
        self.assertEqual(document_tokens('A $x$\nB \\(y\\)'),
                         [{'text': 'A', 'space_before': False},
                          {'text': '$x$', 'space_before': True}, {'newline': True},
                          {'text': 'B', 'space_before': False},
                          {'text': '\\(y\\)', 'space_before': True}])

    def test_all_four_delimiter_forms_and_source_are_retained(self):
        records = document_tokens('A $x^2$\n$$\\frac{1}{2}$$\nB \\(y+1\\) \\[z_i\\]', True)
        math = [item for item in records if 'math' in item]
        self.assertEqual([item['source'] for item in math], ['x^2', r'\frac{1}{2}', 'y+1', 'z_i'])
        self.assertEqual([item['display_math'] for item in math], [False, True, False, True])
        self.assertEqual(sum('newline' in item for item in records), 2)
        self.assertEqual(records[0], {'text': 'A', 'space_before': False})

    def test_adjacent_math_and_prose_and_multiline_display(self):
        records = document_tokens('left$x$right\n$$x+\ny$$', True)
        self.assertEqual(records[0], {'text': 'left', 'space_before': False})
        self.assertEqual(records[2], {'text': 'right', 'space_before': False})
        self.assertEqual(records[3], {'newline': True})
        self.assertEqual(required_glyphs(records[4]['math']), set('x+y'))
        adjacent = document_tokens('$x$$y$', True)
        self.assertEqual([record['source'] for record in adjacent], ['x', 'y'])
        self.assertEqual([record['space_before'] for record in adjacent], [False, False])

    def test_escaped_dollar_is_literal_and_does_not_close_math(self):
        records = document_tokens(r'Cost \$5; $\text{cost \$5}$', True)
        self.assertEqual(records[1], {'text': '$5;', 'space_before': True})
        self.assertEqual(required_glyphs(records[2]['math']), set('cost$5'))

    def test_inline_math_adjacency_distinguishes_punctuation_and_word_spaces(self):
        records = document_tokens('Value $x$. $x$ is $(y)$,then $z$!', True)
        self.assertEqual([record['space_before'] for record in records],
                         [False, True, False, True, True, True, False, True, False])
        self.assertEqual([record.get('text', record.get('source')) for record in records],
                         ['Value', 'x', '.', 'x', 'is', '(y)', ',then', 'z', '!'])

    def test_boundary_flags_reset_at_newline_and_ignore_math_internal_spaces(self):
        records = document_tokens('A \t$x + y $B\nC\n  $z$ D', True)
        self.assertEqual([record.get('space_before') for record in records],
                         [False, True, False, None, False, None, True, True])
        self.assertEqual([record for record in records if record.get('newline')],
                         [{'newline': True}, {'newline': True}])

    def test_display_math_keeps_existing_breaks_and_has_source_boundary_flags(self):
        records = document_tokens('Intro\n$$ x+\ny $$\n\nAfter', True)
        self.assertEqual([record.get('space_before') for record in records],
                         [False, None, False, None, None, False])
        self.assertTrue(records[2]['display_math'])
        self.assertEqual(required_glyphs(records[2]['math']), set('x+y'))

    def test_horizontal_whitespace_boundaries_are_retained_without_extra_tokens(self):
        records = document_tokens('  A\tB\u00a0C\r\nD')
        self.assertEqual(records, [
            {'text': 'A', 'space_before': True}, {'text': 'B', 'space_before': True},
            {'text': 'C', 'space_before': True}, {'newline': True},
            {'text': 'D', 'space_before': False}])

    def test_unclosed_unmatched_empty_and_nested_delimiters_rejected(self):
        for source in ('$x', '$$x$', r'\(x', r'\[x', r'x\)', r'x\]',
                       '$$', '$$$$', r'$x\(y\)$'):
            with self.subTest(source=source), self.assertRaises(MathSyntaxError):
                document_tokens(source, True)


if __name__ == '__main__':
    unittest.main()

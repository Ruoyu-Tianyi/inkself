"""Bounded math notation parser; never invokes TeX, a shell, or Python evaluation.

ASTs contain JSON values only. Fraction bars, radical strokes and scalable fences
are renderer responsibilities. Unsupported TeX commands fail explicitly.
"""
from __future__ import annotations

import re

MAX_EXPRESSION_LENGTH = 2000
MAX_DEPTH = 16
MAX_NODES = 1000

GREEK = {
    'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ε',
    'zeta': 'ζ', 'eta': 'η', 'theta': 'θ', 'iota': 'ι', 'kappa': 'κ',
    'lambda': 'λ', 'mu': 'μ', 'nu': 'ν', 'xi': 'ξ', 'omicron': 'ο',
    'pi': 'π', 'rho': 'ρ', 'sigma': 'σ', 'tau': 'τ', 'upsilon': 'υ',
    'phi': 'φ', 'chi': 'χ', 'psi': 'ψ', 'omega': 'ω',
    'varepsilon': 'ϵ', 'vartheta': 'ϑ', 'varpi': 'ϖ', 'varrho': 'ϱ',
    'varsigma': 'ς', 'varphi': 'ϕ', 'varkappa': 'ϰ',
}
GREEK.update({name[0].upper() + name[1:]: char.upper()
              for name, char in list(GREEK.items()) if not name.startswith('var')})
SYMBOL_COMMANDS = {
    **GREEK, 'times': '×', 'cdot': '·', 'div': '÷', 'pm': '±',
    'leq': '≤', 'le': '≤', 'geq': '≥', 'ge': '≥', 'neq': '≠', 'ne': '≠',
    'infty': '∞', 'to': '→', 'rightarrow': '→',
    'partial': '∂', 'nabla': '∇', 'in': '∈', 'notin': '∉', 'approx': '≈',
}
OPERATORS = {name: (name, name in {'lim', 'max', 'min'})
             for name in ('sin', 'cos', 'tan', 'log', 'ln', 'lim', 'max', 'min')}
OPERATORS.update({'sum': ('∑', True), 'prod': ('∏', True), 'int': ('∫', True)})
UNICODE_OPERATORS = {text: name for name, (text, _) in OPERATORS.items() if len(text) == 1}
DELIMITER_COMMANDS = {'lbrace': '{', 'rbrace': '}', 'langle': '⟨', 'rangle': '⟩',
                      'vert': '|', 'lvert': '|', 'rvert': '|',
                      'Vert': '‖', 'lVert': '‖', 'rVert': '‖'}
ESCAPES = {'{': '{', '}': '}', '%': '%', '_': '_', '#': '#', '&': '&', '$': '$', '|': '‖'}
SPACING = {',', ';', ':', '!', ' '}


class MathSyntaxError(ValueError):
    """Invalid or deliberately unsupported notation, with a character offset."""


class _Parser:
    def __init__(self, source):
        self.source = source
        self.position = 0
        self.nodes = 0

    def error(self, message):
        raise MathSyntaxError(f'{message} at character {self.position + 1}.')

    def depth(self, depth):
        if depth > MAX_DEPTH:
            self.error(f'Math nesting exceeds {MAX_DEPTH}')

    def node(self, kind, **fields):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            self.error(f'Math node budget exceeds {MAX_NODES}')
        return {'type': kind, **fields}

    def space(self):
        while self.position < len(self.source) and self.source[self.position].isspace():
            self.position += 1

    def starts_command(self, name):
        marker = '\\' + name
        end = self.position + len(marker)
        return (self.source.startswith(marker, self.position)
                and (end == len(self.source) or not self.source[end].isascii()
                     or not self.source[end].isalpha()))

    def command(self):
        self.position += 1  # Backslash already inspected by the caller.
        if self.position >= len(self.source):
            self.error('Trailing backslash')
        start = self.position
        while self.position < len(self.source) and self.source[self.position] in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
            self.position += 1
        if self.position == start:
            self.position += 1
        return self.source[start:self.position]

    def sequence(self, depth=0, closing=None, right=False, preserve_space=False):
        self.depth(depth)
        children = []
        while True:
            before_space = self.position
            self.space()
            if preserve_space and self.position > before_space:
                children.append(self.node('glyph', text=' '))
            if self.position == len(self.source):
                if closing or right:
                    self.error('Unclosed math group or fence')
                break
            char = self.source[self.position]
            if closing and char == closing:
                break
            if right and self.starts_command('right'):
                break
            if char in '})]' or self.starts_command('right'):
                self.error('Unexpected closing math delimiter')
            if char in '^_':
                self.error('A script requires a base')
            base = self.atom(depth)
            sub = sup = None
            while True:
                before_space = self.position
                self.space()
                if self.position == len(self.source) or self.source[self.position] not in '^_':
                    if preserve_space:
                        self.position = before_space
                    break
                marker = self.source[self.position]
                self.position += 1
                if marker == '^':
                    if sup is not None:
                        self.error('Duplicate superscript; use braces for nesting')
                    sup = self.argument(depth + 1)
                else:
                    if sub is not None:
                        self.error('Duplicate subscript; use braces for nesting')
                    sub = self.argument(depth + 1)
            if sub is not None or sup is not None:
                base = self.node('script', base=base, sub=sub, sup=sup)
            children.append(base)
        if not children:
            self.error('Empty math expression or group')
        return self.node('sequence', children=children)

    def argument(self, depth):
        self.depth(depth)
        self.space()
        if self.position >= len(self.source) or self.source[self.position] in '^_})]':
            self.error('Missing math argument')
        return self.atom(depth)

    def group(self, depth, opening='{', closing='}', preserve_space=False):
        self.depth(depth)
        self.space()
        if self.position == len(self.source) or self.source[self.position] != opening:
            self.error(f'Expected {opening}')
        self.position += 1
        body = self.sequence(depth, closing=closing, preserve_space=preserve_space)
        self.position += 1
        return body

    def delimiter(self):
        self.space()
        if self.position >= len(self.source):
            self.error('Missing fence delimiter')
        char = self.source[self.position]
        if char == '\\':
            name = self.command()
            if name in DELIMITER_COMMANDS:
                return DELIMITER_COMMANDS[name]
            if name in ('{', '}', '|'):
                return ESCAPES[name]
            self.error('Unsupported fence delimiter')
        self.position += 1
        if char == '.':
            return ''
        if char not in '()[]|⟨⟩‖':
            self.error('Unsupported fence delimiter')
        return char

    def literal_text(self, depth):
        self.depth(depth)
        self.space()
        if self.position == len(self.source) or self.source[self.position] != '{':
            self.error('Text requires a braced group')
        self.position += 1
        children = []
        while self.position < len(self.source) and self.source[self.position] != '}':
            char = self.source[self.position]
            if char == '{':
                children.append(self.literal_text(depth + 1))
                continue
            if char == '\\':
                name = self.command()
                if name not in ESCAPES and name not in SPACING:
                    self.error('Unsupported command inside text')
                char = ESCAPES.get(name, ' ')
            else:
                self.position += 1
            if ord(char) < 32 and not char.isspace():
                self.error('Control characters are not supported')
            children.append(self.node('glyph', text=' ' if char.isspace() else char))
        if self.position == len(self.source):
            self.error('Unclosed text group')
        self.position += 1
        if not children:
            self.error('Empty text group')
        return self.node('sequence', children=children)

    def atom(self, depth):
        self.depth(depth)
        self.space()
        if self.position >= len(self.source):
            self.error('Missing math atom')
        char = self.source[self.position]
        if char == '{':
            return self.group(depth + 1)
        if char in '([':
            self.position += 1
            closing = ')' if char == '(' else ']'
            body = self.sequence(depth + 1, closing=closing)
            self.position += 1
            return self.node('fence', left=char, right=closing, body=body)
        if char in '^_})]$':
            self.error('Unexpected math delimiter or script')
        if char == '\\':
            name = self.command()
            if name in SYMBOL_COMMANDS:
                return self.node('glyph', text=SYMBOL_COMMANDS[name])
            if name in OPERATORS:
                text, limits = OPERATORS[name]
                return self.node('named_operator', name=name, text=text, limits=limits)
            if name in ESCAPES:
                return self.node('glyph', text=ESCAPES[name])
            if name in SPACING:
                return self.node('glyph', text=' ')
            if name == 'frac':
                numerator = self.argument(depth + 1)
                denominator = self.argument(depth + 1)
                return self.node('fraction', numerator=numerator, denominator=denominator)
            if name == 'sqrt':
                self.space()
                index = self.group(depth + 1, '[', ']') if self.position < len(self.source) and self.source[self.position] == '[' else None
                return self.node('radical', body=self.argument(depth + 1), index=index)
            if name == 'left':
                left = self.delimiter()
                body = self.sequence(depth + 1, right=True)
                if not self.starts_command('right'):
                    self.error('Missing \\right')
                self.command()
                return self.node('fence', left=left, right=self.delimiter(), body=body)
            if name == 'mathrm':
                # Keep mathematical scripts/commands while retaining label spaces.
                return self.group(depth + 1, preserve_space=True)
            if name == 'text':
                return self.literal_text(depth + 1)
            self.error(f'Unsupported math command \\{name}')
        if ord(char) < 32:
            self.error('Control characters are not supported')
        self.position += 1
        if char in UNICODE_OPERATORS:
            name = UNICODE_OPERATORS[char]
            return self.node('named_operator', name=name, text=char, limits=True)
        return self.node('glyph', text=char)


def parse_math(text):
    """Parse a math expression without its document-level delimiters."""
    if not isinstance(text, str):
        raise MathSyntaxError('Math expression must be text.')
    if len(text) > MAX_EXPRESSION_LENGTH:
        raise MathSyntaxError(f'Math expression exceeds {MAX_EXPRESSION_LENGTH} characters.')
    return _Parser(text).sequence()


def required_glyphs(ast):
    """Rendered characters only; fraction/radical strokes are drawn structurally."""
    kind = ast['type']
    if kind in ('glyph', 'named_operator'):
        return {char for char in ast['text'] if not char.isspace()}
    if kind == 'sequence':
        return set().union(*(required_glyphs(child) for child in ast['children']))
    if kind == 'script':
        result = required_glyphs(ast['base'])
        for key in ('sub', 'sup'):
            if ast.get(key) is not None:
                result.update(required_glyphs(ast[key]))
        return result
    if kind == 'fraction':
        return required_glyphs(ast['numerator']) | required_glyphs(ast['denominator'])
    if kind == 'radical':
        return required_glyphs(ast['body']) | (required_glyphs(ast['index']) if ast.get('index') is not None else set())
    if kind == 'fence':
        return required_glyphs(ast['body']) | set(ast['left'] + ast['right'])
    raise MathSyntaxError('Unknown math AST node type.')


def document_tokens(text, math_enabled=False):
    """Tokenize prose plus explicitly delimited math, retaining prose newlines.

    source is the expression inside its delimiters. Escaped dollars in enabled
    prose are literal dollars. Turning math off preserves the previous tokenizer.
    """
    if not isinstance(text, str):
        raise MathSyntaxError('Document must be text.')
    def prose(chunk):
        return [{'newline': True} if word == '\n' else {'text': word}
                for word in re.findall(r'\n|[^\s]+', chunk)]
    if not math_enabled:
        return prose(text)
    records = []
    pending = []
    position = 0
    while position < len(text):
        if text.startswith('\\$', position):
            pending.append('$');position += 2;continue
        opening = next((item for item in ('$$', '\\(', '\\[', '$') if text.startswith(item, position)), None)
        if opening is None:
            if text.startswith(('\\)', '\\]'), position):
                raise MathSyntaxError(f'Unexpected closing math delimiter at character {position + 1}.')
            pending.append(text[position]);position += 1;continue
        records.extend(prose(''.join(pending)));pending = []
        closing = {'$$': '$$', '$': '$', '\\(': '\\)', '\\[': '\\]'}[opening]
        start = position + len(opening)
        end = start
        while end < len(text):
            if text.startswith(closing, end):
                break
            if text[end] == '\\':
                end += 2  # Do not confuse escaped dollars with delimiters.
            else:
                end += 1
        if end >= len(text):
            raise MathSyntaxError(f'Unclosed math delimiter at character {position + 1}.')
        source = text[start:end]
        records.append({'math': parse_math(source), 'source': source,
                        'display_math': opening in ('$$', '\\[')})
        position = end + len(closing)
    records.extend(prose(''.join(pending)))
    return records

"""Bounded Markdown-to-handwriting conversion, without HTML or link execution.

This is an intentionally small document importer, not an HTML renderer. It keeps
visible text and mathematical notation for the existing generation preview.
Unsupported structures fail explicitly rather than dropping their contents.
"""
from __future__ import annotations

import html
import re
import string


MAX_UPLOAD_BYTES = 256 * 1024
MAX_SOURCE_CHARACTERS = 100_000
MAX_OUTPUT_CHARACTERS = 20_000
_SLOT = re.compile('\x00([0-9]+)\x00')
_ESCAPABLE = set(string.punctuation)
_FENCE = re.compile(r'^[ ]{0,3}(`{3,}|~{3,})[ \t]*([^\n]*)$')
_LIST = re.compile(r'^(\s*)([-+*]|[0-9]{1,9}[.)])[ \t]+(.*)$')
_REFERENCE = re.compile(r'^[ ]{0,3}\[([^\]\n]+)\]:[ \t]*(\S.*)$')


def _filename(filename):
    if (not isinstance(filename, str) or not filename or len(filename) > 255
            or filename != filename.strip() or any(c in filename for c in '/\\:\x00')
            or any(ord(c) < 32 for c in filename)
            or not re.fullmatch(r'.+\.(?:md|markdown)', filename, re.IGNORECASE)):
        raise ValueError('请上传名称以 .md 或 .markdown 结尾的 Markdown 文件。')
    return filename


def decode_markdown_upload(content, filename='document.md'):
    """Decode a size-limited UTF-8 upload, accepting an initial UTF-8 BOM only."""
    _filename(filename)
    if not isinstance(content, (bytes, bytearray)):
        raise ValueError('Markdown 上传内容必须是字节数据。')
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError('Markdown 文件不能超过 256 KB。')
    try:
        text = bytes(content).decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError('Markdown 文件必须使用 UTF-8 编码；请重新保存后上传。') from error
    if len(text) > MAX_SOURCE_CHARACTERS:
        raise ValueError('Markdown 源文件不能超过 100,000 个字符。')
    return text


def _reference_key(value):
    return ' '.join(value.split()).casefold()


class _Document:
    def __init__(self):
        self.slots = []
        self.references = {}
        self.warnings = []
        self.summary = {name: 0 for name in (
            'headings', 'lists', 'list_items', 'tables', 'table_rows', 'math',
            'inline_math', 'display_math', 'links', 'images', 'blockquotes',
            'code_blocks', 'inline_code', 'paragraphs', 'characters', 'source_characters')}

    def warn(self, value):
        if value not in self.warnings:
            self.warnings.append(value)

    def slot(self, value, kind='literal'):
        marker = f'\x00{len(self.slots)}\x00'
        self.slots.append((value, kind))
        return marker

    def formula(self, value, display):
        self.summary['math'] += 1
        self.summary['display_math' if display else 'inline_math'] += 1
        return self.slot(value, 'math')

    def fenced_blocks(self, source):
        lines = source.split('\n')
        result = []
        index = 0
        while index < len(lines):
            match = _FENCE.fullmatch(lines[index])
            if not match:
                result.append(lines[index])
                index += 1
                continue
            fence, info = match.groups()
            language = info.strip().casefold()
            if language not in ('math', 'latex', 'tex'):
                raise ValueError('暂不支持普通代码块。请将需要手写的内容改为正文；公式代码块请标记 math 或 latex。')
            closing = re.compile(r'^[ ]{0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}[ \t]*$')
            end = index + 1
            while end < len(lines) and not closing.fullmatch(lines[end]):
                end += 1
            if end == len(lines):
                raise ValueError('数学代码块未闭合，请补上结束标记。')
            body = '\n'.join(lines[index + 1:end])
            if not body.strip():
                raise ValueError('数学代码块不能为空。')
            if '$$' in body or r'\[' in body or r'\]' in body:
                raise ValueError('数学代码块内请直接写公式，不要再次添加公式分隔符。')
            result.extend(['', self.formula('$$\n' + body + '\n$$', True), ''])
            self.summary['code_blocks'] += 1
            index = end + 1
        return '\n'.join(result)

    def reference_definitions(self, source):
        result = []
        for line in source.split('\n'):
            if re.match(r'^[ ]{0,3}\[\^', line):
                raise ValueError('暂不支持脚注，请将脚注内容移到正文后再导入。')
            match = _REFERENCE.fullmatch(line)
            if match:
                self.references.setdefault(_reference_key(match[1]), match[2])
                result.append('')
            else:
                result.append(line)
        return '\n'.join(result)

    def protect_inline(self, source, depth=0):
        """Protect math, escaped punctuation, entities and inline code first."""
        if depth > 16:
            raise ValueError('Markdown 行内结构嵌套过深，请简化格式。')
        output = []
        position = 0
        while position < len(source):
            existing = _SLOT.match(source, position)
            if existing:
                output.append(existing[0])
                position = existing.end()
                continue
            char = source[position]
            if char == '`':
                end_run = position + 1
                while end_run < len(source) and source[end_run] == '`':
                    end_run += 1
                run = source[position:end_run]
                end = source.find(run, end_run)
                while end >= 0 and ((end > 0 and source[end - 1] == '`')
                                    or (end + len(run) < len(source) and source[end + len(run)] == '`')):
                    end = source.find(run, end + len(run))
                if end < 0:
                    raise ValueError('行内代码标记未闭合，请检查反引号。')
                body = source[end_run:end].replace('\n', ' ')
                if body.startswith(' ') and body.endswith(' ') and body.strip():
                    body = body[1:-1]
                output.append(self.slot(body))
                self.summary['inline_code'] += 1
                self.warn('行内代码已转换为普通文字；代码不会执行，也不保留等宽字体。')
                position = end + len(run)
                continue
            if char == '[':
                end = self.closing(source, position, '[', ']')
                if end is not None and end + 1 < len(source) and source[end + 1] == '(':
                    destination_end = self.closing(source, end + 1, '(', ')')
                    if destination_end is None:
                        raise ValueError('Markdown 链接未闭合，请检查链接地址的括号。')
                    # Destinations are not rendered. Do not interpret dollars,
                    # HTML or backticks in a URL as document markup or math.
                    label = self.protect_inline(source[position + 1:end], depth + 1)
                    output.append('[' + label + '](' + self.slot(source[end + 2:destination_end], 'destination') + ')')
                    position = destination_end + 1
                    continue
            if char == '<':
                autolink = re.match(r'<((?:(?:https?://|mailto:)[^\s<>]+)|(?:[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+))>', source[position:], re.IGNORECASE)
                if autolink:
                    output.append(self.slot(autolink[1].removeprefix('mailto:')))
                    self.summary['links'] += 1
                    position += len(autolink[0])
                    continue
            opening = next((marker for marker in ('$$', r'\(', r'\[', '$') if source.startswith(marker, position)), None)
            if opening:
                closing = {'$$': '$$', '$': '$', r'\(': r'\)', r'\[': r'\]'}[opening]
                start = position + len(opening)
                end = start
                while end < len(source):
                    if source.startswith(closing, end):
                        break
                    end += 2 if source[end] == '\\' else 1
                if end >= len(source):
                    raise ValueError('公式分隔符未闭合；金额中的美元符号请写为 \\$。')
                if not source[start:end].strip():
                    raise ValueError('公式不能为空。')
                finish = end + len(closing)
                output.append(self.formula(source[position:finish], opening in ('$$', r'\[')))
                position = finish
                continue
            if char == '\\' and position + 1 < len(source) and source[position + 1] == '\n':
                output.append('\n')
                position += 2
                continue
            if char == '\\' and position + 1 < len(source) and source[position + 1] in _ESCAPABLE:
                output.append(self.slot(source[position + 1]))
                position += 2
                continue
            if char == '&':
                entity = re.match(r'&(?:#[xX][0-9a-fA-F]+|#[0-9]+|[A-Za-z][A-Za-z0-9]+);', source[position:])
                if entity:
                    output.append(self.slot(html.unescape(entity[0])))
                    position += len(entity[0])
                    continue
            output.append(char)
            position += 1
        return ''.join(output)

    @staticmethod
    def closing(text, start, opening, closing):
        depth = 1
        index = start + 1
        while index < len(text):
            if text[index] == '\\':
                index += 2
                continue
            if text[index] == opening:
                depth += 1
                if depth > 16:
                    raise ValueError('Markdown 行内结构嵌套过深，请简化格式。')
            elif text[index] == closing:
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return None

    def inline(self, source, depth=0):
        if depth > 16:
            raise ValueError('Markdown 行内结构嵌套过深，请简化格式。')
        output = []
        position = 0
        while position < len(source):
            image = source.startswith('![', position)
            if image or source[position] == '[':
                start = position + int(image)
                end = self.closing(source, start, '[', ']')
                if end is not None:
                    finish = end + 1
                    linked = False
                    if finish < len(source) and source[finish] == '(':
                        destination_end = self.closing(source, finish, '(', ')')
                        if destination_end is None:
                            raise ValueError('Markdown 链接未闭合，请检查链接地址的括号。')
                        finish, linked = destination_end + 1, True
                    elif finish < len(source) and source[finish] == '[':
                        reference_end = source.find(']', finish + 1)
                        if reference_end is None:
                            raise ValueError('Markdown 引用链接未闭合。')
                        label = source[finish + 1:reference_end] or source[start + 1:end]
                        if _reference_key(label) not in self.references:
                            raise ValueError('Markdown 引用链接未定义，请补全链接定义。')
                        finish, linked = reference_end + 1, True
                    elif _reference_key(source[start + 1:end]) in self.references:
                        linked = True
                    if linked:
                        visible = self.inline(source[start + 1:end], depth + 1)
                        if image and not visible.strip():
                            raise ValueError('图片没有替代文字，无法转换为手写内容；请补充 alt 描述。')
                        output.append(visible)
                        self.summary['images' if image else 'links'] += 1
                        if image:
                            self.warn('图片仅保留替代文字（alt），不会读取、下载或嵌入图片。')
                        position = finish
                        continue
            if source[position] == '<':
                end = source.find('>', position + 1)
                body = source[position + 1:end] if end >= 0 else ''
                if end >= 0 and (re.fullmatch(r'(?:https?://|mailto:)[^\s<>]+', body, re.IGNORECASE)
                                 or re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+', body)):
                    output.append(body.removeprefix('mailto:'))
                    self.summary['links'] += 1
                    position = end + 1
                    continue
                if re.match(r'(?:/?[A-Za-z][\w:-]*(?:\s|/?>)|!--|!DOCTYPE|\?)', source[position + 1:], re.IGNORECASE):
                    raise ValueError('暂不支持 HTML，请改成 Markdown 或普通文字后导入。HTML 不会执行。')
            output.append(source[position])
            position += 1
        value = ''.join(output)
        # Formatting is removed only around non-whitespace text. Intraword
        # underscores (such as x_i and file_name) remain literal prose.
        for _ in range(4):
            before = value
            for marker in ('***', '___', '**', '__', '*', '_', '~~'):
                escaped = re.escape(marker)
                pattern = (r'(?<![\w])' if '_' in marker else '') + escaped + r'(?=\S)(.+?\S|\S)' + escaped
                if '_' in marker:
                    pattern += r'(?![\w])'
                value, substitutions = re.subn(pattern, lambda match: match[1], value)
                if marker == '~~' and substitutions:
                    self.warn('删除线样式已去除，划掉的文字仍保留在预览中，请确认是否需要生成。')
            if value == before:
                break
        return value

    @staticmethod
    def cells(line):
        value = line.strip()
        if value.startswith('|'):
            value = value[1:]
        if value.endswith('|'):
            value = value[:-1]
        return [cell.strip() for cell in value.split('|')]

    def table_start(self, lines, index):
        if index + 1 >= len(lines) or '|' not in lines[index]:
            return False
        cells = self.cells(lines[index + 1])
        return bool(cells) and all(re.fullmatch(r':?-{3,}:?', cell) for cell in cells)

    def blocks(self, source):
        lines = source.split('\n')
        output = []
        index = 0
        in_list = False
        while index < len(lines):
            line = lines[index]
            if self.table_start(lines, index):
                headers = self.cells(line)
                if len(headers) != len(self.cells(lines[index + 1])):
                    raise ValueError('Markdown 表格的表头列数与分隔行不一致。')
                output.append('; '.join(self.inline(cell) for cell in headers))
                self.summary['tables'] += 1
                self.warn('表格已转换为逐行文字，列之间使用分号；不保留表格线、列宽和对齐方式。')
                index += 2
                while index < len(lines) and lines[index].strip() and '|' in lines[index]:
                    cells = self.cells(lines[index])
                    if len(cells) != len(headers):
                        raise ValueError('Markdown 表格各行列数不一致，请检查后再导入。')
                    output.append('; '.join(self.inline(cell) for cell in cells))
                    self.summary['table_rows'] += 1
                    index += 1
                in_list = False
                continue
            if not line.strip():
                output.append('')
                in_list = False
                index += 1
                continue
            if (index + 1 < len(lines) and re.fullmatch(r'[ ]{0,3}(?:=+|-+)[ \t]*', lines[index + 1])
                    and not _LIST.match(line)):
                output.append(self.inline(line.strip()))
                self.summary['headings'] += 1
                index += 2
                in_list = False
                continue
            heading = re.match(r'^[ ]{0,3}(#{1,6})(?:[ \t]+|$)(.*)$', line)
            if heading:
                title = re.sub(r'[ \t]+#+[ \t]*$', '', heading[2])
                output.append(self.inline(title))
                self.summary['headings'] += 1
                in_list = False
                index += 1
                continue
            if re.fullmatch(r'[ ]{0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})', line):
                output.append('')
                self.warn('Markdown 分隔线已转换为空行。')
                in_list = False
                index += 1
                continue
            quote = re.match(r'^[ ]{0,3}(?:>[ \t]?)+(.*)$', line)
            if quote:
                output.append(self.inline(quote[1]))
                self.summary['blockquotes'] += 1
                self.warn('引用块已保留为普通段落，不保留引用边框和缩进。')
                in_list = False
                index += 1
                continue
            item = _LIST.match(line)
            if item:
                if not in_list:
                    self.summary['lists'] += 1
                self.summary['list_items'] += 1
                indent, marker, body = item.groups()
                task = re.match(r'^\[([ xX])\][ \t]+(.*)$', body)
                if task:
                    body = ('Done: ' if task[1].lower() == 'x' else 'To do: ') + task[2]
                    self.warn('任务列表勾选状态已转换为 Done / To do 文字。')
                output.append(indent + ('-' if marker in ('*', '+') else marker) + ' ' + self.inline(body))
                if indent:
                    self.warn('嵌套列表保留文字与编号；手写排版可能按普通段落处理缩进。')
                in_list = True
                index += 1
                continue
            if re.match(r'^(?: {4}|\t)', line) and not in_list and (not output or not output[-1].strip()) and not line.lstrip().startswith('\x00'):
                raise ValueError('暂不支持缩进代码块，请将需要手写的内容改为普通正文。')
            output.append(self.inline(line.rstrip()))
            index += 1
        return '\n'.join(output)

    def restore(self, source):
        math_enabled = self.summary['math'] > 0
        def replace(match):
            value, kind = self.slots[int(match[1])]
            if kind == 'literal' and math_enabled:
                if any(marker in value for marker in (r'\(', r'\)', r'\[', r'\]')):
                    raise ValueError('含公式的文档暂不支持把公式分隔符作为行内代码；请改写这段文字。')
                return value.replace('$', r'\$')
            return value
        return _SLOT.sub(replace, source)


def parse_markdown(text, filename='document.md'):
    """Return a JSON-ready preview; original input is retained as source_text.

    No links are opened, no local assets are read and no HTML or code is run.
    Formulas keep their original delimiters, escapes and mathematical symbols.
    """
    _filename(filename)
    if not isinstance(text, str):
        raise ValueError('Markdown 内容必须是 UTF-8 文字。')
    if len(text) > MAX_SOURCE_CHARACTERS:
        raise ValueError('Markdown 源文件不能超过 100,000 个字符。')
    if any(ord(char) < 32 and char not in '\n\r\t' for char in text):
        raise ValueError('Markdown 含有不支持的控制字符。')
    original = text
    normalized = text.removeprefix('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    document = _Document()
    protected = document.fenced_blocks(normalized)
    protected = document.reference_definitions(protected)
    protected = document.protect_inline(protected)
    converted = document.restore(document.blocks(protected)).strip()
    # Empty formatting lines can produce extra whitespace, but paragraphs and
    # explicit line breaks remain visible in the preview and generator input.
    converted = re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', converted)
    if not converted:
        raise ValueError('Markdown 转换后没有可生成的文字。')
    if len(converted) > MAX_OUTPUT_CHARACTERS:
        raise ValueError('转换后的正文不能超过 20,000 个字符，请拆分文档后导入。')
    document.summary.update(characters=len(converted), source_characters=len(original),
                            paragraphs=len(re.findall(r'\S(?:[^\n]|\n(?![ \t]*\n))*', converted)))
    return {'filename': filename, 'source_text': original, 'text': converted,
            'math_enabled': document.summary['math'] > 0,
            'warnings': document.warnings, 'summary': document.summary}

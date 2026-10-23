"""Versioned sampling content; math originals are reviewed separately from style lines."""
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


PROMPT_ID = 'english-numbers-math-v2'
LEGACY_PROMPT_ID = 'english-numbers-v1'
PROMPT_LINES = [
    'The quick brown fox jumps over the lazy dog.',
    'Bright mornings bring fresh ideas, quiet thoughts and new beginnings.',
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz',
    'Today I wrote 0123456789, then 27 + 58 = 85 and 120 - 45 = 75.',
    'We paid 24.50 for 3 books; the discount was 15%. Is that right?',
]
MATH_LINES = [
    '+ − × ÷ = ≠ ≈ < > ≤ ≥ ± % ( ) [ ] { }',
    '√x  √(a + b)  ∑  ∏  ∫  ∞  ∂  ∇',
    'α β γ δ ε ζ η θ ι κ λ μ ν ξ ο π ρ σ τ υ φ χ ψ ω',
    'Γ Δ Θ Λ Ξ Π Σ Υ Φ Ψ Ω',
    'xᵢ² + yⱼ² = r²;  aₙ₊₁ = α aₙ + β;  πr²',
]
INSTRUCTIONS = '自然书写，不必刻意工整，也不要刻意把词间距写成相等。深色笔、浅色纸，每句话一行，保持行间距；拍摄整段，避免阴影和反光。'
MATH_INSTRUCTIONS = '需要写公式时，建议再抄写下面五行。数学行与英文行分开，保留自然写法；上传后将这些行标为“数学/希腊字母”。不熟悉的符号可跳过。'
MATH_LIMIT = '数学行会保存在个人档案中，不送入英文少样本编码器。当前仍需核对、定位并建立字形库，上传后不会自动学会个人数学写法。'


def prompt_payload():
    return {
        'id': PROMPT_ID,
        'lines': list(PROMPT_LINES),
        'instructions': INSTRUCTIONS,
        'sections': [
            {'id': 'english-numbers', 'title': '英文与数字', 'optional': False,
             'purpose': 'style', 'lines': list(PROMPT_LINES), 'instructions': INSTRUCTIONS},
            {'id': 'math-greek', 'title': '数学符号与希腊字母', 'optional': True,
             'purpose': 'math', 'lines': list(MATH_LINES),
             'instructions': MATH_INSTRUCTIONS, 'limitation': MATH_LIMIT},
        ],
    }


_SUBSCRIPT = dict(zip('₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ᵢⱼₙ', '0123456789+-=()ijn'))
_SUPERSCRIPT = dict(zip('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾', '0123456789+-=()'))


def _sample_line(pdf, text, x, y, size=12):
    """Embed a licensed Unicode font and retain readable script baselines."""
    for character in text:
        glyph, font_size, baseline = character, size, y
        if character in _SUBSCRIPT:
            glyph, font_size, baseline = _SUBSCRIPT[character], size * .7, y - size * .22
        elif character in _SUPERSCRIPT:
            glyph, font_size, baseline = _SUPERSCRIPT[character], size * .7, y + size * .4
        pdf.setFont('InkselfCapture', font_size)
        pdf.drawString(x, baseline, glyph)
        x += pdfmetrics.stringWidth(glyph, 'InkselfCapture', font_size)
    return x


def write_sampling_guide(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if 'InkselfCapture' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('InkselfCapture', str(Path(__file__).parent/'static/fonts/DejaVuSans.ttf')))
    pdf = canvas.Canvas(str(path), pagesize=(595.2756, 841.8898))
    pdf.setTitle('Inkself sampling guide - English, numbers and optional mathematics')
    pages = [
        ('1. English and numbers', PROMPT_LINES,
         ['Copy these five lines in your usual handwriting; keep your natural word spacing.',
          'Use dark ink, plain paper and a clear gap between lines. Photograph your writing only.',
          'After upload, mark these lines as English / numbers.'], 10),
        ('2. Mathematics and Greek (optional)', MATH_LINES,
         ['For formula writing, copy these rows separately. Skip symbols you do not normally use.',
          'Keep the shape, spacing, scripts and connections you normally write. Do not trace the print.',
          'After upload, mark these rows as Mathematics / Greek; they are not English style input.',
          'Personal math shapes still need alignment and glyph review before use.'], 14),
    ]
    for page_index, (title, lines, instructions, size) in enumerate(pages):
        if page_index:
            pdf.showPage()
        pdf.setFillColorRGB(.15, .2, .17)
        pdf.setFont('Helvetica-Bold', 20)
        pdf.drawString(44, 787, title)
        pdf.setFont('Helvetica', 9)
        for index, instruction in enumerate(instructions):
            pdf.drawString(44, 763 - index * 15, instruction)
        y = 675
        for line in lines:
            _sample_line(pdf, line, 44, y, size)
            pdf.setStrokeColorRGB(.82, .82, .8)
            pdf.line(44, y - 62, 551, y - 62)
            y -= 112
        pdf.setFont('Helvetica', 8)
        pdf.setFillColorRGB(.4, .43, .4)
        pdf.drawString(44, 42, f'Inkself / {PROMPT_ID} / {page_index + 1} of 2')
    pdf.save()
    return path

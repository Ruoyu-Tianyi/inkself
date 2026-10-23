"""Shared preflight for ordinary text and explicitly delimited mathematics."""
from .math_syntax import document_tokens, required_glyphs


def prepare_document(text, bank, math_enabled=False, allow_supplemental=False):
    from .math_glyphs import SUPPORTED_GLYPHS
    tokens=document_tokens(text,math_enabled)
    supplements=set()
    for token in tokens:
        if 'math' in token:
            required=required_glyphs(token['math'])
            if not required:
                raise ValueError('公式不能为空。')
            missing=required-set(bank['glyphs'])
            unsupported=missing-set(SUPPORTED_GLYPHS)
            if unsupported:
                raise ValueError('Unsupported mathematical characters: '+''.join(sorted(unsupported)))
            if missing and not allow_supplemental:
                raise ValueError('原稿未采集这些数学字形：'+''.join(sorted(missing))+'。可启用配套手写字形，或补采样后再生成。')
            supplements.update(missing)
        elif 'text' in token:
            if len(token['text'])>32:
                raise ValueError('单个连续词不能超过 32 个字符，请增加空格。')
            missing=set(token['text'])-set(bank['glyphs'])
            if missing:
                raise ValueError('当前字迹不支持这些正文字符：'+''.join(sorted(missing)))
    return tokens,sorted(supplements)

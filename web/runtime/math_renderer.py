"""Layout a safe mathematical AST using personal glyphs and declared supplements."""
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops, ImageDraw

SCALE = 3
VERSION = 'personal-math-layout-2'


@dataclass
class Box:
    image: Image.Image
    baseline: int


def _join(children, gap=2):
    if not children:
        return Box(Image.new('L', (1, 1), 255), 0)
    ascent = max(0, max(b.baseline for b in children))
    descent = max(0, max(b.image.height-b.baseline for b in children))
    gaps = gap if isinstance(gap,list) else [gap]*(len(children)-1)
    image = Image.new('L', (sum(b.image.width for b in children)+sum(gaps), max(1,ascent+descent)), 255)
    x = 0
    for index,box in enumerate(children):
        image.paste(box.image, (x,ascent-box.baseline))
        x += box.image.width+(gaps[index] if index<len(gaps) else 0)
    return Box(image, ascent)


def _scaled(box, factor):
    return Box(box.image.resize((max(1,round(box.image.width*factor)),max(1,round(box.image.height*factor))),Image.Resampling.LANCZOS),round(box.baseline*factor))


def render_math(ast, bank, model=None, seed=42, variant=0, allow_supplemental=False, spacing=None):
    from .habit_model import habit_token
    from .reference_renderer import reference_token
    from .math_glyphs import supplemental_glyph
    from .math_strokes import draw_fence,draw_radical,estimate_style
    from .spacing import normalize_spacing,adjust_gap
    from .symbol_style import symbol_gap
    settings=normalize_spacing(spacing)
    supplemental = set()
    references = set()
    counter = 0
    placements = []
    structural_strokes = []
    style = estimate_style(bank,SCALE)

    def glyph(char):
        nonlocal counter
        counter += 1
        if char.isspace():
            return Box(Image.new('L',(4*SCALE,1),255),0)
        if char in bank['glyphs']:
            image,meta = habit_token(bank,model,char,seed,variant*10000+counter,spacing=settings) if model else reference_token(bank,char,False,spacing=settings,seed=seed,occurrence=variant*10000+counter)
            factor = 96/float(meta.get('em_height',32))
            image = image.resize((max(1,round(image.width*factor)),max(1,round(image.height*factor))),Image.Resampling.LANCZOS)
            baseline = round(meta.get('baseline',26)*factor)
            references.update(meta.get('references',[]))
        elif allow_supplemental:
            image,base,meta = supplemental_glyph(char,bank,SCALE)
            baseline = round(base*SCALE)
            supplemental.add(char)
        else:
            raise ValueError('Math glyph missing from the reviewed sample: '+char)
        yy,xx = np.where(np.asarray(image)<230)
        if not len(xx):
            raise ValueError('Empty math glyph: '+char)
        x0,x1=max(0,int(xx.min())-1),min(image.width,int(xx.max())+2)
        y0,y1=max(0,int(yy.min())-1),min(image.height,int(yy.max())+2)
        image=image.crop((x0,y0,x1,y1))
        baseline -= y0
        placements.append({'glyph':char,'source':'supplemental' if char in supplemental else 'personal','occurrence':counter})
        # Relations and binary operators have a modest handwritten gap.
        if char in '=+-×÷±≤≥≠→∈':
            pad=max(1,round(symbol_gap(3*SCALE,settings,seed,variant,counter)))
            padded=Image.new('L',(image.width+pad*2,image.height),255);padded.paste(image,(pad,0));image=padded
        return Box(image,baseline)

    def render(node, depth=0):
        if depth>20:
            raise ValueError('Math expression is too deeply nested.')
        kind=node['type']
        if kind=='glyph':
            return glyph(node['text'])
        if kind=='sequence':
            children=node['children']; boxes=[render(child,depth+1) for child in children]
            from .digit_style import digit_gap
            gaps=[]
            for i,(a,b) in enumerate(zip(children,children[1:])):
                left,right=a.get('text',''),b.get('text','')
                both_glyphs=a.get('type')==b.get('type')=='glyph'
                digits=both_glyphs and left in '0123456789' and right in '0123456789' and left and right
                if model and digits:gap=digit_gap(seed,variant*10000+counter,i,settings)*SCALE
                else:
                    kind='number' if digits else 'letter' if both_glyphs and left.isalpha() and right.isalpha() else 'symbol'
                    gap=symbol_gap(2,settings,seed,variant*10000+counter,i) if kind=='symbol' else adjust_gap(2,2,settings,kind)
                gaps.append(max(1,round(gap)))
            return _join(boxes,gaps)
        if kind=='named_operator':
            box=_join([glyph(c) for c in node['text']],gap=max(1,round(settings['letter'])))
            return _scaled(box,1.4) if node.get('limits') and node['text'] in ('∑','∏','∫') else box
        if kind=='fraction':
            top=_scaled(render(node['numerator'],depth+1),.86)
            bottom=_scaled(render(node['denominator'],depth+1),.86)
            gap=4;rule=3;pad=7
            width=max(top.image.width,bottom.image.width)+pad*2
            height=top.image.height+bottom.image.height+gap*2+rule
            image=Image.new('L',(width,height),255)
            image.paste(top.image,((width-top.image.width)//2,0))
            rule_y=top.image.height+gap
            ImageDraw.Draw(image).line((2,rule_y,width-3,rule_y),fill=35,width=rule)
            image.paste(bottom.image,((width-bottom.image.width)//2,rule_y+rule+gap))
            return Box(image,min(height,rule_y+8*SCALE))
        if kind=='script':
            base=render(node['base'],depth+1)
            sub=_scaled(render(node['sub'],depth+1),.68) if node.get('sub') else None
            sup=_scaled(render(node['sup'],depth+1),.68) if node.get('sup') else None
            limits=node['base'].get('type')=='named_operator' and node['base'].get('limits')
            if limits:
                gap=4;width=max(b.image.width for b in (base,sub,sup) if b)
                top=sup.image.height+gap if sup else 0
                height=top+base.image.height+(sub.image.height+gap if sub else 0)
                image=Image.new('L',(width,height),255)
                image.paste(base.image,((width-base.image.width)//2,top))
                if sup:image.paste(sup.image,((width-sup.image.width)//2,0))
                if sub:image.paste(sub.image,((width-sub.image.width)//2,top+base.image.height+gap))
                return Box(image,top+base.baseline)
            sup_y=base.baseline-round(16*SCALE*.65)-(sup.baseline if sup else 0)
            sub_y=base.baseline+round(16*SCALE*.35)-(sub.baseline if sub else 0)
            if sub and sup:
                sub_y=max(sub_y,sup_y+sup.image.height+3)
            top=min(0,sup_y if sup else 0,sub_y if sub else 0)
            bottom=max(base.image.height,sup_y+sup.image.height if sup else 0,sub_y+sub.image.height if sub else 0)
            width=base.image.width+3+max(b.image.width for b in (sub,sup) if b)
            image=Image.new('L',(width,bottom-top),255)
            image.paste(base.image,(0,-top))
            if sup:image.paste(sup.image,(base.image.width+3,sup_y-top))
            if sub:image.paste(sub.image,(base.image.width+3,sub_y-top))
            return Box(image,base.baseline-top)
        if kind=='radical':
            body=render(node['body'],depth+1)
            index=_scaled(render(node['index'],depth+1),.55) if node.get('index') else None
            image,body_xy,index_xy,stroke_meta=draw_radical(body.image.size,index.image.size if index else None,style,seed,variant*10000+len(structural_strokes))
            image.paste(body.image,body_xy)
            if index:
                layer=Image.new('L',image.size,255);layer.paste(index.image,index_xy);image=ImageChops.darker(image,layer)
            structural_strokes.append({'kind':'radical',**stroke_meta})
            return Box(image,body.baseline+body_xy[1])
        if kind=='fence':
            body=render(node['body'],depth+1);height=body.image.height+8
            parts=[]
            for side,char in [('left',node['left']),('body',''),('right',node['right'])]:
                if side=='body':
                    parts.append(Box(body.image,body.baseline));continue
                if not char:continue
                delim=glyph(char)
                im,stroke_meta=draw_fence(char,height,style,seed,variant*10000+counter,
                    source=delim.image if char in bank['glyphs'] else None)
                structural_strokes.append({'kind':'fence','glyph':char,
                    'source':'personal' if char in bank['glyphs'] else 'supplemental',**stroke_meta})
                parts.append(Box(im,body.baseline+4+stroke_meta['top_padding_px']))
            return _join(parts,gap=max(1,round(symbol_gap(3,settings,seed,variant,counter))))
        raise ValueError('Unsupported math node: '+str(kind))

    box=render(ast)
    # Leave explicit margins for page composition and baseline-safe resampling.
    pad=6;image=Image.new('L',(box.image.width+pad*2,box.image.height+pad*2),255)
    image.paste(box.image,(pad,pad))
    return image,{'baseline':box.baseline+pad,'em_height':96,'renderer':VERSION,
        'supplemental_math_glyphs':sorted(supplemental),'references':sorted(references),
        'math_glyphs':placements,'math_ast':ast,
        'math_strokes':structural_strokes,'spacing':settings,
        'limits':'Structure is typeset from explicit math input; supplemental glyphs are not learned personal handwriting.'}

"""Layout a safe mathematical AST using personal glyphs and declared supplements."""
from dataclasses import dataclass
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw

SCALE = 3
VERSION = 'personal-math-layout-1'


@dataclass
class Box:
    image: Image.Image
    baseline: int


def _join(children, gap=2):
    if not children:
        return Box(Image.new('L', (1, 1), 255), 0)
    ascent = max(0, max(b.baseline for b in children))
    descent = max(0, max(b.image.height-b.baseline for b in children))
    image = Image.new('L', (sum(b.image.width for b in children)+gap*(len(children)-1), max(1,ascent+descent)), 255)
    x = 0
    for box in children:
        image.paste(box.image, (x,ascent-box.baseline))
        x += box.image.width+gap
    return Box(image, ascent)


def _scaled(box, factor):
    return Box(box.image.resize((max(1,round(box.image.width*factor)),max(1,round(box.image.height*factor))),Image.Resampling.LANCZOS),round(box.baseline*factor))


def render_math(ast, bank, model=None, seed=42, variant=0, allow_supplemental=False):
    from .habit_model import habit_token
    from .reference_renderer import reference_token
    from .math_glyphs import supplemental_glyph
    supplemental = set()
    references = set()
    counter = 0
    placements = []

    def glyph(char):
        nonlocal counter
        counter += 1
        if char.isspace():
            return Box(Image.new('L',(4*SCALE,1),255),0)
        if char in bank['glyphs']:
            image,meta = habit_token(bank,model,char,seed,variant*10000+counter) if model else reference_token(bank,char,False)
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
            pad=3*SCALE
            padded=Image.new('L',(image.width+pad*2,image.height),255);padded.paste(image,(pad,0));image=padded
        return Box(image,baseline)

    def render(node, depth=0):
        if depth>20:
            raise ValueError('Math expression is too deeply nested.')
        kind=node['type']
        if kind=='glyph':
            return glyph(node['text'])
        if kind=='sequence':
            return _join([render(child,depth+1) for child in node['children']])
        if kind=='named_operator':
            box=_join([glyph(c) for c in node['text']],gap=1)
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
            body=render(node['body'],depth+1);gap=7;hook=10*SCALE;pad=4
            index=_scaled(render(node['index'],depth+1),.55) if node.get('index') else None
            top=max(pad,index.image.height-4 if index else 0)
            root_x=max(0,index.image.width-hook*2//3) if index else 0
            height=body.image.height+top+pad
            width=root_x+hook+body.image.width+gap+pad
            image=Image.new('L',(width,height),255);draw=ImageDraw.Draw(image)
            image.paste(body.image,(root_x+hook+gap,top+pad))
            draw.line([(root_x+2,round(height*.58)),(root_x+hook//3,round(height*.51)),(root_x+hook*2//3,height-3),(root_x+hook,top),(width-2,top)],fill=35,width=3,joint='curve')
            if index:
                layer=Image.new('L',image.size,255);layer.paste(index.image,(0,0));image=ImageChops.darker(image,layer)
            return Box(image,body.baseline+top+pad)
        if kind=='fence':
            body=render(node['body'],depth+1);height=body.image.height+8
            parts=[]
            for side,char in [('left',node['left']),('body',''),('right',node['right'])]:
                if side=='body':
                    parts.append(Box(body.image,body.baseline));continue
                if not char:continue
                delim=glyph(char)
                factor=height/max(1,delim.image.height)
                width=max(3,round(delim.image.width*math.sqrt(factor)))
                im=delim.image.resize((width,height),Image.Resampling.LANCZOS)
                parts.append(Box(im,body.baseline+4))
            return _join(parts,gap=3)
        raise ValueError('Unsupported math node: '+str(kind))

    box=render(ast)
    # Leave explicit margins for page composition and baseline-safe resampling.
    pad=6;image=Image.new('L',(box.image.width+pad*2,box.image.height+pad*2),255)
    image.paste(box.image,(pad,pad))
    return image,{'baseline':box.baseline+pad,'em_height':96,'renderer':VERSION,
        'supplemental_math_glyphs':sorted(supplemental),'references':sorted(references),
        'math_glyphs':placements,'math_ast':ast,
        'limits':'Structure is typeset from explicit math input; supplemental glyphs are not learned personal handwriting.'}

"""Render explicitly reviewed, local reference glyphs and words.

This is faithful sample reuse, not inference of unseen handwriting characters.
"""
from pathlib import Path
import hashlib,json,math,re
import numpy as np
from PIL import Image


def _child(root,name):
    root=Path(root).resolve()
    path=(root/name).resolve()
    if not path.is_relative_to(root):raise ValueError('Reference asset escapes its bank.')
    return path


def load_bank(path):
    path=Path(path).resolve();root=path.parent
    bank=json.loads(path.read_text(encoding='utf-8'))
    if bank.get('schema_version')!=1 or bank.get('reviewed') is not True:raise ValueError('Reference bank must be visually reviewed.')
    if not isinstance(bank.get('glyphs'),dict):raise ValueError('Invalid reference glyph map.')
    for key,records in [('glyphs',bank['glyphs']),('words',bank.get('words',{}))]:
        for text,entry in records.items():
            if not text or (key=='glyphs' and len(text)!=1):raise ValueError('Invalid reference label.')
            file=_child(root,entry['file'])
            if hashlib.sha256(file.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Reference image hash mismatch.')
            with Image.open(file) as image:
                if image.width>2048 or image.height>256:raise ValueError('Reference image too large.')
                if not np.any(np.array(image.convert('L'))<200):raise ValueError('Empty reference glyph.')
            if not math.isfinite(entry['baseline']) or abs(entry['baseline'])>256:raise ValueError('Invalid reference baseline.')
    bank['_manifest_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    bank['_root']=root
    return bank


def missing_characters(bank,text):
    return sorted(set(text)-set(bank['glyphs'])-set(' \n\t\r'))


def _image(bank,record):
    with Image.open(_child(bank['_root'],record['file'])) as source:return source.convert('L').copy()


def reference_token(bank,text,prefer_words=True,spacing=None,seed=42,occurrence=0):
    from .spacing import normalize_spacing,adjust_gap
    settings=normalize_spacing(spacing)
    def boundary_kind(left,right):
        return 'number' if left.isdigit() and right.isdigit() else 'letter' if left.isalpha() and right.isalpha() else 'symbol'
    kinds={boundary_kind(left,right) for left,right in zip(text,text[1:])}
    extra=max(0,settings['variation']-1)
    custom=any(settings[key]!=1 for key in kinds) or bool(kinds and extra)
    # A captured word has no reviewed internal glyph positions. Changing its
    # internal gaps requires composing its reviewed characters, never stretching
    # or cutting the connected original raster.
    if custom:prefer_words=False
    records=bank.get('words',{})
    if prefer_words and text in records:
        record=records[text];image=_image(bank,record)
        return image,{'baseline':record['baseline'],'em_height':32,'renderer':'captured-word','references':[record['sha256']]}
    if missing_characters(bank,text):raise ValueError('Missing reviewed reference characters: '+''.join(missing_characters(bank,text)))
    # Longest known fragments retain observed connections; no synthetic pen bridges.
    fragments=sorted([word for word in records if len(word)>=2],key=len,reverse=True) if prefer_words else []
    pieces=[];offset=0
    rng=np.random.default_rng(int.from_bytes(hashlib.sha256(f'reference-spacing:{seed}:{occurrence}:{text}'.encode()).digest()[:8],'little'))
    numeric=bool(re.fullmatch(r'[0-9.+%\-=]+',text))
    horizontal=float(bank.get('letter_width_scale',1)) if not numeric else 1.
    if not .3<=horizontal<=1.5:raise ValueError('Invalid reference letter width scale.')
    while offset<len(text):
        fragment=next((word for word in fragments if text.startswith(word,offset)),None)
        if fragment:
            record=records[fragment];image=_image(bank,record)
            pieces.append((image,float(record['baseline']),image.width+float(bank.get('spacing_px',2)),record['sha256']))
            offset+=len(fragment)
        else:
            char=text[offset];record=bank['glyphs'][char];image=_image(bank,record)
            char_scale=horizontal if char.isalpha() else 1.
            width=max(1,round(image.width*char_scale));image=image.resize((width,image.height),Image.Resampling.LANCZOS)
            advance=max(width+1,float(record.get('advance',image.width+2))*char_scale)
            if custom and offset+1<len(text):
                right=text[offset+1]
                kind=boundary_kind(char,right)
                mean=advance-width
                # New adjustable tracking stays positive, with reproducible
                # variation only when explicitly requested away from natural.
                sampled=mean+float(rng.uniform(-.3,.3))*mean*extra if extra else mean
                advance=width+adjust_gap(sampled,mean,settings,kind)
            pieces.append((image,float(record['baseline']),advance,record['sha256']));offset+=1
    ascent=max(p[1] for p in pieces);descent=max(p[0].height-p[1] for p in pieces)
    baseline=math.ceil(ascent)+2;height=max(4,math.ceil(ascent+descent)+4)
    width=max(1,math.ceil(sum(p[2] for p in pieces[:-1])+pieces[-1][0].width)+4)
    result=Image.new('L',(width,height),255);x=2.
    for image,base,advance,_ in pieces:
        result.paste(image,(round(x),round(baseline-base)));x+=advance
    return result,{'baseline':baseline,'em_height':32,'renderer':'captured-glyphs-and-fragments',
                   'references':[piece[3] for piece in pieces]}


def calibrate_model_image(image,bank):
    """Measured geometric calibration only; does not claim new character learning."""
    image=image.convert('L')
    scale=float(bank.get('model_width_scale',1));shear=float(bank.get('model_shear',0))
    if not .25<=scale<=1.5 or not -.7<=shear<=.7:raise ValueError('Invalid measured style calibration.')
    image=image.resize((max(1,round(image.width*scale)),image.height),Image.Resampling.LANCZOS)
    extra=math.ceil(abs(shear)*image.height)
    offset=max(0,-shear*image.height)
    image=image.transform((image.width+extra,image.height),Image.Transform.AFFINE,
        (1,-shear,-offset,0,1,0),resample=Image.Resampling.BICUBIC,fillcolor=255)
    return image,{'baseline':26,'em_height':32,'renderer':'style-model-with-geometric-calibration'}

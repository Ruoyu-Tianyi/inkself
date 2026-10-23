"""CPU-only, offline VATr++ generator adapter for the pinned upstream checkpoint.

Uses only Generator; skips training discriminators, OCR, Inception and optimizers.
Upstream code/assets remain in .local/vendor, tracked here only by revision/hash.
"""
import hashlib,importlib.util,json,os,re,sys,time,types
from pathlib import Path
from unittest.mock import patch

RENDERER_VERSION='inkself-runtime-4'


def _sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def request_input_hashes(request):
    """Content identities only: output locations do not affect reproducibility."""
    mode=request.get('render_mode','model');hashes={}
    if mode in ('reference','model-calibrated','learned-habits'):
        hashes['reference_bank_sha256']=_sha256(request['reference_bank'])
    if mode=='learned-habits':hashes['habit_model_sha256']=_sha256(request['habit_model'])
    if mode=='model':hashes['style_images_sha256']=[_sha256(path) for path in request['styles']]
    return hashes


def verify_request_inputs(request):
    actual=request_input_hashes(request)
    expected=request.get('expected_input_hashes')
    if expected is not None and (not isinstance(expected,dict) or expected!=actual):
        raise ValueError('Handwriting inputs changed after this job was queued; submit it again with the current profile.')
    return actual


def renderer_provenance(request,inputs):
    mode=request.get('render_mode','model')
    names=['vatr_worker.py']
    if mode!='model':names.append('reference_renderer.py')
    if mode=='learned-habits':names.extend(['habit_model.py','symbol_style.py'])
    if request.get('math_enabled'):names.extend(['math_syntax.py','math_renderer.py','math_glyphs.py','document_input.py'])
    source_hashes={name:_sha256(Path(__file__).parent/name) for name in names}
    renderer_hash=hashlib.sha256(json.dumps(source_hashes,sort_keys=True).encode()).hexdigest()
    identity={'text':request['text'],'seed':request['seed'],'render_mode':mode,
              'input_hashes':inputs,'renderer_sha256':renderer_hash,
              'math_enabled':request.get('math_enabled',False),'allow_supplemental_math':request.get('allow_supplemental_math',False)}
    return {'renderer_version':RENDERER_VERSION,'renderer_sha256':renderer_hash,
            'input_hashes':inputs,'input_fingerprint_sha256':hashlib.sha256(
                json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'queued_inputs_verified':request.get('expected_input_hashes') is not None}


def run(request_path):
    started=time.monotonic()
    request=json.loads(Path(request_path).read_text(encoding='utf-8'))
    root=Path(request['model']).resolve();output=Path(request['output']).resolve()
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['MPLBACKEND']='Agg'
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from web.runtime.reference_renderer import load_bank,reference_token,calibrate_model_image
    mode=request.get('render_mode','model')
    if mode not in ('model','model-calibrated','reference','learned-habits'):raise ValueError('Unknown handwriting renderer.')
    input_hashes=verify_request_inputs(request)
    bank=load_bank(request['reference_bank']) if mode in ('model-calibrated','reference','learned-habits') else None
    habit=None
    if mode=='learned-habits':
        from web.runtime.habit_model import load_habits,habit_token
        habit=load_habits(request['habit_model'],bank)
    if request_input_hashes(request)!=input_hashes:raise ValueError('Handwriting inputs changed while loading the job.')
    provenance=renderer_provenance(request,input_hashes)
    if mode in ('reference','learned-habits'):
        from web.runtime.document_input import prepare_document
        from web.runtime.math_renderer import render_math
        tokens,supplements=prepare_document(request['text'],bank,request.get('math_enabled',False),request.get('allow_supplemental_math',False))
        result=[]
        for token in tokens:
            if token.get('newline'):result.append({'newline':True});continue
            if 'math' in token:
                image,metadata=render_math(token['math'],bank,habit,request['seed'],len(result),request.get('allow_supplemental_math',False))
                text=token['source']
                metadata.update(math=True,display_math=token['display_math'])
            else:
                text=token['text']
                image,metadata=habit_token(bank,habit,text,request['seed'],len(result)) if habit else reference_token(bank,text)
            name=f'word-{len(result):04}.png';image.save(output/name)
            result.append({'text':text,'file':name,'width':image.width,'height':image.height,**metadata})
        record={'model':{'name':'Sample-fitted handwriting habits' if habit else 'Reviewed reference words and glyphs','device':'cpu','mode':mode,
                'limit':habit['limits'] if habit else 'Captured glyph/fragment composition; unseen joins and unseen characters are not learned.',
                'habit_training_words':len(habit['training_words']) if habit else None,
                'habit_model_sha256':input_hashes.get('habit_model_sha256'),'math_enabled':request.get('math_enabled',False),
                'supplemental_math_glyphs':supplements,**provenance},
                'duration_seconds':round(time.monotonic()-started,2),'words':result,
                'validation':'Reviewed sample label mapping; owner similarity review still required.'}
        (output/'generated.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        return

    import numpy as np
    import torch
    import torchvision.models as tv
    from PIL import Image,ImageOps
    from safetensors import safe_open
    torch.set_num_threads(min(4,max(1,(os.cpu_count() or 2)//2)))
    torch.manual_seed(request['seed']);np.random.seed(request['seed'])
    package=types.ModuleType('inkself_vatr');package.__path__=[str(root)];sys.modules['inkself_vatr']=package
    import importlib
    model_module=importlib.import_module('inkself_vatr.models.model')
    prototype=importlib.import_module('inkself_vatr.models.unifont_module')
    config=json.loads((root/'config.json').read_text(encoding='utf-8'))
    config.update(device='cpu',add_noise=False)
    args=types.SimpleNamespace(**config)
    def asset(repo_id,filename,**kwargs):
        path=(root/filename).resolve()
        if not path.is_relative_to(root) or not path.is_file(): raise ValueError('Missing pinned offline asset: '+filename)
        return str(path)
    original_resnet=tv.resnet18
    # Fully trained checkpoint replaces all ResNet weights; no bootstrap download needed.
    with patch.object(tv,'resnet18',side_effect=lambda *a,**k:original_resnet(weights=None)),patch.object(prototype,'hf_hub_download',side_effect=asset):
        generator=model_module.Generator(args).cpu().eval()
    expected=generator.state_dict();weights={}
    with safe_open(str(root/'model.safetensors'),framework='pt',device='cpu') as handle:
        keys=list(handle.keys())
        prefix='model.netG.' if any(k.startswith('model.netG.') for k in keys) else 'netG.'
        for key in keys:
            if key.startswith(prefix): weights[key[len(prefix):]]=handle.get_tensor(key)
    if set(weights)!=set(expected):
        raise ValueError('Generator checkpoint does not match architecture: '+repr((sorted(set(expected)-set(weights))[:8],sorted(set(weights)-set(expected))[:8])))
    generator.load_state_dict(weights,strict=True);del weights
    chunks=[]
    style_paths=[str(bank['_root']/record['file']) for record in bank['words'].values()] if bank else request['styles']
    for path in style_paths:
        with Image.open(path) as image:
            image=image.convert('L')
            image=image.resize((max(1,round(image.width*32/image.height)),32),Image.Resampling.LANCZOS)
            data=np.array(image)
        for x in range(0,data.shape[1],192):
            part=data[:,x:x+192]
            if part.shape[1]<24 or np.count_nonzero(part<170)<10: continue
            padded=np.full((32,192),255,dtype=np.float32);padded[:,:part.shape[1]]=part
            chunks.append(torch.from_numpy(padded/127.5-1))
    if not chunks: raise ValueError('No usable style patches.')
    # Spread 15 patches across the supplied paragraph; repeat only when genuinely short.
    chosen=[chunks[int(i)%len(chunks)] for i in np.linspace(0,len(chunks)-1,15)]
    styles=torch.stack(chosen).unsqueeze(0)
    encoding={char:i+1 for i,char in enumerate(args.alphabet+args.special_alphabet)}
    result=[]
    with torch.inference_mode():
        cache=Path(request['style_cache']) if request.get('style_cache') else None
        cache_used=bool(cache and cache.is_file())
        if cache_used:
            with np.load(cache,allow_pickle=False) as saved:
                array=saved['style']
                if array.ndim!=3 or not np.isfinite(array).all(): raise ValueError('Invalid cached style embedding.')
                style=torch.from_numpy(array.copy()).float()
        else:
            style=generator.compute_style(styles)
            if cache: np.savez_compressed(cache,style=style.cpu().numpy())
        for token in re.findall(r'\n|[^\s]+',request['text']):
            if token=='\n':result.append({'newline':True});continue
            if bank and re.fullmatch(r'[0-9.+%\-=]+',token):
                image,metadata=reference_token(bank,token,prefer_words=False)
                name=f'word-{len(result):04}.png';image.save(output/name)
                result.append({'text':token,'file':name,'width':image.width,'height':image.height,**metadata})
                continue
            if any(char not in encoding for char in token):raise ValueError('Unsupported model character in '+repr(token))
            query=torch.tensor([[encoding[char] for char in token]],dtype=torch.long)
            generated=generator.generate(style,query)[0,0,:,:len(token)*args.resolution]
            raw=generated.cpu().numpy()
            if not np.isfinite(raw).all():raise ValueError('Model produced invalid pixels.')
            array=np.clip((raw+1)*127.5,0,255).astype('uint8')
            if np.count_nonzero(array<180)<5 or np.mean(array<180)>.8:raise ValueError('Model produced an empty or invalid word image.')
            image=Image.fromarray(array);metadata={}
            if bank:image,metadata=calibrate_model_image(image,bank)
            name=f'word-{len(result):04}.png';image.save(output/name)
            result.append({'text':token,'file':name,'width':image.width,'height':image.height,**metadata})
            print('Generated',len(result),flush=True)
        # Persist actual encoder output, not a claim of personalized model training.
        np.savez_compressed(output/'style-embedding.npz',style=style.cpu().numpy())
    record={'model':{'name':'VATr++','repository':'blowing-up-groundhogs/vatrpp',
             'revision':'fb73be2be8e96ce70d9cad9675a30667e19ac376','device':'cpu','generator_only':True,'mode':mode,'numeric_source':'reviewed reference glyphs' if bank else 'generative model',**provenance},
            'duration_seconds':round(time.monotonic()-started,2),'style_patches':len(chunks),
            'style_cache_used':cache_used,'words':result,
            'validation':'not OCR verified; human review required'}
    (output/'generated.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Completed',record['duration_seconds'],flush=True)


if __name__=='__main__':run(sys.argv[1])

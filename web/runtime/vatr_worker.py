"""CPU-only, offline VATr++ generator adapter for the pinned upstream checkpoint.

Uses only Generator; skips training discriminators, OCR, Inception and optimizers.
Upstream code/assets remain in .local/vendor, tracked here only by revision/hash.
"""
import importlib.util,json,os,re,sys,time,types
from pathlib import Path
from unittest.mock import patch


def run(request_path):
    started=time.monotonic()
    request=json.loads(Path(request_path).read_text(encoding='utf-8'))
    root=Path(request['model']).resolve();output=Path(request['output']).resolve()
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['MPLBACKEND']='Agg'
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
    for path in request['styles']:
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
            if any(char not in encoding for char in token):raise ValueError('Unsupported model character in '+repr(token))
            query=torch.tensor([[encoding[char] for char in token]],dtype=torch.long)
            generated=generator.generate(style,query)[0,0,:,:len(token)*args.resolution]
            raw=generated.cpu().numpy()
            if not np.isfinite(raw).all():raise ValueError('Model produced invalid pixels.')
            array=np.clip((raw+1)*127.5,0,255).astype('uint8')
            if np.count_nonzero(array<180)<5 or np.mean(array<180)>.8:raise ValueError('Model produced an empty or invalid word image.')
            name=f'word-{len(result):04}.png';Image.fromarray(array).save(output/name)
            result.append({'text':token,'file':name,'width':array.shape[1],'height':array.shape[0]})
            print('Generated',len(result),flush=True)
        # Persist actual encoder output, not a claim of personalized model training.
        np.savez_compressed(output/'style-embedding.npz',style=style.cpu().numpy())
    record={'model':{'name':'VATr++','repository':'blowing-up-groundhogs/vatrpp',
             'revision':'fb73be2be8e96ce70d9cad9675a30667e19ac376','device':'cpu','generator_only':True},
            'duration_seconds':round(time.monotonic()-started,2),'style_patches':len(chunks),
            'style_cache_used':cache_used,'words':result,
            'validation':'not OCR verified; human review required'}
    (output/'generated.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Completed',record['duration_seconds'],flush=True)


if __name__=='__main__':run(sys.argv[1])

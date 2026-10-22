"""Fetch pinned upstream inference assets into ignored local storage."""
import hashlib,json,os,time,urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO='blowing-up-groundhogs/vatrpp'
REV='fb73be2be8e96ce70d9cad9675a30667e19ac376'
DEST=ROOT/'.local/vendor/vatrpp'
OPEN=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def download(name,sha=None):
    target=(DEST/name).resolve()
    if not target.is_relative_to(DEST.resolve()):raise ValueError('Invalid upstream asset path')
    if target.exists() and target.stat().st_size>200 and (not sha or hashlib.sha256(target.read_bytes()).hexdigest()==sha): return
    target.parent.mkdir(parents=True,exist_ok=True)
    partial=target.with_suffix(target.suffix+'.part')
    for attempt in range(8):
        try:
            start=partial.stat().st_size if partial.exists() else 0
            request=urllib.request.Request(f'https://huggingface.co/{REPO}/resolve/{REV}/{name}',headers={'Range':f'bytes={start}-'} if start else {})
            with OPEN.open(request,timeout=60) as response:
                append=start and response.status==206
                with partial.open('ab' if append else 'wb') as stream:
                    while block:=response.read(1024*1024): stream.write(block)
            if sha and hashlib.sha256(partial.read_bytes()).hexdigest()!=sha:
                partial.unlink()
                raise ValueError('SHA256 mismatch; partial discarded')
            partial.replace(target)
            print('Downloaded',name,target.stat().st_size,flush=True)
            return
        except Exception as error:
            print('Retry',name,attempt+1,type(error).__name__,flush=True)
            time.sleep(min(1+attempt,5))
    raise RuntimeError('Download failed: '+name)

if __name__=='__main__':
    meta=json.load(OPEN.open(f'https://huggingface.co/api/models/{REPO}/revision/{REV}?blobs=true',timeout=40))
    selected=[]
    for item in meta['siblings']:
        name=item['rfilename']
        if name.endswith('.py') and not name.startswith('vatr/') or name in ['README.md','config.json','model.safetensors','files/unifont.pickle','files/english_words.txt','mytext.txt']:
            selected.append((name,item.get('lfs',{}).get('sha256')))
    # Inference code first, large checkpoint last; never download the IAM datasets.
    selected.sort(key=lambda p:p[0]=='model.safetensors')
    small=[item for item in selected if item[0]!='model.safetensors']
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda item:download(*item),small))
    for name,sha in selected:
        if name=='model.safetensors': download(name,sha)
    (DEST/'download-manifest.json').write_text(json.dumps({'repo':REPO,'revision':REV,'files':selected},indent=2),encoding='utf-8')
    print('Pinned model download complete',flush=True)

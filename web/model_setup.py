"""Explicit one-click installation of pinned, verified public model assets.

Only upstream model files are downloaded. Samples and documents never leave the
computer. Partial downloads can resume; completion requires every SHA-256.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import ssl
import stat
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid

MANIFEST = Path(__file__).with_name('model-assets.json')
LOCK = threading.RLock()
STATES = {}
READY_LOCK = threading.RLock()
READY_CACHE = {}


def manifest():
    value = json.loads(MANIFEST.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict) or value.get('repository') != 'blowing-up-groundhogs/vatrpp' or value.get('revision') != 'fb73be2be8e96ce70d9cad9675a30667e19ac376':
        raise ValueError('Model download manifest is not the pinned release.')
    files = value.get('files')
    if not isinstance(files, list) or not files:
        raise ValueError('Model manifest must contain a nonempty file list.')
    names = set()
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str):
            raise ValueError('Invalid model asset record.')
        path = item['path']
        name = PurePosixPath(path)
        if (name.is_absolute() or any(part in ('', '.', '..') for part in path.split('/'))
                or any(char in path for char in ':\\*?') or any(ord(char) < 32 for char in path)
                or path.casefold() in names):
            raise ValueError('Invalid model asset path.')
        names.add(path.casefold())
        if (not isinstance(item.get('sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', item['sha256'])
                or type(item.get('size')) is not int or item['size'] <= 0):
            raise ValueError('Invalid model asset identity.')
    return value


def _sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _asset(root, name):
    candidate = root / name
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError('Model asset escapes its directory.')
    for part in (candidate, *candidate.parents):
        if part == root.parent:
            break
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Model asset links are not allowed.')
    return candidate


def _root(root):
    path = Path(root).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Model directory links are not allowed.')
    return path.resolve()


def _signature(root, spec):
    result = []
    for item in spec['files']:
        path = _asset(root, item['path'])
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != item['size']:
            raise ValueError('Pinned model asset is missing or has the wrong size.')
        result.append((item['path'], info.st_size, info.st_mtime_ns))
    return tuple(result)


def assets_ready(root):
    """Verify every pinned asset once per unchanged on-disk signature.

    Health polling checks all sizes, mtimes and links, without hashing the large
    checkpoint repeatedly. A manifest or file change invalidates the cache.
    """
    try:
        root = _root(root)
        spec = manifest()
        identity = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        key = (str(root), identity)
        with READY_LOCK:
            signature = _signature(root, spec)
            cached = READY_CACHE.get(key)
            if cached is not None and cached['signature'] == signature:
                return cached['ready']
            ready = all(_sha(_asset(root, item['path'])) == item['sha256'] for item in spec['files'])
            if _signature(root, spec) != signature:
                return False
            # Keep only the current manifest identity for this model directory.
            for previous in list(READY_CACHE):
                if previous[0] == str(root):
                    del READY_CACHE[previous]
            READY_CACHE[key] = {'signature': signature, 'ready': ready}
            return ready
    except (OSError, ValueError, TypeError, KeyError):
        return False


def state(root):
    root = _root(root)
    with LOCK:
        original = STATES.get(str(root))
        current = dict(original) if original is not None else None
    if current is not None:
        if current['status'] == 'ready' and not assets_ready(root):
            current.update(status='idle', bytes_completed=0, files_completed=0, current_file=None,
                           message='本地模型文件有变化，请重新准备并校验。')
            with LOCK:
                # Never replace a new download which began during verification.
                newer = STATES.get(str(root))
                if newer is original and newer.get('status') == 'ready':
                    STATES[str(root)] = current
                elif newer is not None:
                    current = dict(newer)
        return current
    spec = manifest()
    ready = assets_ready(root)
    return {'status':'ready' if ready else 'idle', 'bytes_completed':sum(item['size'] for item in spec['files']) if ready else 0,
            'bytes_total':sum(item['size'] for item in spec['files']),
            'files_completed':len(spec['files']) if ready else 0,'files_total':len(spec['files']), 'current_file':None,
            'message':'本地模型已就绪。' if ready else '首次需联网下载约 580 MB，之后离线使用。'}


def _update(root, **values):
    with LOCK:
        STATES[str(root)].update(values)


def _download(root, spec):
    import certifi
    try:
        root.mkdir(parents=True, exist_ok=True)
        # Explicit CA bundle works in frozen apps even if the launching shell has
        # unrelated SSL_CERT_FILE / proxy settings for its own Python runtime.
        context = ssl.create_default_context(cafile=certifi.where())
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
        completed = 0
        for index, item in enumerate(spec['files']):
            target = _asset(root,item['path'])
            _update(root,current_file=item['path'],message='正在准备本地 AI：'+item['path'])
            if target.is_file() and target.stat().st_size == item['size'] and _sha(target) == item['sha256']:
                completed += item['size']
                _update(root,bytes_completed=completed,files_completed=index+1)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = _asset(root,item['path']+'.part')
            for attempt in range(3):
                try:
                    offset = partial.stat().st_size if partial.is_file() else 0
                    if offset >= item['size']:
                        if offset == item['size'] and _sha(partial) == item['sha256']:
                            partial.replace(target)
                            break
                        partial.unlink()
                        offset = 0
                    url = 'https://huggingface.co/'+spec['repository']+'/resolve/'+spec['revision']+'/'+urllib.parse.quote(item['path'],safe='/')
                    request = urllib.request.Request(url,headers={'Range':f'bytes={offset}-'} if offset else {})
                    with opener.open(request, timeout=30) as response:
                        append = bool(offset and response.status == 206)
                        downloaded = offset if append else 0
                        with partial.open('ab' if append else 'wb') as stream:
                            while block := response.read(1024*1024):
                                downloaded += len(block)
                                if downloaded > item['size']:
                                    raise ValueError('Model download exceeds its pinned size.')
                                stream.write(block)
                                _update(root,bytes_completed=completed+downloaded)
                    if partial.stat().st_size != item['size'] or _sha(partial) != item['sha256']:
                        partial.unlink(missing_ok=True)
                        raise ValueError('Model file verification failed; retrying the original source.')
                    partial.replace(target)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(attempt+1)
            completed += item['size']
            _update(root,bytes_completed=completed,files_completed=index+1)
        if not assets_ready(root):
            raise ValueError('Model assets changed during verification; prepare them again.')
        marker = _asset(root, 'inkself-verified-assets.json')
        temporary = _asset(root, '.inkself-assets-' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(spec, stream, indent=2)
            _asset(root, 'inkself-verified-assets.json')
            temporary.replace(marker)
        finally:
            temporary.unlink(missing_ok=True)
        _update(root,status='ready',current_file=None,message='本地 AI 已准备好。样本和文档无需上传到云端。')
    except Exception as error:
        try:
            _asset(root, 'setup-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        except OSError:
            pass
        _update(root,status='failed',message='模型准备失败，可检查网络后继续；已完成的文件会保留。',error=str(error))


def start(root):
    root = _root(root)
    spec = manifest()
    with LOCK:
        if STATES.get(str(root),{}).get('status') == 'downloading':
            return dict(STATES[str(root)])
        STATES[str(root)] = {'status':'downloading','bytes_completed':0,'bytes_total':sum(item['size'] for item in spec['files']),
                             'files_completed':0,'files_total':len(spec['files']),'current_file':None,'message':'正在检查并准备本地 AI…'}
        threading.Thread(target=_download,args=(root,spec),daemon=True).start()
        return dict(STATES[str(root)])

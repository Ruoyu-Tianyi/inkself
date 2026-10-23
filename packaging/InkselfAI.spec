# -*- mode: python ; coding: utf-8 -*-
"""Headless CPU runtime; model code/assets are separately downloaded and pinned."""
import json
import os
from pathlib import Path
import ssl
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPEC).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Sources are required by the renderer fingerprint, not only by the importer.
datas = [(str(path), 'web/runtime') for path in sorted((ROOT / 'web/runtime').glob('*.py'))]
datas += [(str(ROOT / 'web/__init__.py'), 'web')]
# Some Python distributions load this bundled certificate-policy support file
# relative to ssl.py. Preserve it verbatim at that frozen module's location.
ssl_support = Path(ssl.__file__).resolve().with_name('codex-rejected-cas.pem')
if ssl_support.is_file():
    datas.append((str(ssl_support), '.'))

hiddenimports = collect_submodules('web.runtime')
hiddenimports += [
    # Vendor code is loaded from request['model'] via a runtime ModuleType and
    # importlib. Analysis cannot discover these third-party imports from data.
    'torch', 'torch.utils.data', 'torch.nn', 'torch.nn.functional',
    'torch.optim', 'torch.distributed', 'torch.nn.parallel._functions',
    'torchvision', 'torchvision.models', 'torchvision.transforms',
    'torchvision.transforms.functional', 'torchvision._C',
    'cv2', 'numpy', 'numpy.core.multiarray', 'numpy.core.numeric',
    'numpy._core.multiarray', 'numpy._core.numeric', 'PIL.Image', 'PIL.ImageOps',
    'safetensors', 'safetensors.torch', 'safetensors._safetensors_rust',
    'matplotlib', 'matplotlib.pyplot', 'matplotlib.backends.backend_agg',
    'scipy', 'scipy.linalg', 'scipy.special',
]
# huggingface_hub exposes hf_hub_download through a lazy module; it is patched
# to local pinned assets before the model is constructed, and never downloads.
hiddenimports += collect_submodules(
    'huggingface_hub', filter=lambda name: '.cli' not in name and '.commands' not in name)

excluded = [
    'web.app', 'web.samples', 'web.document_layout', 'desktop', 'desktop_runtime',
    'webview', 'pythonnet', 'clr', 'clr_loader', 'tkinter', '_tkinter',
    'fastapi', 'uvicorn', 'starlette', 'reportlab',
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'qtpy', 'gi', 'wx',
    'pytest', '_pytest', 'IPython', 'jupyter', 'notebook', 'tests',
    'tensorflow', 'tensorboard', 'torchaudio', 'transformers', 'datasets',
    'accelerate', 'pandas', 'sklearn', 'cvxpy', 'pypdfium2', 'fitz',
    'scripts.setup_model', 'scripts.fit_habits', 'scripts.run_handwriting_experiment',
]

# The installed torch hook gathers its DLLs, excludes development .lib/header
# files, and keeps Python sources for TorchScript; torchvision's hook adds _C.
a = Analysis(
    [str(ROOT / 'ai_worker.py')], pathex=[str(ROOT)], binaries=[], datas=datas,
    hiddenimports=sorted(set(hiddenimports)), hookspath=[],
    hooksconfig={'matplotlib': {'backends': ['Agg']}}, runtime_hooks=[],
    excludes=excluded, noarchive=False, optimize=1,
)
private_metadata = {'direct_url.json', 'uv_build.json', 'INSTALLER', 'REQUESTED'}
a.datas = [entry for entry in a.datas if Path(entry[0]).name not in private_metadata]
inventory = os.environ.get('INKSELF_AI_BUILD_INVENTORY')
if inventory:
    Path(inventory).write_text(json.dumps({
        'modules': sorted({entry[0] for entry in a.pure}),
        'binaries': sorted({entry[0] for entry in a.binaries}),
    }, indent=2), encoding='utf-8')

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='InkselfAI',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=True, contents_directory='_internal',
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='InkselfAI')

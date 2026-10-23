# -*- mode: python ; coding: utf-8 -*-
"""Windows directory bundle. Choose destinations with --distpath / --workpath."""
import json
import os
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPEC).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Keep readable runtime sources: the renderer hashes these files, and a separately
# configured model Python executes vatr_worker.py from this resource directory.
datas = [(str(path), str(path.parent.relative_to(ROOT)))
         for pattern in ('web/*.py', 'web/runtime/*.py')
         for path in sorted(ROOT.glob(pattern))]
datas += [(str(ROOT / 'web/static'), 'web/static')]
datas += [(str(ROOT / 'scripts/import_desktop_profiles.py'), 'scripts')]
datas += collect_data_files('reportlab', excludes=['**/tests/**'])

hiddenimports = (collect_submodules('web') + collect_submodules('web.runtime')
                 + collect_submodules('python_multipart'))
hiddenimports += [
    'desktop_runtime', 'scripts.import_desktop_profiles',
    'uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.loops.asyncio',
    'uvicorn.protocols.http.auto', 'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off',
    'reportlab.pdfbase._fontdata', 'reportlab.pdfbase.ttfonts',
    'reportlab.pdfbase.pdfmetrics', 'reportlab.pdfgen.canvas',
    'webview', 'webview.menu', 'webview.platforms.winforms',
    'webview.platforms.win32', 'webview.platforms.edgechromium',
    'pythonnet', 'clr_loader', 'clr', '_cffi_backend',
    'tkinter', 'tkinter.messagebox', 'tkinter.filedialog',
]

excluded = [
    'torch', 'torchvision', 'torchaudio', 'triton', 'transformers',
    'safetensors', 'huggingface_hub', 'datasets', 'accelerate',
    'scipy', 'matplotlib', 'pandas', 'sklearn', 'sympy', 'cvxpy',
    'pytest', '_pytest', 'IPython', 'jupyter', 'notebook',
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'qtpy', 'cefpython3',
    'webview.platforms.qt', 'webview.platforms.gtk',
    'webview.platforms.cocoa', 'webview.platforms.android',
    'webview.platforms.cef', 'gi', 'Cocoa', 'objc',
    'pypdfium2', 'pypdfium2_raw', 'pypdf', 'fitz',
    'engines', 'scripts.setup_model', 'scripts.fit_habits',
    'scripts.run_handwriting_experiment', 'tests',
]

a = Analysis(
    [str(ROOT / 'desktop.py')], pathex=[str(ROOT)], binaries=[], datas=datas,
    hiddenimports=sorted(set(hiddenimports)), hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=excluded, noarchive=False, optimize=1,
)

# Installer provenance can contain the build machine's private filesystem paths.
# Package version metadata is retained, but installer-specific records are not.
private_metadata = {'direct_url.json', 'uv_build.json', 'INSTALLER', 'REQUESTED'}
a.datas = [entry for entry in a.datas if Path(entry[0]).name not in private_metadata]

# Let the build wrapper attribute dependencies actually discovered by Analysis.
# Do not emit source paths into the distributable inventory.
inventory = os.environ.get('INKSELF_BUILD_INVENTORY')
if inventory:
    Path(inventory).write_text(json.dumps({
        'modules': sorted({entry[0] for entry in a.pure}),
        'binaries': sorted({entry[0] for entry in a.binaries}),
    }, indent=2), encoding='utf-8')

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='Inkself',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=os.environ.get('INKSELF_BUILD_ICON') or None,
    contents_directory='_internal',
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Inkself')

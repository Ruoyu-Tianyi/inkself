"""Resolve read-only resources and writable storage for source and desktop runs.

This module deliberately imports only the standard library: the desktop launcher
can select its process mode before loading the web server or any renderers.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


LOCAL_RENDERERS = frozenset({'reference', 'learned-habits'})
RENDERERS = LOCAL_RENDERERS | {'model', 'model-calibrated'}


def is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def resource_root() -> Path:
    if is_frozen() and getattr(sys, '_MEIPASS', None):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parents[1]


def executable_directory() -> Path:
    return Path(sys.executable).resolve().parent


def data_root() -> Path:
    override = os.environ.get('INKSELF_DATA')
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        if sys.platform == 'darwin':
            return Path.home() / 'Library/Application Support/Inkself/data'
        if (executable_directory() / 'installed-mode.json').is_file():
            local = os.environ.get('LOCALAPPDATA')
            if not local:
                raise RuntimeError('Windows 未提供个人应用数据目录。')
            return Path(local).resolve() / 'Inkself/data'
        return executable_directory() / 'data'
    return resource_root() / '.local/web-data'


def model_root() -> Path:
    override = os.environ.get('INKSELF_MODEL_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        if sys.platform == 'darwin':
            return data_root() / 'models/vatrpp'
        if (executable_directory() / 'installed-mode.json').is_file():
            return data_root() / 'models/vatrpp'
        return executable_directory() / 'models/vatrpp'
    return resource_root() / '.local/vendor/vatrpp'


def model_worker() -> Path | None:
    override = os.environ.get('INKSELF_MODEL_WORKER')
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        candidate = (executable_directory().parent / 'Resources/ai-runtime/InkselfAI'
                     if sys.platform == 'darwin' else executable_directory() / 'ai-runtime/InkselfAI.exe')
        if candidate.is_file():
            return candidate
    return None


def model_python() -> Path | None:
    override = os.environ.get('INKSELF_MODEL_PYTHON')
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        # The desktop executable is not a general-purpose Python interpreter.
        return None
    relative = '.local/model-env/Scripts/python.exe' if os.name == 'nt' else '.local/model-env/bin/python'
    return resource_root() / relative


def model_probe_path() -> Path:
    return model_root().parent / 'model-probe.json' if is_frozen() else resource_root() / '.local/model-probe.json'


def worker_command(request_path: Path | str, render_mode: str, *, python: Path | str | None = None) -> list[str]:
    """Keep frozen workers inside the app; external Python remains optional for AI.

    The external neural runtime executes the bundled worker source, never the
    desktop executable as if it were ``python.exe``.
    """
    if render_mode not in RENDERERS:
        raise ValueError('Unknown handwriting renderer.')
    request = str(Path(request_path).resolve())
    if is_frozen() and render_mode in LOCAL_RENDERERS:
        return [sys.executable, '--worker', request]
    worker = model_worker()
    if worker is not None and (os.environ.get('INKSELF_MODEL_WORKER') or python is None):
        return [str(worker), '--worker', request]
    interpreter = Path(python) if python is not None else model_python()
    if interpreter is None:
        raise RuntimeError('此桌面包未包含少样本模型运行环境；请配置 INKSELF_MODEL_PYTHON，或使用已导入档案的样本习惯适配。')
    return [str(interpreter), str(resource_root() / 'web/runtime/vatr_worker.py'), request]

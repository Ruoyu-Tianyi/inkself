"""Desktop process ownership and configuration; no GUI or model imports."""
from __future__ import annotations
import ctypes
import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid
from pathlib import Path

TITLE = 'Inkself · 个人字迹工作室'


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_config(data):
    path = Path(data) / 'desktop-config.json'
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('桌面设置损坏，请检查 data/desktop-config.json。')
    config = {}
    for key in ('model_python', 'model_dir'):
        if value.get(key):
            if not isinstance(value[key], str) or not Path(value[key]).is_absolute():
                raise ValueError('模型设置必须使用完整路径。')
            config[key] = value[key]
    return config


def session(url):
    return request_json(url, '/api/session')


def request_json(url, path):
    # Local HTTP should never initialize proxy or external TLS/CA settings.
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port:
        raise ValueError('桌面服务只允许使用本机回环地址。')
    connection = http.client.HTTPConnection('127.0.0.1', parsed.port, timeout=2)
    try:
        connection.request('GET', path)
        response = connection.getresponse()
        if response.status != 200:
            raise OSError('本地服务响应：' + str(response.status))
        return json.loads(response.read())
    finally:
        connection.close()


class InstanceLock:
    """One desktop controller per data folder, released even after a crash."""
    def __init__(self, data):
        self.handle = None
        self.file = None
        identity = hashlib.sha256(os.path.normcase(str(Path(data).resolve())).encode()).hexdigest()
        if os.name == 'nt':
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            kernel.CreateMutexW.restype = ctypes.c_void_p
            self.handle = kernel.CreateMutexW(None, False, 'Local\\Inkself-' + identity)
            if not self.handle:
                raise OSError(ctypes.get_last_error(), '无法创建应用锁。')
            self.acquired = ctypes.get_last_error() != 183
        else:
            import fcntl
            self.file = (Path(data) / 'desktop.lock').open('a')
            try:
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.acquired = True
            except BlockingIOError:
                self.acquired = False

    def close(self):
        if self.handle:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(self.handle)
            self.handle = None
        if self.file:
            self.file.close()
            self.file = None


class ProcessJob:
    """Windows kills only this app's server and descendant workers on close."""
    def __init__(self, process):
        self.handle = None
        if os.name != 'nt':
            return
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]
        class Io(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
        class Extended(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', Io), ('ProcessMemoryLimit', ctypes.c_size_t),
                        ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel.CreateJobObjectW.restype = ctypes.c_void_p
        kernel.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateJobObjectW(None, None)
        info = Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(handle, ctypes.c_void_p(int(process._handle))):
            if handle:
                kernel.CloseHandle(handle)
            process.terminate()
            raise OSError(ctypes.get_last_error(), '无法建立安全的进程生命周期，请查看日志。')
        self.handle = handle

    def close(self):
        if self.handle:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(self.handle)
            self.handle = None


class OwnedServer:
    def __init__(self, data):
        self.data = Path(data).resolve()
        self.process = None
        self.job = None
        self.log = None
        self.instance = uuid.uuid4().hex
        self.url = None

    def start(self):
        self.data.mkdir(parents=True, exist_ok=True)
        (self.data / 'logs').mkdir(exist_ok=True)
        config = read_config(self.data)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.url = 'http://127.0.0.1:' + str(port)
        env = dict(os.environ, INKSELF_DATA=str(self.data), INKSELF_INSTANCE_ID=self.instance, PYTHONPATH='')
        for key, setting in (('INKSELF_MODEL_PYTHON', 'model_python'), ('INKSELF_MODEL_DIR', 'model_dir')):
            if config.get(setting):
                env[key] = config[setting]
        entry = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).with_name('desktop.py'))]
        self.log = (self.data / 'logs/server.log').open('a', encoding='utf-8')
        try:
            self.process = subprocess.Popen(entry + ['--server', str(port)], cwd=str(self.data), env=env,
                                            stdout=self.log, stderr=subprocess.STDOUT,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.job = ProcessJob(self.process)
            last_error = '服务尚未响应。'
            for _ in range(120):
                if self.process.poll() is not None:
                    raise RuntimeError('本地服务启动失败。请检查 data/logs/server.log。')
                try:
                    status = session(self.url)
                    if status.get('instance_id') == self.instance and status.get('mode') == 'local-single-owner':
                        write_json(self.data / 'desktop-session.json', {'url': self.url, 'instance_id': self.instance, 'pid': self.process.pid})
                        return self.url
                    last_error = '服务身份未匹配。'
                except (OSError, ValueError) as error:
                    last_error = str(error)
                time.sleep(.25)
            raise RuntimeError('启动超时：'+last_error+' 请检查 data/logs/server.log。')
        except Exception:
            self.stop()
            raise

    def active_jobs(self):
        jobs = request_json(self.url, '/api/jobs')
        return [job for job in jobs if job['status'] in ('queued', 'running')]

    def stop(self):
        if self.job:
            self.job.close()
            self.job = None
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()
            self.log = None
        state = self.data / 'desktop-session.json'
        try:
            if state.exists() and json.loads(state.read_text()).get('instance_id') == self.instance:
                state.unlink()
        except (OSError, ValueError):
            pass

"""Windows desktop entry point, also dispatching isolated server/worker modes."""
from __future__ import annotations
import argparse
import ctypes
import json
import multiprocessing
import os
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path


def ensure_stdio(path):
    if sys.stdout is None or sys.stderr is None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        stream = open(path, 'a', encoding='utf-8', buffering=1)
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream


def message(text, title='Inkself'):
    if os.name == 'nt':
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)
    else:
        print(title + ': ' + text)


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description='Inkself Windows desktop')
    parser.add_argument('--server', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--headless', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--exit-after', type=float, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    from web.runtime_paths import data_root, is_frozen, resource_root
    data = args.data_dir.resolve() if args.data_dir else (data_root() if is_frozen() or os.environ.get('INKSELF_DATA') else resource_root()/'.local/desktop-data')
    os.environ['INKSELF_DATA'] = str(data)
    ensure_stdio((args.worker.parent/'worker.log') if args.worker else data/'logs/desktop.log')
    if args.worker:
        from web.runtime.vatr_worker import run
        run(args.worker)
        return 0
    if args.server:
        import uvicorn
        from web.app import app
        uvicorn.run(app, host='127.0.0.1', port=args.server, log_level='warning', access_log=False)
        return 0
    from desktop_runtime import TITLE, InstanceLock, OwnedServer, write_json
    data.mkdir(parents=True, exist_ok=True)
    lock = InstanceLock(data)
    if not lock.acquired:
        if os.name == 'nt' and not args.headless:
            handle = ctypes.windll.user32.FindWindowW(None, TITLE)
            if handle:
                ctypes.windll.user32.ShowWindow(handle, 9)
                ctypes.windll.user32.SetForegroundWindow(handle)
            else:
                message('Inkself 已经在运行。请使用任务栏中的应用窗口。')
        lock.close()
        return 0
    server = OwnedServer(data)
    try:
        url = server.start()
        if args.headless:
            deadline = time.monotonic() + args.exit_after if args.exit_after else None
            while deadline is None or time.monotonic() < deadline:
                if server.process.poll() is not None:
                    raise RuntimeError('本地服务意外退出。')
                time.sleep(.2)
            return 0
        try:
            import webview
            from webview.menu import Menu, MenuAction
            webview.settings['ALLOW_DOWNLOADS'] = True
            webview.settings['ALLOW_FILE_URLS'] = False
            window = webview.create_window(TITLE, url, width=1280, height=900, min_size=(860, 640), background_color='#f4f2eb', text_select=True, hidden=bool(args.exit_after))

            def import_old():
                selected = window.create_file_dialog(webview.FileDialog.FOLDER)
                if not selected:
                    return
                try:
                    from scripts.import_desktop_profiles import import_profiles
                    result = import_profiles(selected[0], data)
                    message(f"已导入 {result['imported_count']} 份字迹，跳过 {result['skipped_count']} 份已有档案。\n历史作品仍保留在原目录。")
                    window.load_url(server.url+'/#library')
                except Exception as error:
                    message(str(error), '档案导入失败')

            def connect_model():
                if server.active_jobs():
                    message('请等待生成任务结束，再连接模型环境。')
                    return
                message('先选择已安装模型环境的 python.exe，再选择包含 model.safetensors 的 VATr++ 文件夹。')
                python = window.create_file_dialog(webview.FileDialog.OPEN, file_types=('Python interpreter (*.exe)',))
                if not python:
                    return
                model = window.create_file_dialog(webview.FileDialog.FOLDER)
                if not model:
                    return
                if not (Path(model[0])/'model.safetensors').is_file():
                    message('该文件夹没有 model.safetensors，请选择已安装的 VATr++ 模型目录。')
                    return
                write_json(data/'desktop-config.json', {'model_python':python[0], 'model_dir':model[0]})
                server.stop()
                server.start()
                window.load_url(server.url)

            def closing():
                try:
                    if server.active_jobs():
                        return window.create_confirmation_dialog('还有生成任务', '退出会中断当前生成。确认退出？')
                except (OSError, ValueError):
                    pass
                return True

            window.events.closing += closing
            def loaded():
                write_json(data/'window-loaded.json', {'loaded':True, 'url':server.url, 'engine':'edgechromium', 'time':time.time()})
                if args.exit_after:
                    threading.Timer(args.exit_after, window.destroy).start()
            window.events.loaded += loaded
            menus = [Menu('文件', [MenuAction('导入旧版字迹档案…', import_old), MenuAction('打开数据目录', lambda:os.startfile(data)), MenuAction('退出', window.destroy)]),
                     Menu('模型', [MenuAction('连接本地少样本模型…', connect_model)]),
                     Menu('帮助', [MenuAction('使用说明', lambda:webbrowser.open('https://github.com/Ruoyu-Tianyi/inkself/blob/main/docs/desktop-guide.md'))])]
            webview.start(gui='edgechromium', private_mode=False, storage_path=str(data/'webview'), menu=menus)
        except Exception:
            traceback.print_exc()
            # Missing WebView2 must not make the local app unusable.
            fallback(server, args.exit_after)
        return 0
    finally:
        server.stop()
        lock.close()


def fallback(server, exit_after=0):
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.title('Inkself · 浏览器模式')
    root.geometry('600x260')
    root.configure(bg='#f4f2eb')
    tk.Label(root, text='Inkself', font=('Segoe UI', 28), bg='#f4f2eb').pack(pady=(20, 8))
    tk.Label(root, text='桌面网页组件暂不可用。可在浏览器继续使用本机工作室。\n保留此窗口，关闭后本地服务会停止。', bg='#f4f2eb').pack(pady=8)
    tk.Button(root, text='打开工作室', command=lambda:webbrowser.open(server.url), width=24).pack(pady=10)
    tk.Button(root, text='打开数据目录', command=lambda:os.startfile(server.data), width=24).pack()
    def close():
        try:
            busy = bool(server.active_jobs())
        except (OSError, ValueError):
            busy = False
        if busy and not messagebox.askokcancel('还有生成任务', '退出会中断当前生成。确认退出？'):
            return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    if exit_after:
        root.after(int(exit_after*1000), root.destroy)
    root.mainloop()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        try:
            traceback.print_exc()
        except Exception:
            pass  # A read-only portable directory may fail before stdio exists.
        if not any(flag in sys.argv for flag in ('--server', '--worker', '--headless')):
            message(str(error)+'\n\n请查看 data/logs 下的诊断日志。', 'Inkself 启动失败')
        raise SystemExit(1)

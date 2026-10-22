"""Start Inkself on loopback, opening a browser after health checks."""
import json,os,subprocess,sys,time,urllib.request,webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:8765'
PYTHON=ROOT/'.local/model-env/Scripts/python.exe' if os.name=='nt' else ROOT/'.local/model-env/bin/python'

def healthy():
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL+'/api/session',timeout=1) as response:
            return json.load(response).get('mode')=='local-single-owner'
    except Exception:return False

if not healthy():
    if not PYTHON.is_file():raise SystemExit('Run setup-web.ps1 first. See docs/web-guide.md.')
    logs=ROOT/'.local';logs.mkdir(exist_ok=True)
    with (logs/'web-server.log').open('a',encoding='utf-8') as log:
        child=subprocess.Popen([str(PYTHON),'-m','uvicorn','web.app:app','--host','127.0.0.1','--port','8765'],
            cwd=ROOT,env=dict(os.environ,PYTHONPATH=''),stdout=log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (logs/'web-server.pid').write_text(str(child.pid))
    for _ in range(60):
        if healthy():break
        if child.poll() is not None:raise SystemExit('Server failed; see .local/web-server.log.')
        time.sleep(.5)
    else:raise SystemExit('Server startup timed out; see .local/web-server.log.')
if '--no-browser' not in sys.argv:webbrowser.open(URL)
print('Inkself is ready: '+URL)

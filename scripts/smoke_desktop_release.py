"""Exercise the frozen app server -> job -> frozen worker -> PDF, using synthetic ink."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import string
import subprocess
import time
import urllib.request
from PIL import Image,ImageDraw


def main():
    p=argparse.ArgumentParser();p.add_argument('--executable',type=Path,required=True);p.add_argument('--data-dir',type=Path,required=True);a=p.parse_args()
    data=a.data_dir.resolve();data.mkdir(parents=True,exist_ok=True)
    profile=data/'profiles'/('a'*32);bank=profile/'bank';bank.mkdir(parents=True)
    im=Image.new('L',(12,20),255);ImageDraw.Draw(im).line((2,17,5,3,9,17),fill=20,width=2);im.save(bank/'ink.png')
    digest=hashlib.sha256((bank/'ink.png').read_bytes()).hexdigest()
    value={'schema_version':1,'reviewed':True,'source_sha256':'synthetic','words':{},'glyphs':{c:{'file':'ink.png','sha256':digest,'baseline':18,'advance':14} for c in string.ascii_letters+string.digits+'+-=%.,;?:×÷'}}
    (bank/'bank.json').write_text(json.dumps(value),encoding='utf-8')
    (profile/'profile.json').write_text(json.dumps({'id':'a'*32,'name':'Synthetic release test','created_at':'2026-10-28','status':'ready','sample_sha256':'synthetic','sample':{'lines':[]},'selected_lines':[],'reference_bank':'bank/bank.json','preferences':{}}),encoding='utf-8')
    env={k:v for k,v in os.environ.items() if not k.startswith(('INKSELF_','PYTHON'))}
    proc=subprocess.Popen([str(a.executable.resolve()),'--headless','--exit-after','120','--data-dir',str(data)],env=env)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def api(path,body=None):
        req=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**({'X-Inkself-Token':token} if token else {})})
        with opener.open(req,timeout=15) as response:return response.read()
    token=None
    try:
        for _ in range(120):
            state=data/'desktop-session.json'
            if state.exists():break
            if proc.poll() is not None:raise RuntimeError('Desktop exited during startup')
            time.sleep(.5)
        url=json.loads(state.read_text())['url'];token=json.loads(api('/api/session'))['token']
        job=json.loads(api('/api/jobs',{'profile_id':'a'*32,'text':'## 1\na. Expected value = 100.25%.\n\n## 2\n$x_i = 12$','render_mode':'reference','layout_mode':'assignment','math_enabled':True,'allow_supplemental_math':True}))
        for _ in range(120):
            job=json.loads(api('/api/jobs/'+job['id']))
            if job['status'] not in ('queued','running'):break
            time.sleep(.5)
        if job['status']!='needs-review':raise RuntimeError('Frozen render failed: '+str(job))
        pdf=api('/api/jobs/'+job['id']+'/files/result.pdf')
        assert pdf.startswith(b'%PDF-') and len(pdf)>1000
        result={'server':True,'frozen_worker_pdf':True,'pages':job['pages'],'pdf_sha256':hashlib.sha256(pdf).hexdigest()}
        (data/'smoke-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
    finally:
        proc.terminate()
        try:proc.wait(timeout=8)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)

if __name__=='__main__':main()

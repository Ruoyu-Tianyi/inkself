"""Build on a native Mac, preserving internal framework links and ad-hoc signatures."""
from __future__ import annotations
import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_ai_runtime import copy_runtime_licenses,dependency_inventory
from scripts.build_desktop import copy_offline_guides


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def validate_bundle(root):
    root=root.resolve()
    for path in root.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(root):
            raise ValueError('External bundle link: '+str(path.relative_to(root)))
        relative=path.relative_to(root)
        if any(part.lower() in {'.local','profiles','samples','outputs','.git','__pycache__'} for part in relative.parts):
            raise ValueError('Private/generated data in bundle: '+str(relative))
        if path.suffix.lower() in {'.safetensors','.pickle','.pth','.ckpt','.pt'}:
            raise ValueError('Model weights in bundle: '+str(relative))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if sys.platform!='darwin':parser.error('A native macOS build machine is required.')
    output=args.output.resolve()
    if output.exists():parser.error('Choose a new output directory.')
    output.mkdir(parents=True)
    scratch=ROOT/'.local/macos-build'/uuid.uuid4().hex;scratch.mkdir(parents=True)
    inventory=scratch/'analysis.json'
    env=dict(os.environ,INKSELF_AI_BUILD_INVENTORY=str(inventory),MPLBACKEND='Agg',HF_HUB_OFFLINE='1')
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(scratch/'ai'),
        '--workpath',str(scratch/'ai-work'),str(ROOT/'packaging/InkselfAI.spec')],cwd=ROOT,env=env,check=True)
    ai=scratch/'ai/InkselfAI'
    copy_runtime_licenses(ai,dependency_inventory(inventory))
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir','--name','Inkself',
        '--osx-bundle-identifier','app.inkself.desktop','--target-arch',platform.machine(),
        '--distpath',str(output),'--workpath',str(scratch/'core-work'),'--specpath',str(scratch),
        '--collect-submodules','web','--collect-submodules','webview','--collect-data','reportlab',
        '--hidden-import','desktop_runtime','--hidden-import','scripts.import_desktop_profiles',
        '--hidden-import','webview.platforms.cocoa']
    for module in ('torch','torchvision','scipy','matplotlib','pandas','pytest','pythonnet','clr','clr_loader'):
        command.extend(['--exclude-module',module])
    for pattern in ('web/*.py','web/runtime/*.py','web/*.json'):
        for source in sorted(ROOT.glob(pattern)):
            command.extend(['--add-data',str(source)+':'+str(source.parent.relative_to(ROOT))])
    command.extend(['--add-data',str(ROOT/'web/static')+':web/static',str(ROOT/'desktop.py')])
    subprocess.run(command,cwd=ROOT,check=True)
    app=output/'Inkself.app';resources=app/'Contents/Resources'
    shutil.copytree(ai,resources/'ai-runtime',symlinks=True)
    # Include complete dependency notices without relicensing third-party code.
    distributions={d.metadata['Name'].lower().replace('_','-'):d for d in metadata.distributions() if d.metadata.get('Name')}
    copy_runtime_licenses(resources,distributions)
    copy_offline_guides(resources)
    shutil.copyfile(ROOT/'docs/macos-guide.md',resources/'macOS-guide.md')
    validate_bundle(app)
    manifest={'application':'Inkself','version':'0.4.0','platform':'macOS','architecture':platform.machine(),
        'signing':'ad-hoc; not Apple Developer ID signed or notarized','includes_model_weights':False,
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'web').rglob('*.py'))}}
    (resources/'build-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True)
    subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    print(app)

if __name__=='__main__':main()

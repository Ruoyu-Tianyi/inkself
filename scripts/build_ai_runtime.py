"""Build InkselfAI without model weights, prototypes, downloaded code or user data.

The output parent defaults to dist/ai-runtime. Existing app/ZIP outputs are never
overwritten. Model assets are installed separately by Inkself's first-run flow.
"""
from __future__ import annotations

import argparse
from importlib import metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_desktop import license_file, normal_name, ordinary_path, sha256, write_json

RUNTIME_DISTRIBUTIONS = (
    'torch', 'torchvision', 'numpy', 'Pillow', 'opencv-python-headless',
    'safetensors', 'huggingface-hub', 'matplotlib', 'scipy',
)
BUILD_DISTRIBUTIONS = ('PyInstaller', 'pyinstaller-hooks-contrib')
PRIVATE_TOP_LEVEL = {'data', 'models', 'config', 'logs', '.local', 'profiles', 'outputs', 'samples'}
FORBIDDEN_PACKAGES = {'webview', 'pythonnet', 'clr_loader', 'tkinter', '_tcl_data', '_tk_data',
                      'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'tensorflow', 'torchaudio'}
MODEL_SUFFIXES = {'.safetensors', '.pickle', '.pkl', '.pth', '.ckpt', '.pt'}


def bundle_files(bundle):
    ordinary_path(bundle)
    for path in sorted(bundle.rglob('*')):
        info = ordinary_path(path)
        if not stat.S_ISREG(info.st_mode):
            continue
        relative = path.relative_to(bundle)
        if relative.parts[0].lower() in PRIVATE_TOP_LEVEL:
            raise ValueError(f'Private runtime data in AI release: {relative.as_posix()}')
        if any(part in FORBIDDEN_PACKAGES for part in relative.parts):
            raise ValueError(f'GUI/unwanted package in AI release: {relative.as_posix()}')
        if path.suffix.lower() in MODEL_SUFFIXES:
            raise ValueError(f'Model/prototype asset in runtime-only release: {relative.as_posix()}')
        if path.name in {'direct_url.json', 'uv_build.json', 'desktop-config.json', '.env'} or path.name.startswith('.env.'):
            raise ValueError(f'Private configuration in AI release: {relative.as_posix()}')
        yield path


def dependency_inventory(analysis_path):
    from packaging.requirements import Requirement
    analysis = json.loads(analysis_path.read_text(encoding='utf-8'))
    names = set(RUNTIME_DISTRIBUTIONS) | set(BUILD_DISTRIBUTIONS)
    modules = {name.split('.')[0] for name in analysis['modules']}
    modules.update(name.replace('\\', '/').split('/')[0].split('.')[0] for name in analysis['binaries'])
    mapping = metadata.packages_distributions()
    for name in modules:
        names.update(mapping.get(name, []))
    found = {}
    pending = sorted(names)
    while pending:
        name = pending.pop()
        key = normal_name(name)
        if key in found:
            continue
        distribution = metadata.distribution(name)
        found[key] = distribution
        for value in distribution.requires or []:
            requirement = Requirement(value)
            if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
                pending.append(requirement.name)
    return found


def copy_runtime_licenses(bundle, distributions, python_license=None):
    """Reuse license selection/copy rules without the desktop-only WebView2 step."""
    for notice in ('LICENSE', 'NOTICE.txt', 'COMMERCIAL-LICENSE.md'):
        shutil.copyfile(ROOT / notice, bundle / notice)
    root = bundle / 'licenses'
    root.mkdir()
    inventory = []
    warnings = []
    for key, distribution in sorted(distributions.items()):
        destination = root / key
        destination.mkdir()
        copied = []
        for relative in distribution.files or []:
            if not license_file(relative):
                continue
            safe = PurePosixPath(str(relative).replace('\\', '/'))
            if safe.is_absolute() or '..' in safe.parts:
                continue
            source = Path(distribution.locate_file(relative))
            if not source.is_file():
                continue
            ordinary_path(source)
            target = destination.joinpath(*safe.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(target.relative_to(bundle).as_posix())
        info = distribution.metadata
        declared = info.get('License-Expression') or info.get('License') or 'Not declared'
        links = list(info.get_all('Project-URL', []))
        if info.get('Home-page'):
            links.append('Homepage, ' + info['Home-page'])
        record = {
            'name': info.get('Name', key), 'version': distribution.version,
            'role': 'build tool / bootloader' if key in {normal_name(n) for n in BUILD_DISTRIBUTIONS} else 'runtime dependency',
            'declared_license': declared, 'project_urls': links, 'license_files': copied,
        }
        write_json(destination / 'package.json', record)
        inventory.append(record)
        if not copied and len(declared) < 150:
            warnings.append(f'{record["name"]}: installed package has no full license text; see package.json and upstream links.')
    python_license = Path(python_license) if python_license is not None else Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('Python LICENSE.txt is required for distribution.')
    (root / 'python').mkdir()
    shutil.copyfile(python_license, root / 'python/LICENSE.txt')
    notices = [
        'InkselfAI CPU runtime — third-party notices', '',
        f'Python {platform.python_version()}: licenses/python/LICENSE.txt',
        'Package license files and original declarations are retained under licenses/.',
        'This runtime does not include VATr++ model weights, upstream model code,',
        'Unifont prototypes, training datasets, or personal handwriting data.',
        'Model assets installed separately retain their own sources and licenses.', '',
    ]
    notices += [f'{item["name"]} {item["version"]} ({item["role"]}) — licenses/{normal_name(item["name"])}/'
                for item in inventory]
    if warnings:
        notices += ['', 'License metadata requiring upstream review:', *warnings]
    (bundle / 'THIRD_PARTY_NOTICES.txt').write_text('\n'.join(notices) + '\n', encoding='utf-8')
    return inventory, warnings


def create_manifest(bundle, inventory):
    sources = [ROOT / 'ai_worker.py', ROOT / 'packaging/InkselfAI.spec', Path(__file__).resolve(),
               ROOT / 'scripts/build_desktop.py', *sorted((ROOT / 'web/runtime').glob('*.py'))]
    write_json(bundle / 'build-manifest.json', {
        'schema_version': 1, 'application': 'InkselfAI', 'kind': 'cpu-neural-runtime',
        'platform': 'Windows', 'architecture': platform.machine(), 'python': platform.python_version(),
        'includes_model_assets': False,
        'dependencies': [{'name': item['name'], 'version': item['version']} for item in inventory],
        'source_sha256': {path.relative_to(ROOT).as_posix(): sha256(path) for path in sources},
    })
    hashes = [f'{sha256(path)}  {path.relative_to(bundle).as_posix()}' for path in bundle_files(bundle)
              if path.name != 'SHA256SUMS.txt']
    (bundle / 'SHA256SUMS.txt').write_text('\n'.join(hashes) + '\n', encoding='utf-8')


def create_zip(bundle, archive_path):
    files = list(bundle_files(bundle))
    with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, (Path(bundle.name) / path.relative_to(bundle)).as_posix())
    with archive_path.with_suffix('.zip.sha256').open('x', encoding='utf-8') as stream:
        stream.write(f'{sha256(archive_path)}  {archive_path.name}\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/ai-runtime', help='New distribution parent directory.')
    parser.add_argument('--no-zip', action='store_true', help='Produce only the app directory, licenses and checksums.')
    args = parser.parse_args(argv)
    if os.name != 'nt':
        parser.error('Build the Windows runtime on Windows.')
    output = args.output.resolve()
    bundle = output / 'InkselfAI'
    architecture = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(platform.machine().lower())
    if architecture != 'x64':
        parser.error('The currently tested CPU Torch runtime requires Windows x64.')
    archive = output / f'InkselfAI-windows-{architecture}.zip'
    for path in [bundle] + ([] if args.no_zip else [archive, archive.with_suffix('.zip.sha256')]):
        if path.exists() or path.is_symlink():
            parser.error(f'Output already exists: {path}; choose another --output. Nothing was removed.')
    for name in (*RUNTIME_DISTRIBUTIONS, *BUILD_DISTRIBUTIONS):
        try:
            metadata.version(name)
        except metadata.PackageNotFoundError:
            parser.error(f'Missing build dependency: {name}')
    if '+cpu' not in metadata.version('torch') or '+cpu' not in metadata.version('torchvision'):
        parser.error('Use the CPU builds of torch and torchvision; CUDA packages are not supported by this bundle.')
    output.mkdir(parents=True, exist_ok=True)
    work = ROOT / '.local/ai-build' / uuid.uuid4().hex
    work.mkdir(parents=True)
    analysis = work / 'analysis-inventory.json'
    env = dict(os.environ, INKSELF_AI_BUILD_INVENTORY=str(analysis), MPLBACKEND='Agg',
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    command = [sys.executable, '-m', 'PyInstaller', '--distpath', str(output),
               '--workpath', str(work / 'work'), str(ROOT / 'packaging/InkselfAI.spec')]
    subprocess.run(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, check=True)
    if not (bundle / 'InkselfAI.exe').is_file():
        raise RuntimeError('PyInstaller did not create InkselfAI.exe.')
    inventory, warnings = copy_runtime_licenses(bundle, dependency_inventory(analysis))
    create_manifest(bundle, inventory)
    if not args.no_zip:
        create_zip(bundle, archive)
    print(f'AI runtime: {bundle}')
    print(f'Checksums: {bundle / "SHA256SUMS.txt"}')
    if not args.no_zip:
        print(f'ZIP: {archive}')
    for warning in warnings:
        print('License note: ' + warning)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

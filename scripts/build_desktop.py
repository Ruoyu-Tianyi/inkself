"""Build a Windows onedir app, license inventory, checksum manifest and ZIP.

Run with the Python environment containing desktop-requirements.txt. --output is
the distribution parent; the app is always named Inkself. Existing artifacts are
never removed or overwritten. Build scratch files stay in .local/desktop-build.
Use --repackage EXISTING_BUNDLE --output NEW_PARENT to update notices and ZIP
without recompiling or modifying the previously tested application directory.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DISTRIBUTIONS = (
    'fastapi', 'uvicorn', 'python-multipart', 'httpx', 'Pillow', 'numpy',
    'opencv-python-headless', 'reportlab', 'pywebview',
)
BUILD_DISTRIBUTIONS = ('PyInstaller', 'pyinstaller-hooks-contrib')
PRIVATE_TOP_LEVEL = {'data', 'models', 'config', 'logs', '.local', 'profiles', 'outputs', 'samples'}
FORBIDDEN_PACKAGES = {
    'torch', 'torchvision', 'torchaudio', 'triton', 'transformers', 'safetensors',
    'huggingface_hub', 'scipy', 'matplotlib', 'pandas', 'pytest', '_pytest',
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
}
PRIVATE_FILENAMES = {'direct_url.json', 'uv_build.json', 'desktop-config.json',
                     'desktop-session.json', 'window-loaded.json', '.env'}
WEBVIEW2_LICENSE_SOURCE = ROOT / 'packaging/licenses/microsoft-web-webview2-1.0.3856.49'

# proxy_tools 0.1.0 omits its upstream license file from the installed wheel.
# Retain that file, including its original wording, rather than inferring terms
# from the conflicting short "MIT" label in this distribution's metadata.
PROXY_TOOLS_LICENSE_URL = 'https://raw.githubusercontent.com/jtushman/proxy_tools/master/LICENSE.txt'
PROXY_TOOLS_LICENSE = '''The BSD License (BSD)

Copyright (c) 2013 Armin Ronacher
Copyright (c) 2014 Jonathan Tushman

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
  * Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.
  * Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''


def normal_name(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def ordinary_path(path):
    """Reject links and Windows junctions instead of following outside the bundle."""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError(f'Bundle contains a link or reparse point: {path.name}')
    return info


def bundle_files(bundle):
    ordinary_path(bundle)
    for path in sorted(bundle.rglob('*')):
        info = ordinary_path(path)
        if stat.S_ISREG(info.st_mode):
            relative = path.relative_to(bundle)
            if relative.parts[0].lower() in PRIVATE_TOP_LEVEL:
                raise ValueError(f'Refusing private runtime data in release: {relative.as_posix()}')
            if path.name in PRIVATE_FILENAMES or path.name.startswith('.env.'):
                raise ValueError(f'Refusing private installer/runtime file: {relative.as_posix()}')
            if any(part in FORBIDDEN_PACKAGES for part in relative.parts):
                raise ValueError(f'Excluded dependency found in release: {relative.as_posix()}')
            yield path


def draw_icon(path):
    from PIL import Image, ImageDraw
    icon = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((5, 5, 251, 251), radius=52, fill='#22392f')
    # A compact handwritten i, drawn without an external font or image asset.
    draw.line([(139, 106), (132, 137), (122, 176), (126, 193), (141, 195), (158, 186)],
              fill='#f4f2eb', width=20, joint='curve')
    draw.ellipse((133, 59, 153, 80), fill='#f4f2eb')
    icon.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def dependency_inventory(analysis_path):
    from packaging.requirements import Requirement
    analysis = json.loads(analysis_path.read_text(encoding='utf-8'))
    names = set(RUNTIME_DISTRIBUTIONS) | set(BUILD_DISTRIBUTIONS)
    module_names = {name.split('.')[0] for name in analysis['modules']}
    # Extension-only packages (numpy/cv2/etc.) may not appear in a.pure.
    module_names.update(name.replace('\\', '/').split('/')[0].split('.')[0]
                        for name in analysis['binaries'])
    mapping = metadata.packages_distributions()
    for module in module_names:
        names.update(mapping.get(module, []))
    pending = sorted(names)
    found = {}
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


def license_file(relative):
    parts = PurePosixPath(str(relative).replace('\\', '/')).parts
    base = parts[-1].lower()
    return ('licenses' in (part.lower() for part in parts)
            or re.match(r'^(licen[sc]e|copying|notice)([._-]|$)', base)
            or base.endswith(('-license.txt', '-copying.txt', '-copying-gpl.txt')))


def webview_license_record(bundle, *, copy=False):
    """Match bundled SDK binaries to the exact NuGet package before attribution."""
    source_file = WEBVIEW2_LICENSE_SOURCE / 'SOURCE.json'
    source = json.loads(source_file.read_text(encoding='utf-8'))
    for name, digest in source['license_files'].items():
        if sha256(WEBVIEW2_LICENSE_SOURCE / name) != digest:
            raise ValueError(f'WebView2 upstream license checksum mismatch: {name}')
    sdk_root = bundle / '_internal/webview/lib'
    for name, item in source['sdk_files'].items():
        binary = sdk_root / name
        if not binary.is_file() or sha256(binary) != item['sha256']:
            raise ValueError(f'WebView2 SDK does not match the recorded {source["version"]} package: {name}. Update its license sources before releasing.')
    directory = 'licenses/microsoft-web-webview2'
    record = {
        'name': source['package'], 'version': source['version'],
        'role': 'WebView2 SDK DLLs bundled by pywebview',
        'declared_license': 'Microsoft BSD 3-Clause; see LICENSE.txt and NOTICE.txt',
        'project_urls': ['NuGet, ' + source['package_url']],
        'license_files': [f'{directory}/{name}' for name in source['license_files']],
        'source': source,
    }
    if copy:
        destination = bundle / directory
        destination.mkdir(parents=True, exist_ok=True)
        for name in source['license_files']:
            shutil.copyfile(WEBVIEW2_LICENSE_SOURCE / name, destination / name)
        shutil.copyfile(source_file, destination / 'SOURCE.json')
        write_json(destination / 'package.json', record)
    return record


def webview_notice_lines(record):
    return [
        f'WebView2 SDK DLLs included by pywebview: {record["name"]} {record["version"]}.',
        record['source']['package_url'],
        'Full SDK license: licenses/microsoft-web-webview2/LICENSE.txt',
        'Third-party notices: licenses/microsoft-web-webview2/NOTICE.txt',
        'Exact package and binary hashes: licenses/microsoft-web-webview2/SOURCE.json',
    ]


def copy_licenses(bundle, distributions):
    license_root = bundle / 'licenses'
    license_root.mkdir()
    inventory = []
    warnings = []
    for key, distribution in sorted(distributions.items()):
        destination = license_root / key
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
        declared_license = info.get('License-Expression') or info.get('License') or 'Not declared'
        links = list(info.get_all('Project-URL', []))
        if info.get('Home-page'):
            links.append('Homepage, ' + info['Home-page'])
        record = {
            'name': info.get('Name', key), 'version': distribution.version,
            'role': 'build tool / bootloader' if key in {normal_name(n) for n in BUILD_DISTRIBUTIONS} else 'dependency',
            'declared_license': declared_license, 'project_urls': links,
            'license_files': copied,
        }
        if key == 'proxy-tools' and distribution.version == '0.1.0':
            upstream = destination / 'UPSTREAM-LICENSE.txt'
            upstream.write_text(PROXY_TOOLS_LICENSE, encoding='utf-8')
            copied.append(upstream.relative_to(bundle).as_posix())
            record['upstream_license_source'] = PROXY_TOOLS_LICENSE_URL
            record['upstream_license_note'] = 'Upstream license is BSD; installed metadata labels it MIT. Both declarations are preserved.'
        # Preserve upstream metadata verbatim without copying installer records.
        write_json(destination / 'package.json', record)
        if not copied and len(declared_license) < 150:
            warnings.append(f'{record["name"]}: installed distribution has no full license text; see declared license and upstream links.')
        inventory.append(record)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('Python LICENSE.txt was not found; release cannot omit the interpreter notice.')
    (license_root / 'python').mkdir()
    shutil.copyfile(python_license, license_root / 'python/LICENSE.txt')
    # PyInstaller collects Tcl/Tk runtime data; retain any provided license terms.
    for source in sorted((Path(sys.base_prefix) / 'tcl').glob('*/license.terms')):
        destination = license_root / 'tcl-tk' / source.parent.name / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    sdk_record = webview_license_record(bundle, copy=True)
    inventory.append(sdk_record)
    notices = [
        'Inkself desktop — third-party notices', '',
        f'Python {platform.python_version()} is bundled; see licenses/python/LICENSE.txt.',
        'Package license texts are copied from the installed distributions under licenses/.',
        'Package declarations and upstream URLs are retained in licenses/*/package.json.',
        'Build tools are identified separately; their listing does not imply they are runtime APIs.',
        'The Windows WebView2 runtime is supplied separately by Microsoft / Windows.',
        *webview_notice_lines(sdk_record),
        '',
    ]
    for record in inventory:
        notices.append(f'{record["name"]} {record["version"]} ({record["role"]}) — licenses/{normal_name(record["name"])}/')
        if record.get('upstream_license_note'):
            notices.append('  ' + record['upstream_license_note'])
    if warnings:
        notices += ['', 'License metadata requiring upstream review:'] + warnings
    (bundle / 'THIRD_PARTY_NOTICES.txt').write_text('\n'.join(notices) + '\n', encoding='utf-8')
    return inventory, warnings


def create_manifest(bundle, inventory):
    manifest = {
        'schema_version': 1, 'application': 'Inkself',
        'platform': 'Windows', 'architecture': platform.machine(),
        'python': platform.python_version(),
        'dependencies': [{'name': item['name'], 'version': item['version']} for item in inventory],
        'source_sha256': {str(path.relative_to(ROOT)).replace('\\', '/'): sha256(path)
                          for path in sorted([ROOT / 'desktop.py', ROOT / 'desktop_runtime.py',
                                              ROOT / 'packaging/Inkself.spec', Path(__file__).resolve(),
                                              ROOT / 'desktop-requirements.txt'])},
    }
    write_json(bundle / 'build-manifest.json', manifest)
    create_checksums(bundle)


def create_checksums(bundle):
    lines = [f'{sha256(path)}  {path.relative_to(bundle).as_posix()}'
             for path in bundle_files(bundle) if path.name != 'SHA256SUMS.txt']
    (bundle / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def verified_bundle_hashes(bundle):
    files = {path.relative_to(bundle).as_posix(): path for path in bundle_files(bundle)}
    expected = {}
    for line in (bundle / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match or match[2] in expected or match[2] not in files:
            raise ValueError('Invalid or duplicate entry in original bundle checksums.')
        expected[match[2]] = match[1]
    if set(expected) != set(files) - {'SHA256SUMS.txt'}:
        raise ValueError('Original bundle contains files not covered by its checksums.')
    for name, digest in expected.items():
        if sha256(files[name]) != digest:
            raise ValueError(f'Original bundle checksum mismatch: {name}')
    return expected


def repackage_bundle(source, destination):
    """Copy a verified clean bundle; update only licensing/provenance records."""
    source = source.resolve()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Repackaging requires a new output directory.')
    if destination.resolve().is_relative_to(source):
        raise ValueError('Repackaging output must be outside the source bundle.')
    hashes = verified_bundle_hashes(source)
    webview_license_record(source)
    original_manifest = json.loads((source / 'build-manifest.json').read_text(encoding='utf-8'))
    # copytree has no dirs_exist_ok: the previously tested bundle is never edited.
    shutil.copytree(source, destination)
    sdk_record = webview_license_record(destination, copy=True)
    notice_path = destination / 'THIRD_PARTY_NOTICES.txt'
    old_lines = notice_path.read_text(encoding='utf-8').splitlines()
    superseded = (
        'WebView2 SDK DLLs included by pywebview',
        'https://www.nuget.org/packages/Microsoft.Web.WebView2',
        'Follow the license link for the SDK version',
        'Full SDK license:', 'Third-party notices: licenses/microsoft-web-webview2/',
        'Exact package and binary hashes: licenses/microsoft-web-webview2/',
        'Microsoft.Web.WebView2 ',
    )
    retained = [line for line in old_lines if not line.startswith(superseded)]
    notice_path.write_text('\n'.join(retained + ['', *webview_notice_lines(sdk_record)]) + '\n', encoding='utf-8')
    original_manifest['dependencies'] = [item for item in original_manifest['dependencies']
                                         if item['name'] != sdk_record['name']]
    original_manifest['dependencies'].append({'name': sdk_record['name'], 'version': sdk_record['version']})
    # Preserve compilation source hashes; the packaging script can evolve later.
    original_manifest['notice_update'] = {
        'input_build_manifest_sha256': hashes['build-manifest.json'],
        'input_checksums_sha256': sha256(source / 'SHA256SUMS.txt'),
        'packaging_script_sha256': sha256(Path(__file__).resolve()),
        'sdk_license_source_sha256': sha256(WEBVIEW2_LICENSE_SOURCE / 'SOURCE.json'),
        'recompiled': False,
    }
    write_json(destination / 'build-manifest.json', original_manifest)
    for name, digest in hashes.items():
        if name in {'THIRD_PARTY_NOTICES.txt', 'build-manifest.json'} or name.startswith('licenses/microsoft-web-webview2/'):
            continue
        if sha256(destination / name) != digest:
            raise ValueError(f'Repackaging changed a previously validated application file: {name}')
    create_checksums(destination)
    return original_manifest


def copy_offline_guides(bundle):
    for source_name, target_name in (
        ('desktop-guide.md', '使用说明.md'),
        ('math-and-documents.md', 'math-and-documents.md'),
        ('experiment-workflow.md', 'experiment-workflow.md'),
        ('habit-adapter.md', 'habit-adapter.md'),
        ('markdown-import.md', 'markdown-import.md'),
        ('ai-workflow.md', 'ai-workflow.md'),
    ):
        source = ROOT / 'docs' / source_name
        text = source.read_text(encoding='utf-8')
        private_paths = (str(ROOT), str(Path.home()))
        if any(value.lower() in text.lower() or value.replace('\\', '/').lower() in text.lower()
               for value in private_paths):
            raise ValueError(f'Offline guide contains a private machine path: {source_name}')
        (bundle / target_name).write_text(text, encoding='utf-8')


def create_zip(bundle, destination):
    # Exclusive creation is deliberate: never replace a previous release ZIP.
    files = list(bundle_files(bundle))
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, (Path(bundle.name) / path.relative_to(bundle)).as_posix())
    checksum = destination.with_suffix(destination.suffix + '.sha256')
    with checksum.open('x', encoding='utf-8') as stream:
        stream.write(f'{sha256(destination)}  {destination.name}\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist',
                        help='Distribution parent directory (default: repository/dist).')
    parser.add_argument('--no-zip', action='store_true', help='Build the directory bundle and manifests only.')
    parser.add_argument('--repackage', type=Path, metavar='EXISTING_BUNDLE',
                        help='Copy a checksum-verified clean bundle and refresh SDK notices without compiling.')
    args = parser.parse_args(argv)
    if os.name != 'nt':
        parser.error('Build on Windows with a Windows Python interpreter.')
    output = args.output.resolve()
    bundle = output / 'Inkself'
    architecture = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64',
                    'x86': 'x86', 'i386': 'x86'}.get(platform.machine().lower(), platform.machine().lower())
    archive = output / f'Inkself-windows-{architecture}.zip'
    reserved = [bundle] + ([] if args.no_zip else [archive, archive.with_suffix('.zip.sha256')])
    for path in reserved:
        if path.exists() or path.is_symlink():
            parser.error(f'Output already exists: {path}. Choose a new --output directory; nothing was removed.')
    if args.repackage:
        if output.is_relative_to(args.repackage.resolve()):
            parser.error('Choose an --output outside the existing bundle.')
        output.mkdir(parents=True, exist_ok=True)
        repackage_bundle(args.repackage, bundle)
        if not args.no_zip:
            create_zip(bundle, archive)
        print(f'Updated copy without recompiling: {bundle}')
        if not args.no_zip:
            print(f'ZIP: {archive}')
        print(f'Checksums: {bundle / "SHA256SUMS.txt"}')
        return 0
    for name in ('desktop.py', 'desktop_runtime.py', 'packaging/Inkself.spec', 'scripts/import_desktop_profiles.py'):
        if not (ROOT / name).is_file():
            parser.error(f'Missing application file: {name}')
    for name in (*RUNTIME_DISTRIBUTIONS, *BUILD_DISTRIBUTIONS):
        try:
            metadata.version(name)
        except metadata.PackageNotFoundError:
            parser.error(f'Missing dependency {name}; install desktop-requirements.txt with this Python.')
    output.mkdir(parents=True, exist_ok=True)
    work = ROOT / '.local/desktop-build' / uuid.uuid4().hex
    work.mkdir(parents=True)
    icon = work / 'inkself.ico'
    draw_icon(icon)
    analysis = work / 'analysis-inventory.json'
    env = dict(os.environ, INKSELF_BUILD_ICON=str(icon), INKSELF_BUILD_INVENTORY=str(analysis))
    command = [sys.executable, '-m', 'PyInstaller', '--distpath', str(output),
               '--workpath', str(work / 'work'), str(ROOT / 'packaging/Inkself.spec')]
    subprocess.run(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, check=True)
    if not (bundle / 'Inkself.exe').is_file():
        raise RuntimeError('PyInstaller did not create the expected Inkself.exe.')
    inventory, warnings = copy_licenses(bundle, dependency_inventory(analysis))
    copy_offline_guides(bundle)
    create_manifest(bundle, inventory)
    if not args.no_zip:
        create_zip(bundle, archive)
    print(f'App: {bundle}')
    if not args.no_zip:
        print(f'ZIP: {archive}')
    print(f'Checksums: {bundle / "SHA256SUMS.txt"}')
    for warning in warnings:
        print('License note: ' + warning)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

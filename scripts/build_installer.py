"""Create a per-user Windows setup from verified clean Inkself release folders.

No dependencies or model assets are downloaded. --model is reserved for a local
offline internal-test installer; the normal installer contains no model weights.
Existing setup artifacts are never replaced. Inno Setup ISCC.exe is supplied
explicitly with --compiler; compiling and installing are separate operations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'packaging/InkselfInstaller.iss'
INSTALLED_MODE = ROOT / 'packaging/installed-mode.json'
MODEL_MANIFEST = ROOT / 'web/model-assets.json'
APP_VERSION = '0.3.1'
PRIVATE_DIRECTORIES = {'.local', 'data', 'config', 'logs', 'log', 'models',
                       'profiles', 'samples', 'outputs', 'experiments', '.git', '.venv'}
PRIVATE_FILENAMES = {'desktop-config.json', 'desktop-session.json', 'window-loaded.json',
                     'profile.json', 'bank.json', 'request.json', 'job.json', 'direct_url.json', 'uv_build.json'}
COMMON_FILES = {'build-manifest.json', 'SHA256SUMS.txt', 'THIRD_PARTY_NOTICES.txt',
                'LICENSE', 'LICENSE.txt', 'NOTICE.txt'}
APP_FILES = COMMON_FILES | {'Inkself.exe', '使用说明.md', 'math-and-documents.md',
                           'experiment-workflow.md', 'habit-adapter.md', 'markdown-import.md', 'ai-workflow.md'}
AI_FILES = COMMON_FILES | {'InkselfAI.exe'}
MODEL_DESTINATION = r'{localappdata}\Inkself\data\models\vatrpp'
MODEL_REPO = 'blowing-up-groundhogs/vatrpp'
MODEL_REVISION = 'fb73be2be8e96ce70d9cad9675a30667e19ac376'
_HASH_LINE = re.compile(r'([a-f0-9]{64})  (.+)')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _ordinary(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Links and Windows reparse points are not allowed in installer inputs.')
    return info


def _safe_path(value, *, directory=False, required=True):
    path = Path(value).absolute()
    _safe_iss_literal(str(path))
    for item in reversed((path, *path.parents)):
        if item.exists() or item.is_symlink():
            _ordinary(item)
    if required and not (path.is_dir() if directory else path.is_file()):
        raise ValueError('Required installer input is missing or has the wrong type: ' + path.name)
    return path.resolve()


def _safe_iss_literal(value):
    # Source accepts wildcard patterns, so wildcard characters must never enter
    # the generated per-file allowlist, even when tests run on another platform.
    if any(char in value for char in '\x00\r\n"*?') or any(ord(char) < 32 for char in value):
        raise ValueError('Installer paths cannot contain control characters, quotes or wildcards.')
    return value.replace('{', '{{')


def _json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid installer input JSON: ' + path.name) from error
    if not isinstance(value, dict):
        raise ValueError('Installer input must be a JSON object: ' + path.name)
    return value


def _walk(root):
    for folder, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(folder) / name
            _safe_iss_literal(name)
            if any(char in name for char in '\\/:'):
                raise ValueError('Installer file names cannot contain path separators or alternate stream syntax.')
            info = _ordinary(path)
            if not path.resolve().is_relative_to(root):
                raise ValueError('Installer input escapes its component directory.')
            if not stat.S_ISDIR(info.st_mode) and not stat.S_ISREG(info.st_mode):
                raise ValueError('Installer inputs may contain only ordinary files and directories.')
            yield path, info


def verified_bundle(bundle, *, ai=False):
    """Require the complete clean release and its original checksum coverage."""
    root = _safe_path(bundle, directory=True)
    allowed_files = AI_FILES if ai else APP_FILES
    files = {}
    folded_names = set()
    for path, info in _walk(root):
        relative = path.relative_to(root)
        if relative.parts[0].casefold() in PRIVATE_DIRECTORIES:
            raise ValueError('Private runtime directory in installer input: ' + relative.as_posix())
        if relative.parts[0] not in ('_internal', 'licenses') and relative.as_posix() not in allowed_files:
            raise ValueError('File is outside the installer allowlist: ' + relative.as_posix())
        if (path.name.casefold() in PRIVATE_FILENAMES or path.name.casefold().startswith('.env')
                or re.fullmatch(r'habit-model(?:[._-].*)?\.json', path.name, re.IGNORECASE)
                or '.local' in (part.casefold() for part in relative.parts)):
            raise ValueError('Private profile or configuration file in installer input.')
        if path.suffix.casefold() in ('.safetensors', '.pickle', '.pkl', '.pt', '.pth', '.ckpt'):
            raise ValueError('App/runtime installer inputs must not contain model weights or prototypes.')
        if stat.S_ISREG(info.st_mode):
            key = relative.as_posix()
            if key.casefold() in folded_names:
                raise ValueError('Case-insensitive duplicate installer file name.')
            files[key] = path
            folded_names.add(key.casefold())
    required = {'InkselfAI.exe' if ai else 'Inkself.exe', 'build-manifest.json', 'SHA256SUMS.txt', 'THIRD_PARTY_NOTICES.txt'}
    if not required.issubset(files) or not (root / '_internal').is_dir() or not (root / 'licenses').is_dir():
        raise ValueError('A complete release with executable, runtime, licenses and checksums is required.')
    manifest = _json(root / 'build-manifest.json')
    if manifest.get('application') != ('InkselfAI' if ai else 'Inkself'):
        raise ValueError('Release build manifest does not identify the expected application.')
    if ai and manifest.get('includes_model_assets') is not False:
        raise ValueError('AI runtime must explicitly exclude model assets.')
    expected = {}
    for line in (root / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        match = _HASH_LINE.fullmatch(line)
        if not match or match[2] in expected or match[2] not in files:
            raise ValueError('Invalid, unknown or duplicate release checksum entry.')
        expected[match[2]] = match[1]
    if set(expected) != set(files) - {'SHA256SUMS.txt'}:
        raise ValueError('Release checksums do not cover every installer input file.')
    for name, digest in expected.items():
        if sha256(files[name]) != digest:
            raise ValueError('Release checksum mismatch: ' + name)
    return root, files


def verified_model(model):
    """Package the same complete pinned asset list used by runtime readiness.

    The full upstream source files are included, together with the weights and
    prototypes. Training datasets, user data and interpreter caches are not.
    """
    root = _safe_path(model, directory=True)
    # Validate links throughout the supplied directory, even in ignored caches.
    list(_walk(root))
    pinned_path = _safe_path(MODEL_MANIFEST)
    pinned = _json(pinned_path)
    if pinned.get('repository') != MODEL_REPO or pinned.get('revision') != MODEL_REVISION:
        raise ValueError('Offline test models must use the pinned VATr++ source and revision.')
    entries = pinned.get('files')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Offline model requires the complete pinned asset manifest.')
    declared = {}
    folded = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('path'), str):
            raise ValueError('Invalid pinned model manifest entry.')
        name, digest, size = entry['path'], entry.get('sha256'), entry.get('size')
        relative = PurePosixPath(name)
        if (relative.is_absolute() or any(part in ('', '.', '..') for part in name.split('/'))
                or any(char in name for char in '\\:*?') or any(ord(char) < 32 for char in name)
                or name.casefold() in folded):
            raise ValueError('Unsafe or duplicate pinned model manifest path.')
        if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest) or type(size) is not int or size <= 0:
            raise ValueError('Invalid pinned model asset size or checksum.')
        declared[name] = entry
        folded.add(name.casefold())
    required = {'model.safetensors', 'config.json', 'files/unifont.pickle', 'files/english_words.txt', 'models/model.py', 'README.md'}
    if not required.issubset(declared):
        raise ValueError('Pinned model manifest lacks required runtime assets.')
    # The installed marker records exactly the manifest whose every asset was
    # verified here. It does not replace runtime size and checksum verification.
    files = {'inkself-verified-assets.json': pinned_path}
    for name, entry in sorted(declared.items()):
        path = root.joinpath(*PurePosixPath(name).parts)
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('Offline model asset is missing or escapes its directory.')
        _ordinary(path)
        if path.stat().st_size != entry['size'] or sha256(path) != entry['sha256']:
            raise ValueError('Offline model checksum mismatch: ' + name)
        files[name] = path
    original_path = root / 'download-manifest.json'
    if original_path.is_file():
        original = _json(original_path)
        if original.get('repo') != MODEL_REPO or original.get('revision') != MODEL_REVISION:
            raise ValueError('Original model download manifest has a different source.')
        original_entries = original.get('files')
        if not isinstance(original_entries, list):
            raise ValueError('Invalid original model download manifest.')
        original_names = set()
        for entry in original_entries:
            if (not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str)
                    or entry[0] not in declared or entry[0] in original_names
                    or (entry[1] is not None and entry[1] != declared[entry[0]]['sha256'])):
                raise ValueError('Unsafe or inconsistent original model download manifest path or checksum.')
            original_names.add(entry[0])
        if original_names != set(declared):
            raise ValueError('Original model manifest does not cover the complete pinned release.')
        files['download-manifest.json'] = original_path
    for name in ('LICENSE', 'LICENSE.txt', 'NOTICE', 'NOTICE.txt'):
        if (root / name).is_file():
            files[name] = root / name
    return root, files


def installer_payload(app, ai_runtime=None, model=None):
    if model is not None and ai_runtime is None:
        raise ValueError('An offline model installer also requires --ai-runtime.')
    components = [('app', *verified_bundle(app), r'{app}', False)]
    if ai_runtime is not None:
        components.append(('ai-runtime', *verified_bundle(ai_runtime, ai=True), r'{app}\ai-runtime', False))
    if model is not None:
        components.append(('model', *verified_model(model), MODEL_DESTINATION, True))
    records = []
    for component, _, files, destination, preserve in components:
        for relative, source in sorted(files.items()):
            records.append({'component': component, 'relative': relative, 'source': source,
                            'destination': destination, 'preserve_on_uninstall': preserve, 'sha256': sha256(source)})
    marker = _safe_path(INSTALLED_MODE)
    if _json(marker).get('mode') != 'installed':
        raise ValueError('Missing installed-mode marker.')
    records.append({'component': 'installer', 'relative': 'installed-mode.json', 'source': marker,
                    'destination': r'{app}', 'preserve_on_uninstall': False, 'sha256': sha256(marker)})
    return records


def files_include(records):
    lines = ['; Generated explicit file allowlist; no wildcard or recursive source entries.']
    for item in records:
        relative = PurePosixPath(item['relative'])
        parent = '' if str(relative.parent) == '.' else '\\' + _safe_iss_literal(str(relative.parent).replace('/', '\\'))
        flags = 'ignoreversion' + (' uninsneveruninstall' if item['preserve_on_uninstall'] else '')
        lines.append('Source: "' + _safe_iss_literal(str(item['source'])) + '"; DestDir: "'
                     + item['destination'] + parent + '"; DestName: "' + _safe_iss_literal(relative.name)
                     + '"; Flags: ' + flags)
    return '\n'.join(lines) + '\n'


def _exclusive_copy(source, destination):
    with Path(source).open('rb') as reader, Path(destination).open('xb') as writer:
        shutil.copyfileobj(reader, writer, 1024 * 1024)


def build_installer(app, *, compiler, output, ai_runtime=None, model=None):
    """Validate inputs, compile into scratch storage, then publish a new setup."""
    compiler = _safe_path(compiler)
    if compiler.name.casefold() != 'iscc.exe':
        raise ValueError('--compiler must name an explicit Inno Setup ISCC.exe.')
    records = installer_payload(app, ai_runtime, model)
    output = _safe_path(output, directory=True, required=False)
    for component in (app, ai_runtime, model):
        if component is not None and output.is_relative_to(Path(component).resolve()):
            raise ValueError('Installer output must be outside all input component directories.')
    base = 'Inkself-Setup-Offline-Internal' if model is not None else 'Inkself-Setup'
    setup = output / (base + '.exe')
    checksum = output / (base + '.exe.sha256')
    receipt = output / (base + '.manifest.json')
    for path in (setup, checksum, receipt):
        if path.exists() or path.is_symlink():
            raise FileExistsError('Installer output already exists; nothing was overwritten: ' + path.name)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='inkself-installer-') as temporary:
        scratch = Path(temporary)
        allowlist = scratch / 'payload-files.iss'
        allowlist.write_text(files_include(records), encoding='utf-8-sig')
        command = [str(compiler), '/Qp', '/DFileListPath=' + str(allowlist), '/DBuildOutput=' + str(scratch),
                   '/DSetupBaseName=' + base, '/DAppVersion=' + APP_VERSION, str(TEMPLATE)]
        if model is not None:
            command.insert(-1, '/DOfflineModel=1')
        subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, check=True)
        built = scratch / (base + '.exe')
        if not built.is_file() or built.stat().st_size == 0:
            raise RuntimeError('Inno Setup did not create the expected nonempty installer.')
        for item in records:
            _ordinary(item['source'])
            if sha256(item['source']) != item['sha256']:
                raise ValueError('Installer input changed during compilation; setup was not published.')
        _exclusive_copy(built, setup)
    digest = sha256(setup)
    with checksum.open('x', encoding='utf-8') as stream:
        stream.write(digest + '  ' + setup.name + '\n')
    manifest = {'schema_version': 1, 'application': 'Inkself', 'version': APP_VERSION,
                'installer': setup.name, 'sha256': digest, 'scope': 'current-user',
                'includes_ai_runtime': ai_runtime is not None, 'includes_model_assets': model is not None,
                'internal_offline_test_only': model is not None,
                'data_location': '%LOCALAPPDATA%/Inkself/data', 'uninstall_preserves_user_data': True,
                'compiler_sha256': sha256(compiler), 'template_sha256': sha256(TEMPLATE),
                'payload': [{key: value for key, value in item.items() if key != 'source'} for item in records]}
    with receipt.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return setup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True, help='Clean complete Inkself release directory, without data/.')
    parser.add_argument('--ai-runtime', type=Path, help='Optional clean InkselfAI runtime directory; includes no weights.')
    parser.add_argument('--model', type=Path, help='Pinned offline model directory; internal testing only, requires AI runtime.')
    parser.add_argument('--compiler', type=Path, required=True, help='Explicit path to Inno Setup ISCC.exe.')
    parser.add_argument('--output', type=Path, required=True, help='New output directory for setup, checksums and manifest.')
    args = parser.parse_args(argv)
    try:
        setup = build_installer(args.app, compiler=args.compiler, output=args.output,
                                ai_runtime=args.ai_runtime, model=args.model)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Installer build failed: {error}\n')
    print('Installer: ' + str(setup))
    print('Checksums and payload manifest are beside the installer. Existing user data is preserved on uninstall.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

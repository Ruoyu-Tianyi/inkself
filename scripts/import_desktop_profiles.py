"""Copy local handwriting profiles into desktop storage, without old job paths.

Only explicitly selected local data is read. This module never downloads or
uploads samples and never replaces an existing profile.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import stat
import sys
import tempfile


PROFILE_ID = re.compile(r'[a-f0-9]{32}')
SHA256 = re.compile(r'[a-f0-9]{64}')


def _no_link(path: Path) -> None:
    """lstat also detects Windows junctions and other reparse points."""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError(f'Symbolic links and reparse points are not allowed: {path.name}')


def _safe_root(value, *, exists: bool) -> Path:
    path = Path(value).absolute()
    # macOS ships these root aliases. Normalize only the exact OS mappings;
    # user-created links anywhere below them remain forbidden.
    if sys.platform == 'darwin':
        for alias,target in (('/var','/private/var'),('/tmp','/private/tmp'),('/etc','/private/etc')):
            prefix=Path(alias)
            if path.is_relative_to(prefix) and prefix.is_symlink() and prefix.resolve()==Path(target):
                path=Path(target)/path.relative_to(prefix)
                break
    for item in reversed((path, *path.parents)):
        if item.exists() or item.is_symlink():
            _no_link(item)
    if exists and not path.is_dir():
        raise ValueError('Source data directory does not exist.')
    if path.exists() and not path.is_dir():
        raise ValueError('Data location must be a directory.')
    return path.resolve()


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'),
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f'Invalid JSON file: {path.name}') from error
    if not isinstance(value, dict):
        raise ValueError(f'Expected JSON object: {path.name}')
    return value


def _tree(root: Path) -> None:
    """Validate every entry, including assets which are not referenced in JSON."""
    _no_link(root)
    for folder, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            child = Path(folder) / name
            _no_link(child)
            if not child.resolve().is_relative_to(root):
                raise ValueError('Profile asset escapes its directory.')
            if not child.is_dir() and not child.is_file():
                raise ValueError('Only ordinary files and directories can be imported.')


def _asset(root: Path, value) -> Path:
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('Profile asset path must be a relative string.')
    parts = value.replace('\\', '/').split('/')
    if (PureWindowsPath(value).anchor or value.startswith('/') or ':' in value
            or any(part in ('', '.', '..') for part in parts)):
        raise ValueError('Profile asset path must stay inside its directory.')
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Profile asset is missing or escapes its directory.')
    _no_link(path)
    return path


def _bank(path: Path, source_hash: str) -> None:
    bank = _object(path)
    if (bank.get('schema_version') != 1 or bank.get('reviewed') is not True
            or bank.get('source_sha256') != source_hash
            or not isinstance(bank.get('glyphs'), dict) or not bank['glyphs']
            or not isinstance(bank.get('words', {}), dict)):
        raise ValueError('Invalid reviewed reference bank.')
    for group in (bank['glyphs'], bank.get('words', {})):
        for label, entry in group.items():
            if not isinstance(label, str) or not label or not isinstance(entry, dict):
                raise ValueError('Invalid reference bank record.')
            asset = _asset(path.parent, entry.get('file'))
            expected = entry.get('sha256')
            if (not isinstance(expected, str) or not SHA256.fullmatch(expected)
                    or hashlib.sha256(asset.read_bytes()).hexdigest() != expected):
                raise ValueError('Reference bank asset checksum mismatch.')


def _profile(folder: Path, expected_id: str) -> None:
    _tree(folder)
    profile = _object(_asset(folder, 'profile.json'))
    name = profile.get('name')
    if (profile.get('id') != expected_id
            or profile.get('status') not in ('ready', 'needs-review')
            or not isinstance(name, str) or not 1 <= len(name.strip()) <= 60
            or not isinstance(profile.get('created_at'), str) or not profile['created_at']
            or not isinstance(profile.get('preferences'), dict)
            or not isinstance(profile.get('sample_sha256'), str)
            or not SHA256.fullmatch(profile['sample_sha256'])):
        raise ValueError(f'Invalid profile metadata: {expected_id}')
    sample = profile.get('sample')
    lines = sample.get('lines') if isinstance(sample, dict) else None
    if not isinstance(lines, list) or not 1 <= len(lines) <= 24:
        raise ValueError('Profile must contain between 1 and 24 sample lines.')
    _asset(folder, 'sample/normalized.png')
    line_files = []
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError('Invalid sample line metadata.')
        line_files.append(_asset(folder / 'sample', line.get('file')))
    if len(set(line_files)) != len(line_files):
        raise ValueError('Sample line paths must be unique.')
    selected = profile.get('selected_lines')
    if (not isinstance(selected, list) or any(type(i) is not int or not 0 <= i < len(lines) for i in selected)
            or len(set(selected)) != len(selected)
            or (profile['status'] == 'ready' and not selected)):
        raise ValueError('Invalid selected sample lines.')
    math_lines = profile.get('math_lines', [])
    if (not isinstance(math_lines, list)
            or any(type(i) is not int or not 0 <= i < len(lines) for i in math_lines)
            or len(set(math_lines)) != len(math_lines)
            or set(math_lines) & set(selected)):
        raise ValueError('Invalid mathematics sample lines.')
    bank_path = None
    if 'reference_bank' in profile:
        bank_path = _asset(folder, profile['reference_bank'])
        _bank(bank_path, profile['sample_sha256'])
    if 'habit_model' in profile:
        model_path = _asset(folder, profile['habit_model'])
        model = _object(model_path)
        if (bank_path is None or model.get('schema_version') != 1
                or model.get('source_sha256') != profile['sample_sha256']
                or (model.get('bank_sha256') and model['bank_sha256'] != hashlib.sha256(bank_path.read_bytes()).hexdigest())):
            raise ValueError('Habit model does not match this profile and reference bank.')


@contextmanager
def _import_lock(profiles: Path):
    lock = profiles / '.profile-import.lock'
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise ValueError('Another profile import is already running.') from error
    try:
        yield
    finally:
        lock.rmdir()


def import_profiles(source_data, target_data) -> dict:
    """Validate all source profiles first, then publish complete new directories.

    Invalid input raises ValueError before copying any profile. Existing IDs are
    skipped without modification. Only profiles are copied; jobs, logs, models
    and old absolute request paths outside profiles are never imported.
    """
    source = _safe_root(source_data, exists=True)
    target = _safe_root(target_data, exists=False)
    source_profiles = source / 'profiles'
    if not source_profiles.is_dir():
        raise ValueError('Source data has no profiles directory.')
    _no_link(source_profiles)
    if target != source and target.is_relative_to(source_profiles):
        raise ValueError('Target data must be outside the source profiles directory.')
    candidates = []
    for folder in sorted(source_profiles.iterdir()):
        _no_link(folder)
        if not folder.is_dir() or not PROFILE_ID.fullmatch(folder.name):
            raise ValueError('Source profiles must contain only valid profile ID directories.')
        _profile(folder, folder.name)
        candidates.append(folder)
    destination = target / 'profiles'
    if destination.exists() or destination.is_symlink():
        _no_link(destination)
        if not destination.is_dir():
            raise ValueError('Target profiles location is not a directory.')
        for folder in candidates:
            item = destination / folder.name
            if item.exists() or item.is_symlink():
                _no_link(item)
    destination.mkdir(parents=True, exist_ok=True)
    imported, skipped = [], []
    with _import_lock(destination):
        for folder in candidates:
            final = destination / folder.name
            if final.exists() or final.is_symlink():
                _no_link(final)
                skipped.append(folder.name)
                continue
            staging = Path(tempfile.mkdtemp(prefix='.profile-import-', dir=destination))
            try:
                _tree(folder)
                # Preserve any link introduced during copying so that the second
                # validation rejects it instead of dereferencing outside assets.
                shutil.copytree(folder, staging, dirs_exist_ok=True, symlinks=True)
                _profile(staging, folder.name)
                if final.exists() or final.is_symlink():
                    _no_link(final)
                    skipped.append(folder.name)
                else:
                    staging.rename(final)
                    imported.append(folder.name)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
    return {'imported': imported, 'skipped': skipped,
            'imported_count': len(imported), 'skipped_count': len(skipped)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Import local Inkself profiles without replacing existing IDs.')
    parser.add_argument('source_data', help='Old web-data directory containing profiles/')
    parser.add_argument('target_data', help='Desktop data directory; jobs are not copied')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(import_profiles(args.source_data, args.target_data), ensure_ascii=False))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Profile import failed: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

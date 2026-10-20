"""Local reference-sample profiles. No glyph extraction or model training."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

DEFAULTS = {
    'ink_color': '#172E52', 'font_size_pt': 13.0, 'line_spacing': 1.5,
    'slant_deg': 0.0, 'baseline_jitter_pt': 0.5, 'glyph_variation': 0.3,
    'spacing_variation': 0.05, 'seed': 1, 'missing_glyph': 'error',
}
RANGES = {'font_size_pt': (8, 32), 'line_spacing': (1, 2.5),
          'slant_deg': (-20, 20), 'baseline_jitter_pt': (0, 3),
          'glyph_variation': (0, 1), 'spacing_variation': (0, 0.3)}

def now():
    return datetime.now(timezone.utc).isoformat()

def validate_preferences(data):
    if not isinstance(data, dict):
        raise ValueError('Preferences must be a JSON object.')
    if set(data) - set(DEFAULTS):
        raise ValueError('Unknown preference fields: ' + ', '.join(sorted(set(data) - set(DEFAULTS))))
    for key, value in data.items():
        if key in RANGES:
            lo, hi = RANGES[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f'{key} must be a finite number in [{lo}, {hi}].')
        elif key == 'ink_color' and (not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value)):
            raise ValueError('ink_color must be #RRGGBB.')
        elif key == 'seed' and (type(value) is not int or not 0 <= value <= 2147483647):
            raise ValueError('seed must be an integer between 0 and 2147483647.')
        elif key == 'missing_glyph' and value not in ('error', 'annotated-fallback'):
            raise ValueError('missing_glyph must be error or annotated-fallback.')
    return data

def folder(store, identifier):
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?', identifier):
        raise ValueError('Invalid profile ID; use 1-64 lowercase letters/digits and interior hyphens.')
    root = Path(store).resolve()
    target = (root / identifier).resolve()
    if target.parent != root:
        raise ValueError('Profile path escapes the store.')
    return target

def write_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    try:
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()

def load(store, identifier):
    dest = folder(store, identifier)
    data = json.loads((dest / 'profile.json').read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or data.get('id') != identifier:
        raise ValueError('Unsupported or inconsistent profile metadata.')
    validate_preferences(data['preferences'])
    return dest, data

def create(store, identifier, name):
    if not name or not name.strip():
        raise ValueError('Display name cannot be blank.')
    dest = folder(store, identifier)
    dest.mkdir(parents=True, exist_ok=False)
    data = {'schema_version': 1, 'id': identifier, 'name': name.strip(),
            'status': 'reference-only', 'created_at': now(), 'updated_at': now(),
            'preferences': dict(DEFAULTS), 'samples': []}
    write_json(dest / 'profile.json', data)
    return data

def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()

def add_sample(store, identifier, source, kind, transcript=None):
    dest, data = load(store, identifier)
    source = Path(source).resolve(strict=True)
    ext = source.suffix.lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.pdf') or not source.is_file():
        raise ValueError('Sample must be an existing PNG, JPEG or PDF file.')
    if kind not in ('freeform', 'labeled-sheet', 'trajectory-reference'):
        raise ValueError('Unsupported sample kind.')
    # The kind is descriptive; this implementation only accepts image/PDF references.
    paired = None
    if transcript:
        text_path = Path(transcript).resolve(strict=True)
        paired = text_path.read_text(encoding='utf-8-sig')
        if not paired.strip():
            raise ValueError('Transcript cannot be blank.')
    sha = digest(source)
    previous = next((x for x in data['samples'] if x['sha256'] == sha), None)
    if previous:
        if paired is not None:
            old_path = previous.get('transcript_path')
            if old_path and (dest / old_path).read_text(encoding='utf-8') != paired:
                raise ValueError('Duplicate sample has a different transcript; resolve the existing pairing first.')
            if not old_path:
                transcript_path = dest / 'samples' / f'{sha}.txt'
                transcript_path.write_text(paired, encoding='utf-8')
                previous['transcript_path'] = transcript_path.relative_to(dest).as_posix()
                previous['transcript_sha256'] = digest(transcript_path)
                data['updated_at'] = now()
                write_json(dest / 'profile.json', data)
        return data
    sample_dir = dest / 'samples'
    if sample_dir.is_symlink() or (sample_dir.exists() and sample_dir.resolve().parent != dest):
        raise ValueError('Sample directory must remain inside the profile.')
    sample_dir.mkdir(exist_ok=True)
    saved = sample_dir / (sha + ext)
    if saved.is_symlink():
        raise ValueError('Sample destination cannot be a symlink.')
    shutil.copyfile(source, saved)
    record = {'sha256': sha, 'path': saved.relative_to(dest).as_posix(),
              'kind': kind, 'imported_at': now()}
    if paired is not None:
        text_path = sample_dir / (sha + '.txt')
        text_path.write_text(paired, encoding='utf-8')
        record['transcript_path'] = text_path.relative_to(dest).as_posix()
        record['transcript_sha256'] = digest(text_path)
    data['samples'].append(record)
    data['updated_at'] = now()
    write_json(dest / 'profile.json', data)
    return data

def update(store, identifier, preferences):
    dest, data = load(store, identifier)
    data['preferences'].update(validate_preferences(preferences))
    data['updated_at'] = now()
    write_json(dest / 'profile.json', data)
    return data

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, default=Path('.local/profiles'))
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('create'); p.add_argument('id'); p.add_argument('--name', required=True)
    p = subs.add_parser('add-sample'); p.add_argument('id'); p.add_argument('--file', required=True)
    p.add_argument('--kind', choices=['freeform', 'labeled-sheet', 'trajectory-reference'], default='freeform')
    p.add_argument('--transcript')
    p = subs.add_parser('update'); p.add_argument('id'); p.add_argument('--preferences', required=True)
    p = subs.add_parser('show'); p.add_argument('id')
    subs.add_parser('list')
    args = parser.parse_args(argv)
    try:
        if args.command == 'create': result = create(args.store, args.id, args.name)
        elif args.command == 'add-sample': result = add_sample(args.store, args.id, args.file, args.kind, args.transcript)
        elif args.command == 'update':
            result = update(args.store, args.id, json.loads(Path(args.preferences).read_text(encoding='utf-8-sig')))
        elif args.command == 'show': result = load(args.store, args.id)[1]
        else:
            root = args.store.resolve()
            result = []
            for path in sorted(root.glob('*/profile.json')):
                if path.parent.resolve().parent != root: continue
                item = load(root, path.parent.name)[1]
                result.append({k: item[k] for k in ('id', 'name', 'status', 'updated_at')})
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())

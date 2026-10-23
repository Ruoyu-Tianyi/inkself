"""Reproduce a local handwriting comparison from frozen, reviewed inputs.

Run with the application's Python environment. All outputs may contain personal
handwriting; choose an ignored local directory, never a public fixture folder.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.metadata
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODES = ('reference', 'learned-habits')
DEFAULT_PREFERENCES = {'size': 16, 'line_spacing': 1.6, 'ink': '#263d57', 'math_enabled': False, 'allow_supplemental_math': False}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def _words(text):
    return re.findall(r'[A-Za-z]+', text.lower())


def diagnostics(case, bank, model, excluded_words):
    words = _words(case['text'])
    training = set(w.lower() for w in model.get('training_words', []))
    reference = {w for text in bank.get('words', {}) for w in _words(text)}
    exact_pairs = {p.lower() for p in model.get('pairs', {})}
    pairs = {w[i:i + 2] for w in words for i in range(len(w) - 1)}
    return {
        'training_word_matches': sorted(set(words) & training),
        'reference_word_matches': sorted(set(words) & reference),
        'words_not_in_training': sorted(set(words) - training),
        'pairs_not_observed_directly_in_training': sorted(pairs - exact_pairs),
        'requested_exclusions_still_in_training': sorted(set(excluded_words) & training),
        'model_excluded_words': sorted(model.get('excluded_words', [])),
        'interpretation': 'Content overlap diagnostics only. Reference glyphs and sample statistics remain available; this is not blind writer validation.'
    }


def preflight(bank_path, model_path, suite_path, output, modes, seed):
    """Read and validate every input before creating or modifying output files."""
    from web.runtime.reference_renderer import load_bank, missing_characters
    from web.runtime.habit_model import load_habits

    output = Path(output).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Output must be a new or empty directory; completed and partial runs are never overwritten.')
    modes = tuple(modes)
    if not modes or len(set(modes)) != len(modes) or any(mode not in MODES for mode in modes):
        raise ValueError('Modes must be a unique subset of reference,learned-habits.')
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError('Seed must be an integer in [0, 4294967295].')
    bank_path = Path(bank_path).resolve()
    model_path = Path(model_path).resolve() if model_path else None
    if 'learned-habits' in modes and not model_path:
        raise ValueError('learned-habits requires an already fitted --model.')
    bank = load_bank(bank_path)
    model = load_habits(model_path, bank) if model_path else {}
    suite = json.loads(Path(suite_path).read_text(encoding='utf-8'))
    if not isinstance(suite, dict) or not isinstance(suite.get('cases'), list) or not 1 <= len(suite['cases']) <= 100:
        raise ValueError('Suite requires 1-100 cases.')
    preferences = {**DEFAULT_PREFERENCES, **suite.get('preferences', {})}
    if set(preferences) != set(DEFAULT_PREFERENCES):
        raise ValueError('Unknown page preference.')
    if any(not isinstance(preferences[name], bool) for name in ('math_enabled','allow_supplemental_math')):
        raise ValueError('Math preferences must be true or false.')
    if not isinstance(preferences['size'], (int, float)) or not 10 <= preferences['size'] <= 26:
        raise ValueError('Page size must be between 10 and 26.')
    if not isinstance(preferences['line_spacing'], (int, float)) or not 1.2 <= preferences['line_spacing'] <= 2.2:
        raise ValueError('Line spacing must be between 1.2 and 2.2.')
    if not isinstance(preferences['ink'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', preferences['ink']):
        raise ValueError('Ink must be a six-digit hex color.')
    excluded = suite.get('excluded_words', [])
    if not isinstance(excluded, list) or any(not isinstance(w, str) or not re.fullmatch('[A-Za-z]+', w) for w in excluded):
        raise ValueError('excluded_words must be a list of English words.')
    if model and set(w.lower() for w in excluded) & set(w.lower() for w in model.get('training_words', [])):
        raise ValueError('Requested excluded words are present in the fitted training set; fit again.')
    rgb = [int(preferences['ink'][i:i + 2], 16) for i in (1, 3, 5)]
    if sum(a*b for a, b in zip(rgb, (.2126, .7152, .0722))) > 200:
        raise ValueError('Ink is too pale for legible output.')
    ids = set()
    for case in suite['cases']:
        if not isinstance(case, dict) or not re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', str(case.get('id', ''))):
            raise ValueError('Each case requires a safe unique id.')
        if case['id'].lower() in {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}:
            raise ValueError('Case id is a reserved filename.')
        if case['id'].lower() in ids:
            raise ValueError('Duplicate case id: ' + case['id'])
        ids.add(case['id'].lower())
        text = case.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 20000:
            raise ValueError('Each case requires 1-20000 characters of nonblank text.')
        if 'title' in case and not isinstance(case['title'], str):
            raise ValueError('Case titles must be strings.')
        if not preferences['math_enabled'] and any(len(word) > 32 for word in text.split()):
            raise ValueError('Words longer than 32 characters must be split before generation.')
        case['text'] = text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ')
        if preferences['math_enabled']:
            from web.runtime.document_input import prepare_document
            try: prepare_document(text,bank,True,preferences['allow_supplemental_math'])
            except ValueError as error: raise ValueError(f"Invalid math/content in {case['id']}: {error}") from error
        else:
            missing = missing_characters(bank, text)
            if missing:
                raise ValueError(f"Unsupported characters in {case['id']}: {''.join(missing)!r}")
    suite['preferences'] = preferences
    return bank, model, suite, output, modes


def provenance(bank_path, model_path, suite, bank, modes, seed):
    packages = {}
    for package in ('Pillow', 'numpy', 'opencv-python-headless', 'reportlab', 'fastapi', 'pydantic'):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    code = {name: digest(ROOT / name) for name in (
        'scripts/run_handwriting_experiment.py', 'scripts/fit_habits.py', 'web/runtime/reference_renderer.py',
        'web/runtime/habit_model.py', 'web/runtime/symbol_style.py', 'web/runtime/vatr_worker.py', 'web/app.py',
        'web/runtime/math_syntax.py', 'web/runtime/math_glyphs.py', 'web/runtime/math_renderer.py',
        'web/runtime/document_input.py', 'web/document_layout.py')}
    assets = {record['file']: record['sha256'] for group in ('glyphs', 'words') for record in bank.get(group, {}).values()}
    return {
        'bank_sha256': digest(bank_path), 'model_sha256': digest(model_path) if model_path else None,
        'reference_assets': assets, 'suite_sha256': canonical_hash(suite),
        'seed': seed, 'modes': list(modes), 'code_sha256': code,
        'runtime': {'python': platform.python_version(), 'platform': platform.platform(), 'packages': packages},
    }


def snapshot_inputs(output, bank_path, model_path, bank):
    target = output / 'inputs' / 'bank'
    target.mkdir(parents=True)
    shutil.copy2(bank_path, target / 'bank.json')
    for record in list(bank['glyphs'].values()) + list(bank.get('words', {}).values()):
        destination = target / record['file']
        # load_bank already enforces containment; a portable snapshot also rejects
        # absolute or parent-relative names even if they resolve inside the bank.
        name = Path(record['file'])
        if name.is_absolute() or '..' in name.parts:
            raise ValueError('Portable input snapshots require bank-relative asset paths.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bank['_root'] / record['file'], destination)
    if model_path:
        shutil.copy2(model_path, output / 'inputs' / 'habit-model.json')
    return target / 'bank.json', output / 'inputs' / 'habit-model.json' if model_path else None


def render_case(folder, request, preferences):
    from web.app import compose_pdf
    write_json(folder / 'request.json', request)
    completed = subprocess.run([sys.executable, str(ROOT / 'web/runtime/vatr_worker.py'), str(folder / 'request.json')],
                               capture_output=True, text=True, timeout=1800)
    (folder / 'worker.log').write_text(completed.stdout + completed.stderr, encoding='utf-8')
    if completed.returncode:
        raise RuntimeError(f'Generation failed in {folder}; inspect worker.log.')
    generated = json.loads((folder / 'generated.json').read_text(encoding='utf-8'))
    # Elapsed wall time is not part of a reproducible result.
    generated.pop('duration_seconds', None)
    write_json(folder / 'generated.json', generated)
    compose_pdf(folder, {'text': request['text'], 'preferences': preferences}, generated)
    return generated


def review_html(suite, modes, artifacts):
    escape = html.escape
    sections = []
    for case in suite['cases']:
        columns = []
        for mode in modes:
            prefix = case['id'] + '/' + mode
            pages = sorted(name for name in artifacts if name.startswith(prefix + '/page-') and name.endswith('.png'))
            pictures = ''.join(f'<img loading="lazy" src="{escape(name, quote=True)}" alt="{escape(mode, quote=True)} page {i + 1}">' for i, name in enumerate(pages))
            columns.append(f'<article><h3>{escape(mode)}</h3><a href="{prefix}/result.pdf">PDF</a>{pictures}</article>')
        sections.append(f'<section><h2>{escape(case.get("title", case["id"]))}</h2><pre>{escape(case["text"])}</pre><div class="columns">{"".join(columns)}</div></section>')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>Inkself local comparison</title><style>body{font:16px system-ui,sans-serif;margin:2rem;background:#f3f2ee;color:#222}h1{font-size:1.8rem}section{margin:2rem 0}pre{white-space:pre-wrap;background:white;padding:1rem}.columns{display:flex;gap:1rem;align-items:flex-start}article{flex:1;min-width:0}img{width:100%;display:block;margin-top:1rem;background:white;border:1px solid #ccc}@media(max-width:760px){.columns{display:block}}</style>
<h1>Inkself local comparison</h1><p>Review spelling, digits, symbols, joins, spacing and similarity against the original sample. Accuracy and similarity are unverified; software checks are not handwriting validation.</p><p><a href="manifest.json">Reproduction manifest and overlap diagnostics</a></p>''' + ''.join(sections) + '</html>'


def run_experiment(bank_path, model_path, suite_path, output, seed=42, modes=MODES, snapshot=False):
    bank_path = Path(bank_path).resolve()
    model_path = Path(model_path).resolve() if model_path else None
    bank, model, suite, output, modes = preflight(bank_path, model_path, suite_path, output, modes, seed)
    if snapshot:
        for group in ('glyphs', 'words'):
            for record in bank.get(group, {}).values():
                name = Path(record['file'])
                if name.is_absolute() or '..' in name.parts or name.as_posix() == 'bank.json':
                    raise ValueError('Portable snapshots require ordinary bank-relative asset paths.')
    identity = provenance(bank_path, model_path, suite, bank, modes, seed)
    manifest = {
        'schema_version': 1, 'status': 'running', 'run_fingerprint': canonical_hash(identity), 'identity': identity,
        'suite': suite, 'original_inputs': {'bank': str(bank_path), 'model': str(model_path) if model_path else None},
        'snapshot_inputs': snapshot,
        'replay_inputs': {'bank': 'inputs/bank/bank.json', 'model': 'inputs/habit-model.json' if model_path else None, 'suite': 'suite.json'} if snapshot else None,
        'validation': {'text_accuracy': 'unverified', 'writer_similarity': 'unverified', 'human_review_required': True},
        'diagnostics': {case['id']: diagnostics(case, bank, model, [w.lower() for w in suite.get('excluded_words', [])]) for case in suite['cases']},
        'artifact_sha256': {},
    }
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / 'suite.json', suite)
    write_json(output / 'manifest.json', manifest)
    try:
        if snapshot:
            bank_path, model_path = snapshot_inputs(output, bank_path, model_path, bank)
        for case in suite['cases']:
            for mode in modes:
                folder = output / case['id'] / mode
                folder.mkdir(parents=True)
                request = {'text': case['text'], 'seed': seed, 'render_mode': mode, 'reference_bank': str(bank_path),
                           'habit_model': str(model_path) if model_path else None, 'output': str(folder), 'model': str(ROOT / '.local/vendor/vatrpp'),
                           'math_enabled':suite['preferences']['math_enabled'], 'allow_supplemental_math':suite['preferences']['allow_supplemental_math']}
                # Freeze the run's original identity across snapshots and cases.
                # The worker rejects inputs changed after preflight or copying.
                request['expected_input_hashes'] = {'reference_bank_sha256': identity['bank_sha256']}
                if mode == 'learned-habits':
                    request['expected_input_hashes']['habit_model_sha256'] = identity['model_sha256']
                render_case(folder, request, suite['preferences'])
                for path in sorted(folder.iterdir()):
                    if path.suffix in ('.png', '.pdf') or path.name in ('generated.json', 'report.json','layout.json'):
                        manifest['artifact_sha256'][path.relative_to(output).as_posix()] = digest(path)
        (output / 'review.html').write_text(review_html(suite, modes, manifest['artifact_sha256']), encoding='utf-8')
        manifest['artifact_sha256']['review.html'] = digest(output / 'review.html')
        manifest['status'] = 'needs-human-review'
    except Exception as error:
        manifest.update(status='failed', error=str(error))
        write_json(output / 'manifest.json', manifest)
        raise
    write_json(output / 'manifest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', required=True, type=Path)
    parser.add_argument('--model', type=Path, help='Already fitted habit model; required for learned-habits.')
    parser.add_argument('--suite', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--modes', default=','.join(MODES), help='Comma-separated subset: reference,learned-habits')
    parser.add_argument('--snapshot-inputs', action='store_true', help='Copy reviewed private inputs into the local output for portable replay.')
    args = parser.parse_args()
    try:
        result = run_experiment(args.bank, args.model, args.suite, args.output, args.seed, args.modes.split(','), args.snapshot_inputs)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps({'status': result['status'], 'run_fingerprint': result['run_fingerprint'], 'review': str(args.output.resolve() / 'review.html')}))


if __name__ == '__main__':
    main()

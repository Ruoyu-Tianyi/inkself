"""Headless entry for the optional, self-contained CPU inference runtime."""
from __future__ import annotations

import argparse
import multiprocessing
import os
from pathlib import Path
import sys
import traceback


def ensure_stdio(request_path):
    """Own a reliable job log, including when inherited stdio handles are invalid."""
    path = Path(request_path).resolve().parent / 'worker.log'
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open('a', encoding='utf-8', buffering=1)
    sys.stdout = stream
    sys.stderr = stream
    return stream


def main(argv=None):
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description='Inkself CPU handwriting worker')
    parser.add_argument('--worker', type=Path, required=True, metavar='REQUEST_JSON')
    args = parser.parse_args(argv)
    stream = None
    try:
        stream = ensure_stdio(args.worker)
        print('InkselfAI started', flush=True)
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['MPLBACKEND'] = 'Agg'
        from web.runtime.vatr_worker import run
        run(args.worker.resolve())
        print('InkselfAI finished successfully', flush=True)
        return 0
    except Exception:
        if sys.stderr is not None:
            traceback.print_exc()
        return 1
    finally:
        if stream is not None:
            stream.flush()


if __name__ == '__main__':
    raise SystemExit(main())

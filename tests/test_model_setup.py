"""Pinned model installer tests use tiny bytes and never contact the network."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import unquote

from web import model_setup as setup


REAL_MANIFEST = setup.MANIFEST
REPOSITORY = 'blowing-up-groundhogs/vatrpp'
REVISION = 'fb73be2be8e96ce70d9cad9675a30667e19ac376'


class Response:
    def __init__(self, body, status=200):
        self.body = io.BytesIO(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body.read(size)


class Opener:
    def __init__(self, replies):
        self.replies = {name: list(items) for name, items in replies.items()}
        self.requests = []

    def open(self, request, timeout):
        prefix = f'https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/'
        if not request.full_url.startswith(prefix):
            raise AssertionError('Downloader attempted an unpinned URL.')
        name = unquote(request.full_url[len(prefix):])
        self.requests.append((name, request.get_header('Range'), timeout))
        if not self.replies.get(name):
            raise AssertionError('Unexpected network request in test: ' + name)
        reply = self.replies[name].pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class ModelSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = (Path(self.tmp.name) / 'model 数据').resolve()
        self.manifest_path = Path(self.tmp.name) / 'tiny-assets.json'
        self.bodies = {'config.json': b'{"device":"cpu"}',
                       'models/model.py': b'# synthetic model source',
                       'files/unifont.pickle': b'synthetic bytes, not a real pickle',
                       'model.safetensors': b'synthetic safe weights'}
        self.spec = {'schema_version': 1, 'repository': REPOSITORY, 'revision': REVISION,
                     'files': [{'path': name, 'size': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
                               for name, body in self.bodies.items()]}
        self.write_manifest(self.spec)
        self.manifest_patch = patch.object(setup, 'MANIFEST', self.manifest_path)
        self.manifest_patch.start()
        self.sleep_patch = patch.object(setup.time, 'sleep')
        self.sleep_patch.start()
        with setup.LOCK:
            setup.STATES.clear()
        with setup.READY_LOCK:
            setup.READY_CACHE.clear()

    def tearDown(self):
        with setup.LOCK:
            setup.STATES.clear()
        with setup.READY_LOCK:
            setup.READY_CACHE.clear()
        self.sleep_patch.stop()
        self.manifest_patch.stop()
        self.tmp.cleanup()

    def write_manifest(self, spec):
        self.manifest_path.write_text(json.dumps(spec), encoding='utf-8')

    def cache(self, names=None):
        for name in self.bodies if names is None else names:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.bodies[name])

    def seed_state(self):
        with setup.LOCK:
            setup.STATES[str(self.root)] = {'status': 'downloading', 'bytes_completed': 0,
                'bytes_total': sum(item['size'] for item in self.spec['files']),
                'files_completed': 0, 'files_total': len(self.spec['files']),
                'current_file': None, 'message': 'Synthetic test'}

    def download(self, replies, *, seed=True):
        if seed:
            self.seed_state()
        opener = Opener(replies)
        with patch.object(setup.urllib.request, 'build_opener', return_value=opener):
            setup._download(self.root, self.spec)
        return opener

    def assert_not_ready(self):
        self.assertNotEqual(setup.state(self.root)['status'], 'ready')
        self.assertFalse((self.root / 'inkself-verified-assets.json').exists())

    def test_original_manifest_has_49_unique_safe_pinned_assets(self):
        with patch.object(setup, 'MANIFEST', REAL_MANIFEST):
            manifest = setup.manifest()
        self.assertEqual(manifest['repository'], REPOSITORY)
        self.assertEqual(manifest['revision'], REVISION)
        self.assertEqual(len(manifest['files']), 49)
        names = [item['path'] for item in manifest['files']]
        self.assertEqual(len(names), len(set(names)))
        for item in manifest['files']:
            self.assertFalse(PurePosixPath(item['path']).is_absolute())
            self.assertNotIn('..', PurePosixPath(item['path']).parts)
            self.assertNotIn('\\', item['path'])
            self.assertNotIn(':', item['path'])
            self.assertRegex(item['sha256'], r'^[0-9a-f]{64}$')
            self.assertGreater(item['size'], 0)

    def test_manifest_rejects_unpinned_source_and_unsafe_paths(self):
        for key, value in [('repository', 'other/repository'), ('revision', 'main')]:
            spec = dict(self.spec, **{key: value})
            self.write_manifest(spec)
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    setup.manifest()
        for name in ('../outside.py', '/absolute.py', 'models/../outside.py',
                     r'models\outside.py', 'C:/outside.py', '', '.', 'models//model.py'):
            spec = copy.deepcopy(self.spec)
            spec['files'][0]['path'] = name
            self.write_manifest(spec)
            with self.subTest(path=name):
                with self.assertRaises(ValueError):
                    setup.manifest()

    def test_manifest_rejects_bad_hash_size_and_duplicate_paths(self):
        for key, value in [('sha256', 'g' * 64), ('sha256', 'a' * 63), ('size', 0), ('size', -1)]:
            spec = copy.deepcopy(self.spec)
            spec['files'][0][key] = value
            self.write_manifest(spec)
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    setup.manifest()
        for entries in ([], [self.spec['files'][0], self.spec['files'][0]]):
            self.write_manifest(dict(self.spec, files=entries))
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    setup.manifest()

    def test_existing_files_are_reused_only_after_size_and_sha_verification(self):
        self.cache()
        opener = self.download({})
        self.assertEqual(opener.requests, [])
        result = setup.state(self.root)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['files_completed'], len(self.spec['files']))
        self.assertEqual(result['bytes_completed'], result['bytes_total'])
        self.assertEqual(json.loads((self.root / 'inkself-verified-assets.json').read_text()), self.spec)

    def test_partial_range_206_appends_and_verifies_complete_file(self):
        self.cache()
        name = 'model.safetensors'
        target = self.root / name
        target.unlink()
        body = self.bodies[name]
        partial = target.with_name(target.name + '.part')
        partial.write_bytes(body[:7])
        opener = self.download({name: [Response(body[7:], 206)]})
        self.assertEqual(opener.requests, [(name, 'bytes=7-', 30)])
        self.assertEqual(target.read_bytes(), body)
        self.assertFalse(partial.exists())
        self.assertEqual(setup.state(self.root)['status'], 'ready')

    def test_partial_range_200_resets_instead_of_appending(self):
        self.cache()
        name = 'model.safetensors'
        target = self.root / name
        target.unlink()
        partial = target.with_name(target.name + '.part')
        partial.write_bytes(b'bad old prefix')
        opener = self.download({name: [Response(self.bodies[name], 200)]})
        self.assertEqual(opener.requests[0][1], 'bytes=14-')
        self.assertEqual(target.read_bytes(), self.bodies[name])
        self.assertEqual(setup.state(self.root)['status'], 'ready')

    def test_complete_verified_partial_is_promoted_without_downloading(self):
        self.cache()
        target = self.root / 'model.safetensors'
        target.replace(target.with_name(target.name + '.part'))
        opener = self.download({})
        self.assertEqual(opener.requests, [])
        self.assertEqual(target.read_bytes(), self.bodies['model.safetensors'])
        self.assertEqual(setup.state(self.root)['status'], 'ready')

    def test_wrong_hash_and_oversized_downloads_never_mark_ready(self):
        name = 'model.safetensors'
        for body in (b'X' * len(self.bodies[name]), self.bodies[name] + b'oversized'):
            with self.subTest(length=len(body)):
                self.cache()
                target = self.root / name
                target.unlink()
                self.download({name: [Response(body), Response(body), Response(body)]})
                self.assertEqual(setup.state(self.root)['status'], 'failed')
                self.assertFalse(target.exists())
                self.assert_not_ready()
                (self.root / (name + '.part')).unlink(missing_ok=True)

    def test_corrupt_existing_file_is_redownloaded(self):
        self.cache()
        name = 'config.json'
        target = self.root / name
        target.write_bytes(b'X' * len(self.bodies[name]))
        opener = self.download({name: [Response(self.bodies[name])]})
        self.assertEqual([item[0] for item in opener.requests], [name])
        self.assertEqual(target.read_bytes(), self.bodies[name])
        self.assertEqual(setup.state(self.root)['status'], 'ready')

    def test_success_requires_every_asset_and_sha_before_ready(self):
        opener = self.download({name: [Response(body)] for name, body in self.bodies.items()})
        self.assertEqual(len(opener.requests), len(self.spec['files']))
        self.assertEqual(setup.state(self.root)['status'], 'ready')
        for item in self.spec['files']:
            target = self.root / item['path']
            self.assertEqual(target.stat().st_size, item['size'])
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), item['sha256'])

    def test_concurrent_start_creates_only_one_downloader_thread(self):
        barrier = threading.Barrier(8)
        results, errors = [], []
        def begin():
            try:
                barrier.wait(timeout=3)
                results.append(setup.start(self.root))
            except Exception as error:
                errors.append(error)
        workers = [threading.Thread(target=begin) for _ in range(8)]
        with patch.object(setup.threading, 'Thread') as downloader:
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=4)
            self.assertFalse(any(worker.is_alive() for worker in workers))
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 8)
            self.assertTrue(all(result['status'] == 'downloading' for result in results))
            downloader.assert_called_once()
            downloader.return_value.start.assert_called_once()

    def test_failure_can_retry_and_keeps_previously_verified_files(self):
        first, second = list(self.bodies)[:2]
        opener = self.download({first: [Response(self.bodies[first])],
                               second: [OSError('Synthetic disconnected network')] * 3})
        self.assertEqual(setup.state(self.root)['status'], 'failed')
        self.assertEqual((self.root / first).read_bytes(), self.bodies[first])
        self.assertEqual(setup.state(self.root)['files_completed'], 1)
        self.assertEqual(len(opener.requests), 4)
        self.assert_not_ready()
        with patch.object(setup.threading, 'Thread') as downloader:
            result = setup.start(self.root)
            self.assertEqual(result['status'], 'downloading')
            downloader.return_value.start.assert_called_once()
        retries = self.download({name: [Response(body)] for name, body in self.bodies.items() if name != first}, seed=False)
        self.assertNotIn(first, [name for name, _, _ in retries.requests])
        self.assertEqual(setup.state(self.root)['status'], 'ready')

    def test_asset_escape_symlink_and_reparse_points_are_rejected(self):
        self.root.mkdir()
        with self.assertRaisesRegex(ValueError, 'escapes'):
            setup._asset(self.root, '../outside')
        with patch.object(Path, 'is_symlink', return_value=True):
            with self.assertRaisesRegex(ValueError, 'links'):
                setup._asset(self.root, 'model.safetensors')
        target = self.root / 'model.safetensors'
        target.write_bytes(b'synthetic target')
        class Info:
            st_file_attributes = 0x400
        with patch.object(Path, 'is_symlink', return_value=False), patch.object(Path, 'lstat', return_value=Info()):
            with self.assertRaisesRegex(ValueError, 'links'):
                setup._asset(self.root, 'model.safetensors')

    def test_completed_marker_cannot_follow_a_symbolic_link(self):
        marker = self.root / 'inkself-verified-assets.json'
        original = Path.is_symlink
        def linked(path):
            return path == marker or original(path)
        with patch.object(Path, 'is_symlink', autospec=True, side_effect=linked):
            self.download({name: [Response(body)] for name, body in self.bodies.items()})
        self.assertEqual(setup.state(self.root)['status'], 'failed')
        self.assertFalse(marker.exists())

    def test_restart_state_does_not_trust_oversized_existing_weights(self):
        self.cache()
        weight = self.root / 'model.safetensors'
        original = Path.stat
        def oversized(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == weight:
                values = list(info)
                values[6] = 100_000_001
                return os.stat_result(values)
            return info
        with patch.object(Path, 'stat', autospec=True, side_effect=oversized):
            self.assertNotEqual(setup.state(self.root)['status'], 'ready')

    def test_ready_cache_reuses_hashes_and_invalidates_after_file_change(self):
        self.cache()
        with patch.object(setup, '_sha', wraps=setup._sha) as hashed:
            self.assertTrue(setup.assets_ready(self.root))
            self.assertEqual(hashed.call_count, len(self.spec['files']))
            self.assertTrue(setup.assets_ready(self.root))
            self.assertEqual(hashed.call_count, len(self.spec['files']))
            path = self.root / 'config.json'
            path.write_bytes(b'X' * len(self.bodies['config.json']))
            self.assertFalse(setup.assets_ready(self.root))
            self.assertGreater(hashed.call_count, len(self.spec['files']))
            after_failure = hashed.call_count
            self.assertFalse(setup.assets_ready(self.root))
            self.assertEqual(hashed.call_count, after_failure)

    def test_missing_or_wrong_size_is_false_without_hashing(self):
        with patch.object(setup, '_sha') as hashed:
            self.assertFalse(setup.assets_ready(self.root))
            hashed.assert_not_called()
            self.cache()
            (self.root / 'model.safetensors').write_bytes(b'too short')
            self.assertFalse(setup.assets_ready(self.root))
            hashed.assert_not_called()

    def test_ready_state_and_manifest_identity_detect_changed_assets(self):
        self.cache()
        self.assertEqual(setup.state(self.root)['status'], 'ready')
        self.seed_state()
        setup._update(self.root, status='ready')
        (self.root / 'config.json').write_bytes(b'X' * len(self.bodies['config.json']))
        self.assertEqual(setup.state(self.root)['status'], 'idle')
        self.cache()
        self.assertTrue(setup.assets_ready(self.root))
        changed = copy.deepcopy(self.spec)
        changed['files'][0]['sha256'] = '0' * 64
        self.write_manifest(changed)
        self.assertFalse(setup.assets_ready(self.root))


if __name__ == '__main__':
    unittest.main()

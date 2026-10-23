import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from desktop_runtime import InstanceLock, OwnedServer, read_config, request_json, write_json


class DesktopRuntime(unittest.TestCase):
    def test_config_requires_absolute_runtime_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            self.assertEqual(read_config(folder), {})
            write_json(folder/'desktop-config.json', {'model_python':'relative/python.exe'})
            with self.assertRaises(ValueError):
                read_config(folder)
            write_json(folder/'desktop-config.json', {'model_python':str(folder/'python.exe'), 'untrusted':'ignored'})
            self.assertEqual(read_config(folder), {'model_python':str(folder/'python.exe')})

    def test_instance_lock_is_scoped_to_data_and_released(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            first = InstanceLock(data)
            second = InstanceLock(data)
            try:
                self.assertTrue(first.acquired)
                self.assertFalse(second.acquired)
            finally:
                second.close()
                first.close()
            third = InstanceLock(data)
            try:
                self.assertTrue(third.acquired)
            finally:
                third.close()

    def test_old_service_cannot_impersonate_owned_instance(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = MagicMock()
            fake.poll.return_value = None
            server = OwnedServer(temp)
            with patch('desktop_runtime.subprocess.Popen', return_value=fake), patch('desktop_runtime.ProcessJob'), patch('desktop_runtime.session', return_value={'mode':'local-single-owner', 'instance_id':'different'}), patch('desktop_runtime.time.sleep'):
                with self.assertRaisesRegex(RuntimeError, '超时'):
                    server.start()
            self.assertFalse((Path(temp)/'desktop-session.json').exists())
            fake.terminate.assert_called_once()

    def test_stopping_server_preserves_other_instance_state(self):
        with tempfile.TemporaryDirectory() as temp:
            server = OwnedServer(temp)
            state = Path(temp)/'desktop-session.json'
            write_json(state, {'instance_id':'another-controller'})
            server.stop()
            self.assertEqual(json.loads(state.read_text())['instance_id'], 'another-controller')

    def test_server_from_unrelated_chinese_path_serves_assets_and_stops(self):
        with tempfile.TemporaryDirectory(prefix='Inkself 空格 ') as temp:
            server = OwnedServer(temp)
            try:
                url = server.start()
                health = request_json(url, '/api/health')
                self.assertEqual(health['status'], 'ok')
                self.assertEqual(request_json(url, '/api/profiles'), [])
                self.assertEqual(request_json(url, '/api/session')['instance_id'], server.instance)
                self.assertTrue((Path(temp)/'desktop-session.json').exists())
                pid = server.process.pid
            finally:
                server.stop()
            self.assertIsNotNone(server.process.poll(), pid)
            self.assertFalse((Path(temp)/'desktop-session.json').exists())
            with self.assertRaises(OSError):
                request_json(url, '/api/session')


if __name__ == '__main__':
    unittest.main()

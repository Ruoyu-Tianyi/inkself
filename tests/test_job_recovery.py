"""Submission and worker failures must release queue capacity for a retry."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from tests.test_math_renderer import fixture
from web import app as web


class JobRecovery(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.pid='e'*32
        self.profile=self.root/'profiles'/self.pid/'profile.json'
        bank=self.profile.parent/'bank';bank.mkdir(parents=True)
        fixture(bank)
        web.write(self.profile,{'id':self.pid,'name':'Synthetic recovery','status':'ready',
            'created_at':'2026-01-01','sample_sha256':'synthetic-math',
            'sample':{'lines':[]},'selected_lines':[],'preferences':{'size':14},
            'reference_bank':'bank/bank.json'})
        self.original_profile=web.read(self.profile)
        self.store=patch.object(web,'DATA',self.root);self.store.start()
        self.submit=patch.object(web.POOL,'submit');self.worker=self.submit.start()
        self.client=TestClient(web.app);self.client.__enter__()
        self.headers={'X-Inkself-Token':self.client.get('/api/session').json()['token']}

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.submit.stop();self.store.stop();self.temp.cleanup()

    def queue(self):
        return self.client.post('/api/jobs',headers=self.headers,json={
            'profile_id':self.pid,'text':'Result 123','render_mode':'reference','size':18})

    def history(self):
        return self.client.get('/api/jobs').json()

    def test_executor_rejection_restores_preferences_and_allows_retry(self):
        self.worker.side_effect=RuntimeError('cannot schedule new futures')
        response=self.queue()
        self.assertEqual(response.status_code,503,response.text)
        failed=self.history()[0]
        self.assertEqual(failed['status'],'failed')
        self.assertIn('completed_at',failed)
        self.assertEqual(web.read(self.profile),self.original_profile)
        # An executor can retain work after failing to start a thread.
        with patch.object(web.subprocess,'run') as run:
            web.run_job(failed['id'])
            run.assert_not_called()
        self.worker.side_effect=None
        self.assertEqual(self.queue().status_code,202)

    def test_request_write_failure_does_not_leave_queued_job(self):
        real_write=web.write
        def failing_write(path,data):
            if Path(path).name=='request.json':raise OSError('disk full')
            return real_write(path,data)
        with patch.object(web,'write',side_effect=failing_write):
            response=self.queue()
        self.assertEqual(response.status_code,503,response.text)
        self.worker.assert_not_called()
        self.assertEqual(self.history()[0]['status'],'failed')
        self.assertEqual(web.read(self.profile),self.original_profile)
        self.assertEqual(self.queue().status_code,202)

    def test_unwritable_failure_record_withdraws_queued_state(self):
        response=self.queue();jid=response.json()['id']
        with (patch.object(web,'write',side_effect=OSError('disk full')),
              self.assertLogs(web.LOGGER,level='ERROR'),patch.object(web.subprocess,'run') as run):
            web.run_job(jid)
            run.assert_not_called()
        self.assertEqual(self.history(),[])
        self.assertTrue((self.root/'jobs'/jid/'request.json').is_file())
        self.assertEqual(self.queue().status_code,202)

    def test_worker_failure_is_terminal_and_can_be_retried(self):
        for failure in (subprocess.TimeoutExpired('synthetic worker',1800),OSError('permission denied')):
            with self.subTest(failure=type(failure).__name__):
                response=self.queue();jid=response.json()['id']
                with patch.object(web.subprocess,'run',side_effect=failure):web.run_job(jid)
                saved=web.read(self.root/'jobs'/jid/'job.json')
                self.assertEqual(saved['status'],'failed')
                self.assertIn('completed_at',saved)
        self.assertEqual(self.queue().status_code,202)

    def test_completion_write_failure_does_not_remain_running(self):
        response=self.queue();jid=response.json()['id'];folder=self.root/'jobs'/jid
        web.write(folder/'generated.json',{'model':{'name':'synthetic'},'duration_seconds':0})
        web.write(folder/'layout.json',{'warnings':[]})
        (folder/'result.pdf').write_bytes(b'synthetic output')
        real_write=web.write
        def failing_write(path,data):
            if Path(path).name=='job.json' and data.get('status')=='needs-review':
                raise OSError('disk full')
            return real_write(path,data)
        with patch.object(web,'write',side_effect=failing_write),patch.object(web,'compose_pdf',return_value=1),patch.object(web.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
            web.run_job(jid)
        saved=web.read(folder/'job.json')
        self.assertEqual(saved['status'],'failed')
        self.assertIn('completed_at',saved)
        self.assertEqual(self.queue().status_code,202)


if __name__=='__main__':unittest.main()

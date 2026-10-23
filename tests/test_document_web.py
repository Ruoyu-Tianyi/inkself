import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from web import app as w
from tests.test_math_renderer import fixture


class DocumentWeb(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.store=patch.object(w,'DATA',self.root);self.store.start()
        self.client=TestClient(w.app);self.client.__enter__()
        self.headers={'X-Inkself-Token':self.client.get('/api/session').json()['token']}
    def tearDown(self):
        self.client.__exit__(None,None,None);self.store.stop();self.temp.cleanup()
    def upload(self,content,filename='answer.md',headers=None):
        return self.client.post('/api/documents/markdown',headers=self.headers if headers is None else headers,files={'file':(filename,content,'text/markdown')})
    def profile(self):
        pid='d'*32;folder=self.root/'profiles'/pid
        bank=folder/'reference-bank';bank.mkdir(parents=True);fixture(bank)
        w.write(folder/'profile.json',{'id':pid,'name':'Synthetic document','status':'ready','created_at':'2026-01-01',
            'sample_sha256':'synthetic-math','sample':{'lines':[]},'selected_lines':[],
            'preferences':{},'reference_bank':'reference-bank/bank.json'})
        return pid
    def test_import_keeps_source_preview_and_math_without_generating(self):
        source='# 1.\n**Result** $x_i=2$.\n'
        response=self.upload(source.encode())
        self.assertEqual(response.status_code,201,response.text)
        result=response.json()
        self.assertEqual(result['source_text'],source)
        self.assertEqual(result['text'],'1.\nResult $x_i=2$.')
        self.assertTrue(result['math_enabled'])
        self.assertEqual(w.read(self.root/'documents'/f"{result['id']}.json"),result)
        self.assertEqual(list((self.root/'jobs').glob('*')),[])
    def test_bad_upload_and_foreign_origin_do_not_create_document(self):
        for content,name in [(b'bad','x.exe'),(b'\xff','x.md'),(b'a'*(256*1024+1),'x.md'),(b'<script>bad</script>','x.md')]:
            self.assertEqual(self.upload(content,name).status_code,422)
        self.assertEqual(self.upload(b'text',headers={}).status_code,403)
        self.assertEqual(self.upload(b'text',headers={**self.headers,'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(list((self.root/'documents').glob('*')),[])
    def test_document_source_and_edits_are_recorded_per_job(self):
        pid=self.profile();original='# Result\nResult $x_i=2$'
        doc=self.upload(original.encode()).json()
        with patch.object(w.POOL,'submit'):
            response=self.client.post('/api/jobs',headers=self.headers,json={'profile_id':pid,'text':doc['text']+' Done',
                'render_mode':'reference','math_enabled':True,'document_id':doc['id']})
        self.assertEqual(response.status_code,202,response.text)
        job=response.json();folder=self.root/'jobs'/job['id']
        self.assertTrue(job['document_source']['edited_after_import'])
        self.assertNotIn('document_id',job['preferences'])
        self.assertEqual((folder/'source.md').read_text(),original)
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/files/source.md").text,original)
    def test_unknown_document_id_is_rejected_before_queueing(self):
        response=self.client.post('/api/jobs',headers=self.headers,json={'profile_id':'d'*32,'text':'x','document_id':'../../bad'})
        self.assertEqual(response.status_code,404)
        self.assertEqual(list((self.root/'jobs').glob('*')),[])
    def test_onboarding_distinguishes_missing_runtime_and_prepared_profiles(self):
        model={'ready':False,'runtime_ready':False,'bundled_runtime':False}
        with patch.object(w,'model_status',return_value=model):
            first=self.client.get('/api/onboarding').json()
            self.assertFalse(first['can_generate']);self.assertEqual(first['profiles_ready'],0)
            self.assertEqual(self.client.post('/api/setup/model',headers=self.headers).status_code,409)
            self.profile()
            prepared=self.client.get('/api/onboarding').json()
            self.assertTrue(prepared['can_generate']);self.assertEqual(prepared['prepared_profiles'],1)
    def test_setup_requires_local_session_before_downloader_is_started(self):
        with patch('web.model_setup.start') as start:
            self.assertEqual(self.client.post('/api/setup/model').status_code,403)
            start.assert_not_called()


if __name__=='__main__':unittest.main()

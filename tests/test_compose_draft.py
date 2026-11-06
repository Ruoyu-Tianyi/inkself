"""Private compose drafts survive a desktop restart and changing local ports."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from web import app as web


class ComposeDraftAPI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=patch.object(web,'DATA',self.root);self.store.start()
        self.client=TestClient(web.app);self.client.__enter__()
        self.headers={'X-Inkself-Token':self.client.get('/api/session').json()['token']}

    def tearDown(self):
        self.client.__exit__(None,None,None);self.store.stop();self.temp.cleanup()

    def test_roundtrip_retains_unfinished_text_and_settings_across_clients(self):
        self.assertIsNone(self.client.get('/api/compose-draft').json())
        draft={'version':1,'edited_at':1793952000000,'profile_id':'','text':'An unfinished $x_{', 'document_id':None,
               'dirty':True,'preferences':{'spacing':{'preset':'compact'},'answer_header':'Name: Test'}}
        response=self.client.put('/api/compose-draft',headers=self.headers,json=draft)
        self.assertEqual(response.status_code,200,response.text)
        saved=response.json()
        self.assertEqual(saved['text'],draft['text'])
        self.assertEqual(saved['edited_at'],draft['edited_at'])
        self.assertEqual(saved['preferences']['spacing']['word'],.8)
        self.assertEqual(saved['preferences']['size'],16)
        with TestClient(web.app,base_url='http://localhost:19999') as reopened:
            self.assertEqual(reopened.get('/api/compose-draft').json(),saved)
        self.assertEqual(list((self.root/'jobs').glob('*')),[])

    def test_invalid_or_foreign_writes_leave_previous_draft_intact(self):
        saved=self.client.put('/api/compose-draft',headers=self.headers,json={'text':'Keep this'}).json()
        for draft in ({'text':'x'*20001},{'version':2},{'edited_at':-1},{'profile_id':'../../bad'},
                      {'document_id':'bad'},{'preferences':{'spacing':{'word':3}}},
                      {'preferences':{'size':0}},{'preferences':{'render_mode':'unknown'}}):
            with self.subTest(draft=str(draft)[:80]):
                response=self.client.put('/api/compose-draft',headers=self.headers,json=draft)
                self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.client.put('/api/compose-draft',json={}).status_code,403)
        self.assertEqual(self.client.put('/api/compose-draft',headers={**self.headers,'Origin':'https://example.org'},json={}).status_code,403)
        self.assertEqual(self.client.get('/api/compose-draft').json(),saved)

    def test_stale_profile_identity_does_not_discard_written_content(self):
        payload={'profile_id':'a'*32,'document_id':'b'*32,'text':'Keep my draft','dirty':True}
        response=self.client.put('/api/compose-draft',headers=self.headers,json=payload)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get('/api/compose-draft').json()['text'],'Keep my draft')

    def test_save_and_load_failures_are_reported_without_overwriting_previous_file(self):
        self.client.put('/api/compose-draft',headers=self.headers,json={'text':'Keep this'})
        path=self.root/'compose-draft.json';previous=path.read_bytes()
        with patch.object(web,'write',side_effect=OSError('disk full')):
            self.assertEqual(self.client.put('/api/compose-draft',headers=self.headers,json={'text':'new'}).status_code,503)
        self.assertEqual(path.read_bytes(),previous)
        path.write_text('{incomplete',encoding='utf-8')
        self.assertEqual(self.client.get('/api/compose-draft').status_code,503)
        self.assertEqual(path.read_text(encoding='utf-8'),'{incomplete')


if __name__=='__main__':unittest.main()

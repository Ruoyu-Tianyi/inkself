"""The API gates math syntax and supplemental shapes before creating work."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from tests.test_math_renderer import fixture
from web import app as w


class MathWeb(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.pid='d'*32;folder=self.root/'profiles'/self.pid
        bank_dir=folder/'reference-bank';bank_dir.mkdir(parents=True);fixture(bank_dir)
        w.write(folder/'profile.json',{'id':self.pid,'name':'Synthetic math','status':'ready',
            'sample_sha256':'synthetic-math','sample':{'lines':[]},'selected_lines':[],
            'preferences':{},'reference_bank':'reference-bank/bank.json'})
        self.patch=patch.object(w,'DATA',self.root);self.patch.start()
        self.client=TestClient(w.app);self.client.__enter__()
        self.headers={'X-Inkself-Token':self.client.get('/api/session').json()['token']}
    def tearDown(self):
        self.client.__exit__(None,None,None);self.patch.stop();self.tmp.cleanup()
    def submit(self,text,**fields):
        return self.client.post('/api/jobs',headers=self.headers,json={'profile_id':self.pid,'text':text,'render_mode':'reference',**fields})
    def test_math_flags_and_source_identity_reach_worker(self):
        with patch.object(w.POOL,'submit'):
            r=self.submit(r'Result $\alpha_i=\frac{x_i}{2}$',math_enabled=True,allow_supplemental_math=True)
        self.assertEqual(r.status_code,202,r.text)
        request=w.read(self.root/'jobs'/r.json()['id']/'request.json')
        self.assertTrue(request['math_enabled']);self.assertTrue(request['allow_supplemental_math'])
        self.assertIn('reference_bank_sha256',request['expected_input_hashes'])
    def test_missing_supplement_and_bad_math_do_not_create_jobs(self):
        for text,allow in [(r'$\alpha_i$',False),(r'$\input{file}$',True),('$x_{1$',True)]:
            with self.subTest(text=text):
                self.assertEqual(self.submit(text,math_enabled=True,allow_supplemental_math=allow).status_code,422)
        self.assertEqual(list((self.root/'jobs').glob('*/job.json')),[])
    def test_long_reference_is_allowed_but_neural_mode_keeps_its_limit(self):
        with patch.object(w.POOL,'submit'):
            self.assertEqual(self.submit('a '*2001).status_code,202)
            response=self.client.post('/api/jobs',headers=self.headers,json={'profile_id':self.pid,'text':'a '*2001,'render_mode':'model'})
            self.assertEqual(response.status_code,422)
    def test_formula_mode_rejects_neural_renderer_and_overlong_documents(self):
        self.assertEqual(self.client.post('/api/jobs',headers=self.headers,json={'profile_id':self.pid,'text':'$x_i$','render_mode':'model','math_enabled':True}).status_code,422)
        self.assertEqual(self.submit('a '*10001).status_code,422)


if __name__=='__main__':unittest.main()

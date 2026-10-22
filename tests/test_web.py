"""Web API tests use a synthetic printed fixture, never claim personal similarity."""
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageFont
from fastapi.testclient import TestClient
from web import app as w


def sample():
    image=Image.new('RGB',(1500,650),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf' if Path('C:/Windows/Fonts/arial.ttf').exists() else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',42)
    for i,line in enumerate(w.PROMPT_LINES):draw.text((35,25+i*110),line,font=font,fill='#20334a')
    stream=io.BytesIO();image.save(stream,format='PNG');return stream.getvalue()


class WebAPI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name)
        self.store=patch.object(w,'DATA',self.data);self.store.start()
        self.client=TestClient(w.app);self.client.__enter__()
        self.headers={'X-Inkself-Token':self.client.get('/api/session').json()['token']}
    def tearDown(self):
        self.client.__exit__(None,None,None);self.store.stop();self.tmp.cleanup()
    def create(self):
        response=self.client.post('/api/profiles',headers=self.headers,data={'name':'Synthetic fixture'},files={'file':('sample.png',sample(),'image/png')})
        self.assertEqual(response.status_code,201,response.text);return response.json()
    def review(self,profile):
        response=self.client.post(f"/api/profiles/{profile['id']}/review",headers=self.headers,json={'lines':list(range(len(profile['sample']['lines']))),'inspected':True})
        self.assertEqual(response.status_code,200);return response.json()
    def test_upload_review_and_delete(self):
        p=self.create();self.assertGreaterEqual(len(p['sample']['lines']),3)
        self.assertEqual(p['status'],'needs-review')
        image=self.client.get(f"/api/profiles/{p['id']}/sample/normalized.png")
        self.assertEqual(image.status_code,200)
        self.assertEqual(self.review(p)['status'],'ready')
        response=self.client.delete('/api/profiles/'+p['id'],headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertEqual(self.client.get('/api/profiles').json(),[])
    def test_csrf_and_foreign_host_rejected(self):
        self.assertEqual(self.client.post('/api/profiles',data={'name':'x'}).status_code,403)
        self.assertEqual(self.client.post('/api/profiles',headers={**self.headers,'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/health',headers={'Host':'evil.example'}).status_code,400)
    def test_bad_image_and_blank_leave_no_profiles(self):
        image=Image.new('RGB',(500,500),'white');stream=io.BytesIO();image.save(stream,format='PNG')
        for content in [b'not image',stream.getvalue()]:
            response=self.client.post('/api/profiles',headers=self.headers,data={'name':'x'},files={'file':('x.png',content,'image/png')})
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.client.get('/api/profiles').json(),[])
    def test_review_indices_and_unreviewed_gate(self):
        p=self.create()
        for lines in [[-1],[999],[0,0]]:
            self.assertEqual(self.client.post(f"/api/profiles/{p['id']}/review",headers=self.headers,json={'lines':lines,'inspected':True}).status_code,422)
        with patch.object(w,'model_status',return_value={'ready':True}):
            response=self.client.post('/api/jobs',headers=self.headers,json={'profile_id':p['id'],'text':'Hello'})
            self.assertEqual(response.status_code,409)
    def test_missing_model_and_unsupported_content(self):
        p=self.review(self.create())
        with patch.object(w,'model_status',return_value={'ready':False}):
            self.assertEqual(self.client.post('/api/jobs',headers=self.headers,json={'profile_id':p['id'],'text':'Hello'}).status_code,503)
        for text in ['中文','x = 5','  ','a'*33,'$12']:
            self.assertEqual(self.client.post('/api/jobs',headers=self.headers,json={'profile_id':p['id'],'text':text}).status_code,422)
    def test_job_queue_and_active_delete_protection(self):
        p=self.review(self.create())
        with patch.object(w,'model_status',return_value={'ready':True}),patch.object(w.POOL,'submit'):
            response=self.client.post('/api/jobs',headers=self.headers,json={'profile_id':p['id'],'text':'Hello 27'})
            self.assertEqual(response.status_code,202,response.text);job=response.json()
            self.assertEqual(job['content_verification'],'needs-human-review')
            self.assertEqual(w.read(self.data/'profiles'/p['id']/'profile.json')['preferences']['seed'],42)
            self.assertEqual(self.client.delete('/api/profiles/'+p['id'],headers=self.headers).status_code,409)
            self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/files/request.json").status_code,404)
            self.assertEqual(self.client.post(f"/api/jobs/{job['id']}/feedback",headers=self.headers,json={'text_correct':True,'similarity':5,'naturalness':5}).status_code,409)
    def test_pdf_composition_and_feedback(self):
        p=self.review(self.create());jid='a'*32;folder=self.data/'jobs'/jid;folder.mkdir(parents=True)
        word=Image.new('L',(120,32),'white');ImageDraw.Draw(word).text((10,4),'TEST',fill=0);word.save(folder/'word.png')
        job={'id':jid,'profile_id':p['id'],'profile_name':p['name'],'created_at':w.now(),'status':'needs-review','text':'TEST '*80,
             'preferences':{'size':16,'line_spacing':1.2,'ink':'#263d57'}}
        generated={'model':'synthetic-composition-only','words':[{'file':'word.png','text':'TEST'} for _ in range(80)]}
        pages=w.compose_pdf(folder,job,generated);self.assertGreaterEqual(pages,1)
        w.write(folder/'job.json',job)
        self.assertEqual(self.client.get(f'/api/jobs/{jid}/files/result.pdf').status_code,200)
        response=self.client.post(f'/api/jobs/{jid}/feedback',headers=self.headers,json={'text_correct':False,'similarity':2,'naturalness':3,'notes':'fixture'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['content_verification'],'human-reported-errors')
    def test_light_ink_and_incomplete_attestation_rejected(self):
        p=self.create()
        self.assertEqual(self.client.post(f"/api/profiles/{p['id']}/review",headers=self.headers,json={'lines':[0],'inspected':False}).status_code,422)
        self.review(p)
        self.assertEqual(self.client.post('/api/jobs',headers=self.headers,json={'profile_id':p['id'],'text':'Hello','ink':'#ffffff'}).status_code,422)

    def test_restart_marks_interrupted_tasks(self):
        jid='b'*32;folder=self.data/'jobs'/jid
        w.write(folder/'job.json',{'id':jid,'status':'running','created_at':w.now()})
        with TestClient(w.app):
            self.assertEqual(w.read(folder/'job.json')['status'],'interrupted')

    def test_traversal_and_prompt(self):
        self.assertEqual(self.client.get('/api/profiles/not-an-id/sample/normalized.png').status_code,404)
        self.assertTrue(self.client.get('/api/prompt.pdf').content.startswith(b'%PDF'))
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertIn('frame-ancestors',self.client.get('/').headers['content-security-policy'])

if __name__=='__main__':unittest.main()

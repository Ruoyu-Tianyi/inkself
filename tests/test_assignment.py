import hashlib,json,string,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from fastapi.testclient import TestClient
from web.runtime.assignment import parse_assignment,preflight_assignment,render_assignment,compose_assignment
from web.runtime.reference_renderer import load_bank
from web.runtime.word_spacing import fit_word_spacing


def bank_fixture(root):
    root.mkdir(parents=True,exist_ok=True)
    image=Image.new('L',(12,20),255);ImageDraw.Draw(image).line((2,17,5,3,9,17),fill=20,width=2)
    image.save(root/'ink.png');digest=hashlib.sha256((root/'ink.png').read_bytes()).hexdigest()
    value={'schema_version':1,'reviewed':True,'source_sha256':'synthetic','words':{},
        'glyphs':{c:{'file':'ink.png','sha256':digest,'baseline':18,'advance':14}
            for c in string.ascii_letters+string.digits+'+-=%.,;?:×÷'}}
    (root/'bank.json').write_text(json.dumps(value));return load_bank(root/'bank.json')


class Assignment(unittest.TestCase):
    def test_structure_keeps_bullets_choices_tables_and_terminal_numbers(self):
        source='## 1–2\n1. B\n2. E\n\n## 3\n**(a)** EMV_C = 2.175.\n\n| A | Max |\n|---|---|\n| C | 15 |\n\n```text\n□ D0\n└── Weak (0.825) → −2.90\n```\n\n- First reason.\n- Second reason.'
        doc=parse_assignment(source)
        self.assertEqual(doc['summary'],{'heading':2,'paragraph':3,'table':1,'tree':1,'choices':1})
        self.assertEqual(doc['source_sha256'],hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(next(b for b in doc['blocks'] if b['kind']=='choices')['choices'],[['1','B'],['2','E']])
        tree=next(b for b in doc['blocks'] if b['kind']=='tree')
        self.assertIn('0.825',tree['rows'][1]['text']);self.assertIn('-2.90',tree['rows'][1]['text'])
        self.assertTrue(doc['blocks'][-1]['text'].startswith('- Second'))

    def test_rejects_executable_html_bad_tables_and_unclosed_trees(self):
        for source in ['```python\nprint(1)\n```','<script>alert(1)</script>','| A | B |\n|---|---|\n| 1 |','```text\n└── x']:
            with self.subTest(source=source),self.assertRaises(ValueError):parse_assignment(source)

    def test_math_supplements_require_opt_in(self):
        with tempfile.TemporaryDirectory() as temporary:
            bank=bank_fixture(Path(temporary))
            with self.assertRaises(ValueError):preflight_assignment('## 1\na. p* > 0.',bank,False)
            preflight_assignment('## 1\na. p* > 0.',bank,True)

    def test_end_to_end_repeatable_and_table_headers_repeat_after_wrap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);bank=bank_fixture(root/'bank');spacing=fit_word_spacing()
            source='## 1\n1. B\n2. E\n\n## 2\n**(a)** $x_i=2$.\n\n| Alternative | Maximum |\n|---|---|\n'+'\n'.join(f'| A{i} | {i} |' for i in range(70))
            outputs=[]
            for name in ('one','two'):
                folder=root/name;folder.mkdir()
                request={'text':source,'seed':42,'answer_size':16,'allow_supplemental_math':True,'answer_header':'Name: Test'}
                meta=render_assignment(request,bank,None,spacing,folder)
                generated={'assignment_layout':meta,'model':{'name':'Synthetic'}}
                count=compose_assignment(folder,{'preferences':{'ink':'#263d57'}},generated)
                self.assertGreater(count,2)
                layout=json.loads((folder/'layout.json').read_text())
                self.assertTrue(any(p.get('repeated_table_header') for p in layout['placements']))
                for p in layout['placements']:
                    self.assertGreaterEqual(p['y'],80);self.assertLessEqual(p['y']+p['height'],1642)
                outputs.append(hashlib.sha256((folder/'result.pdf').read_bytes()).hexdigest())
            self.assertEqual(outputs[0],outputs[1])

    def test_api_import_preserves_raw_markdown_and_queues_assignment(self):
        from web import app as w
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);pid='a'*32;folder=root/'profiles'/pid
            bank_fixture(folder/'bank')
            w.write(folder/'profile.json',{'id':pid,'name':'Synthetic','created_at':'2026-01-01','status':'ready','sample_sha256':'synthetic','sample':{'lines':[]},'selected_lines':[],'reference_bank':'bank/bank.json','preferences':{}})
            with patch.object(w,'DATA',root),patch.object(w.POOL,'submit'),TestClient(w.app) as client:
                headers={'X-Inkself-Token':client.get('/api/session').json()['token']}
                source='## 2\n**(a)** A_A = 15.\n\n| A | Max |\n|---|---|\n| C | 15 |'
                response=client.post('/api/documents/markdown',headers=headers,data={'layout_mode':'assignment'},files={'file':('answer.md',source.encode(),'text/markdown')})
                self.assertEqual(response.status_code,201,response.text);document=response.json()
                self.assertEqual(document['text'],source)
                response=client.post('/api/jobs',headers=headers,json={'profile_id':pid,'text':source,'document_id':document['id'],'render_mode':'reference','layout_mode':'assignment','answer_header':'Name: Test'})
                self.assertEqual(response.status_code,202,response.text)
                job=response.json();request=w.read(root/'jobs'/job['id']/'request.json')
                self.assertEqual(request['layout_mode'],'assignment')
                self.assertEqual(request['answer_header'],'Name: Test')
                self.assertIn('assignment_options_sha256',request['expected_input_hashes'])


if __name__=='__main__':unittest.main()

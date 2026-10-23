"""Queued jobs must retain their input identity; fixtures contain no personal data."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image,ImageDraw
from web import app as web
from web.runtime.habit_model import VERSION
from web.runtime.vatr_worker import request_input_hashes,run


class JobProvenance(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.profile_id='d'*32;self.folder=self.root/'profiles'/self.profile_id
        self.bank_dir=self.folder/'reference-bank';self.bank_dir.mkdir(parents=True)
        glyph=Image.new('L',(9,18),255);ImageDraw.Draw(glyph).line((3,3,4,14),fill=0,width=2)
        glyph_path=self.bank_dir/'one.png';glyph.save(glyph_path)
        bank={'schema_version':1,'reviewed':True,'source_sha256':'synthetic',
              'glyphs':{'1':{'file':'one.png','sha256':hashlib.sha256(glyph_path.read_bytes()).hexdigest(),
                             'baseline':15,'advance':11}},'words':{}}
        self.bank_path=self.bank_dir/'bank.json';web.write(self.bank_path,bank)
        # Minimal synthetic adapter is sufficient to exercise input binding; no quality claim.
        habit={'schema_version':VERSION,'source_sha256':'synthetic',
               'bank_sha256':hashlib.sha256(self.bank_path.read_bytes()).hexdigest(),
               'source_word_hashes':[],'baseline_slopes':[],'pairs':{},'family_pairs':{},
               'width_coefficients':[.7,0,0,0,0,0,0],'height_coefficients':[.8,0,0,0,0,0,0],
               'width_residual_std':0,'connector_bow_px':0,'bridge_height_by_pair':{},
               'allographs':{},'training_words':[],'observations':0,'limits':'Synthetic fixture.'}
        self.habit_path=self.folder/'habit.json';web.write(self.habit_path,habit)
        web.write(self.folder/'profile.json',{'id':self.profile_id,'name':'Synthetic','status':'ready',
                  'sample_sha256':'synthetic','sample':{'lines':[]},'selected_lines':[],
                  'reference_bank':'reference-bank/bank.json','habit_model':'habit.json','preferences':{}})

    def tearDown(self):self.tmp.cleanup()

    def queue(self,mode):
        with patch.object(web,'DATA',self.root),patch.object(web.POOL,'submit'),TestClient(web.app) as client:
            token=client.get('/api/session').json()['token']
            response=client.post('/api/jobs',headers={'X-Inkself-Token':token},
                                 json={'profile_id':self.profile_id,'text':'11 1','render_mode':mode})
            self.assertEqual(response.status_code,202,response.text)
        return self.root/'jobs'/response.json()['id']/'request.json'

    def test_queued_reference_bank_mutation_rejected_before_any_output(self):
        request_path=self.queue('reference');request=web.read(request_path)
        self.assertEqual(request['expected_input_hashes']['reference_bank_sha256'],
                         hashlib.sha256(self.bank_path.read_bytes()).hexdigest())
        bank=web.read(self.bank_path);bank['spacing_px']=4;web.write(self.bank_path,bank)
        with self.assertRaisesRegex(ValueError,'changed after.*queued'):run(request_path)
        self.assertEqual(list(request_path.parent.glob('word-*.png')),[])
        self.assertFalse((request_path.parent/'generated.json').exists())

    def test_queued_habit_refit_rejected_before_any_output(self):
        request_path=self.queue('learned-habits');request=web.read(request_path)
        self.assertEqual(request['expected_input_hashes']['habit_model_sha256'],
                         hashlib.sha256(self.habit_path.read_bytes()).hexdigest())
        habit=web.read(self.habit_path);habit['width_residual_std']=.01;web.write(self.habit_path,habit)
        with self.assertRaisesRegex(ValueError,'changed after.*queued'):run(request_path)
        self.assertEqual(list(request_path.parent.glob('word-*.png')),[])

    def test_asset_mutation_without_manifest_change_is_rejected(self):
        request_path=self.queue('reference')
        Image.new('L',(9,18),0).save(self.bank_dir/'one.png')
        with self.assertRaisesRegex(ValueError,'image hash mismatch'):run(request_path)
        self.assertEqual(list(request_path.parent.glob('word-*.png')),[])

    def test_legacy_cli_records_inputs_and_repeated_run_has_same_fingerprint(self):
        records=[];pixels=[]
        for suffix in ('first','second'):
            output=self.root/suffix;output.mkdir()
            request={'model':'unused-for-reference','output':str(output),'render_mode':'reference',
                     'reference_bank':str(self.bank_path),'text':'11 1','seed':42}
            path=output/'request.json';web.write(path,request);run(path)
            record=web.read(output/'generated.json')['model'];records.append(record)
            pixels.append((output/'word-0000.png').read_bytes())
            self.assertEqual(record['input_hashes'],request_input_hashes(request))
            self.assertFalse(record['queued_inputs_verified'])
            self.assertTrue(record['renderer_version']);self.assertEqual(len(record['renderer_sha256']),64)
        self.assertEqual(records[0]['input_fingerprint_sha256'],records[1]['input_fingerprint_sha256'])
        self.assertEqual(pixels[0],pixels[1])

    def test_unchanged_queued_inputs_are_verified_and_recorded(self):
        request_path=self.queue('learned-habits');request=web.read(request_path);run(request_path)
        model=web.read(request_path.parent/'generated.json')['model']
        self.assertTrue(model['queued_inputs_verified'])
        self.assertEqual(model['input_hashes'],request['expected_input_hashes'])
        self.assertEqual(model['habit_model_sha256'],request['expected_input_hashes']['habit_model_sha256'])


if __name__=='__main__':unittest.main()

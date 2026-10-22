"""Synthetic tests; no personal handwriting or claimed similarity scores."""
import hashlib,json,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from web.runtime.reference_renderer import load_bank,reference_token
from web.runtime.habit_model import align_words,fit_habits,habit_token,load_habits,pair_evidence

def fixture(root):
 bank={'schema_version':1,'reviewed':True,'source_sha256':'synthetic','glyphs':{},'words':{}}
 for i,c in enumerate('ane12+%'):
  im=Image.new('L',(12,20),255);d=ImageDraw.Draw(im);d.line((2,17,5+i%3,3,9,17),fill=0,width=2)
  path=root/f'g{i}.png';im.save(path);bank['glyphs'][c]={'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'baseline':18,'advance':14}
 for i,text in enumerate(['anne','nana','naan','nean','aane','enna','naen','anan']):
  im=Image.new('L',(len(text)*10,20),255)
  for j,c in enumerate(text):
   glyph=Image.open(root/bank['glyphs'][c]['file']).resize((9,18));im.paste(glyph,(j*10,1))
  path=root/f'w{i}.png';im.save(path);bank['words'][text]={'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'baseline':18}
 path=root/'bank.json';path.write_text(json.dumps(bank));return load_bank(path)

class HabitAdapter(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.bank=fixture(self.root)
  self.model=fit_habits(self.bank,align_words(self.bank),excluded={'naen'})
 def tearDown(self):self.tmp.cleanup()
 def test_fit_excludes_heldout_and_generalizes_without_word_lookup(self):
  self.assertNotIn('naen',self.model['training_words']);self.assertGreaterEqual(self.model['observations'],20)
  im,meta=habit_token(self.bank,self.model,'naen')
  self.assertEqual(meta['renderer'],'sample-fitted-habits');self.assertEqual(len(meta['references']),4)
  self.assertTrue(np.any(np.asarray(im)<170))
 def test_digit_operator_pixels_unchanged(self):
  a,_=reference_token(self.bank,'12+1%',False);b,_=habit_token(self.bank,self.model,'12+1%')
  self.assertEqual(a.tobytes(),b.tobytes());self.assertEqual(a.size,b.size)
 def test_seed_and_occurrence_reproducible_and_margins_not_clipped(self):
  a,meta=habit_token(self.bank,self.model,'anne',seed=7,variant=4);b,_=habit_token(self.bank,self.model,'anne',seed=7,variant=4)
  self.assertEqual(a.tobytes(),b.tobytes());self.assertEqual(meta['em_height'],32)
  pixels=np.asarray(a);self.assertTrue(np.all(pixels[[0,-1],:]==255));self.assertTrue(np.all(pixels[:,[0,-1]]==255))
 def test_family_rules_need_evidence_and_observed_lifts_override(self):
  model={'pairs':{},'family_pairs':{'arch:bowl':[1,1]}}
  self.assertEqual(pair_evidence(model,'na'),[0,0]);model['family_pairs']['arch:bowl']=[3,4]
  self.assertEqual(pair_evidence(model,'na'),[3,4]);model['pairs']['na']=[0,2]
  self.assertEqual(pair_evidence(model,'na'),[0,2])
 def test_invalid_model_and_wrong_source_rejected(self):
  path=self.root/'habit.json';self.model['source_sha256']='other';path.write_text(json.dumps(self.model))
  with self.assertRaises(ValueError):load_habits(path,self.bank)
  self.model['source_sha256']='synthetic';self.model['bank_sha256']='stale';path.write_text(json.dumps(self.model))
  with self.assertRaises(ValueError):load_habits(path,self.bank)
  del self.model['bank_sha256'];self.model['width_coefficients'][0]=float('nan');path.write_text(json.dumps(self.model))
  with self.assertRaises(ValueError):load_habits(path,self.bank)
 def test_api_habit_mode_requires_model_and_can_run_without_vatr_weights(self):
  from fastapi.testclient import TestClient
  from unittest.mock import patch
  from web import app as w
  pid='c'*32;folder=self.root/'profiles'/pid;folder.mkdir(parents=True)
  import shutil
  shutil.copytree(self.bank['_root'],folder/'reference-bank',ignore=shutil.ignore_patterns('profiles'))
  model_path=folder/'habit.json';model_path.write_text(json.dumps(self.model))
  profile={'id':pid,'name':'Synthetic','status':'ready','sample_sha256':'synthetic',
           'sample':{'lines':[]},'selected_lines':[],'preferences':{},'reference_bank':'reference-bank/bank.json'}
  w.write(folder/'profile.json',profile)
  with patch.object(w,'DATA',self.root),patch.object(w,'model_status',return_value={'ready':False}),patch.object(w.POOL,'submit'),TestClient(w.app) as client:
   headers={'X-Inkself-Token':client.get('/api/session').json()['token']}
   body={'profile_id':pid,'text':'naen 12+1%','render_mode':'learned-habits'}
   self.assertEqual(client.post('/api/jobs',headers=headers,json=body).status_code,409)
   profile['habit_model']='habit.json';w.write(folder/'profile.json',profile)
   response=client.post('/api/jobs',headers=headers,json=body);self.assertEqual(response.status_code,202,response.text)
   request=w.read(self.root/'jobs'/response.json()['id']/'request.json')
   self.assertEqual(request['render_mode'],'learned-habits');self.assertEqual(request['habit_model'],str(model_path.resolve()))
   profile['habit_model']='../../escape.json';w.write(folder/'profile.json',profile)
   self.assertEqual(client.post('/api/jobs',headers=headers,json=body).status_code,409)
 def test_missing_characters_fail_without_silent_substitution(self):
  with self.assertRaises(ValueError):habit_token(self.bank,self.model,'unseen!')
if __name__=='__main__':unittest.main()

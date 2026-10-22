import hashlib,json,tempfile,unittest
from pathlib import Path
from PIL import Image,ImageDraw
from web.runtime.reference_renderer import load_bank,reference_token,calibrate_model_image
class ReferenceRenderer(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  im=Image.new('L',(16,26),255);ImageDraw.Draw(im).line((3,3,9,22),fill=0,width=2);im.save(self.root/'glyph.png')
  self.record={'file':'glyph.png','sha256':hashlib.sha256((self.root/'glyph.png').read_bytes()).hexdigest(),'baseline':22,'advance':18}
  self.bank={'schema_version':1,'reviewed':True,'glyphs':{c:dict(self.record) for c in 'a1+%'},'words':{}}
  self.save()
 def tearDown(self):self.tmp.cleanup()
 def save(self):
  (self.root/'bank.json').write_text(json.dumps(self.bank));return self.root/'bank.json'
 def test_review_and_hash_required(self):
  self.bank['reviewed']=False
  with self.assertRaises(ValueError):load_bank(self.save())
  self.bank['reviewed']=True;self.bank['glyphs']['a']['sha256']='bad'
  with self.assertRaises(ValueError):load_bank(self.save())
 def test_escape_and_missing_rejected(self):
  self.bank['glyphs']['a']['file']='../escape.png'
  with self.assertRaises(ValueError):load_bank(self.save())
  self.bank['glyphs']['a']['file']='glyph.png';bank=load_bank(self.save())
  with self.assertRaises(ValueError):reference_token(bank,'unknown')
 def test_source_provenance_and_no_clipping(self):
  bank=load_bank(self.save());im,meta=reference_token(bank,'1+1%')
  self.assertEqual(len(meta['references']),4);self.assertEqual(meta['em_height'],32)
  self.assertGreater(im.height,26);self.assertGreater(meta['baseline'],22)
  self.assertIsNone(im.crop((0,0,im.width,1)).point(lambda x:255-x).getbbox())
 def test_exact_word_retains_captured_join(self):
  self.bank['words']['aa']=dict(self.record);bank=load_bank(self.save())
  im,meta=reference_token(bank,'aa');self.assertEqual(meta['renderer'],'captured-word');self.assertEqual(im.size,(16,26))
 def test_bad_calibration_rejected(self):
  with self.assertRaises(ValueError):calibrate_model_image(Image.new('L',(20,32),255),{'model_width_scale':0})
if __name__=='__main__':unittest.main()

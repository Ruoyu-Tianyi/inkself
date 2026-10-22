"""Small-sample statistical layout adapter, not a neural handwriting clone.

Fits shared character geometry and conservative pen-lift/connector statistics from
transcribed word images. Never uses the requested output text during fitting.
"""
import hashlib,json,math,re
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageChops
from .reference_renderer import _image,reference_token,missing_characters

VERSION=1
HOLDOUTS=frozenset()

def family(char):
 if char in 'mnuwh':return 'arch'
 if char in 'aceosz':return 'bowl'
 if char in 'gjpqy':return 'descender'
 if char in 'bdfklt':return 'tall'
 return 'other'

def pair_evidence(model,pair):
 if pair in model['pairs']:return model['pairs'][pair]
 counts=model.get('family_pairs',{}).get(family(pair[0])+':'+family(pair[1]),[0,0]) if len(pair)==2 else [0,0]
 return counts if counts[1]>=3 else [0,0]

def features(char):
 return np.array([1.,char.isupper(),char in 'iljtfr',char in 'mwMW',char in 'bdfhkltABCDEFGHIJKLMNOPQRSTUVWXYZ',char in 'gjpqy',char in 'aceosuvxz'],float)

def _ridge(x,y,prior):
 x=np.asarray(x);y=np.asarray(y);strength=4.
 return np.linalg.solve(x.T@x+strength*np.eye(x.shape[1]),x.T@y+strength*np.asarray(prior)).tolist()


def align_words(bank):
 import cv2
 def normalized(a):
  yy,xx=np.where(a<180)
  if not len(xx):return np.full((32,24),255,np.uint8)
  a=a[yy.min():yy.max()+1,xx.min():xx.max()+1]
  return cv2.copyMakeBorder(cv2.resize(a,(20,28)),2,2,2,2,cv2.BORDER_CONSTANT,value=255)
 def distance(a,b):
  a=normalized(a)<180;b=normalized(b)<180
  da=cv2.distanceTransform((~a).astype('uint8'),cv2.DIST_L2,3);db=cv2.distanceTransform((~b).astype('uint8'),cv2.DIST_L2,3)
  if not a.any() or not b.any():return 100.
  return float(da[b].mean()+db[a].mean())/2
 records=[]
 for word,rec in bank['words'].items():
  if not word.isalpha() or len(word)<2 or any(c not in bank['glyphs'] for c in word):continue
  a=np.asarray(_image(bank,rec));width=a.shape[1]
  widths=np.array([_image(bank,bank['glyphs'][c]).width+1 for c in word],float)
  widths=widths/widths.sum()*width;centers=np.r_[0,np.cumsum(widths)];dp={0:(0,[])}
  for i,char in enumerate(word):
   proto=np.asarray(_image(bank,bank['glyphs'][char]));nxt={}
   candidates=[width] if i==len(word)-1 else range(max(i+1,round(centers[i+1])-5),min(width-(len(word)-i-1),round(centers[i+1])+5)+1)
   for end in candidates:
    for start,(value,bounds) in dp.items():
     if end-start<2 or not np.any(a[:,start:end]<180):continue
     cost=distance(a[:,start:end],proto)+.35*((end-start-widths[i])/max(3,widths[i]))**2
     if end<width:cost+=.08*max(0,int((a[:,end-1:end+1]<180).sum())-4)
     cost+=value
     if end not in nxt or cost<nxt[end][0]:nxt[end]=(cost,bounds+[end])
   dp=nxt
  if width in dp:
   value,bounds=dp[width];records.append({'text':word,'bounds':[0]+bounds,'cost':value/len(word)})
 return records

def fit_habits(bank,alignments,excluded=HOLDOUTS):
 """Alignment boundaries are estimates; reject uncertain dense-stem cuts."""
 import cv2
 widths=[];heights=[];vectors=[];pairs={};bows=[];records=[];source_hashes=[];word_x=[];word_y=[];bridge_y={};allograph_samples={};baseline_slopes=[]
 for r in alignments:
  word=r['text']
  if word in excluded or r['cost']>1.15 or not word.isalpha():continue
  rec=bank['words'][word];a=np.asarray(_image(bank,rec));ink=a<170;bounds=r['bounds']
  records.append(word);source_hashes.append(rec['sha256'])
  points=[]
  for j,c in enumerate(word):
   part=ink[:,bounds[j]:bounds[j+1]];py,_=np.where(part)
   if len(py) and c.islower() and c not in 'gjpqyf':points.append(((bounds[j]+bounds[j+1])/2,float(py.max())))
  if len(points)>=3:
   xs,ys=np.asarray(points).T;sl=float(np.polyfit(xs,ys,1)[0]);baseline_slopes.append(float(np.clip(sl,-.06,.06)))
  word_x.append(sum(_image(bank,bank['glyphs'][c]).width*features(c) for c in word)/len(word))
  word_y.append((a.shape[1]-.5*(len(word)-1))/len(word))
  for i,char in enumerate(word):
   seg=ink[:,bounds[i]:bounds[i+1]];yy,xx=np.where(seg)
   if len(xx)<3:continue
   proto=_image(bank,bank['glyphs'][char]);wr=(xx.max()-xx.min()+1)/proto.width;hr=(yy.max()-yy.min()+1)/proto.height
   if .3<wr<1.6 and .35<hr<1.4:
    vectors.append(features(char));widths.append(wr);heights.append(hr)
    crop=a[:,bounds[i]:bounds[i+1]][yy.min():yy.max()+1,xx.min():xx.max()+1]
    normalized=cv2.resize(crop,(proto.width*3,proto.height*3),interpolation=cv2.INTER_CUBIC)
    allograph_samples.setdefault(char,[]).append(normalized)
  for i,x in enumerate(bounds[1:-1]):
   # Locate the local ink valley instead of treating an approximate split as exact.
   candidates=range(max(1,x-2),min(a.shape[1]-1,x+3))
   x=min(candidates,key=lambda col:int(ink[:,col].sum()))
   # A thin bridge across a plausible split is evidence; dense cuts are uncertain.
   column=np.where(ink[:,x])[0];left=np.where(ink[:,max(0,x-2)])[0];right=np.where(ink[:,min(a.shape[1]-1,x+2)])[0]
   if len(column)>7:continue
   joined=bool(len(column)>0 and len(left)>0 and len(right)>0)
   key=word[i:i+2];counts=pairs.setdefault(key,[0,0]);counts[0]+=int(joined);counts[1]+=1
   if joined:
    bridge_y.setdefault(key,[]).append(float(np.mean(column)-rec['baseline']))
    ys=[]
    for xx in range(max(0,x-2),min(a.shape[1],x+3)):
     values=np.where(ink[:,xx])[0]
     if len(values):
      center=float(np.median(column));near=values[np.abs(values-center)<=5]
      if len(near):ys.append(float(np.mean(near)))
    if len(ys)==5:bows.append(float(ys[2]-(ys[0]+ys[-1])/2))
 if len(vectors)<20:raise ValueError('Too few reliable word alignments for a habit adapter.')
 wc=_ridge(word_x,word_y,[.7,0,0,0,0,0,0]);hc=_ridge(vectors,heights,[.8,0,0,0,0,0,0])
 residual=(np.asarray(word_y)-np.asarray(word_x)@wc)/10
 family_pairs={}
 for pair,(yes,total) in pairs.items():
  key=family(pair[0])+':'+family(pair[1]);counts=family_pairs.setdefault(key,[0,0]);counts[0]+=yes;counts[1]+=total
 allographs={}
 for char,samples in allograph_samples.items():
  if len(samples)<5:continue
  raster=np.clip(np.median(samples,axis=0),0,255).astype('uint8')
  allographs[char]={'width':raster.shape[1],'height':raster.shape[0],'values':raster.flatten().tolist(),'observations':len(samples)}
 return {'family_pairs':family_pairs,'allographs':allographs,'schema_version':VERSION,'method':'sample-fitted shared character geometry and observed pen-lift statistics',
  'source_sha256':bank['source_sha256'],'baseline_slopes':baseline_slopes,'training_words':records,'excluded_words':sorted(excluded),
  'source_word_hashes':source_hashes,'observations':len(vectors),'width_coefficients':wc,'height_coefficients':hc,
  'width_residual_std':float(np.clip(np.std(residual),0,.1)),'pairs':pairs,
  'connector_bow_px':float(np.clip(np.median(bows) if bows else 0,-1.5,1.5)),
  'connector_examples':len(bows),'bridge_height_by_pair':{k:float(np.clip(np.median(v),-16,1)) for k,v in bridge_y.items()},'limits':'Raster glyph scaffold retained; stroke order and unseen motor trajectories are not learned.'}

def load_habits(path,bank):
 model=json.loads(Path(path).read_text(encoding='utf-8'))
 if model.get('schema_version')!=VERSION or model.get('source_sha256')!=bank['source_sha256']:raise ValueError('Habit model source mismatch.')
 if model.get('bank_sha256') and model['bank_sha256']!=bank.get('_manifest_sha256'):raise ValueError('Habit model bank has changed; fit again.')
 if not set(model.get('source_word_hashes',[])).issubset({r['sha256'] for r in bank.get('words',{}).values()}):raise ValueError('Habit training references do not match bank.')
 if not 0<=model.get('width_residual_std',0)<=.1 or not np.isfinite(model.get('width_residual_std',0)):raise ValueError('Invalid habit variation.')
 for value in model.get('baseline_slopes',[]):
  if not np.isfinite(value) or abs(value)>.06:raise ValueError('Invalid baseline statistics.')
 for counts in list(model.get('pairs',{}).values())+list(model.get('family_pairs',{}).values()):
  if len(counts)!=2 or not 0<=counts[0]<=counts[1] or counts[1]>10000:raise ValueError('Invalid connection statistics.')
 for key in ('width_coefficients','height_coefficients'):
  if len(model.get(key,[]))!=7 or not np.isfinite(model[key]).all() or max(abs(float(x)) for x in model[key])>3:raise ValueError('Invalid habit geometry.')
 if not np.isfinite(model.get('connector_bow_px',0)) or abs(model.get('connector_bow_px',0))>2:raise ValueError('Invalid connector shape.')
 for pair,value in model.get('bridge_height_by_pair',{}).items():
  if len(pair)!=2 or not np.isfinite(value) or not -16<=value<=1:raise ValueError('Invalid connector height.')
 for char,raster in model.get('allographs',{}).items():
  if char not in bank['glyphs'] or not 1<=raster['width']<=256 or not 1<=raster['height']<=256:raise ValueError('Invalid learned glyph.')
  values=np.asarray(raster['values'])
  if values.size!=raster['width']*raster['height'] or not np.isfinite(values).all() or np.any(values<0) or np.any(values>255):raise ValueError('Invalid learned glyph pixels.')
 return model

def _endpoint(image,baseline,side,target_offset=-5):
 a=np.asarray(image);yy,xx=np.where(a<170)
 keep=(yy>=baseline-9)&(yy<=baseline+1)
 if not np.any(keep):return None
 xx=xx[keep];yy=yy[keep];edge=xx.max() if side=='right' else xx.min();m=xx==edge
 values=yy[m];target=baseline+target_offset
 return float(edge),float(values[np.argmin(np.abs(values-target))])

def habit_token(bank,model,text,seed=42,variant=0,connect=True,allographs=True):
 if missing_characters(bank,text):raise ValueError('Missing reviewed glyphs.')
 # Numeric and punctuation-only tokens remain exact reviewed compositions.
 if not any(c.isalpha() for c in text):return reference_token(bank,text,prefer_words=False)
 # Stable per occurrence: a fitted residual distribution, not fresh page-wide noise.
 digest=hashlib.sha256(f'{seed}:{variant}:{text}'.encode()).digest();rng=np.random.default_rng(int.from_bytes(digest[:8],'little'))
 pieces=[];provenance=[]
 for char in text:
  rec=bank['glyphs'][char];im=_image(bank,rec);wx=hy=1.
  if allographs and char in model.get('allographs',{}):
   raster=model['allographs'][char];im=Image.fromarray(np.asarray(raster['values'],dtype='uint8').reshape(raster['height'],raster['width'])).resize(im.size,Image.Resampling.LANCZOS)
  if char.isalpha():
   wx=float(np.clip(features(char)@model['width_coefficients'],.4,1.1));hy=float(np.clip(features(char)@model['height_coefficients'],.55,1.15))
   # Residual is bounded and small; numerals and punctuation never deformed.
   wx*=float(np.clip(1+rng.normal(0,model['width_residual_std']*.18),.97,1.03))
  im=im.resize((max(2,round(im.width*wx)),max(2,round(im.height*hy))),Image.Resampling.LANCZOS)
  base=float(rec['baseline'])*hy;pieces.append((char,im,base));provenance.append(rec['sha256'])
 baseline=math.ceil(max(p[2] for p in pieces))+4;height=baseline+math.ceil(max(im.height-base for _,im,base in pieces))+4
 positions=[];x=4.
 slope=.35*float(rng.choice(model.get('baseline_slopes') or [0]))
 for i,(char,im,base) in enumerate(pieces):
  positions.append((round(x),round(baseline-base)))
  # Learn whether to bring letter bodies close enough for an observed join.
  pair=text[i:i+2];counts=pair_evidence(model,pair);prob=(counts[0]+.3)/(counts[1]+1.)
  gap=0 if counts[1] and prob>=.5 else 1
  if not char.isalpha() or (i+1<len(text) and not text[i+1].isalpha()):gap=3
  x+=im.width+gap
 positions=[(px,py+round(float(np.clip(slope*(px-x/2),-.8,.8)))) for px,py in positions]
 result=Image.new('L',(math.ceil(x)+4,height),255)
 # Darken composition: overlapping white margins cannot erase existing strokes.
 for (_,im,_),(x,y) in zip(pieces,positions):
  layer=Image.new('L',result.size,255);layer.paste(im,(x,y));result=ImageChops.darker(result,layer)
 joined=[];draw=ImageDraw.Draw(result)
 if connect:
  for i in range(len(pieces)-1):
   pair=text[i:i+2];yes,total=pair_evidence(model,pair)
   if not pair.isalpha() or total<1 or (yes+.3)/(total+1.)<.5:continue
   _,left,lb=pieces[i];_,right,rb=pieces[i+1];offset=float(model.get('bridge_height_by_pair',{}).get(pair,-5));a=_endpoint(left,lb,'right',offset);b=_endpoint(right,rb,'left',offset)
   if a is None or b is None:continue
   x0,y0=positions[i][0]+a[0],positions[i][1]+a[1];x1,y1=positions[i+1][0]+b[0],positions[i+1][1]+b[1]
   # Reject implausible bridges; pen lifts are preferable to damaged letters.
   if not 0<x1-x0<=7 or abs(y1-y0)>7:continue
   bow=model['connector_bow_px'];points=[]
   for t in np.linspace(0,1,20):points.append((x0+t*(x1-x0),y0+t*(y1-y0)+4*bow*t*(1-t)))
   draw.line(points,fill=45,width=1);joined.append(pair)
 return result,{'baseline':baseline,'em_height':32,'renderer':'sample-fitted-habits','references':provenance,
  'sampled_baseline_slope':slope,'learned_allographs':[c for c in text if allographs and c in model.get('allographs',{})],'connections_from_generalized_rules':[pair for pair in joined if pair not in model['pairs']],'learned_connections':joined,'habit_observations':model['observations'],
  'limits':model['limits']}

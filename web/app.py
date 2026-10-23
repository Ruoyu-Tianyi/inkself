"""Local single-owner handwriting web application; binds to loopback only."""
from __future__ import annotations
import concurrent.futures
from contextlib import asynccontextmanager
import hashlib,io,json,os,re,secrets,shutil,subprocess,sys,threading,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI,File,Form,HTTPException,Request,UploadFile
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from .samples import process_sample

ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.environ.get('INKSELF_DATA',ROOT/'.local/web-data')).resolve()
MODEL=ROOT/'.local/vendor/vatrpp'
MODEL_PYTHON=Path(os.environ.get('INKSELF_MODEL_PYTHON',ROOT/'.local/model-env/Scripts/python.exe' if os.name=='nt' else ROOT/'.local/model-env/bin/python'))
PROMPT_LINES=[
    'The quick brown fox jumps over the lazy dog.',
    'Bright mornings bring fresh ideas, quiet thoughts and new beginnings.',
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz',
    'Today I wrote 0123456789, then 27 + 58 = 85 and 120 - 45 = 75.',
    'We paid 24.50 for 3 books; the discount was 15%. Is that right?']
ALPHABET=set(' !"#%&\'()*+,-./0123456789:;?ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
POOL=concurrent.futures.ThreadPoolExecutor(max_workers=1)
LOCK=threading.RLock()
TOKEN=secrets.token_urlsafe(32)


def now(): return datetime.now(timezone.utc).isoformat()
def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def identifier(value):
    if not re.fullmatch('[a-f0-9]{32}',value): raise HTTPException(404,'记录不存在。')
    return value
def profile_path(pid):
    path=DATA/'profiles'/identifier(pid)
    if not (path/'profile.json').is_file(): raise HTTPException(404,'字迹档案不存在。')
    return path
def job_path(jid):
    path=DATA/'jobs'/identifier(jid)
    if not (path/'job.json').is_file(): raise HTTPException(404,'生成任务不存在。')
    return path
def model_status():
    required=['model.safetensors','config.json','models/model.py','files/unifont.pickle']
    missing=[name for name in required if not (MODEL/name).is_file()]
    if not MODEL_PYTHON.is_file(): missing.append('model-python')
    ready=not missing and (MODEL/'model.safetensors').stat().st_size>100_000_000
    probe=ROOT/'.local/model-probe.json'
    tested=read(probe) if probe.exists() else None
    return {'name':'VATr++','ready':ready,'device':'cpu','missing':missing,
            'inference_verified':bool(tested and tested.get('status')=='passed'),
            'description':'少样本生成实验版；本人相似度与文字准确性需要人工核对。'}

@asynccontextmanager
async def lifespan(app):
    DATA.mkdir(parents=True,exist_ok=True)
    for path in (DATA/'jobs').glob('*/job.json'):
        data=read(path)
        if data['status'] in ('queued','running'):
            data.update(status='interrupted',message='服务重启中断了任务，请重新生成。');write(path,data)
    yield

app=FastAPI(title='Inkself · 个人字迹实验室',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver','[::1]'])

@app.middleware('http')
async def local_session(request:Request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and origin!=str(request.base_url).rstrip('/'):
            return JSONResponse({'detail':'仅允许本地页面提交。'},status_code=403)
        if not secrets.compare_digest(request.headers.get('x-inkself-token',''),TOKEN):
            return JSONResponse({'detail':'页面会话已更新，请刷新后重试。'},status_code=403)
        length=request.headers.get('content-length')
        if length and (not length.isdigit() or int(length)>22*1024*1024):
            return JSONResponse({'detail':'单次上传不能超过 20 MB。'},status_code=413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; frame-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'self'"
    return response

@app.get('/api/session')
def session(): return {'token':TOKEN,'mode':'local-single-owner','version':'0.2.0-web-preview'}
@app.get('/api/health')
def health(): return {'status':'ok','model':model_status(),'privacy':'样本、风格和文档保存在当前电脑。此版本仅支持本机单用户，不应直接暴露到公网。'}
@app.get('/api/prompt')
def prompt(): return {'id':'english-numbers-v1','lines':PROMPT_LINES,'instructions':'自然书写，不必刻意工整。深色笔、浅色纸，每句话一行，保持行间距；拍摄整段，避免阴影和反光。'}
@app.get('/api/prompt.pdf')
def prompt_pdf():
    path=DATA/'sampling-guide.pdf'
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        c=canvas.Canvas(str(path),pagesize=(595.2756,841.8898));c.setTitle('Inkself sampling guide')
        c.setFont('Helvetica-Bold',20);c.drawString(44,785,'Your handwriting, naturally.')
        c.setFont('Helvetica',10)
        c.drawString(44,760,'Copy each sentence below in your normal handwriting. Use dark ink on plain paper.')
        c.drawString(44,744,'Leave a clear gap between lines. Photograph your writing only, without these instructions.')
        y=698
        for line in PROMPT_LINES:
            c.setFont('Helvetica',10);c.drawString(44,y,line);c.setStrokeColorRGB(.82,.82,.8);c.line(44,y-67,551,y-67);y-=113
        c.save()
    return FileResponse(path,filename='inkself-sampling-guide.pdf')
@app.get('/api/profiles')
def profiles():
    return sorted([read(p) for p in (DATA/'profiles').glob('*/profile.json')],key=lambda p:p['created_at'],reverse=True)
@app.post('/api/profiles',status_code=201)
async def create_profile(name:str=Form(...),file:UploadFile=File(...)):
    name=name.strip()
    if not 1<=len(name)<=60: raise HTTPException(422,'请输入 1–60 字的档案名称。')
    content=await file.read(20*1024*1024+1)
    if len(content)>20*1024*1024: raise HTTPException(413,'图片不能超过 20 MB。')
    if file.content_type not in ('image/png','image/jpeg','image/webp'): raise HTTPException(415,'请上传 PNG、JPG 或 WebP 图片。')
    pid=uuid.uuid4().hex;folder=DATA/'profiles'/pid;folder.mkdir(parents=True)
    try:
        source=folder/'upload.bin';source.write_bytes(content)
        analysis=await __import__('asyncio').to_thread(process_sample,source,folder/'sample')
        source.unlink()
        data={'id':pid,'name':name,'created_at':now(),'status':'needs-review','sample':analysis,
              'sample_sha256':hashlib.sha256(content).hexdigest(),'selected_lines':[],
              'prompt_id':'english-numbers-v1','preferences':{'size':16,'line_spacing':1.6,'ink':'#263d57'},
              'similarity':'not-evaluated'}
        write(folder/'profile.json',data);return data
    except (ValueError,OSError,Image.DecompressionBombError) as error:
        shutil.rmtree(folder);raise HTTPException(422,str(error))

@app.get('/api/profiles/{pid}/sample/{file}')
def sample_file(pid:str,file:str):
    folder=profile_path(pid)
    if file!='normalized.png' and not re.fullmatch(r'line-\d{3}\.png',file):raise HTTPException(404,'图片不存在。')
    path=folder/'sample'/file
    if not path.is_file(): raise HTTPException(404,'图片不存在。')
    return FileResponse(path)
class Review(BaseModel):
    lines:list[int]=Field(min_length=1,max_length=24)
    inspected:Literal[True]
@app.post('/api/profiles/{pid}/review')
def review(pid:str,body:Review):
    with LOCK:
        folder=profile_path(pid);data=read(folder/'profile.json')
        if len(set(body.lines))!=len(body.lines) or any(i<0 or i>=len(data['sample']['lines']) for i in body.lines):raise HTTPException(422,'选择的文字行无效。')
        data.update(selected_lines=body.lines,status='ready',reviewed_at=now())
        write(folder/'profile.json',data);return data
@app.delete('/api/profiles/{pid}')
def delete_profile(pid:str):
    with LOCK:
        folder=profile_path(pid)
        owned=[read(p) for p in (DATA/'jobs').glob('*/job.json') if read(p).get('profile_id')==pid]
        if any(j['status'] in ('queued','running') for j in owned):raise HTTPException(409,'请等待该档案的生成任务结束后再删除。')
        for job in owned: shutil.rmtree(job_path(job['id']))
        shutil.rmtree(folder)
    return {'deleted':True}
class Generation(BaseModel):
    profile_id:str
    text:str=Field(min_length=1,max_length=20000)
    size:int=Field(default=16,ge=10,le=26)
    line_spacing:float=Field(default=1.6,ge=1.2,le=2.2)
    ink:str=Field(default='#263d57',pattern=r'^#[0-9a-fA-F]{6}$')
    seed:int=Field(default=42,ge=0,le=2147483647)
    render_mode:Literal['model','model-calibrated','reference','learned-habits']='model'
    math_enabled:bool=False
    allow_supplemental_math:bool=False

@app.post('/api/jobs',status_code=202)
def generate(body:Generation):
    text=body.text.replace('\r\n','\n').replace('\r','\n').replace('\t','    ')
    if not text.strip():raise HTTPException(422,'请输入需要生成的英文或数字。')
    rgb=[int(body.ink[i:i+2],16) for i in (1,3,5)]
    if sum(a*b for a,b in zip(rgb,(.2126,.7152,.0722)))>200:raise HTTPException(422,'墨色太浅，请选择深色以保证字迹可读。')
    bank=None;bank_path=None
    if body.render_mode!='model':
        from .runtime.reference_renderer import load_bank,missing_characters
        folder=profile_path(body.profile_id);profile=read(folder/'profile.json')
        if not profile.get('reference_bank'):raise HTTPException(409,'此档案还没有逐字核对的原稿字形库。')
        bank_path=(folder/profile['reference_bank']).resolve()
        if not bank_path.is_relative_to(folder.resolve()):raise HTTPException(409,'原稿字形库路径无效。')
        try:
            bank=load_bank(bank_path)
            if bank.get('source_sha256')!=profile['sample_sha256']:raise ValueError('原稿来源不匹配。')
        except (ValueError,OSError,KeyError) as error:raise HTTPException(409,str(error))
    habit_path=None
    if body.render_mode=='learned-habits':
        from .runtime.habit_model import load_habits
        if not profile.get('habit_model'):raise HTTPException(409,'此档案还没有拟合并检查过的习惯适配器。')
        habit_path=(folder/profile['habit_model']).resolve()
        if not habit_path.is_relative_to(folder.resolve()):raise HTTPException(409,'习惯适配器路径无效。')
        try:load_habits(habit_path,bank)
        except (ValueError,OSError,KeyError,TypeError) as error:raise HTTPException(409,str(error))
    if body.math_enabled and body.render_mode not in ('reference','learned-habits'):
        raise HTTPException(422,'数学公式需使用样本习惯适配或原稿字形保真。')
    if body.render_mode in ('reference','learned-habits'):
        from .runtime.document_input import prepare_document
        try:prepare_document(text,bank,body.math_enabled,body.allow_supplemental_math)
        except ValueError as error:raise HTTPException(422,str(error)) from error
    else:
        missing=sorted(set(text)-ALPHABET-{'\n'})
        if missing:raise HTTPException(422,'当前生成方式不支持这些字符：'+''.join(missing))
        if any(len(word)>32 for word in text.split()):raise HTTPException(422,'单个连续词不能超过 32 个字符，请增加空格。')
        if len(text)>3000:raise HTTPException(422,'少样本模型单次最多 3,000 字符；长文请使用样本习惯适配。')
    if body.render_mode not in ('reference','learned-habits') and not model_status()['ready']:raise HTTPException(503,'生成模型尚未安装完成，请稍后再试。')
    with LOCK:
        folder=profile_path(body.profile_id);profile=read(folder/'profile.json')
        if profile['status']!='ready':raise HTTPException(409,'请先检查并确认采样图片。')
        active=[p for p in (DATA/'jobs').glob('*/job.json') if read(p)['status'] in ('queued','running')]
        if len(active)>=3:raise HTTPException(429,'已有三个任务等待处理，请稍后提交。')
        jid=uuid.uuid4().hex;dest=DATA/'jobs'/jid
        job={'id':jid,'profile_id':body.profile_id,'profile_name':profile['name'],'created_at':now(),
             'status':'queued','message':'等待生成','text':text,'preferences':body.model_dump(exclude={'profile_id','text'}),
             'content_verification':'needs-human-review','similarity':'not-evaluated'}
        paths=[str(folder/'sample'/profile['sample']['lines'][i]['file']) for i in profile['selected_lines']]
        cache_key=hashlib.sha256((profile['sample_sha256']+repr(profile['selected_lines'])+'vatrpp-fb73be2'+body.render_mode+(hashlib.sha256(bank_path.read_bytes()).hexdigest() if bank_path else '')).encode()).hexdigest()[:20]
        request={'text':text,'styles':paths,'seed':body.seed,'output':str(dest),'model':str(MODEL),
                 'style_cache':str(folder/f'style-{cache_key}.npz'),'render_mode':body.render_mode,
                 'math_enabled':body.math_enabled,'allow_supplemental_math':body.allow_supplemental_math}
        if bank_path:request['reference_bank']=str(bank_path)
        if habit_path:request['habit_model']=str(habit_path)
        from .runtime.vatr_worker import request_input_hashes
        try:request['expected_input_hashes']=request_input_hashes(request)
        except (OSError,ValueError) as error:raise HTTPException(409,'生成输入已变化，请重新提交。') from error
        write(dest/'job.json',job)
        write(dest/'request.json',request)
        profile['preferences']=body.model_dump(exclude={'profile_id','text'})
        write(folder/'profile.json',profile)
        POOL.submit(run_job,jid)
    return job

def run_job(jid):
    folder=job_path(jid);job=read(folder/'job.json')
    try:
        local_layout=job['preferences'].get('render_mode') in ('reference','learned-habits')
        job.update(status='running',message='正在生成字迹、公式并规划分页。' if local_layout else '正在运行本地少样本模型，CPU 生成可能需要几分钟。');write(folder/'job.json',job)
        with (folder/'worker.log').open('w',encoding='utf-8') as log:
            env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',MPLBACKEND='Agg',PYTHONPATH='')
            result=subprocess.run([str(MODEL_PYTHON),str(ROOT/'web/runtime/vatr_worker.py'),str(folder/'request.json')],
                                  cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise RuntimeError('模型运行失败；诊断日志已保留，请检查模型环境。')
        output=read(folder/'generated.json')
        pages=compose_pdf(folder,job,output)
        job.update(status='needs-review',message='生成完成，请逐字核对文字和数字，并评价字迹相似度。',pages=pages,
                   layout_warnings=read(folder/'layout.json')['warnings'],
                   completed_at=now(),model=output['model'],duration_seconds=output['duration_seconds'],
                   pdf_sha256=hashlib.sha256((folder/'result.pdf').read_bytes()).hexdigest())
        if output['model'].get('supplemental_math_glyphs'):
            job['message']='生成完成；公式中的配套手写字形尚未学习你的个人写法，请核对：'+''.join(output['model']['supplemental_math_glyphs'])
    except subprocess.TimeoutExpired:
        job.update(status='failed',message='生成超过 30 分钟，请缩短内容后重试。')
    except Exception as error:
        job.update(status='failed',message=str(error))
    write(folder/'job.json',job)

def compose_pdf(folder,job,generated):
    from .document_layout import compose_document
    return compose_document(folder,job,generated)

@app.get('/api/jobs')
def jobs():return sorted([read(p) for p in (DATA/'jobs').glob('*/job.json')],key=lambda j:j['created_at'],reverse=True)
@app.get('/api/jobs/{jid}')
def job(jid:str):return read(job_path(jid)/'job.json')
@app.get('/api/jobs/{jid}/files/{file}')
def job_file(jid:str,file:str):
    folder=job_path(jid)
    if file not in ('result.pdf','report.json','layout.json') and not re.fullmatch(r'page-\d{3}\.png',file):raise HTTPException(404,'文件不存在。')
    path=folder/file
    if not path.is_file():raise HTTPException(404,'文件尚未生成。')
    return FileResponse(path,filename='inkself-handwriting.pdf' if file=='result.pdf' else None)
class Feedback(BaseModel):
    text_correct:bool
    similarity:int=Field(ge=1,le=5)
    naturalness:int=Field(ge=1,le=5)
    notes:str=Field(default='',max_length=2000)
@app.post('/api/jobs/{jid}/feedback')
def feedback(jid:str,body:Feedback):
    with LOCK:
        folder=job_path(jid);data=read(folder/'job.json')
        if data['status'] not in ('needs-review','reviewed'):raise HTTPException(409,'请等待生成完成后评价。')
        data.update(feedback=body.model_dump(),status='reviewed',reviewed_at=now(),
                    content_verification='human-confirmed' if body.text_correct else 'human-reported-errors')
        write(folder/'job.json',data);return data

app.mount('/',StaticFiles(directory=ROOT/'web/static',html=True),name='static')

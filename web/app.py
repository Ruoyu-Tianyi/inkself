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
from .capture_prompt import PROMPT_ID,LEGACY_PROMPT_ID,PROMPT_LINES,prompt_payload,write_sampling_guide
from .runtime_paths import data_root,model_root,model_python,model_worker,model_probe_path,resource_root,worker_command

ROOT=resource_root()
DATA=data_root()
MODEL=model_root()
MODEL_PYTHON=model_python()
MODEL_WORKER=model_worker()
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
    runtime_ready=bool((MODEL_WORKER and MODEL_WORKER.is_file()) or (MODEL_PYTHON and MODEL_PYTHON.is_file()))
    if not runtime_ready: missing.append('model-runtime')
    from .model_setup import assets_ready
    verified=assets_ready(MODEL)
    if not verified and not missing:missing.append('model-assets-unverified')
    ready=not missing and verified
    probe=model_probe_path()
    tested=read(probe) if probe.exists() else None
    return {'name':'VATr++','ready':ready,'runtime_ready':runtime_ready,'bundled_runtime':bool(MODEL_WORKER and MODEL_WORKER.is_file()),'device':'cpu','missing':missing,
            'inference_verified':bool(tested and tested.get('status')=='passed'),
            'description':'请使用完整安装包准备本地 AI，或导入已核对字迹档案。' if not runtime_ready else '少样本生成实验版；本人相似度与文字准确性需要人工核对。'}

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
def session(): return {'token':TOKEN,'mode':'local-single-owner','version':'0.3.0-desktop-preview','instance_id':os.environ.get('INKSELF_INSTANCE_ID')}
@app.get('/api/health')
def health(): return {'status':'ok','model':model_status(),'privacy':'样本、风格和文档保存在当前电脑。此版本仅支持本机单用户，不应直接暴露到公网。'}
@app.get('/api/prompt')
def prompt(): return prompt_payload()

@app.post('/api/documents/markdown',status_code=201)
async def import_markdown(file:UploadFile=File(...)):
    from .markdown_document import decode_markdown_upload,parse_markdown
    try:
        filename=file.filename or 'document.md'
        parsed=parse_markdown(decode_markdown_upload(await file.read(256*1024+1),filename),filename)
    except ValueError as error:
        raise HTTPException(422,'Markdown 导入失败：'+str(error)) from error
    document_id=uuid.uuid4().hex
    parsed.update(id=document_id,imported_at=now(),source_sha256=hashlib.sha256(parsed['source_text'].encode('utf-8')).hexdigest())
    write(DATA/'documents'/f'{document_id}.json',parsed)
    return parsed

@app.get('/api/setup/model')
def setup_state():
    from .model_setup import state
    return {**state(MODEL),'runtime_ready':model_status()['runtime_ready']}

@app.post('/api/setup/model',status_code=202)
def prepare_ai():
    from .model_setup import start
    if not model_status()['runtime_ready']:
        raise HTTPException(409,'请安装包含本地 AI 的完整安装包，再准备模型。')
    return start(MODEL)

@app.get('/api/onboarding')
def onboarding():
    all_profiles=profiles()
    ready=[p for p in all_profiles if p.get('status')=='ready']
    prepared=[p for p in ready if p.get('habit_model') or p.get('reference_bank')]
    model=model_status()
    reviewed=any(read(path).get('status')=='reviewed' for path in (DATA/'jobs').glob('*/job.json'))
    return {'model':model,'profiles_ready':len(ready),'prepared_profiles':len(prepared),
            'can_generate':bool(prepared or (ready and model['ready'])),
            'steps':[{'id':'model','done':model['ready'],'needed':not bool(prepared)},
                     {'id':'sample','done':bool(ready),'needed':True},
                     {'id':'review','done':reviewed,'needed':True}],
            'message':'准备本地 AI，写一段样本，检查第一份试写。样本与生成内容保存在本机。'}
@app.get('/api/prompt.pdf')
def prompt_pdf():
    path=DATA/f'sampling-guide-{PROMPT_ID}.pdf'
    if not path.exists():
        write_sampling_guide(path)
    return FileResponse(path,filename='inkself-sampling-guide.pdf')
@app.get('/api/profiles')
def profiles():
    return sorted([read(p) for p in (DATA/'profiles').glob('*/profile.json')],key=lambda p:p['created_at'],reverse=True)
@app.post('/api/profiles',status_code=201)
async def create_profile(name:str=Form(...),file:UploadFile=File(...),prompt_id:str=Form(PROMPT_ID)):
    name=name.strip()
    if not 1<=len(name)<=60: raise HTTPException(422,'请输入 1–60 字的档案名称。')
    if prompt_id not in (PROMPT_ID,LEGACY_PROMPT_ID):raise HTTPException(422,'采样内容版本无效，请刷新页面后重试。')
    content=await file.read(20*1024*1024+1)
    if len(content)>20*1024*1024: raise HTTPException(413,'图片不能超过 20 MB。')
    if file.content_type not in ('image/png','image/jpeg','image/webp'): raise HTTPException(415,'请上传 PNG、JPG 或 WebP 图片。')
    pid=uuid.uuid4().hex;folder=DATA/'profiles'/pid;folder.mkdir(parents=True)
    try:
        source=folder/'upload.bin';source.write_bytes(content)
        analysis=await __import__('asyncio').to_thread(process_sample,source,folder/'sample')
        source.unlink()
        data={'id':pid,'name':name,'created_at':now(),'status':'needs-review','sample':analysis,
              'sample_sha256':hashlib.sha256(content).hexdigest(),'selected_lines':[],'math_lines':[],
              'math_capture_status':'not-provided',
              'prompt_id':prompt_id,'preferences':{'size':16,'line_spacing':1.6,'ink':'#263d57'},
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
    math_lines:list[int]=Field(default_factory=list,max_length=24)
    inspected:Literal[True]
@app.post('/api/profiles/{pid}/review')
def review(pid:str,body:Review):
    with LOCK:
        folder=profile_path(pid);data=read(folder/'profile.json')
        all_lines=body.lines+body.math_lines
        if len(set(all_lines))!=len(all_lines) or any(i<0 or i>=len(data['sample']['lines']) for i in all_lines):raise HTTPException(422,'选择的文字行无效，英文与数学行不能重复。')
        data.update(selected_lines=body.lines,math_lines=body.math_lines,
                    math_capture_status='captured-needs-alignment' if body.math_lines else 'not-provided',
                    status='ready',reviewed_at=now())
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
    document_id:str|None=None

@app.post('/api/jobs',status_code=202)
def generate(body:Generation):
    text=body.text.replace('\r\n','\n').replace('\r','\n').replace('\t','    ')
    if not text.strip():raise HTTPException(422,'请输入需要生成的英文或数字。')
    imported_document=None
    if body.document_id:
        document_path=DATA/'documents'/f'{identifier(body.document_id)}.json'
        if not document_path.is_file():raise HTTPException(404,'导入的 Markdown 文档不存在，请重新选择文件。')
        imported_document=read(document_path)
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
             'status':'queued','message':'等待生成','text':text,'preferences':body.model_dump(exclude={'profile_id','text','document_id'}),
             'content_verification':'needs-human-review','similarity':'not-evaluated'}
        paths=[str(folder/'sample'/profile['sample']['lines'][i]['file']) for i in profile['selected_lines']]
        from .runtime.word_spacing import fit_word_spacing
        spacing_model=fit_word_spacing(bank=bank,sample_dir=folder/'sample',
            sample_lines=profile['sample']['lines'],selected_lines=profile['selected_lines'],
            source_sha256=profile['sample_sha256'])
        cache_key=hashlib.sha256((profile['sample_sha256']+repr(profile['selected_lines'])+'vatrpp-fb73be2'+body.render_mode+(hashlib.sha256(bank_path.read_bytes()).hexdigest() if bank_path else '')).encode()).hexdigest()[:20]
        request={'text':text,'styles':paths,'seed':body.seed,'output':str(dest),'model':str(MODEL),
                 'style_cache':str(folder/f'style-{cache_key}.npz'),'render_mode':body.render_mode,
                 'math_enabled':body.math_enabled,'allow_supplemental_math':body.allow_supplemental_math,
                 'word_spacing':spacing_model}
        if bank_path:request['reference_bank']=str(bank_path)
        if habit_path:request['habit_model']=str(habit_path)
        from .runtime.vatr_worker import request_input_hashes
        try:request['expected_input_hashes']=request_input_hashes(request)
        except (OSError,ValueError) as error:raise HTTPException(409,'生成输入已变化，请重新提交。') from error
        write(dest/'job.json',job)
        if imported_document:
            job['document_source']={'id':body.document_id,'filename':imported_document['filename'],
                'source_sha256':imported_document['source_sha256'],'parser_version':imported_document.get('parser_version'),
                'edited_after_import':text!=imported_document['text'],'warnings':imported_document['warnings']}
            (dest/'source.md').write_bytes(imported_document['source_text'].encode('utf-8'))
            write(dest/'document.json',imported_document)
            write(dest/'job.json',job)
        write(dest/'request.json',request)
        profile['preferences']=body.model_dump(exclude={'profile_id','text','document_id'})
        profile['word_spacing']=spacing_model
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
            result=subprocess.run(worker_command(folder/'request.json',job['preferences'].get('render_mode','model'),python=MODEL_PYTHON),
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
    if file not in ('result.pdf','report.json','layout.json','source.md','document.json') and not re.fullmatch(r'page-\d{3}\.png',file):raise HTTPException(404,'文件不存在。')
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

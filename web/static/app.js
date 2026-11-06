'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const state={token:'',profiles:[],draft:null,job:null,health:null,editorDirty:false,editorRevision:0,importing:false};
const jobWatcher=InkselfWorkflow.createJobWatcher({
  fetchJob:id=>api('/jobs/'+id),
  onUpdate:job=>{$('#job-retry').hidden=true;showJob(job);},
  onError:(_error,retrying)=>{
    $('#progress-title').textContent='正在重新连接';
    $('#progress-message').textContent=retrying?'连接暂时中断，正在自动重试。已提交的任务会在本地继续。':'暂时无法读取任务状态。恢复连接后可继续查看，无需重复生成。';
    $('#job-retry').hidden=false;
  },
});
const labels={capture:'采集字迹',compose:'写下新内容',library:'字迹与作品'};
function notice(message,error=false){const node=$('#notice');node.textContent=message;node.className=error?'error':'';node.hidden=false;window.scrollTo({top:0,behavior:'smooth'});}
function clearNotice(){$('#notice').hidden=true;}
function element(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
async function api(path,options={}){const headers={...(options.headers||{})};if(options.method&&options.method!=='GET')headers['X-Inkself-Token']=state.token;if(options.body&&!(options.body instanceof FormData))headers['Content-Type']='application/json';const response=await fetch('/api'+path,{...options,headers});if(!response.ok){let message='请求失败，请重试。';try{const data=await response.json();message=typeof data.detail==='string'?data.detail:'输入内容无效，请检查后重试。';}catch{}throw new Error(message);}return response.json();}
function view(name){if(!labels[name])name='capture';$$('.view').forEach(n=>n.hidden=n.id!==name);$$('.nav').forEach(n=>n.classList.toggle('active',n.dataset.view===name));$('#breadcrumb').textContent='工作室 / '+labels[name];if(location.hash!=='#'+name)history.replaceState(null,'','#'+name);window.scrollTo({top:0,behavior:'auto'});if(name==='library')loadLibrary().catch(e=>notice(e.message,true));}
$$('[data-view]').forEach(n=>n.addEventListener('click',()=>{clearNotice();view(n.dataset.view);}));
$$('[data-goto]').forEach(n=>n.addEventListener('click',()=>view(n.dataset.goto)));
window.addEventListener('hashchange',()=>view(location.hash.slice(1)));
function showFile(){const file=$('#sample-file').files[0];if(!file)return;if(!['image/jpeg','image/png','image/webp'].includes(file.type)){notice('请上传 JPG、PNG 或 WebP 图片。',true);$('#sample-file').value='';return;}if(file.size>20*1024*1024){notice('图片不能超过 20 MB。',true);$('#sample-file').value='';return;}$('#file-label').textContent=file.name;const image=$('#upload-preview');if(image.dataset.blob)URL.revokeObjectURL(image.dataset.blob);image.dataset.blob=URL.createObjectURL(file);image.src=image.dataset.blob;image.hidden=false;}
$('#sample-file').addEventListener('change',showFile);
for(const type of ['dragenter','dragover'])$('#drop-zone').addEventListener(type,event=>{event.preventDefault();$('#drop-zone').classList.add('dragging');});
for(const type of ['dragleave','drop'])$('#drop-zone').addEventListener(type,event=>{event.preventDefault();$('#drop-zone').classList.remove('dragging');});
$('#drop-zone').addEventListener('drop',event=>{if(event.dataTransfer.files.length){const transfer=new DataTransfer();transfer.items.add(event.dataTransfer.files[0]);$('#sample-file').files=transfer.files;showFile();}});
$('#upload-form').addEventListener('submit',async event=>{event.preventDefault();clearNotice();const button=$('#upload-button');button.disabled=true;button.textContent='正在检查图片、切分文字行…';try{const form=new FormData();form.append('name',$('#profile-name').value);form.append('file',$('#sample-file').files[0]);if(state.promptId)form.append('prompt_id',state.promptId);const data=await api('/profiles',{method:'POST',body:form});await loadProfiles();showReview(data);$('#sample-review').scrollIntoView({behavior:'smooth',block:'start'});}catch(error){notice(error.message,true);}finally{button.disabled=false;button.textContent='提取我的字迹 →';}});
function showReview(data){
  state.draft=data;view('capture');$('#sample-review').hidden=false;$('#review-check').checked=false;
  const grid=$('#line-grid');grid.replaceChildren();
  data.sample.lines.forEach((line,index)=>{
    const tile=element('div',undefined,'line-tile'),label=element('label',`第 ${index+1} 行`,'line-purpose-label'),select=document.createElement('select'),image=document.createElement('img');
    select.id=`line-purpose-${index}`;select.dataset.line=index;select.className='line-purpose';label.htmlFor=select.id;
    select.append(new Option('请选择类型',''),new Option('英文/数字','style'),new Option('数学/希腊字母','math'),new Option('不使用','skip'));
    select.value=data.math_lines?.includes(index)?'math':data.selected_lines?.includes(index)?'style':data.status==='ready'?'skip':'';
    image.src=`/api/profiles/${data.id}/sample/${line.file}`;image.alt=`提取的第 ${index+1} 行字迹`;
    tile.append(image,label,select);grid.append(tile);
  });
  const warnings=$('#sample-warnings');warnings.replaceChildren();data.sample.warnings.forEach(w=>warnings.append(element('p',w,'warning')));
}
$('#accept-sample').addEventListener('click',async()=>{
  if(!$('#review-check').checked){notice('请先检查每行的图片和类型，并勾选确认。',true);return;}
  const choices=$$('#line-grid .line-purpose');
  if(choices.some(node=>!node.value)){notice('请为每一行选择类型，切分错误的行选“不使用”。',true);return;}
  const lines=choices.filter(node=>node.value==='style').map(node=>Number(node.dataset.line));
  const math_lines=choices.filter(node=>node.value==='math').map(node=>Number(node.dataset.line));
  if(!lines.length){notice('至少保留一行完整的英文/数字字迹，供英文模型读取风格。',true);return;}
  const button=$('#accept-sample');button.disabled=true;
  try{await api(`/profiles/${state.draft.id}/review`,{method:'POST',body:JSON.stringify({lines,math_lines,inspected:true})});await loadProfiles(state.draft.id);if(typeof refreshOnboarding==='function')refreshOnboarding();view('compose');clearNotice();notice(math_lines.length?'字迹档案已保存。数学行已单独保留，仍需定位和核对后建立个人字形；先试写英文/数字。':'字迹档案已保存。先生成一小段，检查实际模仿效果。');}
  catch(error){notice(error.message,true);}finally{button.disabled=false;}
});
async function loadProfiles(selected,{restoreSelection=true}={}){state.profiles=await api('/profiles');const select=$('#profile-select'),previous=selected||select.value;select.replaceChildren();select.append(new Option('选择已确认的字迹',''));state.profiles.filter(p=>p.status==='ready').forEach(p=>select.append(new Option(p.name,p.id)));if([...select.options].some(o=>o.value===previous))select.value=previous;else if(select.options.length===2)select.selectedIndex=1;if(restoreSelection||select.value!==previous)showReference();}
function showReference(){
  const pid=$('#profile-select').value;
  const profile=state.profiles.find(p=>p.id===pid);
  const prefs=profile?.preferences||{};
  for(const option of $('#render-mode').options)option.disabled=option.value==='learned-habits'?!profile?.habit_model:option.value!=='model'&&!profile?.reference_bank;
  const preferred=[...$('#render-mode').options].find(option=>option.value===prefs.render_mode&&!option.disabled);
  $('#render-mode').value=preferred?.value||(profile?.habit_model?'learned-habits':profile?.reference_bank?'reference':'model');
  $('#selected-sample').hidden=!pid;
  if(pid)$('#reference-image').src=`/api/profiles/${pid}/sample/normalized.png`;
  restoreAnswerPreferences(prefs);
  $('#size').value=prefs.size??16;
  $('#size-value').value=prefs.size??16;
  restoreLineSpacing(prefs.line_spacing);
  $('#ink').value=prefs.ink||'#263d57';
  $('#math-enabled').checked=!!prefs.math_enabled;
  $('#allow-supplemental-math').checked=!!prefs.allow_supplemental_math;
  updateMathControls();
}
function restoreLineSpacing(value){const selected=String(value??1.6);if(![...$('#line-spacing').options].some(option=>option.value===selected))$('#line-spacing').append(new Option(selected+' 倍',selected));$('#line-spacing').value=selected;}
$('#profile-select').addEventListener('change',showReference);
function countText(){const limit=['model','model-calibrated'].includes($('#render-mode').value)?3000:20000;const count=$('#content').value.length;$('#char-count').textContent=`${count} / ${limit}`;$('#char-count').classList.toggle('over-limit',count>limit);$('#content').setCustomValidity(count>limit?`当前生成方式最多支持 ${limit.toLocaleString()} 字符，请缩短正文或切换为样本习惯适配。`:'');}
$('#content').addEventListener('input',countText);countText();$('#size').addEventListener('input',()=>$('#size-value').value=$('#size').value);
function editorSnapshot(){return {version:1,edited_at:Date.now(),profile_id:$('#profile-select').value,text:$('#content').value,document_id:state.documentId||null,dirty:state.editorDirty,preferences:{size:Number($('#size').value),line_spacing:Number($('#line-spacing').value),spacing:InkselfSpacing.read(),ink:$('#ink').value,seed:42,render_mode:$('#render-mode').value,math_enabled:$('#math-enabled').checked,allow_supplemental_math:$('#allow-supplemental-math').checked,layout_mode:$('#layout-mode')?.value||'standard',answer_header:$('#answer-header')?.value||''}};}
function saveEditorDraft(){
  const draft=editorSnapshot();InkselfWorkflow.writeStorage('inkself-compose-draft',JSON.stringify(draft));
  state.pendingDraft=draft;clearTimeout(state.draftTimer);
  $('#draft-status').textContent='正在保存草稿…';$('#draft-retry').hidden=true;
  state.draftTimer=setTimeout(flushEditorDraft,400);
}
async function flushEditorDraft(){
  if(state.savingDraft||!state.pendingDraft||!state.token)return;
  const draft=state.pendingDraft;state.pendingDraft=null;state.savingDraft=true;let saved=false;
  try{await api('/compose-draft',{method:'PUT',body:JSON.stringify(draft),keepalive:true});saved=true;
    if(!state.pendingDraft){$('#draft-status').textContent='草稿已保存在本机，关闭后可继续编辑。';$('#draft-retry').hidden=true;}
  }catch{if(!state.pendingDraft)state.pendingDraft=draft;$('#draft-status').textContent='草稿尚未保存到应用，请保持窗口打开并重试。';$('#draft-retry').hidden=false;}
  finally{state.savingDraft=false;if(saved&&state.pendingDraft)state.draftTimer=setTimeout(flushEditorDraft,0);}
}
$('#draft-retry').addEventListener('click',flushEditorDraft);
window.addEventListener('pagehide',()=>{clearTimeout(state.draftTimer);flushEditorDraft();});
function editorChanged(event){if(event?.target?.type==='file')return;state.editorDirty=true;state.editorRevision+=1;$('#preview-draft-note').hidden=!['needs-review','reviewed'].includes(state.job?.status);saveEditorDraft();}
function restoreEditor(draft){
  state.editorRevision+=1;
  const profileAvailable=[...$('#profile-select').options].some(option=>option.value===draft.profile_id);
  if(draft.profile_id)$('#profile-select').value=profileAvailable?draft.profile_id:'';
  else if($('#profile-select').options.length!==2)$('#profile-select').value='';
  showReference();
  const prefs=draft.preferences||{};restoreAnswerPreferences(prefs);
  $('#content').value=draft.text||'';
  $('#size').value=prefs.size??16;$('#size-value').value=$('#size').value;
  restoreLineSpacing(prefs.line_spacing);$('#ink').value=prefs.ink||'#263d57';
  if([...$('#render-mode').options].some(option=>option.value===prefs.render_mode&&!option.disabled))$('#render-mode').value=prefs.render_mode;
  $('#math-enabled').checked=!!prefs.math_enabled;$('#allow-supplemental-math').checked=!!prefs.allow_supplemental_math;
  state.documentId=draft.document_id||draft.document_source?.id||null;
  const documentInfo=$('#markdown-info');if(documentInfo){documentInfo.hidden=true;documentInfo.textContent='';}
  state.editorDirty=!!draft.dirty;updateMathControls();countText();saveEditorDraft();
}
$('#generate-form').addEventListener('input',editorChanged);
$('#generate-form').addEventListener('change',editorChanged);
$('#generate-form').addEventListener('spacingchange',editorChanged);
$('#generate-form').addEventListener('submit',async event=>{
  event.preventDefault();clearNotice();
  if(state.importing)return;
  if(!$('#profile-select').value){notice('请先采集并确认一份字迹。',true);return;}
  countText();if(!$('#generate-form').reportValidity())return;
  const button=$('#generate-button');button.disabled=true;button.textContent='正在提交…';
  state.openRequest=(state.openRequest||0)+1;
  const submitted=editorSnapshot(),revision=state.editorRevision;
  try{
    const job=await api('/jobs',{method:'POST',body:JSON.stringify({profile_id:submitted.profile_id,text:submitted.text,...submitted.preferences,document_id:submitted.document_id||undefined})});
    InkselfSpacing.recordGeneratedPreferences(state.profiles,job);
    if(state.editorRevision===revision){state.editorDirty=false;saveEditorDraft();}
    showJob(job);pollJob(job.id);
  }catch(error){notice(error.message,true);button.disabled=false;button.textContent='生成试写 →';}
});
function restoreAnswerPreferences(prefs){InkselfSpacing.restore(prefs?.spacing);if($('#layout-mode'))$('#layout-mode').value=prefs?.layout_mode||'standard';if($('#answer-header'))$('#answer-header').value=prefs?.answer_header||'';if(typeof updateLayoutControls==='function')updateLayoutControls();}
function showJob(job){
  if(job.status==='reviewed'&&typeof refreshOnboarding==='function')refreshOnboarding();
  state.job=job;InkselfWorkflow.writeStorage('inkself-last-job',job.id);
  const running=['queued','running'].includes(job.status),ready=['needs-review','reviewed'].includes(job.status);
  $('#empty-preview').hidden=true;$('#job-progress').hidden=!running;$('#output-pages').hidden=!ready;
  $('#download-bar').hidden=!ready;$('#feedback-panel').hidden=!ready;
  $('#generate-button').disabled=running||state.importing;
  $('#generate-button').textContent=running?'正在生成…':'生成试写 →';
  $('#progress-title').textContent=job.status==='queued'?'排队中':'正在试写';
  $('#progress-message').textContent=job.message||'';
  $('#page-count').textContent=ready?`${job.pages} 页 · A4`:'A4';
  $('#preview-draft-note').hidden=!ready||!state.editorDirty;
  $('#math-notice').hidden=true;$('#layout-notice').hidden=true;
  if(ready){
    const layoutWarnings=job.layout_warnings||[];
    $('#layout-notice').hidden=!layoutWarnings.length;
    $('#layout-notice').textContent=layoutWarnings.some(v=>v.code==='display-math-scaled')?'有公式为适应页面略微缩小，请放大核对。':layoutWarnings.length?'个别段落无法同时满足全部分页规则，请检查跨页处。':'';
    const supplemental=job.model?.supplemental_math_glyphs||[];
    $('#math-notice').hidden=!supplemental.length;
    $('#math-notice').textContent=supplemental.length?'本次使用配套手写数学字形：'+supplemental.join(' ')+'。这些字形尚未学习你的个人写法。':'';
    const pages=$('#output-pages');pages.replaceChildren();
    for(let i=1;i<=job.pages;i++){
      const image=document.createElement('img');
      image.src=`/api/jobs/${job.id}/files/page-${String(i).padStart(3,'0')}.png`;
      image.alt=`生成文档第 ${i} 页，需人工核对内容`;image.loading='lazy';pages.append(image);
    }
    $('#download-pdf').href=`/api/jobs/${job.id}/files/result.pdf`;
    $('#verification-label').textContent=job.content_verification==='human-confirmed'?'已人工确认内容':job.content_verification==='human-reported-errors'?'人工报告存在错误':'待人工核对';
    if(job.feedback){$('#text-verdict').value=job.feedback.text_correct?'correct':'errors';$('#similarity').value=job.feedback.similarity;$('#naturalness').value=job.feedback.naturalness;$('#feedback-notes').value=job.feedback.notes;}
    else{$('#text-verdict').value='';$('#similarity').value='';$('#naturalness').value='';$('#feedback-notes').value='';}
  }
  if(['failed','interrupted'].includes(job.status)){notice(job.message||'本次生成未完成，可调整内容后重试。',true);$('#empty-preview').hidden=false;}
}
function openJob(job,{protectDraft=true,restoreForm=true}={}){
  if(protectDraft&&state.editorDirty&&!window.confirm('当前正文或设置有未生成的修改。打开这份作品将替换当前草稿，是否继续？'))return false;
  jobWatcher.stop();$('#job-retry').hidden=true;
  if(restoreForm)restoreEditor(job);
  showJob(job);if(['queued','running'].includes(job.status))pollJob(job.id);
  return true;
}
function pollJob(id){jobWatcher.watch(id);}
$('#job-retry').addEventListener('click',()=>{ $('#job-retry').hidden=true;$('#progress-message').textContent='正在重新读取任务状态…';jobWatcher.retry(); });
$('#feedback-form').addEventListener('submit',async event=>{
  event.preventDefault();if(!state.job)return;
  const id=state.job.id,button=$('#feedback-form button[type=submit]');button.disabled=true;
  try{
    const job=await api(`/jobs/${id}/feedback`,{method:'POST',body:JSON.stringify({text_correct:$('#text-verdict').value==='correct',similarity:Number($('#similarity').value),naturalness:Number($('#naturalness').value),notes:$('#feedback-notes').value})});
    if(state.job?.id===id)showJob(job);
    notice('评价已保存。内容有错误或字迹不像时，请在备注中记录具体例子。');
  }catch(error){notice(error.message,true);}finally{button.disabled=false;}
});
async function openSavedJob(id){
  const request=state.openRequest=(state.openRequest||0)+1;
  try{const job=await api('/jobs/'+id);if(request===state.openRequest&&openJob(job))view('compose');}
  catch(error){if(request===state.openRequest)notice(error.message,true);}
}
const statusNames={'needs-review':'等待人工核对',reviewed:'已记录评价',queued:'排队中',running:'生成中',failed:'失败',interrupted:'已中断'};
async function loadLibrary(){await loadProfiles(undefined,{restoreSelection:false});const profiles=$('#profile-list');profiles.replaceChildren();if(!state.profiles.length)profiles.append(element('div','还没有个人字迹。从一段自然书写开始。','collection-empty'));for(const p of state.profiles){const row=element('div',undefined,'profile-row'),image=document.createElement('img'),main=element('div',undefined,'row-main'),actions=element('div',undefined,'row-actions');image.src=`/api/profiles/${p.id}/sample/normalized.png`;image.alt=p.name+'字迹样本';image.className='profile-thumb';main.append(element('strong',p.name),element('p',`${p.sample.lines.length} 行样本 · ${p.status==='ready'?'已确认，可试写':'待检查图片'} · 相似度未验收`));const use=element('button',p.status==='ready'?'去试写':'检查');use.onclick=()=>{if(p.status==='ready'){$('#profile-select').value=p.id;showReference();editorChanged();view('compose');}else{showReview(p);$('#sample-review').scrollIntoView({behavior:'smooth'});}};const remove=element('button','删除','danger');remove.onclick=async()=>{if(!window.confirm(`删除“${p.name}”及关联的样本、作品和评价？此操作不能撤销。`))return;try{await api('/profiles/'+p.id,{method:'DELETE'});await loadLibrary();notice('字迹与关联作品已删除。');}catch(error){notice(error.message,true);}};if(p.status==='ready'){const inspect=element('button','检查采样行');inspect.onclick=()=>{showReview(p);$('#sample-review').scrollIntoView({behavior:'smooth'});};actions.append(inspect);}actions.append(use,remove);row.append(image,main,actions);profiles.append(row);}const jobs=await api('/jobs'),list=$('#job-list');list.replaceChildren();if(!jobs.length)list.append(element('div','还没有试写作品。生成第一段新内容后，它会保存在这里。','collection-empty'));for(const job of jobs){const row=element('div',undefined,'job-row'),main=element('div',undefined,'row-main'),actions=element('div',undefined,'row-actions');main.append(element('strong',job.profile_name),element('p',job.text));const status=element('span',statusNames[job.status]||job.status,'job-status');const open=element('button','查看 →');open.onclick=()=>openSavedJob(job.id);actions.append(open);row.append(main,status,actions);list.append(row);}}
$('#refresh-library').addEventListener('click',()=>loadLibrary().catch(e=>notice(e.message,true)));
$('#model-info').addEventListener('click',async()=>{try{state.health=await api('/health');$('#model-chip').textContent=state.health.model.ready?'VATr++ · CPU 实验版':'模型准备中 · 可先采样';const area=$('#status-content');area.replaceChildren();area.append(element('p',`模型：${state.health.model.name} · CPU`),element('p',state.health.model.ready?'模型文件已就绪':'模型安装尚未完成'),element('p',state.health.model.inference_verified?'已通过实际推理冒烟检查':'实际推理尚未验证'),element('p',state.health.model.description));$('#status-dialog').showModal();}catch(error){notice(error.message,true);}});
$('#close-dialog').addEventListener('click',()=>$('#status-dialog').close());
async function start(){
  try{
    const session=await api('/session');state.token=session.token;
    $('#app-version').textContent=session.version?'INKSELF / '+session.version:'INKSELF';
    const prompt=await api('/prompt');state.promptId=prompt.id;
    $('#prompt-lines').replaceChildren(...prompt.lines.map(line=>element('p',line)));
    const mathSection=prompt.sections?.find(section=>section.purpose==='math');
    if(mathSection){$('#math-prompt-lines').replaceChildren(...mathSection.lines.map(line=>element('p',line)));$('#math-capture-instructions').textContent=mathSection.instructions;$('#math-capture-limit').textContent=mathSection.limitation;}
    state.health=await api('/health');$('#model-chip').textContent=state.health.model.ready?'VATr++ · CPU 实验版':'模型准备中 · 可先采样';
    await loadProfiles();
    let savedDraft=InkselfWorkflow.readDraft();
    try{const appDraft=await api('/compose-draft');if(appDraft&&(!savedDraft||(appDraft.edited_at||0)>=(savedDraft.edited_at||0)))savedDraft=appDraft;}
    catch{$('#draft-status').textContent='暂时无法读取已保存草稿，恢复连接后请刷新页面。';}
    if(savedDraft&&!state.editorDirty)restoreEditor(savedDraft);
    view(location.hash.slice(1)||'capture');
    const previous=InkselfWorkflow.readStorage('inkself-last-job');
    if(previous){
      try{const job=await api('/jobs/'+previous);openJob(job,{protectDraft:false,restoreForm:!savedDraft&&!state.editorDirty});}
      catch{InkselfWorkflow.removeStorage('inkself-last-job');}
    }
  }catch(error){notice('连接本地服务失败。请确认服务已经启动，再刷新页面。',true);$('#model-chip').textContent='服务未连接';}
}
start();

function updateMathControls(){countText();InkselfSpacing.modeChanged($('#render-mode').value);const supported=['reference','learned-habits'].includes($('#render-mode').value);$('#math-enabled').disabled=!supported;if(!supported)$('#math-enabled').checked=false;$('#math-settings').hidden=!$('#math-enabled').checked;}
$('#render-mode').addEventListener('change',updateMathControls);
$('#math-enabled').addEventListener('change',updateMathControls);
$('#insert-math-example').addEventListener('click',()=>{const example='\n\nInline: $x_{i}^{2}+y_{i}^{2}=r^{2}$.\n$$\\frac{x_i^2+y_i^2}{n}$$';const field=$('#content');if(field.value.length+example.length>20000){notice('内容已接近上限，请先缩短正文。',true);return;}field.value+=example;countText();editorChanged();});

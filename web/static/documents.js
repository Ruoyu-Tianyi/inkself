'use strict';

// Markdown is parsed by the local service; raw HTML and remote links are never
// rendered here. The editable preview is the actual text sent to generation.
state.documentId = null;
const mdControls = element('div', undefined, 'markdown-controls');
const mdLabel = element('label', '导入 Markdown 文档', 'secondary markdown-upload');
const mdInput = document.createElement('input');
mdInput.type = 'file'; mdInput.accept = '.md,.markdown,text/markdown'; mdInput.id = 'markdown-file';
mdLabel.append(mdInput);
const mdHelp = element('span', '.md / .markdown · UTF-8 · 最大 256 KB', 'muted');
const mdInfo = element('p', undefined, 'markdown-info'); mdInfo.id = 'markdown-info'; mdInfo.hidden = true;
mdControls.append(mdLabel, mdHelp, mdInfo);
document.querySelector('.compose-controls .label-row').before(mdControls);
mdInput.addEventListener('change', async () => {
  const file = mdInput.files[0]; if (!file) return;
  if (file.size > 256 * 1024) { notice('文档不能超过 256 KB，请拆分后导入。', true); mdInput.value = ''; return; }
  mdInput.disabled = true;
  try {
    const form = new FormData(); form.append('file', file);
    const imported = await api('/documents/markdown', {method:'POST', body:form});
    state.documentId = imported.id;
    $('#content').value = imported.text; countText();
    const profile = state.profiles.find(p => p.id === $('#profile-select').value);
    if (imported.math_enabled && profile?.reference_bank) {
      $('#render-mode').value = profile.habit_model ? 'learned-habits' : 'reference';
    }
    $('#math-enabled').checked = imported.math_enabled;
    updateMathControls();
    const notes = [...imported.warnings];
    if (imported.math_enabled && !profile?.reference_bank) notes.push('文档包含公式，需选择已有核对字形库的档案。');
    mdInfo.textContent = `${imported.filename} · ${imported.summary.characters} 字符。已解析为下方可编辑正文。${notes.length ? ' '+notes.join(' ') : ''}`;
    mdInfo.hidden = false;
    notice('文档已导入。检查下方正文与转换提示后，点击“生成试写”。');
  } catch (error) { notice(error.message, true); }
  finally { mdInput.disabled = false; mdInput.value = ''; }
});

let setupWatch = null;
async function refreshOnboarding() {
  try {
    const info = await api('/onboarding');
    $('#model-chip').textContent = info.model.ready ? '本地 AI 已就绪' : info.prepared_profiles ? '个人字迹可离线使用' : '首次准备本地 AI';
    const done = info.steps.find(step => step.id === 'review').done;
    $('#getting-started').hidden = done;
    const items = [...$('#onboarding-steps').children];
    info.steps.forEach((step,index) => { items[index].classList.toggle('done',step.done || !step.needed); });
    const button = $('#onboarding-action');
    button.disabled = false;
    if (!info.model.ready && !info.prepared_profiles) {
      button.textContent = info.model.runtime_ready ? '一键准备本地 AI' : '需要完整安装包';
      button.disabled = !info.model.runtime_ready;
      $('#onboarding-message').textContent = info.model.runtime_ready ? '首次联网下载约 580 MB 模型，之后离线使用。不需要 API 密钥，也不上传你的笔记。' : '此基础包可使用已导入的个人档案；首次采样生成请安装包含本地 AI 的完整版本。';
      button.onclick = prepareLocalModel;
    } else if (!info.profiles_ready) {
      button.textContent = '开始采集笔迹';
      $('#onboarding-message').textContent = '本地 AI 已准备好。抄写指定的英文与数字，上传照片并检查文字行。';
      button.onclick = () => { view('capture'); $('#upload-form').scrollIntoView({behavior:'smooth',block:'center'}); };
    } else {
      button.textContent = '开始试写';
      $('#onboarding-message').textContent = '你的字迹已保存。先生成一小段新内容，再核对数字、字形和自然程度。';
      button.onclick = () => view('compose');
    }
    const progress = await api('/setup/model');
    if (progress.status === 'downloading') watchSetup(progress);
  } catch (error) { $('#setup-progress').textContent = error.message; }
}

async function prepareLocalModel() {
  const button = $('#onboarding-action'); button.disabled = true;
  try { watchSetup(await api('/setup/model',{method:'POST'})); }
  catch (error) { button.disabled = false; notice(error.message,true); }
}

function watchSetup(progress) {
  if (setupWatch) clearTimeout(setupWatch);
  const button = $('#onboarding-action');
  const mb = value => (value / (1024*1024)).toFixed(1);
  $('#setup-progress').textContent = progress.status === 'downloading'
    ? `${progress.message}  ${mb(progress.bytes_completed)} / ${mb(progress.bytes_total)} MB · ${progress.files_completed}/${progress.files_total} 文件`
    : progress.message + (progress.error ? ' '+progress.error : '');
  button.disabled = progress.status === 'downloading';
  if (progress.status === 'downloading') {
    button.textContent = '正在准备…';
    setupWatch = setTimeout(async () => { try { watchSetup(await api('/setup/model')); } catch (error) { button.disabled=false; $('#setup-progress').textContent=error.message; } },1500);
  } else if (progress.status === 'ready') {
    state.health = null;
    refreshOnboarding();
  } else if (progress.status === 'failed') {
    button.textContent = '继续准备'; button.onclick = prepareLocalModel;
  }
}

refreshOnboarding();

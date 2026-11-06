const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const workflow = require('../web/static/workflow.js');

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
function watcherHarness(fetchJob) {
  const timers = new Map(), updates = [], errors = [];
  let next = 0;
  const watcher = workflow.createJobWatcher({fetchJob, onUpdate: job => updates.push(job),
    onError: (_error, retrying) => errors.push(retrying),
    setTimer: fn => { timers.set(++next, fn); return next; }, clearTimer: id => timers.delete(id)});
  async function tick() { const [id, fn] = timers.entries().next().value; timers.delete(id); await fn(); }
  return {watcher, timers, updates, errors, tick};
}

test('an in-flight response from an old job cannot replace the newly opened work', async () => {
  const old = deferred();
  const h = watcherHarness(id => id === 'old' ? old.promise : Promise.resolve({id, status:'reviewed'}));
  h.watcher.watch('old'); const pending = h.tick();
  h.watcher.watch('new'); await h.tick();
  old.resolve({id:'old', status:'needs-review'}); await pending;
  assert.deepEqual(h.updates.map(job => job.id), ['new']);
  assert.equal(h.timers.size, 0);
});

test('a disconnected task retries automatically, then allows an explicit retry', async () => {
  let online = false;
  const h = watcherHarness(async id => { if (!online) throw new Error('offline'); return {id, status:'reviewed'}; });
  h.watcher.watch('work');
  for (let i=0; i<4; i++) await h.tick();
  assert.deepEqual(h.errors, [true, true, true, false]);
  assert.equal(h.timers.size, 0);
  online = true; h.watcher.retry(); await h.tick();
  assert.deepEqual(h.updates, [{id:'work', status:'reviewed'}]);
});

test('stopping a watch ignores a later failure and creates no further retries', async () => {
  const response = deferred(), h = watcherHarness(() => response.promise);
  h.watcher.watch('work'); const pending = h.tick(); h.watcher.stop();
  response.reject(new Error('offline')); await pending;
  assert.equal(h.errors.length, 0); assert.equal(h.timers.size, 0);
});

function appHarness() {
  const nodes = new Map(), storage = new Map();
  function node(key) {
    if (!nodes.has(key)) nodes.set(key, {value:'', textContent:'', hidden:false, checked:false, disabled:false,
      options:[], children:[], classList:{toggle(){}}, listeners:{},
      setCustomValidity(value) { this.validationMessage = value; },
      addEventListener(event, fn) { (this.listeners[event] ||= []).push(fn); },
      append(...items) { this.children.push(...items); }, replaceChildren(...items) { this.children = items; }, before(){},
      setAttribute(){}, reportValidity(){return true;}, scrollIntoView(){}});
    return nodes.get(key);
  }
  const context = vm.createContext({
    document:{querySelector:key=>[...nodes.values()].find(item=>'#'+item.id===key)||node(key), querySelectorAll:()=>[], createElement:tag=>node(Symbol(tag))},
    window:{scrollTo(){}, addEventListener(){}, confirm:()=>false},
    location:{hash:'#compose'}, history:{replaceState(){}},
    fetch:()=>new Promise(()=>{}), FormData:class {append(){}}, Option:class {constructor(text,value){this.text=text;this.value=value;}},
    localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
    setTimeout:()=>1,clearTimeout(){}, InkselfSpacing:{read:()=>({preset:'natural'}),restore(){},modeChanged(){}},
  });
  vm.runInContext(fs.readFileSync('web/static/workflow.js','utf8'),context);
  vm.runInContext(fs.readFileSync('web/static/app.js','utf8'),context);
  const run = code => vm.runInContext(code,context);
  return {node:key=>context.document.querySelector(key),run,context,storage};
}

test('a completed background job preserves edited text, preferences, and document source', () => {
  const h = appHarness();
  h.node('#content').value='My next paragraph';h.node('#size').value='24';
  h.run("state.editorDirty=true;state.documentId='current-document';showJob({id:'finished',status:'needs-review',pages:2,text:'Previous paragraph',preferences:{size:12}})");
  assert.equal(h.node('#content').value,'My next paragraph');
  assert.equal(h.node('#size').value,'24');
  assert.equal(h.run('state.documentId'),'current-document');
  assert.equal(h.node('#preview-draft-note').hidden,false);
  assert.equal(h.node('#output-pages').children.length,2);
});

test('declining to replace an unsent draft leaves the current work untouched', () => {
  const h = appHarness();h.node('#content').value='Keep this draft';
  h.run("state.editorDirty=true;state.job={id:'current'}");
  assert.equal(h.run("openJob({id:'history',status:'reviewed'})"),false);
  assert.equal(h.node('#content').value,'Keep this draft');assert.equal(h.run('state.job.id'),'current');
});

test('the editor validates the actual mode limit without truncating the draft', () => {
  const h = appHarness();h.node('#content').value='x'.repeat(3001);h.node('#render-mode').value='model';h.run('countText()');
  assert.match(h.node('#content').validationMessage,/3,000/);
  assert.equal(h.node('#content').value.length,3001);
  h.node('#render-mode').value='reference';h.run('countText()');
  assert.equal(h.node('#content').validationMessage,'');
  assert.equal(h.node('#char-count').textContent,'3001 / 20000');
});

test('blocked browser storage does not prevent generation preview', () => {
  const h = appHarness();h.context.localStorage.setItem=()=>{throw new Error('blocked');};
  assert.doesNotThrow(()=>h.run("showJob({id:'work',status:'queued',message:'Waiting'})"));
  assert.equal(h.node('#job-progress').hidden,false);
});

test('draft saves are serialized so an older response cannot replace newer edits', async () => {
  const h = appHarness(), first = deferred(), second = deferred(), requests = [];
  h.context.fetch = (_url, options) => {
    requests.push(JSON.parse(options.body));
    return requests.length === 1 ? first.promise : second.promise;
  };
  h.run("state.token='token';state.pendingDraft={text:'first'}");
  const saving = h.run('flushEditorDraft()');
  h.run("state.pendingDraft={text:'second'}");
  await h.run('flushEditorDraft()');
  assert.equal(requests.length,1);
  first.resolve({ok:true,json:async()=>({})});await saving;
  const latest = h.run('flushEditorDraft()');
  assert.equal(requests.length,2);assert.equal(requests[1].text,'second');
  second.resolve({ok:true,json:async()=>({})});await latest;
  assert.match(h.node('#draft-status').textContent,/草稿已保存/);
  assert.equal(h.run('state.pendingDraft'),null);
});

test('a failed save retains the newest draft and offers retry', async () => {
  const h = appHarness(), response = deferred();
  h.context.fetch = () => response.promise;
  h.run("state.token='token';state.pendingDraft={text:'first'}");
  const saving = h.run('flushEditorDraft()');
  h.run("state.pendingDraft={text:'newer'}");response.reject(new Error('offline'));await saving;
  assert.equal(h.run('state.pendingDraft.text'),'newer');
  assert.equal(h.node('#draft-retry').hidden,false);
  assert.match(h.node('#draft-status').textContent,/尚未保存/);
});

test('opening the library refreshes profile data without resetting the editor settings', async () => {
  const h=appHarness();
  h.node('#profile-select').value='kept';h.node('#profile-select').options=[{value:'kept'}];
  h.node('#size').value='23';
  h.context.fetch=async()=>({ok:true,json:async()=>[{id:'kept',status:'ready',name:'Sample',preferences:{size:12}}]});
  await h.run('loadProfiles(undefined,{restoreSelection:false})');
  assert.equal(h.node('#size').value,'23');
});

test('assignment-only header controls follow restored layout preferences', () => {
  const h=appHarness();vm.runInContext(fs.readFileSync('web/static/documents.js','utf8'),h.context);
  h.run("restoreAnswerPreferences({layout_mode:'assignment',answer_header:'Name'})");
  assert.equal(h.node('#answer-header').hidden,false);
  h.run("restoreAnswerPreferences({layout_mode:'standard'})");
  assert.equal(h.node('#answer-header').hidden,true);
});

test('a slow Markdown import cannot overwrite content edited while it was being read', async () => {
  const h=appHarness();vm.runInContext(fs.readFileSync('web/static/documents.js','utf8'),h.context);
  const response=deferred();h.context.fetch=()=>response.promise;
  h.node('#markdown-file').files=[{name:'draft.md',size:50}];
  const pending=h.node('#markdown-file').listeners.change[0]();
  h.node('#content').value='New unsaved work';h.run('state.editorRevision+=1');
  response.resolve({ok:true,json:async()=>({id:'imported',text:'Old imported text'})});await pending;
  assert.equal(h.node('#content').value,'New unsaved work');
  assert.equal(h.run('state.documentId'),null);
  assert.equal(h.node('#generate-button').disabled,false);
  assert.match(h.node('#notice').textContent,/已保留当前草稿/);
});

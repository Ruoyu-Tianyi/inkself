'use strict';

// Keep network responses scoped to the work the user is currently viewing.
const InkselfWorkflow = (() => {
  function createJobWatcher({fetchJob, onUpdate, onError, setTimer = setTimeout, clearTimer = clearTimeout}) {
    let generation = 0, timer = null, current = null, failures = 0;
    function stop() {
      generation += 1;
      if (timer !== null) clearTimer(timer);
      timer = null;
      current = null;
    }
    function schedule(token, delay) {
      timer = setTimer(async () => {
        timer = null;
        if (token !== generation || !current) return;
        const id = current;
        try {
          const job = await fetchJob(id);
          if (token !== generation || id !== current) return;
          failures = 0;
          onUpdate(job);
          if (['queued', 'running'].includes(job.status)) schedule(token, 1800);
          else current = null;
        } catch (error) {
          if (token !== generation || id !== current) return;
          failures += 1;
          const retrying = failures <= 3;
          onError(error, retrying);
          if (retrying) schedule(token, Math.min(1500 * 2 ** failures, 12000));
        }
      }, delay);
    }
    function watch(id) {
      stop(); current = id; failures = 0;
      schedule(generation, 1800);
    }
    function retry() {
      if (!current) return;
      if (timer !== null) clearTimer(timer);
      generation += 1; failures = 0;
      schedule(generation, 0);
    }
    return {watch, stop, retry};
  }

  function readStorage(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function writeStorage(key, value) { try { localStorage.setItem(key, value); return true; } catch { return false; } }
  function removeStorage(key) { try { localStorage.removeItem(key); } catch {} }
  function readDraft() {
    try {
      const draft = JSON.parse(readStorage('inkself-compose-draft'));
      return draft?.version === 1 && typeof draft.text === 'string' && draft.text.length <= 20000
        && typeof draft.profile_id === 'string' && draft.preferences && typeof draft.preferences === 'object'
        ? draft : null;
    } catch { return null; }
  }
  return {createJobWatcher, readStorage, writeStorage, removeStorage, readDraft};
})();

if (typeof module !== 'undefined' && module.exports) module.exports = InkselfWorkflow;

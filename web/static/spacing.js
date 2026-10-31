'use strict';

// Relative layout preferences. Original ink shapes are never resized here.
const InkselfSpacing = (() => {
  const ranges = {
    letter: [.6, 1.8], word: [.5, 2], line: [.8, 1.8], paragraph: [.3, 2.5],
    number: [.6, 1.8], symbol: [.6, 1.8], baseline: [0, 2], variation: [0, 2],
  };
  const natural = Object.fromEntries(Object.keys(ranges).map(key => [key, 1]));
  const presets = {
    natural,
    neat: {...natural, line: 1.05, baseline: .25, variation: .2},
    compact: {letter: .85, word: .8, line: .9, paragraph: .75, number: .9, symbol: .9, baseline: .75, variation: .7},
    relaxed: {letter: 1.15, word: 1.3, line: 1.2, paragraph: 1.3, number: 1.15, symbol: 1.15, baseline: 1.15, variation: 1.25},
  };
  const labels = {letter: '字母间距', word: '词间距', line: '行间距', paragraph: '段落间距', number: '数字间距', symbol: '符号间距', baseline: '词语上下起伏', variation: '间距变化'};
  const fineKeys = ['letter', 'number', 'symbol'];
  let current = {preset: 'natural', ...natural};
  let mounted = false;

  function normalize(saved) {
    const source = saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
    const preset = Object.hasOwn(presets, source.preset) || source.preset === 'custom' ? source.preset : 'natural';
    const values = {...(presets[preset] || natural)};
    for (const [key, [min, max]] of Object.entries(ranges)) {
      if (typeof source[key] === 'number' && Number.isFinite(source[key])) {
        values[key] = Math.max(min, Math.min(max, source[key]));
      }
    }
    const matches = preset !== 'custom' && Object.keys(ranges).every(key => values[key] === presets[preset][key]);
    return {preset: matches ? preset : 'custom', ...values};
  }

  function percentage(value) { return Math.round(value * 100) + '%'; }

  function render() {
    if (!mounted) return;
    document.getElementById('spacing-preset').value = current.preset;
    for (const key of Object.keys(ranges)) {
      const input = document.getElementById('spacing-' + key);
      input.value = current[key];
      input.setAttribute('aria-valuetext', percentage(current[key]));
      document.getElementById('spacing-' + key + '-value').value = percentage(current[key]);
    }
  }

  function restore(saved) {
    // Start from the selected preset every time: old profiles must not inherit
    // sliders left over from a different profile or a previously opened job.
    current = normalize(saved);
    render();
  }

  function recordGeneratedPreferences(profiles, job) {
    const profile = profiles.find(item => item.id === job.profile_id);
    if (!profile || !job.preferences) return;
    // The service saves profile preferences when accepting a new generation.
    // Keep the selector's cache in step without mutating the job snapshot.
    profile.preferences = JSON.parse(JSON.stringify(job.preferences));
  }

  function modeChanged(mode) {
    if (!mounted) return;
    const fine = ['reference', 'learned-habits'].includes(mode);
    for (const key of fineKeys) {
      const input = document.getElementById('spacing-' + key);
      input.disabled = !fine;
      input.closest('.spacing-control').classList.toggle('unavailable', !fine);
    }
    document.getElementById('spacing-mode-help').hidden = fine;
  }

  function mount() {
    const grid = document.getElementById('spacing-grid');
    if (!grid) return;
    for (const [key, [min, max]] of Object.entries(ranges)) {
      const label = document.createElement('label');
      label.className = 'spacing-control';
      label.htmlFor = 'spacing-' + key;
      const name = document.createElement('span');
      name.textContent = labels[key];
      const output = document.createElement('output');
      output.id = 'spacing-' + key + '-value';
      output.htmlFor = 'spacing-' + key;
      const input = document.createElement('input');
      Object.assign(input, {id: 'spacing-' + key, type: 'range', min, max, step: .05});
      input.setAttribute('aria-label', labels[key]);
      input.setAttribute('aria-describedby', fineKeys.includes(key) ? 'spacing-detail-help spacing-mode-help' : 'spacing-detail-help');
      input.addEventListener('input', () => {
        current = {...current, preset: 'custom', [key]: Number(input.value)};
        render();
      });
      label.append(name, output, input);
      grid.append(label);
    }
    document.getElementById('spacing-preset').addEventListener('change', event => {
      if (Object.hasOwn(presets, event.target.value)) restore({preset: event.target.value});
    });
    document.getElementById('spacing-reset').addEventListener('click', () => restore({preset: 'natural'}));
    mounted = true;
    render();
    modeChanged(document.getElementById('render-mode').value);
  }

  if (typeof document !== 'undefined') mount();
  return {restore, recordGeneratedPreferences, modeChanged, read: () => ({...current}), normalize, presets, ranges};
})();

if (typeof module !== 'undefined' && module.exports) module.exports = InkselfSpacing;

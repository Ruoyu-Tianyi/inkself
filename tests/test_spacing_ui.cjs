const assert = require('node:assert/strict');
const test = require('node:test');
const spacing = require('../web/static/spacing.js');

test('opening a legacy profile clears the previous profile spacing', () => {
  spacing.restore({preset: 'compact', number: 1.6});
  assert.equal(spacing.read().preset, 'custom');
  spacing.restore(undefined);
  assert.deepEqual(spacing.read(), {preset: 'natural', ...spacing.presets.natural});
});

test('a stored job can restore a partial preset without retaining previous sliders', () => {
  spacing.restore({preset: 'custom', paragraph: 2.5, symbol: 1.8, variation: 0});
  spacing.restore({preset: 'neat'});
  assert.deepEqual(spacing.read(), {preset: 'neat', ...spacing.presets.neat});
});

test('submitting a request receives an independent copy of stored settings', () => {
  spacing.restore({preset: 'relaxed'});
  const request = spacing.read();
  request.word = 2;
  assert.equal(spacing.read().word, 1.3);
});

test('invalid legacy preferences cannot leave blank or non-finite controls', () => {
  spacing.restore({preset: 'obsolete', word: NaN, line: 'bad', number: 99});
  const restored = spacing.read();
  assert.equal(restored.word, 1);
  assert.equal(restored.line, 1);
  assert.equal(restored.number, 1.8);
  assert.equal(restored.preset, 'custom');
});

test('a successful generation keeps profile-switch restoration current, while viewing history does not overwrite it', () => {
  const profiles = [
    {id: 'a', preferences: {spacing: {preset: 'compact'}}},
    {id: 'b', preferences: {spacing: {preset: 'natural'}}},
  ];
  const preferences = {size: 18, spacing: spacing.normalize({preset: 'relaxed', word: 1.7})};
  spacing.recordGeneratedPreferences(profiles, {profile_id: 'a', preferences});
  spacing.restore(profiles[1].preferences.spacing);
  spacing.restore(profiles[0].preferences.spacing);
  assert.equal(spacing.read().word, 1.7);
  assert.equal(profiles[0].preferences.size, 18);

  spacing.restore({preset: 'neat'}); // Viewing an older job only restores controls.
  spacing.restore(profiles[0].preferences.spacing);
  assert.equal(spacing.read().word, 1.7);
  preferences.spacing.word = .5;
  assert.equal(profiles[0].preferences.spacing.word, 1.7);
  assert.deepEqual(profiles[1].preferences.spacing, {preset: 'natural'});
});

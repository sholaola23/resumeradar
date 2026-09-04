const assert = require('node:assert/strict');
const test = require('node:test');
let utils;
try { utils = require('../static/js/scan-utils.js'); } catch { utils = {}; }
test('unknown score is never represented as zero percent', () => {
  assert.equal(utils.scoreText?.(null), 'Not scored');
  assert.equal(utils.scoreText?.(0), '0%');
});
test('only same job and scoring version produce a progress delta', () => {
  const current = {score: 70, jobKey:'job-a', scoreVersion:'2'};
  assert.equal(utils.scoreDelta?.(current, {score:50,jobKey:'job-b',scoreVersion:'2'}), null);
  assert.equal(utils.scoreDelta?.(current, {score:50,jobKey:'job-a',scoreVersion:'1'}), null);
  assert.equal(utils.scoreDelta?.(current, {score:50,jobKey:'job-a',scoreVersion:'2'}), 20);
  assert.equal(utils.scoreDelta?.(current, {score:null,jobKey:'job-a',scoreVersion:'2'}), null);
});
test('job key ignores whitespace but distinguishes different requirements', async () => {
  assert.equal(typeof utils.jobKey, 'function');
  assert.equal(await utils.jobKey('AWS   Engineer\nPython'), await utils.jobKey('aws engineer python'));
  assert.notEqual(await utils.jobKey('AWS Engineer Python'), await utils.jobKey('AWS Engineer Java'));
});

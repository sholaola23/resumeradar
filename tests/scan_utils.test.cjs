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

test('rescan comparison names evidence changes only for the same job and score version', () => {
  const before = {score:50, jobKey:'a', scoreVersion:'2', matchedKeywords:['python', 'aws']};
  const after = {score:70, jobKey:'a', scoreVersion:'2', matchedKeywords:['python', 'docker', 'docker']};
  assert.deepEqual(utils.compareScan?.(after, before), {delta:20, added:['docker'], removed:['aws']});
  assert.equal(utils.compareScan?.({...after, jobKey:'b'}, before), null);
  assert.equal(utils.compareScan?.({...after, score:null}, before), null);
});

test('job view index finds every mention, with a term inside a longer one keeping its own status', () => {
  const segments = [
    {text: 'We use '},
    {text: 'GitHub Actions', keyword: 'github actions', category: 'technical_skills', status: 'missing',
     parts: [{text: 'GitHub', keyword: 'github', category: 'technical_skills', status: 'matched'}, {text: ' Actions'}]},
    {text: ' and '},
    {text: 'Python', keyword: 'python', category: 'technical_skills', status: 'matched'},
    {text: '. More '},
    {text: 'python', keyword: 'python', category: 'technical_skills', status: 'matched'},
  ];
  const index = utils.jobTermIndex?.(segments);
  assert.deepEqual(index.positions, {'github actions': ['jd-term-1'], github: ['jd-term-1-0'],
    python: ['jd-term-3', 'jd-term-5']});
  assert.equal(index.matched, 2);  // github and python
  assert.equal(index.missing, 1);
});
test('job view index is empty for missing or malformed segments', () => {
  for (const input of [undefined, null, [], [null, {text: 'plain'}, {text: 'x', keyword: 'x', status: 'other'}]]) {
    assert.deepEqual(utils.jobTermIndex?.(input), {positions: {}, matched: 0, missing: 0});
  }
});

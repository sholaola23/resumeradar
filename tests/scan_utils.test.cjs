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

test('share links carry only an allowlisted ref tag, never a score', () => {
  assert.equal(utils.shareUrl?.('https://x.test', 'whatsapp'), 'https://x.test/?ref=whatsapp');
  assert.equal(utils.shareUrl?.('https://x.test', '<script>'), 'https://x.test/?ref=copy');
  assert.equal(utils.refSource?.('?ref=qr'), 'qr');
  assert.equal(utils.refSource?.('?ref=evil&utm_source=x'), null);
  assert.equal(utils.refSource?.(''), null);
  assert.doesNotMatch(utils.shareMessage?.() || '%', /%|score|interview|hired/i);
});

test('a job link round-trips the job description inside the fragment only', async () => {
  const job = 'Senior Data Analyst — London\n\nRequirements:\n• SQL, Python, dbt\n• “Stakeholder” management ✅ 日本語';
  const url = await utils.jobLink('https://x.test', job);
  const parsed = new URL(url);
  assert.equal(parsed.search, '?ref=job');
  assert.ok(!parsed.search.includes('SQL') && parsed.hash.startsWith('#job='));
  assert.equal(await utils.decodeJob(parsed.hash), job);
});

test('a job link works without compression support', async () => {
  const saved = globalThis.CompressionStream;
  globalThis.CompressionStream = undefined;
  try {
    const encoded = await utils.encodeJob('Plain job text with ten or more words in it for a scan');
    assert.ok(encoded.startsWith('t.'));
    assert.equal(await utils.decodeJob('#job=' + encoded), 'Plain job text with ten or more words in it for a scan');
  } finally { globalThis.CompressionStream = saved; }
});

test('messy or hostile job links decode to nothing instead of throwing', async () => {
  for (const hash of ['', '#job=', '#job=z.', '#job=z.!!!!', '#job=t.____', '#job=q.abcd', '#other=1',
    '#job=z.AAAA', '#job=t.' + 'A'.repeat(9000), '#job=t.wyg', null, undefined]) {
    assert.equal(await utils.decodeJob(hash), null, String(hash).slice(0, 20));
  }
});

test('a decompression bomb in a job link is refused', async () => {
  const stream = new Blob([new Uint8Array(5_000_000)]).stream().pipeThrough(new CompressionStream('deflate-raw'));
  const packed = Buffer.from(await new Response(stream).arrayBuffer()).toString('base64url');
  assert.ok(packed.length < 8000);
  assert.equal(await utils.decodeJob('#job=z.' + packed), null);
});

test('a job description too long for a link is reported, not truncated silently', async () => {
  const words = Array.from({length: 4000}, (_, i) => 'w' + (i * 7919 % 100003).toString(36)).join(' ');
  assert.equal(await utils.jobLink('https://x.test', words), null);
});

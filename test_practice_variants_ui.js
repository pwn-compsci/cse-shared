const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

async function check(file, ok, ready) {
  const source = fs.readFileSync(path.join(__dirname, file), 'utf8').split('(function showExamBadge()')[0];
  const links = [];
  const body = {appendChild: link => links.push(link)};
  let onReady;
  const document = {
    currentScript: {src: 'https://example.edu/workspace/proxy/8080/js/exam-badge.js?v=1'},
    body: ready ? body : null,
    createElement: () => ({style: {}, setAttribute: () => {}}),
    addEventListener: (event, fn) => {assert.equal(event, 'DOMContentLoaded'); onReady = fn;}
  };
  vm.runInNewContext(source, {
    document, URL,
    fetch: async (url, options) => {
      assert.equal(url.href, 'https://example.edu/workspace/proxy/8080/exam_api/practice-variants/available');
      assert.equal(options.cache, 'no-store');
      return {ok};
    }
  });
  await new Promise(resolve => setImmediate(resolve));
  if (onReady) { document.body = body; onReady(); }
  assert.equal(links.length, ok ? 1 : 0);
  if (ok) {
    assert.equal(links[0].textContent, '↺  Practice & review');
    assert.equal(links[0].href, 'https://example.edu/workspace/proxy/8080/exam_api/practice-variants');
  }
}
(async () => {
  for (const file of ['common/web/js/exam-badge.js', 'exam_common/web/js/exam-badge.js']) {
    for (const ok of [true, false]) for (const ready of [true, false]) await check(file, ok, ready);
  }
  console.log('Practice variant links: 8 checks passed');
})().catch(error => {console.error(error); process.exitCode = 1;});

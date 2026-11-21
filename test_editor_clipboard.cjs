const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const {browser, route} = JSON.parse(fs.readFileSync(0, 'utf8'));
const listeners = {}, pending = [], sent = [];
let area = 'editor', selection = '', reads = 0, failWrite = false;
const clipboard = {
  async readText() { reads++; throw Error('clipboard-read denied'); },
  async writeText() { if (failWrite) throw Error('clipboard-write denied'); }
};
const document = {
  currentScript: {src: 'https://example.test/code/ultima-terminal-clipboard.js'},
  activeElement: {closest(selector) {return selector.includes('terminal') ? area === 'terminal' : selector === '.monaco-editor' ? area === 'editor' : false;}},
  querySelector() {return {textContent: 'main.c'};},
  addEventListener(name, fn) {listeners[name] = fn;}
};
vm.runInNewContext(browser, {
  document, window: {getSelection: () => ({toString: () => selection})},
  navigator: {clipboard}, URL, crypto: {randomUUID: () => 'session'},
  queueMicrotask: fn => pending.push(fn),
  fetch: async (url, options) => {sent.push(JSON.parse(options.body));}
});
function dom(event, text, trusted = true) {
  let stored = '';
  const data = {setData(type, value) {stored = value;}, getData() {return stored;}};
  const original = data.setData;
  listeners[event]({isTrusted: trusted, clipboardData: data});
  if (text !== null) data.setData('text/plain', text);
  while (pending.length) pending.shift()();
  assert.equal(data.setData, original);
}
(async () => {
  // The student's clipboard-read permission stays denied throughout.
  dom('copy', 'int main() {}');
  dom('copy', 'int main() {}');
  dom('cut', 'int main() {}');
  assert.equal(sent.length, 3); // rapid identical copies must survive
  assert.deepEqual(sent.map(r => r.event), ['copy', 'copy', 'cut']);
  assert.ok(sent.every(r => r.area === 'editor' && r.status === 'attempted'));
  assert.equal(sent[0].text, 'int main() {}');
  assert.equal(sent[0].fileLabel, 'main.c');
  assert.equal(sent[0].textOrigin, 'clipboard-event');
  assert.notEqual(sent[0].sequence, sent[1].sequence);
  dom('copy', null);
  assert.equal(sent.at(-1).contentAvailable, false);
  selection = 'fallback'; dom('copy', null);
  assert.equal(sent.at(-1).textOrigin, 'dom-selection');
  const before = sent.length;
  dom('copy', 'synthetic', false);
  dom('paste', 'editor paste');
  assert.equal(sent.length, before);
  await clipboard.writeText('menu copy');
  assert.equal(sent.at(-1).status, 'succeeded');
  failWrite = true;
  await assert.rejects(clipboard.writeText('blocked copy'), /denied/);
  assert.equal(sent.at(-1).status, 'failed');
  assert.equal(sent.at(-1).text, 'blocked copy');
  assert.equal(reads, 0);
  dom('copy', 'x'.repeat(300000) + '\nend');
  assert.equal(sent.at(-1).originalLength, 300004);
  assert.equal(sent.at(-1).originalLines, 2);
  assert.equal(sent.at(-1).text.length, 262144);
  assert.equal(sent.at(-1).truncated, true);
  area = null;
  const count = sent.length;
  dom('copy', 'outside editor');
  assert.equal(sent.length, count);
  area = 'terminal'; dom('copy', 'terminal output');
  assert.equal(sent.at(-1).area, 'terminal');

  const routes = {}, files = [];
  const crypto = require('node:crypto');
  vm.runInNewContext(route, {
    exports: {router: {get() {}, post(path, middleware, handler) {routes[path] = handler;}}},
    express: {json() {}}, http_1: {authenticated: async () => true},
    require(name) {
      if (name !== 'fs') return require(name);
      return {constants: fs.constants, promises: {
        readFile: async () => JSON.stringify({module:'23-proj-pointers',challenge:'p23-level-01',pwn_college_id:123}),
        mkdir: async () => {}, appendFile: async (path, text) => files.push({path, row:JSON.parse(text)})
      }};
    }
  });
  async function post(body, site = 'same-origin') {
    let status;
    await routes['/ultima-terminal-event']({body, get: () => site}, {sendStatus(n) {status = n;}}, error => {throw error;});
    return status;
  }
  assert.equal(await post(sent[0]), 204);
  assert.ok(files[0].path.endsWith('/editor-clipboard.jsonl'));
  assert.equal(files[0].row.capturedSha256, crypto.createHash('sha256').update(sent[0].text).digest('hex'));
  assert.equal(files[0].row.pwn_college_id, 123);
  assert.equal(await post({...sent[0], status:'definitely exported to AI'}), 400);
  assert.equal(await post({...sent[0], event:'paste'}), 400);
  assert.equal(await post({...sent[0], fileLabel: '../../secret'.repeat(200)}), 400);
  assert.equal(await post(sent[0], 'cross-site'), 403);
  assert.equal(await post(sent.at(-1)), 204);
  assert.ok(files.at(-1).path.endsWith('/terminal-clipboard.jsonl'));
  console.log('Editor copy/cut with denied clipboard reads, repeated actions, API failures, scope and route validation passed');
})().catch(error => {console.error(error); process.exitCode = 1;});

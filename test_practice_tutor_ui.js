const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'common/bin/practice_tutor/widget.js'), 'utf8');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.dataset = {}; this.hidden = false; this.events = {}; this.classList = {add: () => {}}; this.value = ''; }
  append(...children) { this.children.push(...children); }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, callback) { this.events[key] = callback; }
  focus() { this.focused = true; }
}
async function run(standalone) {
  const head = new Element('head'), body = new Element('body');
  body.dataset.tutorStandalone = String(standalone);
  const elements = [];
  const document = {
    head, body,
    currentScript: {src: 'https://example.edu/workspace/proxy/8080/exam_api/tutor/widget.js'},
    createElement: tag => {const element = new Element(tag); elements.push(element); return element;},
    getElementById: id => elements.find(element => element.id === id)
  };
  const calls = [];
  vm.runInNewContext(source, {
    document, location: {pathname:'/workspace/proxy/8080/'}, URL,
    fetch: async (url, options) => {
      calls.push({url:url.href, options});
      return {ok:true,json:async () => url.href.endsWith('session') ? {token:'csrf'} : {reply:'What did you expect to observe?',conversation_id:'conversation'}};
    }
  });
  const launcher = document.getElementById('practice-tutor-launcher');
  const panel = document.getElementById('practice-tutor-window');
  assert.equal(launcher.hidden, standalone);
  assert.equal(panel.hidden, !standalone);
  if (!standalone) {
    launcher.onclick(); assert.equal(panel.hidden,false);
    assert.equal(launcher.attributes['aria-expanded'],'true');
    panel.events.keydown({key:'Escape',stopPropagation(){},preventDefault(){}});
    assert.equal(panel.hidden,true);
    assert.equal(launcher.focused,true);
    launcher.onclick();
  }
  const textarea = elements.find(element => element.tag === 'textarea');
  const form = elements.find(element => element.tag === 'form');
  textarea.value = 'Why does the input repeat?';
  await form.onsubmit({preventDefault(){}});
  assert.equal(calls[0].url,'https://example.edu/workspace/proxy/8080/exam_api/tutor/session');
  assert.equal(calls[1].url,'https://example.edu/workspace/proxy/8080/exam_api/tutor/messages');
  assert.deepEqual(JSON.parse(calls[1].options.body),{message:'Why does the input repeat?'});
  assert.equal(calls[1].options.headers['X-Tutor-Token'],'csrf');
  assert(elements.some(element => element.textContent === 'Tutor: What did you expect to observe?'));
  const link = elements.find(element => element.tag === 'a');
  assert.equal(link.href,standalone ? 'https://example.edu/workspace/proxy/8080/' : 'https://example.edu/workspace/proxy/8080/exam_api/tutor/');
}
(async () => {await run(false); await run(true); console.log('Tutor popup, standalone chat, proxy URLs, and message flow passed');})().catch(error => {console.error(error);process.exitCode=1;});

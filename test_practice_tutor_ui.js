const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'common/bin/practice_tutor/widget.js'), 'utf8');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.dataset = {}; this.hidden = false; this.events = {}; this.classList = {add: () => {}}; this.value = ''; this.scrollHeight = 1200; this.scrollTop = 0; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, callback) { this.events[key] = callback; }
  focus() { this.focused = true; }
  requestSubmit() { this.submission = this.onsubmit({preventDefault(){}}); }
}
async function settle() { await new Promise(resolve => setImmediate(resolve)); }
async function mount(standalone = false, limited = false) {
  const head = new Element('head'), body = new Element('body');
  body.dataset.tutorStandalone = String(standalone);
  const elements = [], calls = [];
  const old = {id:'old',created_at:'2026-11-24T12:00:00Z',message:'An earlier question',reply:'An earlier hint',status:'completed'};
  const latest = {id:'latest',created_at:'2026-11-25T12:00:00Z',message:'Saved question',reply:'Saved hint',status:'completed'};
  let sent = false;
  const document = {head,body,currentScript:{src:'https://example.edu/workspace/proxy/8080/exam_api/tutor/widget.js'},
    createElement:tag => {const element = new Element(tag); elements.push(element); return element;},
    getElementById:id => elements.find(element => element.id === id)};
  vm.runInNewContext(source, {document,location:{pathname:'/workspace/proxy/8080/'},URL,setInterval:()=>0,
    fetch:async (url,options) => {
      calls.push({url:url.href,options});
      if (url.pathname.endsWith('session')) return {ok:true,json:async()=>({token:'csrf'})};
      if (url.pathname.endsWith('history')) return {ok:true,json:async()=>({conversation_id:'conversation',before:url.searchParams.has('before') ? null : 'older-cursor',turns:url.searchParams.has('before') ? [old] : sent ? [latest,{id:'new',created_at:'2026-11-25T12:15:00Z',message:'Why does the input repeat?',reply:'What did you expect to observe?',status:'completed'}] : [latest],retry_after:0})};
      sent = true;
      return limited ? {ok:false,status:429,json:async()=>({error:'Take a moment to try the hints.',retry_after:20})}
                     : {ok:true,json:async()=>({reply:'What did you expect to observe?',conversation_id:'conversation',retry_after:10})};
    }});
  const launcher = document.getElementById('practice-tutor-launcher');
  const panel = document.getElementById('practice-tutor-window');
  if (!standalone) launcher.onclick();
  await settle();
  return {document,elements,calls,launcher,panel};
}
(async () => {
  for (const standalone of [false,true]) {
    const {document,elements,calls,launcher,panel} = await mount(standalone);
    const log = elements.find(element => element.attributes.role === 'log');
    const text = () => log.children.flatMap(bubble => bubble.children).map(element => element.textContent).join(' ');
    assert.equal(launcher.hidden,standalone); assert.equal(panel.hidden,false);
    assert.equal(document.getElementById('practice-tutor-title').textContent,'Aita');
    assert(text().includes('Saved hint'), 'saved chat must reload');
    assert.equal(log.scrollTop,log.scrollHeight, 'restored history must scroll to bottom');
    assert(log.children.some(element => element.className === 'tutor-bubble tutor-you'));
    assert(log.children.some(element => element.className === 'tutor-bubble tutor-aita'));
    const earlier = elements.find(element => element.textContent === 'Load earlier messages');
    await earlier.onclick();
    assert(text().includes('An earlier hint'));
    assert.equal(earlier.hidden,true);
    const textarea = elements.find(element => element.tag === 'textarea');
    const form = elements.find(element => element.tag === 'form');
    textarea.value = 'Why does the input repeat?';
    let prevented = false;
    textarea.events.keydown({key:'Enter',shiftKey:true,preventDefault(){prevented=true;}});
    assert.equal(prevented,false,'Shift+Enter must retain native newline behavior');
    textarea.events.keydown({key:'Enter',isComposing:true,preventDefault(){throw Error('IME composition must not submit');}});
    textarea.events.keydown({key:'Enter',shiftKey:false,preventDefault(){prevented=true;}});
    assert.equal(prevented,true); await form.submission;
    const messages = calls.filter(call => call.url.endsWith('messages'));
    assert.equal(messages.length,1);
    assert.deepEqual(JSON.parse(messages[0].options.body),{message:'Why does the input repeat?',conversation_id:'conversation'});
    assert.equal(messages[0].options.headers['X-Tutor-Token'],'csrf');
    assert.equal(messages[0].url,'https://example.edu/workspace/proxy/8080/exam_api/tutor/messages');
    assert(text().includes('What did you expect to observe?'));
    const send = elements.find(element => element.type === 'submit');
    assert.equal(send.disabled,true,'cooldown must prevent immediate repeat sends');
    textarea.value = 'spam'; await form.onsubmit({preventDefault(){}});
    assert.equal(calls.filter(call => call.url.endsWith('messages')).length,1);
    if (!standalone) {
      panel.events.keydown({key:'Escape',stopPropagation(){},preventDefault(){}});
      assert.equal(panel.hidden,true); assert.equal(launcher.focused,true);
      launcher.onclick(); await settle();
      assert.equal(log.scrollTop,log.scrollHeight);
    }
  }
  const {elements} = await mount(false,true);
  const textarea = elements.find(element => element.tag === 'textarea');
  const form = elements.find(element => element.tag === 'form');
  textarea.value = 'my question'; await form.onsubmit({preventDefault(){}});
  assert.equal(textarea.value,'my question','throttled questions must remain editable');
  assert(elements.find(element => element.attributes.role === 'status').textContent.includes('Take a moment'));
  assert(elements.find(element => element.type === 'submit').textContent.startsWith('Wait '));
  console.log('Aita bubbles, restored/paginated history, Enter/Shift+Enter, IME, proxy URLs, and throttling passed');
})().catch(error => {console.error(error);process.exitCode=1;});

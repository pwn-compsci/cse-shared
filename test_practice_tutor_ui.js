const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'common/bin/practice_tutor/widget.js'), 'utf8');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.dataset = {}; this.hidden = false; this.events = {}; this.style = {}; this.classList = {add: () => {}}; this.value = ''; this.scrollHeight = 1200; this.scrollTop = 0; }
  append(...children) { for (const child of children) child.parent = this; this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, callback) { this.events[key] = callback; }
  focus() { this.focused = true; }
  contains(target) { return target === this || this.children.some(child => child.contains(target)); }
  closest(selector) { return selector.split(',').includes(this.tag) ? this : this.parent?.closest(selector); }
  setPointerCapture(id) { this.captured = id; }
  getBoundingClientRect() {
    if (this.hidden) return {left:0,top:0,width:0,height:0};
    const icon = this.id === 'practice-tutor-launcher', size = this.attributes['data-open'] === 'true' ? 36 : 58;
    return {left:parseFloat(this.style.left) || (icon ? 1180-size : 760),top:parseFloat(this.style.top) || (icon ? 778-size : 328),width:icon ? size : 420,height:icon ? size : 400};
  }
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
  const document = {head,body,events:{},addEventListener(key,callback){this.events[key]=callback;},currentScript:{src:'https://example.edu/workspace/proxy/8080/exam_api/tutor/widget.js'},
    createElement:tag => {const element = new Element(tag); elements.push(element); return element;},
    getElementById:id => elements.find(element => element.id === id)};
  const location = {pathname:'/workspace/proxy/8080/',assign(url){this.assigned=url;}};
  const window = {innerWidth:1200,innerHeight:800,closed:false,events:{},addEventListener(key,callback){this.events[key]=callback;},close(){this.closed=true;}};
  vm.runInNewContext(source, {document,location,window,URL,setInterval:()=>0,
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
  return {document,elements,calls,launcher,panel,window,location};
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
      document.events.keydown({key:'Escape',stopPropagation(){},preventDefault(){}});
      assert.equal(panel.hidden,true); assert.equal(launcher.focused,true);
      launcher.onclick(); await settle();
      assert.equal(log.scrollTop,log.scrollHeight);
    }
  }
  const moved = await mount(false);
  const {panel,launcher,document,elements} = moved;
  const header = elements.find(element => element.tag === 'header');
  const external = elements.find(element => element.tag === 'a');
  assert.equal(external.textContent,'↗');
  assert.equal(external.title,'Launch in a separate tab');
  assert.equal(external.href,'https://example.edu/workspace/proxy/8080/exam_api/tutor/');
  assert.equal(launcher.attributes['data-open'],'true');
  assert(!elements.some(element => element.className === 'tutor-note'),'top notice removed');
  assert.equal(document.getElementById('practice-tutor-title').className,'tutor-sr-only');
  const pointer = (target,x,y) => ({target,button:0,pointerId:1,clientX:x,clientY:y,preventDefault(){}});
  header.events.pointerdown(pointer(header,800,330));
  header.events.pointermove(pointer(header,700,250));
  header.events.pointerup(pointer(header,700,250));
  assert.equal(panel.style.left,'660px');
  assert.equal(panel.style.top,'248px');
  launcher.events.pointerdown(pointer(launcher,1044,662));
  launcher.events.pointermove(pointer(launcher,1084,682));
  launcher.events.pointerup(pointer(launcher,1084,682));
  launcher.onclick({preventDefault(){}});
  assert.equal(panel.hidden,false,'dragging launcher must not toggle chat');
  assert.equal(panel.style.left,'700px');
  document.events.pointerdown({target:panel});
  assert.equal(panel.hidden,false,'inside clicks must not close chat');
  launcher.focused = false;
  document.events.pointerdown({target:new Element('outside')});
  assert.equal(panel.hidden,true,'outside click closes popup');
  assert.equal(launcher.focused,false,'outside click must not steal editor focus');
  assert.equal(launcher.attributes['data-open'],'false');
  const page = await mount(true);
  page.document.events.keydown({key:'Escape',stopPropagation(){},preventDefault(){}});
  assert.equal(page.window.closed,true,'Escape closes standalone tab');
  const limited = await mount(false,true);
  const limitedElements = limited.elements;
  const textarea = limitedElements.find(element => element.tag === 'textarea');
  const form = limitedElements.find(element => element.tag === 'form');
  textarea.value = 'my question'; await form.onsubmit({preventDefault(){}});
  assert.equal(textarea.value,'my question','throttled questions must remain editable');
  assert(limitedElements.find(element => element.attributes.role === 'status').textContent.includes('Take a moment'));
  assert(limitedElements.find(element => element.type === 'submit').textContent.startsWith('Wait '));
  console.log('Aita drag controls, compact header, outside/Escape close, tab history, bubbles, keyboard and throttling passed');
})().catch(error => {console.error(error);process.exitCode=1;});

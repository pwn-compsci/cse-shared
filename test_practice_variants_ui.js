const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const variants = ['common/web/js/exam-badge.js', 'exam_common/web/js/exam-badge.js'];

async function mount(file, {ok = true, ready = true, saved = null, width = 1340, height = 800} = {}) {
  const source = fs.readFileSync(path.join(__dirname, file), 'utf8').split('(function showExamBadge()')[0];
  const links = [], styles = [], events = {}, windowEvents = {}, documentEvents = {};
  const frames = new Map();
  let frame = 0, onReady, stored = saved, resized, intersected;
  const window = {innerWidth: width, innerHeight: height, addEventListener: (event, fn) => {windowEvents[event] = fn;}};
  const root = {getBoundingClientRect: () => ({width: window.innerWidth, height: window.innerHeight})};
  const body = {appendChild: link => links.push(link)};
  const document = {
    hidden: false, documentElement: root,
    currentScript: {src: 'https://example.edu/workspace/proxy/8080/js/exam-badge.js?v=1'},
    body: ready ? body : null, head: {appendChild: style => styles.push(style)},
    getElementById: () => null, querySelector: () => null,
    createElement: () => ({style: {}, attributes: {},
      setAttribute(name, value) {this.attributes[name] = value;},
      addEventListener: (name, handler) => {events[name] = handler;}, setPointerCapture: () => {},
      getBoundingClientRect() {
        const manual = this.attributes['data-positioned'];
        return {left: manual ? parseFloat(this.style.left) : window.innerWidth - (window.innerWidth < 620 ? 8 : 136) - 155,
          top: manual ? parseFloat(this.style.top) : window.innerWidth < 620 ? 40 : 4, width: 155, height: 28};
      }
    }),
    addEventListener: (event, fn) => {if (event === 'DOMContentLoaded') onReady = fn; else documentEvents[event] = fn;}
  };
  vm.runInNewContext(source, {document, window, URL,
    requestAnimationFrame: fn => {frames.set(++frame, fn); return frame;}, cancelAnimationFrame: id => frames.delete(id),
    ResizeObserver: class {constructor(fn) {resized = fn;} observe() {}},
    IntersectionObserver: class {constructor(fn) {intersected = fn;} observe() {}},
    localStorage: {getItem: () => stored, setItem: (key, value) => {stored = value;}},
    fetch: async (url, options) => {
      assert.equal(url.href, 'https://example.edu/workspace/proxy/8080/exam_api/practice-variants/available');
      assert.equal(options.cache, 'no-store'); return {ok};
    }
  });
  await new Promise(resolve => setImmediate(resolve));
  if (onReady) {document.body = body; onReady();}
  assert.equal(links.length, ok ? 1 : 0);
  const tick = () => {const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach(fn => fn());};
  return {link: links[0], events, windowEvents, documentEvents, window, document, styles, stored: () => stored,
    tick, settle: () => {tick(); tick();}, resized: (...args) => resized(...args), intersected: (...args) => intersected(...args)};
}

(async () => {
  for (const file of variants) {
    for (const ok of [true, false]) for (const ready of [true, false]) {
      const {link, styles} = await mount(file, {ok, ready});
      if (ok) {
        assert.equal(link.textContent, 'Practice & review');
        assert.equal(link.href, 'https://example.edu/workspace/proxy/8080/exam_api/practice-variants');
        assert.match(link.style.cssText, /height:28px/);
        assert.match(link.style.cssText, /width:max-content/);
        assert.match(link.style.cssText, /background:#161616/);
        assert.match(styles[0].textContent, /right:136px!important/);
      }
    }
    const control = await mount(file);
    const pointer = (x, y) => ({button: 0, pointerId: 1, clientX: x, clientY: y});
    const original = control.link.getBoundingClientRect();
    control.events.pointerdown(pointer(original.left + 10, 10));
    control.events.pointermove(pointer(original.left - 190, 110));
    control.events.pointerup(pointer(original.left - 190, 110));
    assert.equal(control.link.style.left, (original.left - 200) + 'px');
    assert.equal(control.link.style.width, '155px'); assert.equal(control.link.style.height, '28px');
    assert.equal(control.link.style.right, 'auto');
    let prevented = false;
    control.events.click({detail: 1, preventDefault: () => {prevented = true;}});
    assert.equal(prevented, true, 'drag must not navigate');
    const restored = await mount(file, {saved: control.stored()});
    assert.equal(restored.link.style.left, control.link.style.left);
    restored.events.pointerdown(pointer(610, 110)); restored.events.pointerup(pointer(610, 110));
    prevented = false;
    restored.events.click({detail: 1, preventDefault: () => {prevented = true;}});
    assert.equal(prevented, false, 'ordinary click must navigate');
    const before = parseFloat(restored.link.style.left);
    restored.events.keydown({altKey: true, key: 'ArrowLeft', preventDefault: () => {}});
    assert.equal(restored.link.style.left, (before - 20) + 'px');

    const hidden = await mount(file, {width: 0, height: 0});
    hidden.settle();
    assert.equal(hidden.link.attributes['data-positioned'], undefined, 'default must remain CSS-anchored');
    hidden.window.innerWidth = 1340; hidden.window.innerHeight = 800;
    hidden.intersected([{isIntersecting: true}]); hidden.settle();
    assert.equal(hidden.link.getBoundingClientRect().left, 1049);
    assert.equal(hidden.link.attributes['data-positioned'], undefined);
    const manual = await mount(file, {width: 0, height: 0, saved: JSON.stringify({left: 900, top: 80})});
    manual.settle(); assert.equal(manual.link.style.left, '8px');
    manual.window.innerWidth = 1340; manual.window.innerHeight = 800;
    manual.intersected([{isIntersecting: true}]); manual.settle();
    assert.equal(manual.link.style.left, '900px', 'reopening restores preferred coordinates, not clamped startup values');
    assert.equal(manual.link.style.top, '80px');

    const source = fs.readFileSync(path.join(__dirname, file), 'utf8');
    const identity = {textContent: 'pex30 01 - 123 - Student'}, assigned = {};
    const ctx = vm.createContext({URL, monitorStatusUrl: 'https://example.edu/workspace/proxy/8080/exam-monitor-status.json',
      document: {querySelector: selector => selector === '.exam-badge-label' ? identity : assigned},
      fetch: async () => ({ok: true, text: async () => 'chosen_problem=f\n'})});
    vm.runInContext(source.slice(source.indexOf('async function updateAssignedVariant'), source.indexOf('function installInformationBarDrag')), ctx);
    await ctx.updateAssignedVariant(); await ctx.updateAssignedVariant();
    assert.equal(identity.textContent, 'pex30 - 01F - 123 - Student');
    assert.equal(assigned.hidden, true);
    assert.match(source, /reloadBtn.textContent = "↻"/);
  }
  console.log('Practice controls passed: compact sizes, icons, identity, click/drag, saved positions, keyboard movement, and collapsed iframe startup.');
})().catch(error => {console.error(error); process.exitCode = 1;});

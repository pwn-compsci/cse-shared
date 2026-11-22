const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

async function mount(file, ok = true, ready = true, saved = null) {
  const source = fs.readFileSync(path.join(__dirname, file), 'utf8').split('(function showExamBadge()')[0];
  const links = [];
  const events = {};
  let onReady;
  let stored = saved;
  const window = {innerWidth: 1200, innerHeight: 800, addEventListener: () => {}};
  const body = {appendChild: link => links.push(link)};
  const document = {
    currentScript: {src: 'https://example.edu/workspace/proxy/8080/js/exam-badge.js?v=1'},
    body: ready ? body : null,
    createElement: () => ({style: {}, setAttribute: () => {},
      addEventListener: (name, handler) => {events[name] = handler;},
      setPointerCapture: () => {},
      getBoundingClientRect() {return {left: parseFloat(this.style.left) || 0,
        top: parseFloat(this.style.top) || 0, width: 165, height: 36};}
    }),
    addEventListener: (event, fn) => {assert.equal(event, 'DOMContentLoaded'); onReady = fn;}
  };
  vm.runInNewContext(source, {
    document, window, URL,
    localStorage: {getItem: () => stored, setItem: (key, value) => {stored = value;}},
    fetch: async (url, options) => {
      assert.equal(url.href, 'https://example.edu/workspace/proxy/8080/exam_api/practice-variants/available');
      assert.equal(options.cache, 'no-store');
      return {ok};
    }
  });
  await new Promise(resolve => setImmediate(resolve));
  if (onReady) { document.body = body; onReady(); }
  assert.equal(links.length, ok ? 1 : 0);
  return {link: links[0], events, window, stored: () => stored};
}
(async () => {
  for (const file of ['common/web/js/exam-badge.js', 'exam_common/web/js/exam-badge.js']) {
    for (const ok of [true, false]) for (const ready of [true, false]) {
      const {link} = await mount(file, ok, ready);
      if (ok) {
        assert.equal(link.textContent, 'Practice & review');
        assert.equal(link.href, 'https://example.edu/workspace/proxy/8080/exam_api/practice-variants');
        assert.equal(link.style.left, '300px');
      }
    }
    const control = await mount(file);
    const pointer = (x, y) => ({button: 0, pointerId: 1, clientX: x, clientY: y});
    control.events.pointerdown(pointer(310, 10));
    control.events.pointermove(pointer(610, 110));
    control.events.pointerup(pointer(610, 110));
    assert.equal(control.link.style.left, '600px');
    assert.equal(control.link.style.top, '104px');
    let prevented = false;
    control.events.click({detail: 1, preventDefault: () => {prevented = true;}});
    assert.equal(prevented, true, 'drag must not navigate');
    const restored = await mount(file, true, true, control.stored());
    assert.equal(restored.link.style.left, '600px');
    restored.events.pointerdown(pointer(610, 110));
    restored.events.pointerup(pointer(610, 110));
    prevented = false;
    restored.events.click({detail: 1, preventDefault: () => {prevented = true;}});
    assert.equal(prevented, false, 'ordinary click must navigate');
    restored.events.keydown({altKey: true, key: 'ArrowLeft', preventDefault: () => {}});
    assert.equal(restored.link.style.left, '580px');
    const clamped = await mount(file, true, true, JSON.stringify({left: 9999, top: -100}));
    assert.equal(clamped.link.style.left, '1027px');
    assert.equal(clamped.link.style.top, '4px');

    // Check that only practice badges replace the existing exam identity.
    const source = fs.readFileSync(path.join(__dirname, file), 'utf8');
    const badgeCode = source.slice(source.indexOf('async function updatePracticeBadge'), source.indexOf('// Read the selected problem'));
    const label = {};
    const variant = {};
    const reload = {};
    const badge = {style: {}, querySelector: () => reload};
    const ctx = vm.createContext({URL,
      monitorStatusUrl: 'https://example.edu/workspace/proxy/8080/exam-monitor-status.json',
      document: {querySelector: selector => ({'.exam-badge': badge, '.exam-badge-label': label, '.exam-assigned-variant': variant})[selector]},
      fetch: async () => ({ok: true, json: async () => ({label: 'pex30 - 01a'})})
    });
    vm.runInContext(badgeCode, ctx);
    assert.equal(await ctx.updatePracticeBadge(), true);
    assert.equal(label.textContent, 'pex30 - 01a');
    assert.equal(variant.hidden, true);
    assert.equal(reload.textContent, 'Reload');
    assert.match(badge.style.cssText, /background:#26351f/);
    ctx.fetch = async () => ({ok: false});
    assert.equal(await ctx.updatePracticeBadge(), false);
  }
  console.log('Practice controls: visibility, compact badge, drag, click, keyboard movement, persistence and bounds passed');
})().catch(error => {console.error(error); process.exitCode = 1;});

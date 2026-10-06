const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

(async () => {
  for (const file of ['common/web/js/exam-badge.js', 'exam_common/web/js/exam-badge.js']) {
    const source = fs.readFileSync(file, 'utf8');
    let elapsed = 0;
    let wallClock = Date.parse('2026-10-06T21:30:00Z');
    let status = {state: 'active', updated_at: '2026-10-06T14:30:00Z'};
    let failed = false;
    let serverDate = null;
    const seen = [];
    const ctx = vm.createContext({URL, Number, Math, Date: {parse: Date.parse, now: () => wallClock},
      performance: {now: () => elapsed},
      fetch: async () => {if (failed) throw Error('offline'); return {ok: true, headers: {get: () => serverDate}, json: async () => status};},
      applyMonitorStatus: value => seen.push(value),
    });
    const declarations = source.slice(source.indexOf('const monitorPollIntervalMs'), source.indexOf('function positionMonitorHint'));
    const poll = source.slice(source.indexOf('async function pollExamMonitorStatus'), source.indexOf('function insertBadge'));
    vm.runInContext(`const monitorStatusUrl = 'https://example.test/status';\n${declarations}\n${poll}`, ctx);
    await ctx.pollExamMonitorStatus();
    assert.equal(seen.at(-1).state, 'active', `${file}: seven-hour offset`);
    wallClock -= 14 * 3600000;
    elapsed = 30000;
    status = {...status, updated_at: '2026-10-06T14:30:30Z'};
    await ctx.pollExamMonitorStatus();
    assert.equal(seen.at(-1).state, 'active', 'clock adjustment must not warn');
    elapsed = 120001;
    await ctx.pollExamMonitorStatus();
    assert.equal(seen.at(-1).state, 'warning', 'unchanged status must warn');
    status = {...status, updated_at: '2026-10-06T14:32:00Z'};
    await ctx.pollExamMonitorStatus();
    assert.equal(seen.at(-1).state, 'active', 'fresh update must recover');
    serverDate = 'Tue, 06 Oct 2026 14:40:00 GMT';
    await ctx.pollExamMonitorStatus();
    assert.equal(seen.at(-1).state, 'warning', 'server time detects old file immediately');
    // A new page has no monotonic history but must still reject an old file.
    vm.runInContext('monitorLastUpdatedAt = null; monitorLastUpdateObservedMs = null;', ctx);
    await ctx.pollExamMonitorStatus();
    assert.equal(seen.at(-1).state, 'warning', 'reload must not grant old file a fresh grace');
    status = {...status, updated_at: '2026-10-06T14:40:00Z'};
    await ctx.pollExamMonitorStatus();
    assert.equal(seen.at(-1).state, 'active', 'server freshness ignores browser clock');
    status = {...status, updated_at: '2026-10-06T15:40:00Z'};
    await ctx.pollExamMonitorStatus();
    assert.equal(seen.at(-1).state, 'warning', 'future status timestamp warns about server clock mismatch');
    status = {...status, updated_at: 'invalid'};
    await ctx.pollExamMonitorStatus();
    assert.equal(seen.at(-1).state, 'warning');
    failed = true;
    for (let i = 0; i < 3; i++) await ctx.pollExamMonitorStatus();
    assert.match(seen.at(-1).message, /cannot be read/);
    console.log(`${file}: clock, stale status, recovery, and fetch failure checks passed`);
  }
})().catch(error => {console.error(error); process.exitCode = 1;});

(() => {
  if (document.getElementById('practice-tutor-launcher')) return;
  const base = new URL('./', document.currentScript.src);
  if (location.pathname.includes('/practice-editor/')) return;
  const standalone = document.body.dataset.tutorStandalone === 'true';
  const style = document.createElement('style');
  style.textContent = `
#practice-tutor-launcher,#practice-tutor-window{font:14px system-ui,sans-serif;box-sizing:border-box;color:#edf2f7;z-index:2147483000}
#practice-tutor-launcher{position:fixed;right:20px;bottom:22px;width:58px;height:58px;border:1px solid #90b9e4;border-radius:50%;background:#214e7b;box-shadow:0 4px 20px #0007;cursor:pointer;font-size:25px}
#practice-tutor-launcher:hover{background:#2b659e}
#practice-tutor-launcher[data-open=true]{width:36px;height:36px;font-size:18px;opacity:.9}
#practice-tutor-launcher{touch-action:none;cursor:grab}
#practice-tutor-launcher:active{cursor:grabbing}
#practice-tutor-window{position:fixed;right:20px;bottom:72px;width:min(420px,calc(100vw - 32px));max-height:calc(100dvh - 115px);background:#172535;border:1px solid #54728e;border-radius:14px;box-shadow:0 8px 36px #0008;overflow:auto;padding:10px 12px}
#practice-tutor-window[hidden],#practice-tutor-launcher[hidden]{display:none!important}
#practice-tutor-window header{display:flex;align-items:center;gap:4px;height:28px;margin-bottom:6px;cursor:grab;touch-action:none;user-select:none}
#practice-tutor-window header:active{cursor:grabbing}
#practice-tutor-window .tutor-grip{flex:1;color:#7f9bb4;font-size:17px;letter-spacing:3px;padding-left:3px}
#practice-tutor-window .tutor-sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap;border:0}
#practice-tutor-window button,#practice-tutor-window textarea{font:inherit;box-sizing:border-box;border:1px solid #7391ab;border-radius:6px}
#practice-tutor-window button{background:#214e7b;color:#fff;padding:7px 12px;cursor:pointer}
#practice-tutor-window button:disabled{opacity:.6;cursor:not-allowed}
#practice-tutor-window button:focus-visible,#practice-tutor-launcher:focus-visible,#practice-tutor-window textarea:focus-visible{outline:3px solid #c6e8ff;outline-offset:3px}
#practice-tutor-window textarea{display:block;width:100%;min-height:76px;resize:vertical;background:#0f1c2a;color:#fff;padding:10px;margin:8px 0}
#practice-tutor-window [role=log]{height:34dvh;min-height:130px;overflow:auto;overscroll-behavior:contain;overflow-wrap:anywhere;padding:4px 2px}
#practice-tutor-window .tutor-bubble{border-radius:10px;padding:10px 12px;margin:10px 0;max-width:90%;box-sizing:border-box;line-height:1.5;border:1px solid transparent}
#practice-tutor-window .tutor-you{background:#234e73;color:#f1f7ff;border-color:#547fa4;margin-left:auto}
#practice-tutor-window .tutor-aita{background:#193e3d;color:#e4f7f2;border-color:#4c8d87;margin-right:auto}
#practice-tutor-window .tutor-bubble strong{display:block;font-size:11px;margin-bottom:4px;letter-spacing:.02em}
#practice-tutor-window .tutor-bubble p{white-space:pre-wrap;margin:0}
#practice-tutor-window .tutor-session{text-align:center;color:#b9cbdc;font-size:11px;margin:18px 0 8px}
#practice-tutor-window [role=status]{font-size:12px;color:#c3d3e2;line-height:1.5;margin:10px 0}
#practice-tutor-window .tutor-history-tools{display:flex;gap:8px;margin-bottom:8px}
#practice-tutor-window .tutor-history-tools button{font-size:12px;padding:5px 8px}
#practice-tutor-window .tutor-icon{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;width:28px;height:28px;padding:0;border:0;border-radius:7px;background:transparent;color:#b9dcff;text-decoration:none;font-size:20px;line-height:1;cursor:pointer}
#practice-tutor-window .tutor-icon:hover{background:#2a4258;color:#fff}
#practice-tutor-window .tutor-close{font-size:25px}
#practice-tutor-window,#practice-tutor-window [role=log],#practice-tutor-window textarea{scrollbar-width:thin;scrollbar-color:#547f88 #122331;scrollbar-gutter:stable}
#practice-tutor-window ::-webkit-scrollbar,#practice-tutor-window::-webkit-scrollbar{width:8px;height:8px}
#practice-tutor-window ::-webkit-scrollbar-track,#practice-tutor-window::-webkit-scrollbar-track{background:#122331;border-radius:8px}
#practice-tutor-window ::-webkit-scrollbar-thumb,#practice-tutor-window::-webkit-scrollbar-thumb{background:#547f88;border:2px solid #122331;border-radius:8px}
#practice-tutor-window ::-webkit-scrollbar-thumb:hover,#practice-tutor-window::-webkit-scrollbar-thumb:hover{background:#79a9af}
@media(pointer:coarse){#practice-tutor-window .tutor-icon{width:34px;height:34px}}
#practice-tutor-window.tutor-standalone{position:static;width:100%;max-height:none;box-shadow:none}
`;
  document.head.append(style);
  const launcher = document.createElement('button');
  launcher.id = 'practice-tutor-launcher'; launcher.type = 'button'; launcher.textContent = '💬';
  launcher.title = 'Aita'; launcher.setAttribute('aria-label', 'Open Aita');
  launcher.setAttribute('aria-expanded', String(standalone)); launcher.setAttribute('aria-controls', 'practice-tutor-window');
  launcher.hidden = standalone;
  const panel = document.createElement('section');
  panel.id = 'practice-tutor-window'; panel.setAttribute('role', 'region'); panel.setAttribute('aria-labelledby', 'practice-tutor-title');
  panel.hidden = !standalone;
  if (standalone) panel.classList.add('tutor-standalone');
  const header = document.createElement('header');
  const title = document.createElement('span'); title.id = 'practice-tutor-title'; title.className = 'tutor-sr-only'; title.textContent = 'Aita';
  const grip = document.createElement('span'); grip.className = 'tutor-grip'; grip.textContent = '⠿'; grip.setAttribute('aria-hidden','true');
  header.title = 'Drag to move Aita';
  const close = document.createElement('button'); close.type = 'button'; close.textContent = '×'; close.setAttribute('aria-label', 'Close Aita'); close.title = 'Close Aita (Esc)'; close.className = 'tutor-icon tutor-close';
  const historyTools = document.createElement('div'); historyTools.className = 'tutor-history-tools';
  const earlier = document.createElement('button'); earlier.type = 'button'; earlier.textContent = 'Load earlier messages'; earlier.hidden = true;
  const reload = document.createElement('button'); reload.type = 'button'; reload.textContent = 'Reload history';
  historyTools.append(earlier, reload);
  const log = document.createElement('div'); log.setAttribute('role', 'log'); log.setAttribute('aria-live', 'polite'); log.setAttribute('aria-label', 'Saved conversation with Aita');
  const status = document.createElement('p'); status.setAttribute('role', 'status');
  const form = document.createElement('form');
  const input = document.createElement('textarea'); input.setAttribute('aria-label', 'Your question');
  input.placeholder = 'Ask Aita… Enter to send, Shift+Enter for a new line'; input.maxLength = 2000; input.required = true;
  const send = document.createElement('button'); send.type = 'submit'; send.textContent = 'Ask Aita';
  form.append(input, send);
  const pageLink = document.createElement('a'); pageLink.href = standalone ? new URL('../../', base).href : base.href;
  pageLink.className = 'tutor-icon'; pageLink.textContent = standalone ? '←' : '↗';
  pageLink.title = standalone ? 'Back to the editor' : 'Launch in a separate tab';
  pageLink.setAttribute('aria-label',pageLink.title);
  if (!standalone) { pageLink.target = '_blank'; pageLink.rel = 'noopener'; }
  header.append(grip, title, pageLink, close);
  panel.append(header, historyTools, log, status, form);
  (document.getElementById('tutor-mount') || document.body).append(launcher, panel);
  let conversation, token, before, turns = [], historyReady = false, loading = false, sending = false, waitUntil = 0;
  function updateSend() {
    const remaining = Math.max(0, Math.ceil((waitUntil - Date.now()) / 1000));
    send.disabled = sending || loading || !historyReady || remaining > 0;
    send.textContent = sending ? 'Thinking…' : remaining ? `Wait ${remaining}s` : 'Ask Aita';
    reload.disabled = earlier.disabled = loading || sending;
  }
  function cooldown(seconds) { if (seconds > 0) waitUntil = Math.max(waitUntil, Date.now() + seconds * 1000); updateSend(); }
  function bottom() { log.scrollTop = log.scrollHeight; }
  function line(who, text) {
    const bubble = document.createElement('article'); bubble.className = 'tutor-bubble ' + (who === 'You' ? 'tutor-you' : 'tutor-aita');
    const label = document.createElement('strong'); label.textContent = who;
    const paragraph = document.createElement('p'); paragraph.textContent = text;
    bubble.append(label, paragraph); log.append(bubble);
  }
  function render() {
    log.replaceChildren();
    let previous;
    for (const turn of turns) {
      const time = new Date(turn.created_at);
      if (!previous || time - previous > 30 * 60 * 1000 || time.toDateString() !== previous.toDateString()) {
        const separator = document.createElement('p'); separator.className = 'tutor-session';
        separator.textContent = time.toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
        log.append(separator);
      }
      line('You', turn.message);
      if (turn.reply) line('Aita', turn.reply);
      else line('Aita', turn.status === 'failed' ? 'This question could not be answered. You can try it again.' : 'No saved reply yet. Reload history to check again.');
      previous = time;
    }
    if (!turns.length) status.textContent = 'What part of the requirements would you like to understand?';
  }
  async function sessionToken() {
    if (token) return;
    const response = await fetch(new URL('session', base), {cache:'no-store'});
    if (!response.ok) throw Error('Aita is unavailable. Reload the editor and try again.');
    token = (await response.json()).token;
  }
  async function loadHistory(older = false) {
    if (loading) return;
    loading = true; updateSend(); status.textContent = 'Loading saved chat…';
    const oldHeight = log.scrollHeight, oldScroll = log.scrollTop;
    try {
      await sessionToken();
      const url = new URL('history', base);
      if (older && before) url.searchParams.set('before', before);
      const response = await fetch(url, {cache:'no-store'});
      const result = await response.json();
      if (!response.ok) throw Error(result.error || 'Could not load Aita’s saved chat.');
      conversation = result.conversation_id; before = result.before;
      turns = older ? [...result.turns, ...turns] : result.turns;
      turns = [...new Map(turns.map(turn => [turn.id, turn])).values()];
      historyReady = true; earlier.hidden = !before; status.textContent = '';
      cooldown(result.retry_after || 0); render();
      if (older) log.scrollTop = oldScroll + log.scrollHeight - oldHeight; else bottom();
    } catch (error) { status.textContent = error.message; }
    finally { loading = false; updateSend(); }
  }
  const open = (value, restoreFocus = true) => {
    panel.hidden = !value; launcher.setAttribute('aria-expanded', String(value)); launcher.setAttribute('data-open',String(value));
    if (value) { if (panel.style.left) place(panel,box(panel),0,0); input.focus(); if (!sending) void loadHistory(); else bottom(); } else if (restoreFocus) launcher.focus();
  };
  let drag = null, suppressLauncherClick = false;
  function closeChat() {
    if (!standalone) { open(false); return; }
    window.close();
    // Browsers may refuse to close a manually opened tab; return to its editor.
    if (!window.closed) location.assign(new URL('../../',base).href);
  }
  launcher.onclick = event => {
    if (suppressLauncherClick) { suppressLauncherClick = false; event?.preventDefault(); return; }
    open(panel.hidden);
  };
  close.onclick = closeChat;
  reload.onclick = () => loadHistory(); earlier.onclick = () => loadHistory(true);
  panel.addEventListener('keydown', event => event.stopPropagation());
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !event.isComposing && !panel.hidden) {
      event.preventDefault(); event.stopPropagation(); closeChat();
    }
  }, true);
  document.addEventListener('pointerdown', event => {
    if (!standalone && !panel.hidden && !drag && !panel.contains(event.target) && !launcher.contains(event.target)) open(false,false);
  }, true);
  window.addEventListener('blur', () => {
    if (!standalone && !panel.hidden && !drag && document.activeElement?.tagName === 'IFRAME') open(false,false);
  });
  function box(element) {
    const rect = element.getBoundingClientRect();
    if (rect.width && rect.height) return rect;
    const width = Math.min(420, window.innerWidth - 32), height = Math.min(500, window.innerHeight - 115);
    const left = parseFloat(element.style.left), top = parseFloat(element.style.top);
    return {left:Number.isFinite(left) ? left : window.innerWidth-width-20,top:Number.isFinite(top) ? top : window.innerHeight-height-72,width,height};
  }
  function place(element, rect, dx, dy) {
    element.style.left = Math.max(8,Math.min(rect.left+dx,window.innerWidth-rect.width-8)) + 'px';
    const top = Math.max(8,Math.min(rect.top+dy,window.innerHeight-rect.height-8));
    element.style.top = top + 'px';
    if (element === panel) element.style.maxHeight = Math.max(28,window.innerHeight-top-8) + 'px';
    element.style.right = element.style.bottom = 'auto';
  }
  for (const handle of [header, launcher]) {
    handle.addEventListener('pointerdown', event => {
      if (standalone || event.button !== 0 || event.isPrimary === false) return;
      if (handle === header && event.target.closest?.('button,a,textarea')) return;
      drag = {id:event.pointerId,x:event.clientX,y:event.clientY,handle,moved:false,panel:box(panel),launcher:box(launcher)};
      handle.setPointerCapture(event.pointerId);
    });
    handle.addEventListener('pointermove', event => {
      if (!drag || drag.id !== event.pointerId) return;
      const dx = event.clientX-drag.x, dy = event.clientY-drag.y;
      if (!drag.moved && Math.hypot(dx,dy) < 5) return;
      drag.moved = true; event.preventDefault();
      place(panel,drag.panel,dx,dy); place(launcher,drag.launcher,dx,dy);
    });
    const finish = event => {
      if (!drag || drag.id !== event.pointerId) return;
      if (drag.handle === launcher) suppressLauncherClick = drag.moved;
      drag = null;
    };
    handle.addEventListener('pointerup',finish);
    handle.addEventListener('pointercancel',finish);
    handle.addEventListener('lostpointercapture',finish);
  }
  window.addEventListener('resize', () => {
    if (!standalone) { place(panel,box(panel),0,0); place(launcher,box(launcher),0,0); }
  });
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
      event.preventDefault(); if (!send.disabled) form.requestSubmit();
    }
  });
  form.onsubmit = async event => {
    event.preventDefault();
    if (send.disabled || !input.value.trim()) return;
    sending = true; updateSend(); status.textContent = 'Aita is thinking…';
    const message = input.value;
    try {
      await sessionToken(); line('You', message); bottom(); input.value = '';
      const response = await fetch(new URL('messages', base), {
        method:'POST', headers:{'Content-Type':'application/json', 'X-Tutor-Token':token},
        body:JSON.stringify({message, conversation_id:conversation})
      });
      const result = await response.json(); cooldown(result.retry_after || 0);
      if (!response.ok) { if (response.status === 403) token = null; throw Error(result.error || 'Aita is unavailable. Please try again shortly.'); }
      conversation = result.conversation_id;
      line('Aita', result.reply); bottom();
      await loadHistory();
    } catch (error) {
      await loadHistory(); status.textContent = error.message;
      if (!input.value) input.value = message;
    } finally { sending = false; updateSend(); }
  };
  launcher.setAttribute('data-open',String(standalone));
  updateSend();
  setInterval(updateSend, 250);
  if (standalone) void loadHistory();
})();

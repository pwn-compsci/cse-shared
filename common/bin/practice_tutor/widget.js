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
#practice-tutor-window{position:fixed;right:20px;bottom:92px;width:min(390px,calc(100vw - 32px));max-height:calc(100dvh - 115px);background:#172535;border:1px solid #54728e;border-radius:14px;box-shadow:0 8px 36px #0008;overflow:auto;padding:16px}
#practice-tutor-window[hidden],#practice-tutor-launcher[hidden]{display:none!important}
#practice-tutor-window header{display:flex;align-items:center;gap:12px;margin-bottom:12px}
#practice-tutor-window h2{font-size:18px;margin:0;flex:1}
#practice-tutor-window button,#practice-tutor-window textarea{font:inherit;box-sizing:border-box;border:1px solid #7391ab;border-radius:6px}
#practice-tutor-window button{background:#214e7b;color:#fff;padding:7px 12px;cursor:pointer}
#practice-tutor-window button:disabled{opacity:.6;cursor:wait}
#practice-tutor-window button:focus-visible,#practice-tutor-launcher:focus-visible,#practice-tutor-window textarea:focus-visible{outline:3px solid #c6e8ff;outline-offset:3px}
#practice-tutor-window textarea{display:block;width:100%;min-height:76px;resize:vertical;background:#0f1c2a;color:#fff;padding:10px;margin:8px 0}
#practice-tutor-window [role=log]{max-height:34dvh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}
#practice-tutor-window p{line-height:1.5;margin:10px 0}
#practice-tutor-window .tutor-note{font-size:12px;color:#b9cbdc}
#practice-tutor-window a{color:#b9dcff;font-size:12px}
#practice-tutor-window.tutor-standalone{position:static;width:100%;max-height:none;box-shadow:none}
`;
  document.head.append(style);
  const launcher = document.createElement('button');
  launcher.id = 'practice-tutor-launcher';
  launcher.type = 'button';
  launcher.textContent = '💬';
  launcher.title = 'Practice tutor';
  launcher.setAttribute('aria-label', 'Open practice tutor');
  launcher.setAttribute('aria-expanded', String(standalone));
  launcher.setAttribute('aria-controls', 'practice-tutor-window');
  launcher.hidden = standalone;
  const panel = document.createElement('section');
  panel.id = 'practice-tutor-window';
  panel.setAttribute('role', 'region');
  panel.setAttribute('aria-labelledby', 'practice-tutor-title');
  panel.hidden = !standalone;
  if (standalone) panel.classList.add('tutor-standalone');
  const header = document.createElement('header');
  const title = document.createElement('h2');
  title.id = 'practice-tutor-title';
  title.textContent = 'Practice tutor';
  const close = document.createElement('button');
  close.type = 'button';
  close.textContent = '×';
  close.setAttribute('aria-label', 'Close practice tutor');
  close.hidden = standalone;
  header.append(title, close);
  const note = document.createElement('p');
  note.className = 'tutor-note';
  note.textContent = 'Conceptual hints only. Save your files first: your code and recent test results are sent with your question. Conversations are recorded for instructor review.';
  const log = document.createElement('div');
  log.setAttribute('role', 'log');
  log.setAttribute('aria-live', 'polite');
  const form = document.createElement('form');
  const input = document.createElement('textarea');
  input.setAttribute('aria-label', 'Your question');
  input.placeholder = 'What are you trying to understand?';
  input.maxLength = 2000;
  input.required = true;
  const send = document.createElement('button');
  send.type = 'submit';
  send.textContent = 'Ask tutor';
  form.append(input, send);
  const pageLink = document.createElement('a');
  pageLink.href = standalone ? new URL('../../', base).href : base.href;
  pageLink.textContent = standalone ? 'Back to the editor' : 'Open chat in a separate tab';
  if (!standalone) { pageLink.target = '_blank'; pageLink.rel = 'noopener'; }
  panel.append(header, note, log, form, pageLink);
  (document.getElementById('tutor-mount') || document.body).append(launcher, panel);
  let conversation, token;
  const open = value => {
    panel.hidden = !value;
    launcher.setAttribute('aria-expanded', String(value));
    if (value) input.focus(); else launcher.focus();
  };
  launcher.onclick = () => open(panel.hidden);
  close.onclick = () => open(false);
  panel.addEventListener('keydown', event => {
    event.stopPropagation();
    if (event.key === 'Escape' && !standalone) { event.preventDefault(); open(false); }
  });
  function line(who, text) {
    const paragraph = document.createElement('p');
    paragraph.textContent = who + ': ' + text;
    log.append(paragraph);
    log.scrollTop = log.scrollHeight;
  }
  form.onsubmit = async event => {
    event.preventDefault();
    if (send.disabled || !input.value.trim()) return;
    send.disabled = true;
    send.textContent = 'Thinking…';
    const message = input.value;
    try {
      if (!token) {
        const response = await fetch(new URL('session', base), {cache:'no-store'});
        if (!response.ok) throw Error('Tutor session unavailable. Reload the editor and try again.');
        token = (await response.json()).token;
      }
      line('You', message);
      input.value = '';
      const response = await fetch(new URL('messages', base), {
        method:'POST', headers:{'Content-Type':'application/json', 'X-Tutor-Token':token},
        body:JSON.stringify({message, conversation_id:conversation})
      });
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 403) token = null;
        throw Error(result.error || 'Tutor unavailable. Please try again shortly.');
      }
      conversation = result.conversation_id;
      line('Tutor', result.reply);
    } catch (error) {
      line('Status', error.message);
      if (!input.value) input.value = message;
    } finally {
      send.disabled = false;
      send.textContent = 'Ask tutor';
    }
  };
})();

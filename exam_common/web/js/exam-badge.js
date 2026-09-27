
(function showExamBadge() {
    console.log("CSE240: in showExamBadge");
    
// Store for copied text
let lastCopiedText = '';

// Listen for post-messages from the extension
window.addEventListener('message', (event) => {
    if (event.data.type === 'exam_requirements_copy') {
        console.log('CSE240: Exam copy detected via post-message:', event.data.text?.length || 0, 'chars');
        if (event.data.text) {
            lastCopiedText = event.data.text;
            console.log('CSE240: Updated lastCopiedText from post-message, length:', lastCopiedText.length);
        }
    }
});

// Poll localStorage as fallback if post-message doesn't work
setInterval(() => {
    const copyData = localStorage.getItem('exam_requirements_copy');
    if (copyData) {
        try {
            const data = JSON.parse(copyData);
            if (data.text) {
                console.log('CSE240: Exam copy detected via localStorage:', data.text.length, 'chars');
                lastCopiedText = data.text;
                console.log('CSE240: Updated lastCopiedText from localStorage, length:', lastCopiedText.length);
            }
            localStorage.removeItem('exam_requirements_copy'); // Clear after read
        } catch (err) {
            console.error('CSE240: Error parsing localStorage exam copy data:', err);
            localStorage.removeItem('exam_requirements_copy'); // Clear bad data
        }
    }
}, 100);

const monitorStatusUrl = (() => {
  const scriptUrl = document.currentScript && document.currentScript.src;
  if (!scriptUrl) return null;
  return new URL('../exam-monitor-status.json', scriptUrl).toString();
})();
const monitorPollIntervalMs = 15000;
const monitorFileStaleMs = 90000;
let monitorStatusSeen = false;
let monitorFetchFailures = 0;
let lastMonitorStatus = null;
let monitorMessage = '';
let monitorPauseDeadlineMs = null;
let monitorShutdownDeadlineMs = null;

function positionMonitorHint() {
  const badge = document.querySelector(".exam-badge");
  const hint = document.querySelector(".exam-monitor-hint");
  if (!badge || !hint || hint.hidden) return;
  const badgeRect = badge.getBoundingClientRect();
  hint.style.left = Math.max(4, Math.round(badgeRect.left)) + "px";
  hint.style.top = Math.round(badgeRect.bottom + 4) + "px";
}

function ensureMonitorHint() {
  let hint = document.querySelector(".exam-monitor-hint");
  if (hint) return hint;
  if (!document.querySelector("#exam-monitor-hint-styles")) {
    const styles = document.createElement("style");
    styles.id = "exam-monitor-hint-styles";
    styles.textContent = ".exam-monitor-hint{position:fixed;z-index:9998;max-width:calc(100vw - 8px);padding:7px 10px;border:1px solid #f2c078;border-radius:5px;background:#fff7e6;color:#7c3e08;box-shadow:0 3px 10px rgba(15,23,42,.24);cursor:pointer;font:700 13px/1.3 sans-serif;text-align:left}.exam-monitor-hint.blocked{border-color:#f0a6a6;background:#fff1f1;color:#8f1d1d}.exam-monitor-hint.pulse{animation:exam-monitor-pulse .8s ease-in-out 3}@keyframes exam-monitor-pulse{50%{box-shadow:0 0 0 5px rgba(217,119,6,.32)}}@media(prefers-reduced-motion:reduce){.exam-monitor-hint.pulse{animation:none}}";
    document.head.appendChild(styles);
  }
  hint = document.createElement("button");
  hint.className = "exam-monitor-hint";
  hint.type = "button";
  hint.hidden = true;
  hint.textContent = "Exam monitoring needs attention  \u25be";
  hint.addEventListener("click", showMonitorModal);
  document.body.appendChild(hint);
  window.addEventListener("resize", positionMonitorHint);
  return hint;
}

function monitorDeadline(status, timestampField, secondsField) {
  const rawSeconds = status && status[secondsField];
  const seconds = rawSeconds === null || rawSeconds === undefined ? NaN : Number(rawSeconds);
  if (Number.isFinite(seconds)) return Date.now() + Math.max(0, seconds) * 1000;
  const parsed = Date.parse(status && status[timestampField]);
  return Number.isFinite(parsed) ? parsed : null;
}

function monitorSecondsRemaining(deadlineMs) {
  if (!Number.isFinite(deadlineMs)) return null;
  return Math.max(0, Math.ceil((deadlineMs - Date.now()) / 1000));
}

function formatMonitorCountdown(seconds) {
  const minutes = Math.floor(seconds / 60);
  const remainder = String(seconds % 60).padStart(2, "0");
  return minutes + ":" + remainder;
}

function updateMonitorCountdown() {
  const state = lastMonitorStatus && lastMonitorStatus.state;
  const pauseSeconds = monitorSecondsRemaining(monitorPauseDeadlineMs);
  const shutdownSeconds = monitorSecondsRemaining(monitorShutdownDeadlineMs);
  const seconds = state === "blocked" ? shutdownSeconds : pauseSeconds;
  const hint = document.querySelector(".exam-monitor-hint");
  if (hint && !hint.hidden) {
    if (state === "blocked") {
      hint.textContent = seconds === null
        ? "Workspace shutdown imminent  \u25be"
        : "Workspace shutdown imminent - " + formatMonitorCountdown(seconds) + "  \u25be";
    } else {
      hint.textContent = seconds === null
        ? "Exam monitoring needs attention  \u25be"
        : seconds === 0
          ? "Tester pause pending - checking status  \u25be"
          : "Exam monitoring needs attention - " + formatMonitorCountdown(seconds) + " remaining  \u25be";
    }
    positionMonitorHint();
  }
  const countdown = document.querySelector(".exam-monitor-modal-countdown");
  if (countdown) {
    countdown.hidden = seconds === null;
    if (seconds !== null) {
      countdown.textContent = seconds > 0
        ? (state === "blocked" ? "Workspace shutdown in approximately " : "Tester pauses in ") + formatMonitorCountdown(seconds) + (state === "warning" && shutdownSeconds !== null ? ". Workspace shutdown in " + formatMonitorCountdown(shutdownSeconds) + "." : "")
        : (state === "blocked" ? "Workspace shutdown may occur at any moment." : "The tester may pause at any moment.");
    }
  }
}

function updateOpenMonitorModal() {
  const overlay = document.querySelector(".exam-monitor-modal-overlay");
  if (!overlay || !lastMonitorStatus) return;
  const state = lastMonitorStatus.state;
  if (state === "blocked") {
    overlay.querySelector(".exam-monitor-modal").style.borderTopColor = "#b91c1c";
    overlay.querySelector(".exam-monitor-modal-title").textContent = "Tester Paused - Reconnect Now";
    overlay.querySelector(".exam-monitor-modal-summary").textContent = "The tester is paused, but your workspace is still running until the shutdown countdown expires.";
    overlay.querySelector(".exam-monitor-modal-detail").textContent = monitorMessage || "Reconnect monitoring now or contact your proctor immediately.";
  }
  updateMonitorCountdown();
}

function closeMonitorModal() {
  const overlay = document.querySelector('.exam-monitor-modal-overlay');
  if (overlay) overlay.remove();
}

function validLauncherUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.toString() : null;
  } catch (error) {
    return null;
  }
}

function showMonitorModal() {
  closeMonitorModal();
  const launcherUrl = validLauncherUrl(lastMonitorStatus && lastMonitorStatus.launcher_url);

  if (!document.querySelector('#exam-monitor-modal-styles')) {
    const styles = document.createElement('style');
    styles.id = 'exam-monitor-modal-styles';
    styles.textContent = `
      .exam-monitor-modal-overlay { position: fixed; inset: 0; z-index: 100000; display: flex;
        align-items: flex-start; justify-content: center; padding: 64px 16px 16px;
        background: rgba(15, 23, 42, 0.58); font-family: sans-serif; pointer-events: auto; }
      .exam-monitor-modal { width: min(460px, 100%); background: #fff; color: #17202a;
        border: 1px solid #cbd5e1; border-top: 5px solid #b45309; border-radius: 6px;
        box-shadow: 0 18px 48px rgba(15, 23, 42, 0.35); }
      .exam-monitor-modal-header { display: flex; align-items: center; justify-content: space-between;
        gap: 12px; padding: 16px 18px 12px; }
      .exam-monitor-modal-title { margin: 0; font-size: 20px; line-height: 1.25; }
      .exam-monitor-modal-close { width: 32px; height: 32px; border: 0; background: transparent;
        color: #475569; cursor: pointer; font-size: 26px; line-height: 1; }
      .exam-monitor-modal-body { padding: 0 18px 18px; font-size: 14px; line-height: 1.5; }
      .exam-monitor-modal-body p { margin: 0 0 12px; }
      .exam-monitor-modal-steps { margin: 0 0 12px; padding-left: 22px; }
      .exam-monitor-modal-steps li { margin: 0 0 7px; }
      .exam-monitor-modal-detail { color: #475569; }
      .exam-monitor-modal-countdown,
      .exam-monitor-modal-warning { margin: 12px 0; padding: 10px 12px; border: 1px solid #f0a6a6;
        border-radius: 5px; background: #fff5f5; color: #8f1d1d; font-weight: 700; }
      .exam-monitor-modal-actions { display: flex; justify-content: flex-end; gap: 8px;
        flex-wrap: wrap; margin-top: 18px; }
      .exam-monitor-modal-button { display: inline-flex; min-height: 38px; align-items: center;
        justify-content: center; padding: 8px 13px; border: 1px solid #94a3b8; border-radius: 5px;
        background: #fff; color: #1e293b; cursor: pointer; font-weight: 700; text-decoration: none; }
      .exam-monitor-modal-button.primary { border-color: #1d4ed8; background: #1d4ed8; color: #fff; }
    `;
    document.head.appendChild(styles);
  }

  const overlay = document.createElement('div');
  overlay.className = 'exam-monitor-modal-overlay';
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) closeMonitorModal();
  });

  const dialog = document.createElement('section');
  dialog.className = 'exam-monitor-modal';
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  dialog.setAttribute('aria-labelledby', 'exam-monitor-modal-title');

  const header = document.createElement('div');
  header.className = 'exam-monitor-modal-header';
  const title = document.createElement('h2');
  title.id = 'exam-monitor-modal-title';
  title.className = 'exam-monitor-modal-title';
  title.textContent = 'Reconnect the exam launcher';
  const closeButton = document.createElement('button');
  closeButton.className = 'exam-monitor-modal-close';
  closeButton.type = 'button';
  closeButton.textContent = '×';
  closeButton.title = 'Close';
  closeButton.setAttribute('aria-label', 'Close');
  closeButton.addEventListener('click', closeMonitorModal);
  header.append(title, closeButton);

  const body = document.createElement('div');
  body.className = 'exam-monitor-modal-body';
  const summary = document.createElement("p");
  summary.className = "exam-monitor-modal-summary";
  summary.textContent = 'The system is not receiving check-ins from your exam launcher. Your code and VS Code session are still available.';
  const countdown = document.createElement("p");
  countdown.className = "exam-monitor-modal-countdown";
  countdown.hidden = true;
  const steps = document.createElement("ol");
  steps.className = 'exam-monitor-modal-steps';
  [
    'Find the browser tab named "Mastery Exam X" (X is your exam number). Its address starts with cse240.com.',
    'On that page, click Reconnect Monitoring. Do not use the browser Refresh command; it may ask you to resubmit the login form.',
    'Leave the launcher tab open, then return to VS Code. The badge should return to blue within 60 seconds.'
  ].forEach((text) => {
    const item = document.createElement('li');
    item.textContent = text;
    steps.appendChild(item);
  });
  const warning = document.createElement("p");
  warning.className = "exam-monitor-modal-warning";
  warning.textContent = "Do not click Start Instance, Restart Problem, or the circular restart arrow at the bottom right of pwn.college. These controls restart the container and may record another attempt. Return to your already-open VS Code workspace.";
  const detail = document.createElement("p");
  detail.className = 'exam-monitor-modal-detail';
  detail.textContent = 'If the tab is missing or does not show Reconnect Monitoring, use the safe launcher link below. If the badge remains amber after 60 seconds, notify your proctor.';

  const actions = document.createElement('div');
  actions.className = 'exam-monitor-modal-actions';
  const dismissButton = document.createElement('button');
  dismissButton.className = 'exam-monitor-modal-button';
  dismissButton.type = 'button';
  dismissButton.textContent = 'Close';
  dismissButton.addEventListener('click', closeMonitorModal);
  actions.appendChild(dismissButton);

  const recheckButton = document.createElement("button");
  recheckButton.className = "exam-monitor-modal-button primary exam-monitor-recheck";
  recheckButton.type = "button";
  recheckButton.textContent = "Recheck Status";
  recheckButton.addEventListener("click", async () => {
    recheckButton.disabled = true;
    recheckButton.textContent = "Checking...";
    await pollExamMonitorStatus();
    const state = lastMonitorStatus && lastMonitorStatus.state;
    if (state !== "warning" && state !== "blocked") {
      recheckButton.textContent = "Status Healthy";
      setTimeout(closeMonitorModal, 500);
      return;
    }
    detail.textContent = (monitorMessage || "Exam monitoring still needs attention.")
      + " Follow the steps above, then recheck. If it remains amber, notify your proctor.";
    recheckButton.textContent = "Recheck Status";
    recheckButton.disabled = false;
  });
  actions.appendChild(recheckButton);

  if (launcherUrl) {
    const launcherButton = document.createElement('a');
    launcherButton.className = "exam-monitor-modal-button exam-monitor-launcher";
    launcherButton.href = launcherUrl;
    launcherButton.target = '_blank';
    launcherButton.rel = 'noreferrer';
    launcherButton.textContent = 'Open Safe Launcher Page';
    launcherButton.addEventListener('click', () => setTimeout(closeMonitorModal, 0));
    actions.appendChild(launcherButton);
  }

  body.append(summary, countdown, steps, warning, detail, actions);
  dialog.append(header, body);
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
  closeButton.focus();
  updateOpenMonitorModal();
}

function applyMonitorStatus(status) {
  const previousState = lastMonitorStatus && lastMonitorStatus.state;
  lastMonitorStatus = Object.assign({}, lastMonitorStatus || {}, status);
  monitorPauseDeadlineMs = monitorDeadline(status, "pause_at", "seconds_until_pause");
  monitorShutdownDeadlineMs = monitorDeadline(status, "shutdown_at", "seconds_until_shutdown");
  const badge = document.querySelector(".exam-badge");
  if (!badge) return;

  const statusButton = badge.querySelector(".exam-monitor-status-btn");
  const hint = ensureMonitorHint();
  const state = status && status.state;
  const needsAttention = state === "warning" || state === "blocked";
  const previouslyNeededAttention = previousState === "warning" || previousState === "blocked";
  if (state === "warning") {
    badge.style.backgroundColor = "rgba(180, 83, 9, 0.95)";
  } else if (state === "blocked") {
    badge.style.backgroundColor = "rgba(185, 28, 28, 0.95)";
  } else {
    badge.style.removeProperty("background-color");
  }

  monitorMessage = lastMonitorStatus && lastMonitorStatus.message ? lastMonitorStatus.message : "";
  if (statusButton) {
    statusButton.hidden = !needsAttention;
    statusButton.title = monitorMessage || "Exam monitoring status";
    statusButton.setAttribute("aria-label", statusButton.title);
  }
  hint.hidden = !needsAttention;
  hint.classList.toggle("blocked", state === "blocked");
  hint.title = monitorMessage || "Open exam monitoring details";
  if (needsAttention) {
    updateMonitorCountdown();
    requestAnimationFrame(positionMonitorHint);
    if (!previouslyNeededAttention || state !== previousState) {
      hint.classList.remove("pulse");
      void hint.offsetWidth;
      hint.classList.add("pulse");
    }
    if (state === "blocked" && previousState !== "blocked") {
      if (document.querySelector(".exam-monitor-modal-overlay")) {
        updateOpenMonitorModal();
      } else {
        showMonitorModal();
      }
    } else {
      updateOpenMonitorModal();
    }
  } else {
    hint.classList.remove("pulse");
    if (previouslyNeededAttention) {
      const overlay = document.querySelector(".exam-monitor-modal-overlay");
      if (overlay) {
        overlay.querySelector(".exam-monitor-modal").style.borderTopColor = "#15803d";
        overlay.querySelector(".exam-monitor-modal-title").textContent = "Monitoring Restored";
        overlay.querySelector(".exam-monitor-modal-summary").textContent = "The exam monitoring connection is active again.";
        overlay.querySelector(".exam-monitor-modal-steps").hidden = true;
        overlay.querySelector(".exam-monitor-modal-warning").hidden = true;
        overlay.querySelector(".exam-monitor-modal-detail").textContent = "You can return to your already-open VS Code workspace.";
        overlay.querySelector(".exam-monitor-modal-actions").hidden = true;
        setTimeout(closeMonitorModal, 1800);
      }
    }
  }
}

async function pollExamMonitorStatus() {
  if (!monitorStatusUrl) return;
  try {
    const requestUrl = new URL(monitorStatusUrl);
    requestUrl.searchParams.set("_", String(Date.now()));
    const response = await fetch(requestUrl.toString(), {
      cache: 'no-store',
      credentials: 'same-origin'
    });
    if (response.status === 404 && !monitorStatusSeen) return;
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const status = await response.json();
    monitorStatusSeen = true;
    monitorFetchFailures = 0;
    const updatedAt = Date.parse(status.updated_at);
    if (!Number.isFinite(updatedAt) || Date.now() - updatedAt > monitorFileStaleMs) {
      applyMonitorStatus(Object.assign({}, status, {
        state: 'warning',
        message: 'The local exam monitor status has stopped updating. Contact course staff.'
      }));
      return;
    }
    applyMonitorStatus(status);
  } catch (error) {
    if (!monitorStatusSeen) return;
    monitorFetchFailures += 1;
    if (monitorFetchFailures >= 3) {
      applyMonitorStatus({
        state: 'warning',
        message: 'The local exam monitor status cannot be read. Contact course staff.'
      });
    }
  }
}

function insertBadge() {
  if (document.querySelector(".exam-badge")) return;
  if (!document.body) return setTimeout(insertBadge, 100);

  // Create and insert the badge
  const badge = document.createElement("div");
  badge.className = "exam-badge";
  
  // Create badge text
  const badgeText = document.createElement("span");
  badgeText.textContent = "LEVEL_ID";
  badge.appendChild(badgeText);

  const monitorStatusBtn = document.createElement("button");
  monitorStatusBtn.className = "exam-reload-btn exam-monitor-status-btn";
  monitorStatusBtn.textContent = "!";
  monitorStatusBtn.hidden = true;
  monitorStatusBtn.addEventListener("click", function(e) {
    e.preventDefault();
    e.stopPropagation();
    showMonitorModal();
  });
  badge.appendChild(monitorStatusBtn);
  
  // Create reload button
  const reloadBtn = document.createElement("button");
  reloadBtn.className = "exam-reload-btn";
  reloadBtn.textContent = "↻";
  reloadBtn.title = "Reload current frame - Does not restart container";
  
  // Add click handler for reload functionality
  reloadBtn.addEventListener("click", function(e) {
    e.preventDefault();
    e.stopPropagation();
    
    // Check if we're in an iframe
    if (window.self !== window.top) {
      // We're in an iframe, reload just this frame
      window.location.reload();
    } else {
      // We're in the top window, reload the page
      window.location.reload();
    }
  });
  
  badge.appendChild(reloadBtn);
  
  // Create paste button
  const pasteBtn = document.createElement("button");
  pasteBtn.className = "exam-reload-btn";
  pasteBtn.textContent = "📋";
  pasteBtn.title = "Ctrl+Shift+L to paste to terminal";
  
  // Add click handler for paste functionality
  pasteBtn.addEventListener("click", function(e) {
    e.preventDefault();
    e.stopPropagation();
    
    console.log('CSE240: Paste button clicked, inserting stored text, length:', lastCopiedText.length);
    
    if (!lastCopiedText) {
      console.log('CSE240: No text stored to paste');
      return;
    }
    
    // Find the xterm terminal textarea (button click loses focus, so can't use activeElement)
    const xtermTextarea = document.querySelector('.xterm-helper-textarea');
    
    if (xtermTextarea) {
      console.log('CSE240: Found xterm terminal textarea, inserting text via input event');
      
      // Focus it first
      xtermTextarea.focus();
      
      // Set the textarea value
      xtermTextarea.value = lastCopiedText;
      
      // Dispatch a single input event with all the text
      const inputEvt = new InputEvent('input', {
        data: lastCopiedText,
        inputType: 'insertText',
        bubbles: true,
        cancelable: false
      });
      
      xtermTextarea.dispatchEvent(inputEvt);
      
      // Clear the textarea value after xterm processes it
      setTimeout(() => { xtermTextarea.value = ''; }, 0);
      
      console.log('CSE240: Dispatched input event for xterm');
      return;
    }
    
    // Fallback to activeElement for other cases
    const target = document.activeElement;
    console.log('CSE240: Using activeElement:', target.tagName);
    
    // Handle contenteditable elements
    if (target && target.contentEditable === 'true') {
      const selection = window.getSelection();
      if (selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        range.deleteContents();
        const textNode = document.createTextNode(lastCopiedText);
        range.insertNode(textNode);
        range.setStartAfter(textNode);
        range.setEndAfter(textNode);
        selection.removeAllRanges();
        selection.addRange(range);
      }
      return;
    }
    
    // Handle regular input/textarea
    if (target && (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT')) {
      const start = target.selectionStart;
      const end = target.selectionEnd;
      const value = target.value;
      target.value = value.substring(0, start) + lastCopiedText + value.substring(end);
      const newPos = start + lastCopiedText.length;
      target.selectionStart = target.selectionEnd = newPos;
      target.dispatchEvent(new Event('input', { bubbles: true }));
    }
  });
  
  badge.appendChild(pasteBtn);
  document.body.appendChild(badge);
  ensureMonitorHint();
  if (lastMonitorStatus) applyMonitorStatus(lastMonitorStatus);
}

insertBadge();
pollExamMonitorStatus();
setInterval(pollExamMonitorStatus, monitorPollIntervalMs);
setInterval(updateMonitorCountdown, 1000);

// Capture copy events to store the copied text
document.addEventListener('copy', function(e) {
  try {
    // First try to get data from clipboard event itself
    let copiedText = '';
    
    if (e.clipboardData && e.clipboardData.getData) {
      copiedText = e.clipboardData.getData('text/plain');
      console.log('CSE240: Got text from clipboardData:', copiedText.length, 'chars');
    }
    
    // Fallback to selection
    if (!copiedText) {
      copiedText = window.getSelection().toString();
      console.log('CSE240: Got text from selection:', copiedText.length, 'chars');
    }
    
    if (copiedText) {
      lastCopiedText = copiedText;
      console.log('CSE240: Captured copy event, stored text length:', lastCopiedText.length);
    }
  } catch (err) {
    console.error('CSE240: Error capturing copy:', err);
  }
}, true);

// Also try to capture from clipboard API
document.addEventListener('cut', function(e) {
  try {
    const selection = window.getSelection().toString();
    if (selection) {
      lastCopiedText = selection;
      console.log('CSE240: Captured cut event, stored text length:', lastCopiedText.length);
    }
  } catch (err) {
    console.error('CSE240: Error capturing cut:', err);
  }
}, true);

// Global keyboard listener to translate Ctrl+Shift+L to paste stored text
document.addEventListener('keydown', function(e) {
  // Log all Ctrl+Shift combinations for debugging
  if (e.ctrlKey && e.shiftKey) {
    console.log('CSE240: Ctrl+Shift+' + e.key + ' detected');
  }
  
  // Check for Ctrl+Shift+C to capture selection
  if (e.ctrlKey && e.shiftKey && (e.key === 'C' || e.key === 'c')) {
    console.log('CSE240: Ctrl+Shift+C detected, capturing selection');
    
    try {
      // Try standard selection first
      let selection = window.getSelection().toString();
      console.log('CSE240: window.getSelection() returned:', selection.length, 'chars');
      
      // If no selection via standard API, try to get xterm selection
      if (!selection) {
        // Look for xterm instance - it's often stored on the terminal element
        const xtermScreen = document.querySelector('.xterm-screen');
        if (xtermScreen && xtermScreen.parentElement) {
          // Try to access xterm instance via various possible locations
          const terminalElement = xtermScreen.parentElement;
          
          // xterm.js often stores instance as _terminal or terminal property
          const xterm = terminalElement._terminal || terminalElement.terminal;
          
          if (xterm && xterm.getSelection) {
            selection = xterm.getSelection();
            console.log('CSE240: xterm.getSelection() returned:', selection.length, 'chars');
          } else if (xterm && xterm.buffer && xterm.buffer.active) {
            console.log('CSE240: Found xterm instance but no getSelection method');
          }
        }
      }
      
      if (selection) {
        lastCopiedText = selection;
        console.log('CSE240: Captured selection via Ctrl+Shift+C, stored text length:', lastCopiedText.length);
      } else {
        console.log('CSE240: No selection to capture via any method');
      }
    } catch (err) {
      console.error('CSE240: Error capturing selection:', err);
    }
    
    // Don't prevent default - let the normal copy happen too
  }
  
  // Check for Ctrl+Shift+L
  if (e.ctrlKey && e.shiftKey && (e.key === 'L' || e.key === 'l')) {
    e.preventDefault();
    e.stopPropagation();
    
    console.log('CSE240: Inserting stored text at cursor, length:', lastCopiedText.length);
    
    // Get the currently focused element
    const target = document.activeElement;
    
    console.log('CSE240: Active element:', target.tagName, 'classes:', target.className, 'contentEditable:', target.contentEditable);
    
    if (!lastCopiedText) {
      console.log('CSE240: No text stored to paste');
      return;
    }
    
    // Handle xterm terminal (xterm-helper-textarea)
    if (target && target.className && target.className.includes('xterm-helper-textarea')) {
      console.log('CSE240: Detected xterm terminal, inserting text via input event');
      
      // Set the textarea value
      target.value = lastCopiedText;
      
      // Dispatch a single input event with all the text
      const inputEvt = new InputEvent('input', {
        data: lastCopiedText,
        inputType: 'insertText',
        bubbles: true,
        cancelable: false
      });
      
      target.dispatchEvent(inputEvt);
      
      // Clear the textarea value after xterm processes it
      setTimeout(() => { target.value = ''; }, 0);
      
      console.log('CSE240: Dispatched input event for xterm');
      return;
    }
    
    // Handle contenteditable elements (like VS Code terminal)
    if (target && target.contentEditable === 'true') {
      console.log('CSE240: Inserting into contenteditable element');
      
      // Try to insert at current selection/cursor
      const selection = window.getSelection();
      if (selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        range.deleteContents();
        const textNode = document.createTextNode(lastCopiedText);
        range.insertNode(textNode);
        
        // Move cursor to end of inserted text
        range.setStartAfter(textNode);
        range.setEndAfter(textNode);
        selection.removeAllRanges();
        selection.addRange(range);
        
        console.log('CSE240: Text inserted into contenteditable');
      }
      return;
    }
    
    // If it's a text input or textarea, insert at cursor position
    if (target && (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT')) {
      const start = target.selectionStart;
      const end = target.selectionEnd;
      const value = target.value;
      
      // Insert the text at cursor position
      target.value = value.substring(0, start) + lastCopiedText + value.substring(end);
      
      // Move cursor to end of inserted text
      const newPos = start + lastCopiedText.length;
      target.selectionStart = target.selectionEnd = newPos;
      
      // Trigger input event so any listeners are notified
      target.dispatchEvent(new Event('input', { bubbles: true }));
      
      console.log('CSE240: Text inserted successfully into input/textarea');
    } else {
      console.log('CSE240: Active element is not a text input or contenteditable');
    }
  }
}, true); // Use capture phase to catch it early

// const observer = new MutationObserver(() => insertBadge());
// observer.observe(document.documentElement, { childList: true, subtree: true });

})();

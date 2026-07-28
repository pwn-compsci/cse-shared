
(function showExamBadge() {
    console.log("CSE240: in showExamBadge");
    
// Store for copied text
let lastCopiedText = '';

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
}

insertBadge();

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

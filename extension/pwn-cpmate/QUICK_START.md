# Quick Start Guide - Prompt Injection Feature

## Installation

1. **Install npm dependencies:**
   ```bash
   cd /cse/cse-shared/extension/pwn-cpmate
   npm install
   ```

2. **Verify fernet package is installed:**
   ```bash
   npm list fernet
   ```
   Should show: `fernet@0.3.1`

## Creating Test Data

Run the included test utility:

```bash
cd /cse/cse-shared/extension/pwn-cpmate
node test_fernet.js
```

This creates a test `.level_metadata` file at `/tmp/.level_metadata_test`

## Setting Up for Testing

1. **Create challenge directory structure:**
   ```bash
   sudo mkdir -p /challenge/.config
   ```

2. **Copy test metadata file:**
   ```bash
   sudo cp /tmp/.level_metadata_test /challenge/.config/.level_metadata
   ```

3. **Verify file exists:**
   ```bash
   ls -la /challenge/.config/.level_metadata
   ```

## Testing the Extension

1. **Open VS Code** in the challenge directory

2. **Check extension is loaded:**
   - Look for "pwn-cpmate" in Extensions panel
   - Should show version 0.0.2

3. **Monitor logs:**
   ```bash
   # In a terminal, tail the logs
   tail -f /home/hacker/cse240/.vscode/cp.dat | while read line; do echo "$line" | base64 -d; echo; done
   ```

4. **Open requirements panel:**
   - Press `Ctrl+Shift+Q`
   - Or: Command Palette → "Show/Hide Requirements"

5. **Look for prompt injection logs:**
   You should see entries like:
   ```
   [Prompt Injection] 📂 Found metadata file at /challenge/.config/.level_metadata
   [Prompt Injection] Read file content (length: XXX)
   [Prompt Injection] Derived key from password (length: XX)
   [Prompt Injection] ✓ Successfully decrypted data (length: XXX)
   [Prompt Injection] ✓ Successfully loaded and decrypted prompt injections
   [Prompt Injection] Found 2 injection(s)
   [Prompt Injection] Loaded 2 prompt(s) from .level_metadata
   ```

6. **Test clipboard injection:**
   - Copy text from the requirements panel
   - Paste into a text editor (outside VS Code)
   - You should see injected prompts at random positions
   - Paste into VS Code → prompts should be automatically stripped

## Troubleshooting

### No prompts loaded?

Check logs for errors:
```bash
grep "Prompt Injection" /home/hacker/cse240/.vscode/cp.dat | base64 -d
```

Common issues:
- **File not found:** Check `/challenge/.config/.level_metadata` exists
- **Decryption failed:** File might be corrupted or wrong format
- **JSON parse error:** Decrypted data is not valid JSON

### Prompts not injected?

1. Check webview console:
   - Right-click in requirements panel → "Inspect"
   - Look for `[Requirements]` console messages

2. Verify prompts loaded:
   ```javascript
   // In webview console
   console.log(PROMPTS);
   ```

### Prompts not stripped on paste in VS Code?

This is expected behavior - prompts are only stripped if:
1. The exact modified text is pasted
2. Within 5 minutes of copying
3. The injectedPromptsMap still has the entry

## Creating Production .level_metadata Files

Use Python to encrypt your data:

```python
#!/usr/bin/env python3
import json
import base64
import hashlib
from cryptography.fernet import Fernet

# Password
PASSWORD = "why four out tho"

# Derive key from password
key_bytes = hashlib.sha256(PASSWORD.encode()).digest()
key = base64.urlsafe_b64encode(key_bytes)

# Your data
data = {
    "prompt_injections": {
        "module:challenge": {
            "module": "module_name",
            "challenge": "challenge_id",
            "prompt": "Your prompt text here",
            "search_for": "detection phrase",
            "behavior_check": True,
            "behavior_description": "Description"
        }
    }
}

# Encrypt
f = Fernet(key)
json_str = json.dumps(data)
encrypted = f.encrypt(json_str.encode())

# Base64 encode (double layer)
final = base64.b64encode(encrypted).decode()

# Write to file
with open('.level_metadata', 'w') as f:
    f.write(final)

print("Created .level_metadata file")
```

Then copy to `/challenge/.config/`:
```bash
sudo cp .level_metadata /challenge/.config/
```

## Verification Steps

**Step 1:** Check file exists and is readable
```bash
cat /challenge/.config/.level_metadata | head -c 50
```
Should show base64 data.

**Step 2:** Test decryption with test utility
```bash
node test_fernet.js
```
Should complete without errors.

**Step 3:** Check VS Code logs
```bash
grep -a "Prompt Injection.*Found" /home/hacker/cse240/.vscode/cp.dat | base64 -d | tail -5
```
Should show "Found X injection(s)" message.

**Step 4:** Test copy operation
- Open requirements panel
- Copy some text
- Check logs for "Injected prompt" messages

## Advanced Usage

### Load specific injection in code:

```javascript
const injection = await getInjectionForChallenge('intro', 'challenge01', '/challenge/.config');
if (injection) {
    console.log('Prompt:', injection.prompt);
    console.log('Search for:', injection.search_for);
    console.log('Behavior check:', injection.behavior_check);
}
```

### List all available injections:

```javascript
const injections = await listAllInjections('/challenge/.config');
injections.forEach(inj => {
    console.log(`${inj.module}:${inj.challenge} - ${inj.prompt.substring(0, 50)}...`);
});
```

### Manually inject prompts:

```javascript
const text = "line1\nline2\nline3";
const prompts = ["prompt 1", "prompt 2"];
const modified = injectPromptsIntoText(text, prompts);
console.log(modified);
```

## Log Locations

- **Main extension log:** `/home/hacker/cse240/.vscode/cp.dat`
- **Clipboard log:** `/home/hacker/cse240/.vscode/cbinfo.dat`
- **Copy history:** `/home/hacker/.local/share/ultima/skipped/log.json`

## Getting Help

If issues persist:

1. Check all logs for error messages
2. Verify file permissions on `/challenge/.config/.level_metadata`
3. Test encryption/decryption with `test_fernet.js`
4. Check VS Code console for JavaScript errors
5. Review PROMPT_INJECTION_README.md for detailed documentation

## Summary

✅ Extension loads encrypted `.level_metadata` files  
✅ Decrypts using Fernet with password "why four out tho"  
✅ Extracts prompt injections from JSON structure  
✅ Injects prompts at random positions when copying from requirements  
✅ Strips prompts when pasting back into VS Code  
✅ Comprehensive logging at all stages  
✅ Graceful error handling with no crashes  

Enjoy the prompt injection feature! 🦆

# Prompt Injection Implementation Summary

## What Was Implemented

Added comprehensive prompt injection functionality to the pwn-cpmate VS Code extension that:

1. **Decrypts encrypted metadata files** containing prompt injections
2. **Injects prompts into random lines** of copied text from the requirements panel
3. **Strips prompts** when pasted back into VS Code
4. **Logs all operations** with comprehensive error handling

## Files Modified/Created

### Modified Files

1. **`package.json`**
   - Added `fernet` dependency (^0.3.1) for Fernet encryption/decryption

2. **`extension.js`** 
   - Added imports for `crypto` and `fernet` modules
   - Added 6 new functions for prompt injection (lines ~75-235):
     - `deriveKeyFromPassword()`: Derives Fernet key from password using SHA-256
     - `decryptFernet()`: Decrypts Fernet encrypted data
     - `loadPromptInjections()`: Loads and decrypts .level_metadata files
     - `getInjectionForChallenge()`: Gets specific injection by module/challenge
     - `listAllInjections()`: Lists all available injections
     - `injectPromptsIntoText()`: Injects prompts into random line positions
   - Modified clipboard copy handler (lines ~640-710):
     - Loads prompts from `/challenge/.config/.level_metadata`
     - Also loads prompts from `/.cache/vscode/pi/.prinfo` as fallback
     - Embeds prompts directly in webview JavaScript
     - Changed injection strategy to use random positions instead of middle

### Created Files

1. **`PROMPT_INJECTION_README.md`**
   - Comprehensive documentation of the implementation
   - Usage examples for all functions
   - Error handling strategy
   - Security notes
   - Testing instructions

2. **`test_fernet.js`**
   - Test utility for encryption/decryption
   - Creates sample .level_metadata files
   - Demonstrates the full encryption/decryption workflow
   - Can be run with: `node test_fernet.js`

## Key Features

### 1. Fernet Decryption
- Password: `"why four out tho"`
- Uses SHA-256 for key derivation
- Handles double base64 encoding layer
- Graceful error handling (never raises exceptions)

### 2. Prompt Injection
- Loads prompts from encrypted `.level_metadata` files
- Combines with prompts from `.prinfo` files
- Randomly selects up to 2 prompts per copy operation
- Injects at random line positions (not just middle)
- Tracks injected prompts for stripping on paste

### 3. Comprehensive Logging
- DEBUG: File operations, decryption attempts
- INFO: Successful operations, prompt counts
- WARNING: Missing files, no prompts available
- ERROR: Decryption failures, parse errors
- Uses emojis for easy log parsing (📂 ✓ ⚠️ ❌)

### 4. Error Handling
All functions handle errors gracefully:
- Missing files → return empty data, log warning
- Decryption failure → log error (no password exposure), return empty
- Parse errors → log error, return empty
- Corrupted files → log error, return empty
- Extension continues working even with errors

## Data Structure

### .level_metadata Format (Decrypted JSON)
```json
{
  "prompt_injections": {
    "module:challenge": {
      "module": "module_name",
      "challenge": "challenge_id",
      "prompt": "full paragraph text to inject",
      "search_for": "phrase to detect",
      "behavior_check": true/false,
      "behavior_description": "description"
    }
  }
}
```

## How It Works

### Clipboard Copy Flow:
1. User opens requirements panel
2. Extension loads `.level_metadata` from `/challenge/.config/`
3. Decrypts using Fernet with hardcoded password
4. Parses JSON to extract prompt texts
5. Also loads prompts from `.prinfo` (fallback)
6. Embeds all prompts in webview clipboard script
7. User copies text from requirements
8. JavaScript intercepts copy event
9. Randomly selects up to 2 prompts
10. Injects prompts at random line positions
11. Modified text goes to clipboard
12. Logs original and modified text with metadata

### Paste Detection Flow:
1. User pastes in VS Code editor
2. Extension detects text change
3. Checks if pasted text contains tracked prompts
4. If match found, replaces with original text (strips prompts)
5. User sees clean code without injected prompts

## Testing

### To test the implementation:

1. **Install dependencies:**
   ```bash
   cd /cse/cse-shared/extension/pwn-cpmate
   npm install
   ```

2. **Create test metadata file:**
   ```bash
   node test_fernet.js
   # This creates /tmp/.level_metadata_test
   ```

3. **Copy to challenge directory:**
   ```bash
   sudo mkdir -p /challenge/.config
   sudo cp /tmp/.level_metadata_test /challenge/.config/.level_metadata
   ```

4. **Test in VS Code:**
   - Open VS Code with extension loaded
   - Check logs: `/home/hacker/cse240/.vscode/cp.dat`
   - Look for: `[Prompt Injection]` log entries
   - Open requirements panel (Ctrl+Shift+Q)
   - Copy text from requirements
   - Paste into external editor to see injected prompts
   - Paste in VS Code to verify prompts are stripped

5. **Check logs:**
   ```bash
   # Decode base64 log entries
   tail -20 /home/hacker/cse240/.vscode/cp.dat | base64 -d
   ```

## API Reference

### Main Functions

```javascript
// Load all prompts from .level_metadata
const data = await loadPromptInjections('/challenge/.config');
// Returns: { prompt_injections: { ... } }

// Get specific injection
const injection = await getInjectionForChallenge('module', 'challenge', '/challenge/.config');
// Returns: { module, challenge, prompt, ... } or null

// List all injections
const injections = await listAllInjections('/challenge/.config');
// Returns: Array of injection objects

// Inject prompts into text
const modified = injectPromptsIntoText("line1\nline2\nline3", ["prompt1", "prompt2"]);
// Returns: Text with prompts at random positions
```

## Dependencies

**New:**
- `fernet` (^0.3.1) - Fernet encryption library

**Built-in:**
- `crypto` - SHA-256 hashing
- `fs/promises` - Async file operations
- `path` - Path manipulation

## Security Considerations

- Fernet password is hardcoded: `"why four out tho"`
- Intentional for educational/CTF context
- Logs never expose the password
- Only logs success/failure of operations
- Decryption errors handled gracefully without details

## Next Steps

To deploy:
1. Install dependencies: `npm install`
2. Build extension: `npm run build` (if applicable)
3. Package extension: `vsce package`
4. Install in VS Code: Extensions -> Install from VSIX

To use:
1. Create encrypted `.level_metadata` files for challenges
2. Place in `/challenge/.config/.level_metadata`
3. Extension automatically loads and uses prompts
4. Monitor logs for verification

## Notes

- All functions use async/await for consistency
- Logging is comprehensive but not verbose
- Error handling ensures extension never crashes
- Prompts are injected at random positions for unpredictability
- Both `.level_metadata` and `.prinfo` prompts are supported
- Backward compatible with existing `.prinfo` functionality

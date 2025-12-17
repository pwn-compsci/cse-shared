# Prompt Injection Feature - Implementation Documentation

## Overview

This extension now includes functionality to extract and inject prompts from encrypted `.level_metadata` files into copied text. The prompts are decrypted using Fernet encryption and automatically injected into random lines when users copy text from the requirements viewer.

## Implementation Details

### 1. Encryption/Decryption

**File Location:** `/challenge/.config/.level_metadata`

**Encryption Method:** Fernet (symmetric encryption)
- Password: `"why four out tho"`
- Key Derivation: SHA-256 hash of password, then base64-urlsafe encoded
- Data Format: Base64-encoded encrypted data (double base64 layer)

**Decrypted JSON Structure:**
```json
{
  "prompt_injections": {
    "module:challenge": {
      "module": "module_name",
      "challenge": "challenge_id",
      "prompt": "full paragraph text to inject",
      "search_for": "phrase to detect",
      "behavior_check": true/false,
      "behavior_description": "description of behavior pattern"
    }
  }
}
```

### 2. Key Functions

#### `deriveKeyFromPassword(password)`
Derives a Fernet key from the password using SHA-256 hash and base64-urlsafe encoding.

**Parameters:**
- `password` (string): The password to derive key from

**Returns:** Base64-urlsafe encoded key string

**Example:**
```javascript
const key = deriveKeyFromPassword("why four out tho");
```

#### `decryptFernet(encryptedBase64, key)`
Decrypts base64-encoded Fernet encrypted data.

**Parameters:**
- `encryptedBase64` (string): Base64-encoded encrypted data
- `key` (string): Fernet key (base64-urlsafe encoded)

**Returns:** Decrypted plaintext string

#### `loadPromptInjections(configDir)`
Loads and decrypts prompt injections from `.level_metadata` file.

**Parameters:**
- `configDir` (string): Path to .config directory (e.g., `/challenge/.config`)

**Returns:** Promise<Object> - Decrypted prompt injections object or empty object on error

**Example:**
```javascript
const data = await loadPromptInjections('/challenge/.config');
```

#### `getInjectionForChallenge(module, challenge, configDir)`
Retrieves a specific prompt injection for a module and challenge.

**Parameters:**
- `module` (string): Module name
- `challenge` (string): Challenge ID
- `configDir` (string): Path to .config directory

**Returns:** Promise<Object|null> - Injection object or null if not found

**Example:**
```javascript
const injection = await getInjectionForChallenge('intro', 'challenge01', '/challenge/.config');
if (injection) {
    console.log(injection.prompt);
}
```

#### `listAllInjections(configDir)`
Gets all available prompt injections from a config directory.

**Parameters:**
- `configDir` (string): Path to .config directory

**Returns:** Promise<Array> - Array of injection objects

**Example:**
```javascript
const injections = await listAllInjections('/challenge/.config');
console.log(`Found ${injections.length} injections`);
```

#### `injectPromptsIntoText(text, prompts)`
Injects prompts into random lines of text.

**Parameters:**
- `text` (string): Original text
- `prompts` (Array<string>): Array of prompt strings to inject

**Returns:** String with injected prompts

**Example:**
```javascript
const original = "line1\nline2\nline3";
const prompts = ["prompt1", "prompt2"];
const modified = injectPromptsIntoText(original, prompts);
// Result: prompts inserted at random positions
```

### 3. Integration with Clipboard Copy

The extension integrates prompt injection into the clipboard copy workflow:

1. **On Requirements Panel Load:**
   - Extension loads prompts from `/challenge/.config/.level_metadata`
   - Also loads prompts from `/.cache/vscode/pi/.prinfo` (fallback)
   - Combines all prompts and embeds them in the webview clipboard script

2. **On User Copy:**
   - Webview intercepts copy event
   - Randomly selects up to 2 prompts (if more than 2 available)
   - Injects prompts at random line positions in the copied text
   - Sends both original and modified text to extension for logging

3. **On Paste in VS Code:**
   - Extension detects paste operations
   - If pasted text contains injected prompts, strips them out
   - User sees original text without prompts

### 4. Logging

Comprehensive logging is included at multiple levels:

**DEBUG Level:**
- File read operations
- Decryption attempts
- Key derivation details

**INFO Level:**
- Successful file loads
- Successful decryptions
- Number of prompts loaded
- Prompt injection operations

**WARNING Level:**
- File not found
- JSON parsing issues
- No prompts available

**ERROR Level:**
- Decryption failures
- Unexpected errors

**Log Examples:**
```
[Prompt Injection] 📂 Found metadata file at /challenge/.config/.level_metadata
[Prompt Injection] ✓ Successfully loaded and decrypted prompt injections
[Prompt Injection] Found 5 injection(s)
[Prompt Injection] Loaded 5 prompt(s) from .level_metadata
[Prompt Injection] Total prompts available: 7
[Prompt Injection] Injected prompt 1 at line 3
[Prompt Injection] Injected prompt 2 at line 8
```

### 5. Error Handling

The implementation follows a graceful degradation strategy:

- **File Not Found:** Returns empty dict/array, logs warning, continues without prompts
- **Decryption Failure:** Logs error (without exposing password), returns empty data
- **JSON Parse Error:** Logs parse error, returns empty data
- **Corrupted Files:** Caught and logged, returns empty data
- **No Exceptions Raised:** All errors are caught, logged, and handled internally

This ensures the extension continues to work even if:
- `.level_metadata` file doesn't exist
- File is corrupted
- Decryption fails
- JSON is malformed

### 6. Dependencies

**New Package Added:**
- `fernet` (^0.3.1): Fernet encryption/decryption library

**Built-in Node.js Modules Used:**
- `crypto`: SHA-256 hashing for key derivation
- `fs/promises`: File operations
- `path`: Path manipulation

## Usage

The prompt injection feature works automatically when the requirements panel is open:

1. User opens requirements panel (automatically or via Ctrl+Shift+Q)
2. Extension loads and decrypts prompts from `.level_metadata`
3. User selects and copies text from requirements
4. Extension injects prompts at random positions
5. Clipboard contains modified text with prompts
6. If pasted in VS Code, prompts are automatically stripped

## Security Notes

- The Fernet password is hardcoded in the extension
- Password is: `"why four out tho"`
- This is intentional for the educational/CTF context
- Logs do NOT expose the password in error messages
- Only logs success/failure of decryption operations

## Testing

To test the implementation:

1. Create a test `.level_metadata` file:
   - Encrypt sample JSON with Fernet using password "why four out tho"
   - Base64 encode the encrypted data
   - Place at `/challenge/.config/.level_metadata`

2. Open VS Code with extension loaded

3. Check logs at `/home/hacker/cse240/.vscode/cp.dat` for:
   - Successful file load messages
   - Decryption success
   - Number of prompts loaded

4. Copy text from requirements panel and paste elsewhere to see injected prompts

## File Structure

```
extension/pwn-cpmate/
├── extension.js          # Main extension file with prompt injection code
├── package.json          # Updated with 'fernet' dependency
└── PROMPT_INJECTION_README.md  # This file
```

## Code Sections

### In extension.js:

**Lines ~75-235:** Prompt injection decryption and utility functions
- `deriveKeyFromPassword()`
- `decryptFernet()`
- `loadPromptInjections()`
- `getInjectionForChallenge()`
- `listAllInjections()`
- `injectPromptsIntoText()`

**Lines ~640-710:** Integration with requirements panel
- Load prompts from `.level_metadata` and `.prinfo`
- Embed prompts in webview clipboard script
- Modified clipboard copy handler to inject at random positions

## Future Enhancements

Possible improvements:
- Cache decrypted prompts to avoid re-decryption
- Support for multiple `.level_metadata` files
- Configuration options for injection behavior
- More sophisticated injection strategies (e.g., based on code structure)
- Telemetry for prompt injection effectiveness

# Keystroke Logging Format

## Overview

The `key.json` file contains a JSON array of session entries. Each session is defined by:
- Same file path (fullPath)
- Same module
- Same challenge

When you type in the same file during the same module/challenge session, keystroke **chunks** are added to the existing entry rather than creating a new entry.

## Chunk Strategy

To balance detail with system overhead:
- Keystrokes are buffered and flushed every **5 seconds of inactivity** OR when **100 characters** are accumulated
- Each flush creates a **chunk** containing the concatenated keystrokes as a string
- Chunks include start/end positions to track cursor movement
- This provides enough information to reconstruct what was typed vs. pasted, without per-keystroke overhead

## Entry Structure

Each entry in the array contains:

| Field | Type | Description |
|-------|------|-------------|
| `startTime` | string (ISO 8601) | When the first chunk in this session was created |
| `lastUpdate` | string (ISO 8601) | When the most recent chunk was added |
| `file` | string | Filename only |
| `fullPath` | string | Complete path to the file |
| `module` | string/null | Module identifier |
| `challenge` | string/null | Challenge identifier |
| `module_name` | string/null | Human-readable module name |
| `challenge_name` | string/null | Human-readable challenge name |
| `hw` | string/null | Homework identifier |
| `hwid` | string/null | Homework ID |
| `labid` | string/null | Lab identifier |
| `languageId` | string | File type (python, javascript, etc.) |
| `chunks` | array | Array of keystroke chunk objects (see below) |
| `chunkCount` | number | Total chunks in this session |
| `totalChars` | number | Total characters across all chunks |

### Chunk Object Structure

Each chunk in the `chunks` array contains:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string (ISO 8601) | When this chunk was flushed |
| `text` | string | Concatenated keystrokes (↵ for enter, ⌫ for backspace) |
| `keystrokes` | array | Individual keystrokes with timestamps (see below) |
| `charCount` | number | Number of characters in this chunk |
| `startPosition` | object | Where typing started (line, character) - 1-indexed |
| `endPosition` | object | Where typing ended (line, character) - 1-indexed |
| `timing` | object/null | Timing statistics (see below) |
| `movements` | array (optional) | Cursor movements during this chunk (see below) |

### Individual Keystroke Structure (within chunk)

Each item in the `keystrokes` array:

| Field | Type | Description |
|-------|------|-------------|
| `key` | string | The character typed (or ↵ for enter, ⌫ for backspace) |
| `ts` | string (ISO 8601) | When this specific key was pressed |
| `line` | number | Line number where typed (1-indexed) |
| `char` | number | Character position where typed (1-indexed) |

### Timing Statistics Structure

The `timing` object (null if only one keystroke):

| Field | Type | Description |
|-------|------|-------------|
| `avgMs` | number | Average milliseconds between consecutive keystrokes |
| `minMs` | number | Minimum delay between keystrokes |
| `maxMs` | number | Maximum delay between keystrokes |
| `stdDevMs` | number | Standard deviation of delays (consistency measure) |

### Cursor Movement Structure

Each item in the optional `movements` array:

| Field | Type | Description |
|-------|------|-------------|
| `ts` | string (ISO 8601) | When the cursor moved |
| `from` | object | Starting position (line, char) - 1-indexed |
| `to` | object | Ending position (line, char) - 1-indexed |

## Format Benefits

✓ **Low overhead** - Chunks group keystrokes, batch processing every 5s or 100 chars  
✓ **Timing analysis** - Per-keystroke timestamps enable pattern detection  
✓ **Statistics included** - Avg/min/max/stdDev calculated at capture time  
✓ **Navigation tracking** - Cursor movements captured separately  
✓ **Python compatible** - Parseable with `json.load()`  
✓ **Copying detection** - Can identify:
  - Uniform typing patterns (low stdDev, consistent timing)
  - Top-down linear progression (no cursor jumps)
  - Lack of corrections (few backspaces)
  - No navigation (empty movements array)  

## Sample JSON

```json
[
  {
    "startTime": "2026-02-06T10:15:23.456Z",
    "lastUpdate": "2026-02-06T10:17:45.789Z",
    "file": "solution.py",
    "fullPath": "/home/hacker/cse240/module-1/challenge-1/solution.py",
    "module": "module-1",
    "challenge": "challenge-1",
    "module_name": "Introduction to Python",
    "challenge_name": "Hello World",
    "hw": "hw1",
    "hwid": "hw1",
    "labid": null,
    "languageId": "python",
    "chunks": [
      {
        "timestamp": "2026-02-06T10:15:28.123Z",
        "text": "def main():↵    print(\"Hello⌫⌫",
        "keystrokes": [
          { "key": "d", "ts": "2026-02-06T10:15:23.456Z", "line": 1, "char": 1 },
          { "key": "e", "ts": "2026-02-06T10:15:23.612Z", "line": 1, "char": 2 },
          { "key": "f", "ts": "2026-02-06T10:15:23.798Z", "line": 1, "char": 3 },
          { "key": " ", "ts": "2026-02-06T10:15:23.945Z", "line": 1, "char": 4 },
          { "key": "m", "ts": "2026-02-06T10:15:24.123Z", "line": 1, "char": 5 },
          { "key": "a", "ts": "2026-02-06T10:15:24.289Z", "line": 1, "char": 6 },
          { "key": "i", "ts": "2026-02-06T10:15:24.445Z", "line": 1, "char": 7 },
          { "key": "n", "ts": "2026-02-06T10:15:24.612Z", "line": 1, "char": 8 },
          { "key": "(", "ts": "2026-02-06T10:15:24.789Z", "line": 1, "char": 9 },
          { "key": ")", "ts": "2026-02-06T10:15:24.934Z", "line": 1, "char": 10 },
          { "key": ":", "ts": "2026-02-06T10:15:25.078Z", "line": 1, "char": 11 },
          { "key": "↵", "ts": "2026-02-06T10:15:25.456Z", "line": 1, "char": 12 },
          { "key": " ", "ts": "2026-02-06T10:15:25.623Z", "line": 2, "char": 1 },
          { "key": " ", "ts": "2026-02-06T10:15:25.734Z", "line": 2, "char": 2 },
          { "key": " ", "ts": "2026-02-06T10:15:25.845Z", "line": 2, "char": 3 },
          { "key": " ", "ts": "2026-02-06T10:15:25.956Z", "line": 2, "char": 4 },
          { "key": "p", "ts": "2026-02-06T10:15:26.234Z", "line": 2, "char": 5 },
          { "key": "r", "ts": "2026-02-06T10:15:26.378Z", "line": 2, "char": 6 },
          { "key": "i", "ts": "2026-02-06T10:15:26.523Z", "line": 2, "char": 7 },
          { "key": "n", "ts": "2026-02-06T10:15:26.667Z", "line": 2, "char": 8 },
          { "key": "t", "ts": "2026-02-06T10:15:26.812Z", "line": 2, "char": 9 },
          { "key": "(", "ts": "2026-02-06T10:15:26.989Z", "line": 2, "char": 10 },
          { "key": "\"", "ts": "2026-02-06T10:15:27.134Z", "line": 2, "char": 11 },
          { "key": "H", "ts": "2026-02-06T10:15:27.345Z", "line": 2, "char": 12 },
          { "key": "e", "ts": "2026-02-06T10:15:27.489Z", "line": 2, "char": 13 },
          { "key": "l", "ts": "2026-02-06T10:15:27.623Z", "line": 2, "char": 14 },
          { "key": "l", "ts": "2026-02-06T10:15:27.767Z", "line": 2, "char": 15 },
          { "key": "o", "ts": "2026-02-06T10:15:27.912Z", "line": 2, "char": 16 },
          { "key": "⌫", "ts": "2026-02-06T10:15:28.067Z", "line": 2, "char": 16 },
          { "key": "⌫", "ts": "2026-02-06T10:15:28.123Z", "line": 2, "char": 15 }
        ],
        "charCount": 28,
        "startPosition": { "line": 1, "character": 1 },
        "endPosition": { "line": 2, "character": 15 },
        "timing": {
          "avgMs": 156.34,
          "minMs": 56,
          "maxMs": 378,
          "stdDevMs": 78.92
        },
        "movements": [
          {
            "ts": "2026-02-06T10:15:26.100Z",
            "from": { "line": 2, "char": 4 },
            "to": { "line": 2, "char": 5 }
          }
        ]
      },
      {
        "timestamp": "2026-02-06T10:16:05.456Z",
        "text": "World\")↵↵if __name__ == \"__main__\":↵    main()",
        "keystrokes": [
          { "key": "W", "ts": "2026-02-06T10:16:00.123Z", "line": 2, "char": 15 },
          { "key": "o", "ts": "2026-02-06T10:16:00.267Z", "line": 2, "char": 16 },
          { "key": "r", "ts": "2026-02-06T10:16:00.412Z", "line": 2, "char": 17 }
        ],
        "charCount": 45,
        "startPosition": { "line": 2, "character": 15 },
        "endPosition": { "line": 5, "character": 10 },
        "timing": {
          "avgMs": 144.5,
          "minMs": 98,
          "maxMs": 234,
          "stdDevMs": 45.67
        }
      }
    ],
    "chunkCount": 2,
    "totalChars": 73
  }
]
```

## Python Usage Example

```python
import json

# Load keystroke data
with open('key.json', 'r') as f:
    sessions = json.load(f)

# Iterate through sessions
for session in sessions:
    print(f"File: {session['file']}")
    print(f"Module: {session['module']}, Challenge: {session['challenge']}")
    print(f"Total chunks: {session['chunkCount']}")
    print(f"Total characters: {session['totalChars']}")
    
    # Analyze each chunk
    for i, chunk in enumerate(session['chunks']):
        print(f"\n  Chunk {i+1} at {chunk['timestamp']}:")
        print(f"    Text preview: {repr(chunk['text'][:50])}...")
        print(f"    Characters: {chunk['charCount']}")
        
        # Check timing statistics
        if chunk.get('timing'):
            timing = chunk['timing']
            print(f"    Timing: avg={timing['avgMs']}ms, "
                  f"min={timing['minMs']}ms, max={timing['maxMs']}ms, "
                  f"stdDev={timing['stdDevMs']}ms")
            
            # Flag suspicious patterns
            if timing['stdDevMs'] < 20 and timing['avgMs'] < 100:
                print("    ⚠️  WARNING: Suspiciously uniform typing pattern")
        
        # Check for cursor movements
        if chunk.get('movements'):
            print(f"    Cursor movements: {len(chunk['movements'])}")
        
        # Calculate backspace ratio
        backspace_count = chunk['text'].count('⌫')
        if chunk['charCount'] > 0:
            backspace_ratio = backspace_count / chunk['charCount']
            print(f"    Backspace ratio: {backspace_ratio:.2%}")
            if backspace_ratio < 0.05 and chunk['charCount'] > 50:
                print("    ⚠️  WARNING: Very few corrections for long text")
        
        # Check position progression
        start_line = chunk['startPosition']['line']
        end_line = chunk['endPosition']['line']
        if start_line <= end_line:
            print(f"    Position: Linear progression (line {start_line} → {end_line})")
        else:
            print(f"    Position: Non-linear (jumped from line {start_line} → {end_line})")
```

### Detection Patterns

**Copying Indicators:**
- Low standard deviation (<20ms) + fast avg typing (<100ms)
- Linear line progression (always going down)
- Very low backspace ratio (<5% for long text)
- No cursor movements in `movements` array

**Genuine Typing Indicators:**
- Higher standard deviation (natural variation)
- Cursor jumps (going back to edit)
- Normal backspace ratio (8-15%)
- Presence of cursor movements for navigation

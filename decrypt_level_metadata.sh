#!/bin/bash
# Bash script to decrypt /challenge/.config/.level_metadata
# Uses Python script for the actual decryption

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/decrypt_level_metadata.py"

# Default path
METADATA_FILE="${1:-/challenge/.config/.level_metadata}"

# Check if file exists
if [ ! -f "$METADATA_FILE" ]; then
    echo "Error: File not found: $METADATA_FILE" >&2
    exit 1
fi

# Check if Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: Python decryption script not found: $PYTHON_SCRIPT" >&2
    exit 1
fi

# Run the Python script
python3 "$PYTHON_SCRIPT" "$METADATA_FILE"

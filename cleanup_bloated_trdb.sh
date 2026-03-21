#!/bin/bash
# Cleanup script to fix bloated trdb.db files
# This script truncates overly large 'outcome' fields in the compilations table

DB_PATH="${1:-/home/hacker/cse240/.vscode/trdb.db}"

if [ ! -f "$DB_PATH" ]; then
    echo "Database not found: $DB_PATH"
    exit 1
fi

echo "Checking database size..."
DB_SIZE_BEFORE=$(du -h "$DB_PATH" | cut -f1)
echo "Size before: $DB_SIZE_BEFORE"

echo "Creating backup..."
cp "$DB_PATH" "${DB_PATH}.backup_$(date +%Y%m%d_%H%M%S)"

echo "Truncating large outcome fields (keeping last 2000 characters)..."
sqlite3 "$DB_PATH" <<EOF
-- Truncate outcome fields that are unreasonably large
-- Keep only the last 2000 characters (approximately last 30-50 lines)
UPDATE compilations 
SET outcome = '...[truncated]...' || substr(outcome, -2000) 
WHERE length(outcome) > 2000;

-- Vacuum to reclaim space
VACUUM;
EOF

DB_SIZE_AFTER=$(du -h "$DB_PATH" | cut -f1)
echo "Size after: $DB_SIZE_AFTER"
echo "Cleanup complete!"

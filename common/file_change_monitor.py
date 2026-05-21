#!/usr/bin/env python3
"""
File Change Monitor - Tracks changes to source files in the working directory
Logs all modifications, creations, and deletions of tracked file types.
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Try to import inotify, fall back to polling if not available
try:
    import inotify.adapters
    INOTIFY_AVAILABLE = True
except ImportError:
    INOTIFY_AVAILABLE = False
    print("[!] inotify not available, using polling mode", file=sys.stderr)

# File extensions to track
TRACKED_EXTENSIONS = {'.c', '.cpp', '.h', '.hpp', '.sh', '.py', '.rkt', '.pl'}

# Extensions to ignore
IGNORED_EXTENSIONS = {'.log', '.tmp', '.swp', '~'}

def should_track_file(filename):
    """Check if a file should be tracked based on extension."""
    path = Path(filename)
    
    # Ignore hidden files and backup files
    if path.name.startswith('.'):
        return False
    
    # Check for ignored extensions
    for ignored_ext in IGNORED_EXTENSIONS:
        if filename.endswith(ignored_ext):
            return False
    
    # Check for tracked extensions
    return path.suffix in TRACKED_EXTENSIONS

def get_file_info(filepath):
    """Get file metadata."""
    try:
        stat = os.stat(filepath)
        return {
            'size': stat.st_size,
            'mtime': stat.st_mtime
        }
    except (OSError, FileNotFoundError):
        return None

def log_change(log_file, event_type, filepath, work_dir, extra_info=None):
    """Log a file change event."""
    timestamp = datetime.now().isoformat()
    rel_path = os.path.relpath(filepath, work_dir) if work_dir else filepath
    
    log_entry = {
        'timestamp': timestamp,
        'event': event_type,
        'file': rel_path,
        'full_path': filepath
    }
    
    if extra_info:
        log_entry.update(extra_info)
    
    # Write to log file
    with open(log_file, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')
    
    print(f"[{timestamp}] {event_type}: {rel_path}", flush=True)

def monitor_with_inotify(work_dir, log_file):
    """Monitor directory using inotify for real-time tracking."""
    print(f"[i] Starting inotify monitoring of {work_dir}", flush=True)
    
    i = inotify.adapters.InotifyTree(work_dir, mask=(
        inotify.constants.IN_MODIFY |
        inotify.constants.IN_CREATE |
        inotify.constants.IN_DELETE |
        inotify.constants.IN_MOVED_TO |
        inotify.constants.IN_MOVED_FROM |
        inotify.constants.IN_CLOSE_WRITE
    ))
    
    for event in i.event_gen(yield_nones=False):
        (_, type_names, path, filename) = event
        
        if not filename:
            continue
        
        full_path = os.path.join(path, filename)
        
        # Skip if not a tracked file
        if not should_track_file(filename):
            continue
        
        # Determine event type
        if 'IN_CLOSE_WRITE' in type_names:
            event_type = 'modified'
        elif 'IN_CREATE' in type_names or 'IN_MOVED_TO' in type_names:
            event_type = 'created'
        elif 'IN_DELETE' in type_names or 'IN_MOVED_FROM' in type_names:
            event_type = 'deleted'
        elif 'IN_MODIFY' in type_names:
            # Skip raw modify events, wait for close_write
            continue
        else:
            event_type = 'changed'
        
        # Get file info if it still exists
        extra_info = {}
        if event_type != 'deleted':
            file_info = get_file_info(full_path)
            if file_info:
                extra_info['size'] = file_info['size']
        
        log_change(log_file, event_type, full_path, work_dir, extra_info)

def monitor_with_polling(work_dir, log_file, interval=2):
    """Fallback polling-based monitoring."""
    print(f"[i] Starting polling monitoring of {work_dir} (interval: {interval}s)", flush=True)
    
    file_states = {}
    
    def scan_directory():
        """Scan directory and return current file states."""
        current_files = {}
        for root, dirs, files in os.walk(work_dir):
            for filename in files:
                if not should_track_file(filename):
                    continue
                
                full_path = os.path.join(root, filename)
                file_info = get_file_info(full_path)
                if file_info:
                    current_files[full_path] = file_info
        return current_files
    
    # Initial scan
    file_states = scan_directory()
    print(f"[i] Initial scan found {len(file_states)} tracked files", flush=True)
    
    while True:
        time.sleep(interval)
        current_files = scan_directory()
        
        # Check for new or modified files
        for filepath, file_info in current_files.items():
            if filepath not in file_states:
                # New file
                log_change(log_file, 'created', filepath, work_dir, {'size': file_info['size']})
            elif file_states[filepath]['mtime'] != file_info['mtime']:
                # Modified file
                log_change(log_file, 'modified', filepath, work_dir, {'size': file_info['size']})
        
        # Check for deleted files
        for filepath in file_states:
            if filepath not in current_files:
                log_change(log_file, 'deleted', filepath, work_dir)
        
        file_states = current_files

def main():
    if len(sys.argv) < 2:
        print("Usage: file_change_monitor.py <work_directory> [log_file]", file=sys.stderr)
        sys.exit(1)
    
    work_dir = sys.argv[1]
    log_file = sys.argv[2] if len(sys.argv) > 2 else '/var/log/file_changes.log'
    
    if not os.path.isdir(work_dir):
        print(f"[!] Directory does not exist: {work_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Create log file if it doesn't exist
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    if not os.path.exists(log_file):
        open(log_file, 'a').close()
    
    print(f"[i] File change monitor starting", flush=True)
    print(f"[i] Monitoring: {work_dir}", flush=True)
    print(f"[i] Log file: {log_file}", flush=True)
    print(f"[i] Tracked extensions: {', '.join(sorted(TRACKED_EXTENSIONS))}", flush=True)
    
    try:
        if INOTIFY_AVAILABLE:
            monitor_with_inotify(work_dir, log_file)
        else:
            monitor_with_polling(work_dir, log_file)
    except KeyboardInterrupt:
        print("\n[i] Monitoring stopped", flush=True)
    except Exception as e:
        print(f"[!] Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()

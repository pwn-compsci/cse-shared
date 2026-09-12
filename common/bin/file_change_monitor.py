#!/usr/bin/env python3
"""
Snapshot source-file changes for later history analysis.

The normal path uses Linux inotify and records every close-write/move event the
kernel reports. Polling is kept only as a degraded fallback for older images.
"""

import argparse
import hashlib
import json
import os
import shutil
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from inotify_simple import INotify, flags
    INOTIFY_SIMPLE_AVAILABLE = True
except ImportError:
    INOTIFY_SIMPLE_AVAILABLE = False

TRACKED_NAMES = {"Makefile", "makefile"}
TRACKED_EXTENSIONS = {".c", ".cpp", ".h", ".hpp"}
IGNORED_DIRS = {".git", ".vscode", "__pycache__", "node_modules", "system_tests", "user_tests"}
DEFAULT_OUTPUT_DIR = Path("/home/hacker/.local/share/ultima/filewatch")
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
POLL_INTERVAL_SECONDS = 0.25
running = True
LEGACY_LOG_FILE = None


def handle_signal(signum, frame):
    global running
    running = False


def now_info():
    ts = time.time()
    return ts, datetime.fromtimestamp(ts, timezone.utc).isoformat()


def load_level_config():
    try:
        with open("/challenge/.config/level.json", "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except Exception:
        config = {}

    course_code = os.getenv("course_code") or config.get("course_code") or "cse240"
    module = config.get("module") or Path(os.getenv("clevel_work_dir", "")).parent.name or "unknown_module"
    level = config.get("level") or Path(os.getenv("clevel_work_dir", "")).name or "unknown_level"
    challenge = config.get("challenge") or config.get("id") or ""
    return {"course_code": str(course_code), "module": str(module), "level": str(level), "challenge": str(challenge)}


def should_descend(path):
    return path.is_dir() and path.name not in IGNORED_DIRS and not path.name.startswith(".")


def should_track(path):
    if path.name in TRACKED_NAMES:
        return True
    return path.suffix in TRACKED_EXTENSIONS and not path.name.startswith(".")


def safe_component(value):
    value = str(value).strip().replace(os.sep, "__")
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value) or "_"


def rel_path(path, work_dir):
    return path.resolve().relative_to(work_dir.resolve())


def file_history_dir(output_dir, context, relative_path):
    parts = [output_dir, safe_component(context["module"]), safe_component(context["level"]), "files"]
    parts.extend(safe_component(part) for part in relative_path.parts)
    return Path(*parts)


def sha256_file(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as file_obj:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_SNAPSHOT_BYTES:
                return None, size
            digest.update(chunk)
    return digest.hexdigest(), size


def append_jsonl(path, entry):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry, sort_keys=True) + "\n")


def log_watcher(base_dir, event, **fields):
    entry = {"ts": time.time(), "event": event}
    entry.update(fields)
    append_jsonl(base_dir / "watcher.log.jsonl", entry)
    if LEGACY_LOG_FILE is not None:
        try:
            append_jsonl(LEGACY_LOG_FILE, entry)
        except Exception:
            pass


def guess_source():
    guesses = []
    try:
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                comm = (proc / "comm").read_text(encoding="utf-8", errors="ignore").strip()
                cmdline = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "ignore")
            except Exception:
                continue
            haystack = f"{comm} {cmdline}".lower()
            if "extensionhost" in haystack or "code-server" in haystack:
                guesses.append("vscode")
            elif any(editor in haystack for editor in (" vim", " nvim", " nano", " emacs")):
                guesses.append("terminal_editor")
            elif any(tool in haystack for tool in (" scp ", "sftp-server", " rsync ")):
                guesses.append("file_transfer")
            elif any(tool in haystack for tool in (" cp ", " mv ", " unzip ", " tar ")):
                guesses.append("shell_copy")
    except Exception:
        return "unknown"

    if not guesses:
        return "unknown"
    for preferred in ("terminal_editor", "file_transfer", "shell_copy", "vscode"):
        if preferred in guesses:
            return preferred
    return guesses[0]


def process_snapshot(path, work_dir, output_dir, context, state, event_name):
    try:
        resolved = path.resolve()
        if not resolved.is_file() or not should_track(resolved):
            return False
        relative = rel_path(resolved, work_dir)
    except Exception:
        return False

    digest, size = sha256_file(resolved)
    prev = state.get(str(relative), {})
    previous_sha = prev.get("sha256")
    previous_size = prev.get("size")
    timestamp, timestamp_iso = now_info()
    history_dir = file_history_dir(output_dir, context, relative)
    snapshots_dir = history_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    snapshot_rel = None
    skipped_reason = None
    if digest is None:
        skipped_reason = f"file exceeds {MAX_SNAPSHOT_BYTES} byte snapshot cap"
    elif digest != previous_sha:
        snapshot_name = f"{timestamp:.6f}_{digest[:16]}{resolved.suffix or '.txt'}"
        snapshot_path = snapshots_dir / snapshot_name
        if not snapshot_path.exists():
            shutil.copy2(resolved, snapshot_path)
        snapshot_rel = str(snapshot_path.relative_to(output_dir))

    entry = {
        "ts": timestamp,
        "timestamp": timestamp_iso,
        "event": event_name,
        "course_code": context["course_code"],
        "module": context["module"],
        "level": context["level"],
        "challenge": context["challenge"],
        "file": str(relative),
        "size": size,
        "sha256": digest,
        "previous_sha256": previous_sha,
        "previous_size": previous_size,
        "delta_bytes": None if previous_size is None else size - previous_size,
        "snapshot": snapshot_rel,
        "skipped_reason": skipped_reason,
        "source_guess": guess_source(),
    }
    if digest == previous_sha and previous_size == size:
        entry["duplicate_content"] = True

    append_jsonl(history_dir / "events.jsonl", entry)
    append_jsonl(output_dir / "events.jsonl", entry)
    log_watcher(
        output_dir,
        "file_event",
        action="snapshot",
        trigger=event_name,
        file=str(relative),
        size=size,
        sha256=digest,
        changed=digest != previous_sha or previous_size != size,
        duplicate_content=entry.get("duplicate_content", False),
        snapshot=snapshot_rel,
        skipped_reason=skipped_reason,
        source_guess=entry["source_guess"],
    )
    with open(history_dir / "latest.json", "w", encoding="utf-8") as latest_file:
        json.dump(entry, latest_file, sort_keys=True)
        latest_file.write("\n")

    try:
        mtime_ns = resolved.stat().st_mtime_ns
    except OSError:
        mtime_ns = None
    state[str(relative)] = {"sha256": digest, "size": size, "mtime_ns": mtime_ns}
    return True


def record_delete(path, work_dir, output_dir, context, state, event_name):
    try:
        relative = path.resolve().relative_to(work_dir.resolve())
    except Exception:
        try:
            relative = Path(os.path.relpath(path, work_dir))
        except Exception:
            return
    if not should_track(Path(relative)):
        return False

    timestamp, timestamp_iso = now_info()
    previous = state.pop(str(relative), {})
    history_dir = file_history_dir(output_dir, context, relative)
    history_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": timestamp,
        "timestamp": timestamp_iso,
        "event": event_name,
        "course_code": context["course_code"],
        "module": context["module"],
        "level": context["level"],
        "challenge": context["challenge"],
        "file": str(relative),
        "size": None,
        "sha256": None,
        "previous_sha256": previous.get("sha256"),
        "previous_size": previous.get("size"),
        "delta_bytes": None,
        "snapshot": None,
        "source_guess": guess_source(),
    }
    append_jsonl(history_dir / "events.jsonl", entry)
    append_jsonl(output_dir / "events.jsonl", entry)
    log_watcher(
        output_dir,
        "file_event",
        action="delete",
        trigger=event_name,
        file=str(relative),
        previous_sha256=entry["previous_sha256"],
        previous_size=entry["previous_size"],
        source_guess=entry["source_guess"],
    )
    return True


def walk_tracked_files(work_dir):
    for root, dirs, files in os.walk(work_dir):
        dirs[:] = [dirname for dirname in dirs if should_descend(Path(root) / dirname)]
        for filename in files:
            path = Path(root) / filename
            if should_track(path):
                yield path


def initial_scan(work_dir, output_dir, context, state):
    scanned = 0
    recorded = 0
    for path in walk_tracked_files(work_dir):
        scanned += 1
        if process_snapshot(path, work_dir, output_dir, context, state, "initial"):
            recorded += 1
    log_watcher(output_dir, "initial_scan_complete", scanned=scanned, recorded=recorded)


def monitor_with_inotify(work_dir, output_dir, context, state):
    inotify = INotify()
    watch_to_path = {}
    mask = flags.CLOSE_WRITE | flags.MOVED_TO | flags.MOVED_FROM | flags.DELETE | flags.CREATE | flags.DELETE_SELF | flags.MOVE_SELF

    def add_watch(directory):
        try:
            watch_descriptor = inotify.add_watch(str(directory), mask)
            watch_to_path[watch_descriptor] = Path(directory)
        except OSError as exc:
            log_watcher(output_dir, "watch_failed", path=str(directory), error=str(exc))

    for root, dirs, _files in os.walk(work_dir):
        root_path = Path(root)
        add_watch(root_path)
        dirs[:] = [dirname for dirname in dirs if should_descend(root_path / dirname)]

    log_watcher(output_dir, "watching", mode="inotify", watch_count=len(watch_to_path), work_dir=str(work_dir))

    while running:
        for event in inotify.read(timeout=500):
            parent = watch_to_path.get(event.wd)
            if parent is None:
                continue
            names = flags.from_mask(event.mask)
            path = parent / event.name if event.name else parent
            if flags.ISDIR in names:
                if flags.CREATE in names or flags.MOVED_TO in names:
                    if should_descend(path):
                        add_watch(path)
                continue
            if flags.CLOSE_WRITE in names:
                process_snapshot(path, work_dir, output_dir, context, state, "close_write")
            elif flags.MOVED_TO in names or flags.CREATE in names:
                process_snapshot(path, work_dir, output_dir, context, state, "moved_to" if flags.MOVED_TO in names else "created")
            elif flags.DELETE in names or flags.MOVED_FROM in names:
                record_delete(path, work_dir, output_dir, context, state, "deleted" if flags.DELETE in names else "moved_from")


def monitor_with_polling(work_dir, output_dir, context, state):
    log_watcher(output_dir, "watching", mode="poll", interval_seconds=POLL_INTERVAL_SECONDS, work_dir=str(work_dir))
    while running:
        seen = set()
        for path in walk_tracked_files(work_dir):
            try:
                relative = str(rel_path(path, work_dir))
                seen.add(relative)
                mtime_ns = path.stat().st_mtime_ns
            except Exception:
                continue
            if state.get(relative, {}).get("mtime_ns") != mtime_ns:
                process_snapshot(path, work_dir, output_dir, context, state, "poll_changed")
        for relative in list(state):
            if relative not in seen:
                record_delete(work_dir / relative, work_dir, output_dir, context, state, "poll_deleted")
        time.sleep(POLL_INTERVAL_SECONDS)


def main():
    global LEGACY_LOG_FILE

    parser = argparse.ArgumentParser()
    parser.add_argument("work_directory")
    parser.add_argument("legacy_log_file", nargs="?")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--poll", action="store_true")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    work_dir = Path(args.work_directory).resolve()
    output_dir = Path(args.output_dir).resolve()
    if args.legacy_log_file:
        LEGACY_LOG_FILE = Path(args.legacy_log_file).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    context = load_level_config()
    state = {}
    log_watcher(output_dir, "started", pid=os.getpid(), work_dir=str(work_dir), output_dir=str(output_dir), module=context["module"], level=context["level"], challenge=context["challenge"], inotify_simple=INOTIFY_SIMPLE_AVAILABLE, mode="poll" if args.poll or not INOTIFY_SIMPLE_AVAILABLE else "inotify")
    initial_scan(work_dir, output_dir, context, state)
    try:
        if args.poll or not INOTIFY_SIMPLE_AVAILABLE:
            monitor_with_polling(work_dir, output_dir, context, state)
        else:
            monitor_with_inotify(work_dir, output_dir, context, state)
    except Exception as exc:
        log_watcher(output_dir, "fatal_error", error=repr(exc))
        raise
    finally:
        log_watcher(output_dir, "stopped", pid=os.getpid())


if __name__ == "__main__":
    main()

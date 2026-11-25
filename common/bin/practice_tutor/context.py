"""Bounded, read-only context collector. Always launched with the student's UID."""
import json
from itertools import chain, islice
import os
from pathlib import Path
import sqlite3
import stat


def read(path, limit=16000, tail=False):
    # Avoid devices, FIFOs and symlinks. Parent paths are confined to student UID.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                return None
            if tail:
                source.seek(max(0, os.fstat(source.fileno()).st_size - limit))
            return source.read(limit).decode('utf-8', 'replace')
    except OSError:
        return None


def collect():
    config = json.loads(Path('/challenge/.config/level.json').read_text())
    work = Path(config['hwdir']) / str(config['level'])
    files, budget = {}, 80000
    # Depth and count limits prevent scanning archived attempts and editor histories.
    candidates = list(islice(chain(work.glob('*'), work.glob('*/*')), 200))
    for path in sorted(candidates)[:200]:
        if path.suffix in ('.c', '.cpp', '.h') or path.name == 'Makefile':
            text = read(path, min(budget, 16000))
            if text is not None:
                files[str(path.relative_to(work))] = text
                budget -= len(text.encode())
            if budget <= 0:
                break
    logs = {}
    for name in ('tester.log', 'compile.log', 'compiler.log', 'build.log'):
        text = read(work / name, 10000, tail=True)
        if text is not None:
            logs[name] = text
    try:
        rendered = json.loads(read('/opt/practice-tutor/rendered.json', 65000) or '{}')
    except ValueError:
        rendered = {}
    tests = []
    database = Path('/home/hacker/cse240/.vscode/trdb.db')
    try:
        if database.is_symlink():
            raise OSError('symlink database')
        conn = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1)
        conn.set_progress_handler(lambda: 1, 100000)
        try:
            cursor = conn.execute('''SELECT timestamp,passed,failed,substr(error_message,1,2000) FROM tests
                WHERE module=? AND (level=? OR level=?) ORDER BY id DESC LIMIT 5''',
                ('pex20', str(config['level']), str(int(config['level']))))
            tests = [dict(zip(('timestamp','passed','failed','error'), row)) for row in cursor]
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        pass
    return dict(files=files, recent_logs=logs, recent_tests=tests,
                rendered_basecode=rendered, note='Unsaved editor buffers are not included.')


if __name__ == '__main__':
    print(json.dumps(collect()))

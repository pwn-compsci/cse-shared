"""Collect only the server-selected practice attempt, running as the student UID."""
import json
import sys
from pathlib import Path
sys.path.insert(0, '/challenge/web')
import practice_attempts as attempts


def collect(selected):
    work = Path(selected['workdir'])
    files, logs, budget = {}, {}, 80000
    for name in attempts.files(work)[:200]:
        if Path(name).suffix.lower() not in ('.c', '.cpp', '.cc', '.h', '.hpp', '.rkt', '.scm', '.pl', '.md', '.dat', '.txt') and Path(name).name != 'Makefile':
            continue
        try:
            text = attempts.read_work(work, name, limit=16000).decode('utf-8', 'replace')
        except (OSError, ValueError):
            continue
        files[name] = text[:budget]
        budget -= len(text.encode())
        if budget <= 0:
            break
    for name in ('tester.log', 'compile.log', 'compiler.log', 'build.log'):
        try:
            logs[name] = attempts.read_work(work, name, limit=10000).decode('utf-8', 'replace')
        except (OSError, ValueError):
            pass
    tests = attempts.feedback(selected['home'], selected['config'], selected['record'])[:5]
    return dict(files=files, recent_logs=logs, recent_tests=tests,
                selection=selected['selection'],
                note='Only saved files from the selected attempt are included. Unsaved buffers are unavailable. Test history is limited to this attempt’s recorded time window; saved-attempt reruns may be absent.')


if __name__ == '__main__':
    print(json.dumps(collect(json.load(sys.stdin))))

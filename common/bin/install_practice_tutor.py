#!/usr/bin/env python3
"""Install the opt-in practice tutor before the exam web service starts."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import urllib.error
import urllib.request

CONFIG = Path('/challenge/.config/level.json')
RUNTIME = Path('/opt/practice-tutor')
SETTINGS = Path('/opt/practice_tutor.json')
API = 'https://api.cse545.com/api/chatbot/session'
ASSETS = {'bridge.py': 'practice_tutor.py', 'context.py': 'tutor_context.py',
          'widget.js': 'practice_tutor.js', 'chat.html': 'practice_tutor.html'}
SCRIPT = '<script defer src="./exam_api/tutor/widget.js"></script>'


def opted_in(config):
    return (config.get('course_code') == 'cse240' and config.get('module') == 'pex20'
            and config.get('challenge') == 'level-20-03'
            and bool(config.get('is_practice_exam') or config.get('practice_exam'))
            and config.get('practice_tutor', {}).get('enabled') is True
            and config['practice_tutor'].get('course_dir') == '/cse/cse240-fc26')


def trusted_directory(path):
    """Only stage into root-owned directories without symlink components."""
    path = Path(path)
    for parent in reversed((path, *path.parents)):
        if not parent.exists():
            parent.mkdir(mode=0o755)
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Untrusted tutor deployment directory')


def write_file(path, content, mode=0o644):
    path = Path(path)
    trusted_directory(path.parent)
    fd, temporary = tempfile.mkstemp(prefix='.tutor-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
        os.chmod(temporary, mode)
        os.chown(temporary, 0, 0)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install_assets(challenge=Path('/challenge'), bundle=None):
    bundle = bundle or Path(__file__).with_name('practice_tutor')
    web = challenge / 'web'
    for source, destination in ASSETS.items():
        write_file(web / destination, (bundle / source).read_text())
    write_file(RUNTIME / 'install.py', Path(__file__).read_text())
    nginx = web / 'nginx.conf'
    content = nginx.read_text()
    if SCRIPT not in content:
        if '<!--CSE240_EXAM-->' not in content:
            raise ValueError('Exam web overlay marker missing')
        content = content.replace('<!--CSE240_EXAM-->', '<!--CSE240_EXAM-->\n' + SCRIPT, 1)
        write_file(nginx, content)


def provision(config):
    info = Path('/.user_info').read_text()
    match = re.search(r"^pwn_college_id='(\d+)'$", info, re.M)
    if not match:
        raise ValueError('Student identity unavailable')
    # Existing image credential, readable by root. Neither it nor the resulting
    # scoped capability is sent to JavaScript, written into Git, or logged.
    credential = Path('/opt/.ring').read_text().strip()
    payload = dict(pwn_college_id=match[1], module=config['module'],
                   challenge=config['challenge'], course_dir=config['practice_tutor']['course_dir'])
    request = urllib.request.Request(API, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'X-API-Token': credential}, method='POST')
    with urllib.request.urlopen(request, timeout=8) as response:
        settings = json.loads(response.read(8000))
    if not isinstance(settings.get('endpoint_key'), str) or not settings.get('expires_at'):
        raise ValueError('Invalid tutor credential response')
    write_file(SETTINGS, json.dumps(settings), 0o600)


def snapshot(challenge=Path('/challenge')):
    rendered, budget = {}, 50000
    # Trusted starter files only, captured after randomization and before the
    # normal exam cleanup removes /challenge/template. No model or test paths.
    for path in sorted((challenge / 'template').glob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix not in ('.c', '.cpp', '.h', '.md', '.html') and path.name != 'Makefile':
            continue
        with path.open('rb') as source:
            content = source.read(min(16000, budget)).decode('utf-8', 'replace')
        rendered[path.name] = content
        budget -= len(content.encode())
        if budget <= 0:
            break
    write_file(RUNTIME / 'rendered.json', json.dumps(rendered))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--credentials', action='store_true')
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    if not opted_in(config):
        return
    if os.geteuid() != 0:
        raise SystemExit('Tutor installation requires root')
    if args.snapshot:
        snapshot()
        return
    if not args.credentials:
        install_assets()
    try:
        provision(config)
    except Exception as error:
        # Do not put HTTP bodies or credentials into the student's startup log.
        print('[tutor] Credential provisioning unavailable (' + type(error).__name__ + '); will retry when opened')
        if args.credentials:
            raise SystemExit(1)
        return
    print('[tutor] Scoped tutor session installed')


if __name__ == '__main__':
    main()

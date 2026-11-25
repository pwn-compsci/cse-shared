#!/usr/bin/env python3
"""Install the opt-in practice tutor before the exam web service starts."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
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
    if config.get('module') == '25-proj-mud':
        return (config.get('course_code') == 'cse240'
                and config.get('challenge') in {f'p25-level-{n:02}' for n in range(1,9)}
                and config.get('practice_tutor', {}).get('enabled') is True
                and config['practice_tutor'].get('course_dir') == '/cse/intro-to-programming-languages')
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
    settings.update(module=config['module'], challenge=config['challenge'], course_dir=config['practice_tutor']['course_dir'])
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



def install_project_assets(config, challenge=Path('/challenge'), bundle=None):
    """Only called after the backend confirms current course enrollment."""
    bundle = bundle or Path(__file__).with_name('practice_tutor')
    web = challenge / 'web'
    for source, destination in ASSETS.items():
        write_file(web / destination, (bundle / source).read_text())
    write_file(web / 'project_tutor_server.py', (bundle / 'project_server.py').read_text())
    write_file(RUNTIME / 'install.py', Path(__file__).read_text())
    # Match .init's helper preference so its later --start sees the same
    # clipboard patch identity and preserves the added Aita routes.
    helper = Path('/usr/local/lib/cse240/terminal_clipboard.py')
    if not helper.is_file():
        helper = challenge / 'bin/terminal_clipboard.py'
    subprocess.run([sys.executable, str(helper), '--prepare-launcher',
                    '--pwn-college-id', container_identity()], check=True, capture_output=True)
    patch_project_editor(Path('/run/ultima-code-server'), bundle)
    pidfile = RUNTIME / 'bridge.pid'
    alive = False
    try:
        os.kill(int(pidfile.read_text()), 0)
        alive = True
    except (OSError, ValueError):
        pass
    if not alive:
        with open('/var/log/aita-bridge.log', 'ab') as log:
            child = subprocess.Popen([sys.executable, str(web / 'project_tutor_server.py')],
                cwd='/', env={'PATH':'/usr/bin:/bin'}, stdout=log, stderr=log, start_new_session=True)
        write_file(pidfile, str(child.pid), 0o600)


def container_identity():
    match = re.search(r"^pwn_college_id='(\d+)'$", Path('/.user_info').read_text(), re.M)
    if not match:
        raise ValueError('Student identity unavailable')
    return match[1]


def patch_project_editor(editor, bundle):
    route = editor / 'out/node/routes/vscode.js'
    html = editor / 'lib/vscode/out/vs/code/browser/workbench/workbench.html'
    anchor = 'exports.router = express.Router();'
    contents = route.read_text()
    markup = html.read_text()
    script = '<script defer src="{{BASE}}/exam_api/tutor/widget.js"></script>'
    patch = (bundle / 'editor_route.js').read_text()
    if '// AITA_PROJECT_ROUTES' not in contents:
        if contents.count(anchor) != 1 or markup.count('</head>') != 1:
            raise ValueError('Unsupported editor version')
        write_file(route, contents.replace(anchor, anchor + '\n' + patch, 1))
    if script not in markup:
        write_file(html, markup.replace('</head>', script + '\n</head>', 1))


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
    mud = config.get('module') == '25-proj-mud'
    if not args.credentials and not mud:
        install_assets()
    try:
        provision(config)
    except Exception as error:
        if mud:
            SETTINGS.unlink(missing_ok=True)
        # Do not put HTTP bodies or credentials into the student's startup log.
        print('[tutor] Credential provisioning unavailable (' + type(error).__name__ + '); will retry when opened')
        if args.credentials:
            raise SystemExit(1)
        return
    if mud and not args.credentials:
        install_project_assets(config)
    print('[tutor] Scoped tutor session installed')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Prepare a writable platform code-server copy; optionally start the dojo service."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ASSET_CONTENTS = {
    'browser.js': r'''/* Ultima terminal clipboard events: event metadata and clipboard text. */
(() => {
  if (window.__ultimaClipboard) return;
  window.__ultimaClipboard = true;
  const endpoint = new URL('./ultima-terminal-event', document.currentScript.src);
  const session = crypto.randomUUID();
  let sequence = 0;
  let last = {event: '', time: 0};
  const terminalFocused = () => !!document.activeElement?.closest('.terminal-instance, .xterm');
  function record(event, source, text) {
    const contentAvailable = typeof text === 'string';
    const originalLength = contentAvailable ? text.length : 0;
    text = contentAvailable ? text.slice(0, 262144) : null;
    const now = Date.now();
    // Clipboard API calls can also generate a DOM clipboard event.
    if (last.event === event && last.text === text && now - last.time < 80) return;
    last = {event, text, time: now};
    fetch(endpoint, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({event, source, session, sequence: ++sequence,
        clientTime: new Date(now).toISOString(), text, contentAvailable,
        originalLength, truncated: originalLength > 262144})
    }).catch(() => {});
  }
  for (const event of ['copy', 'paste']) {
    document.addEventListener(event, e => {
      if (!e.isTrusted || !terminalFocused()) return;
      if (event === 'paste') {
        record(event, 'dom', e.clipboardData ? e.clipboardData.getData('text/plain') : null);
      } else {
        const selection = window.getSelection()?.toString() || null;
        // Let terminal handlers populate clipboardData before reading it.
        queueMicrotask(() => {
          let text = null;
          try { text = e.clipboardData?.getData('text/plain') || null; } catch (_) {}
          record(event, 'dom', text ?? selection);
        });
      }
    }, true);
  }
  // VS Code menu/command actions can use the Clipboard API without DOM events.
  const clipboard = navigator.clipboard;
  for (const [method, event] of [['writeText', 'copy'], ['readText', 'paste']]) {
    if (!clipboard?.[method]) continue;
    const original = clipboard[method].bind(clipboard);
    try {
      clipboard[method] = async (...args) => {
        const terminal = terminalFocused();
        const result = await original(...args);
        if (terminal) record(event, 'clipboard-api', event === 'copy' ? String(args[0]) : result);
        return result;
      };
    } catch (_) { /* Native DOM events remain available. */ }
  }
})();
''',
    'route.js': r'''// Installed immediately after exports.router = express.Router().
exports.router.get('/ultima-terminal-clipboard.js', async (req, res, next) => {
    try {
        if (!await (0, http_1.authenticated)(req)) return res.sendStatus(401);
        res.set('Cache-Control', 'no-store');
        res.type('application/javascript').sendFile(require('path').join(__dirname, 'ultima-browser.js'));
    } catch (error) { next(error); }
});
exports.router.post('/ultima-terminal-event', express.json({limit: '2mb'}), async (req, res, next) => {
    try {
        if (!await (0, http_1.authenticated)(req)) return res.sendStatus(401);
        if (req.get('Sec-Fetch-Site') === 'cross-site') return res.sendStatus(403);
        const b = req.body;
        if (!b || !['copy', 'paste'].includes(b.event) ||
            !['dom', 'clipboard-api'].includes(b.source) ||
            typeof b.session !== 'string' || !/^[a-zA-Z0-9-]{1,64}$/.test(b.session) ||
            !Number.isSafeInteger(b.sequence) || b.sequence < 1 ||
            typeof b.clientTime !== 'string' || b.clientTime.length > 40 ||
            typeof b.contentAvailable !== 'boolean' || typeof b.truncated !== 'boolean' ||
            !Number.isSafeInteger(b.originalLength) || b.originalLength < 0 ||
            (b.contentAvailable ? (typeof b.text !== 'string' || b.text.length > 262144 ||
                b.text.length !== Math.min(b.originalLength, 262144) ||
                b.truncated !== (b.originalLength > 262144)) :
                (b.text !== null || b.originalLength !== 0 || b.truncated))) return res.sendStatus(400);
        const fs = require('fs');
        let level = {}, levelMetadataAvailable = true;
        try {
            level = JSON.parse(await fs.promises.readFile('/challenge/.config/level.json', 'utf8'));
            if (!level || typeof level !== 'object' || Array.isArray(level)) throw new Error('Invalid level metadata');
        } catch (_) { level = {}; levelMetadataAvailable = false; }
        const metadataValue = key => ['string', 'number'].includes(typeof level[key]) ? level[key] : null;
        const dir = require('path').join(require('os').homedir(), '.local/share/ultima');
        await fs.promises.mkdir(dir, {recursive: true, mode: 0o700});
        const row = {module: metadataValue('module'), challenge: metadataValue('challenge'),
            pwn_college_id: metadataValue('pwn_college_id'), levelMetadataAvailable, time: new Date().toISOString(), event: b.event, source: b.source,
            session: b.session, sequence: b.sequence, clientTime: b.clientTime, text: b.text,
            contentAvailable: b.contentAvailable, originalLength: b.originalLength, truncated: b.truncated};
        await fs.promises.appendFile(require('path').join(dir, 'terminal-clipboard.jsonl'),
            JSON.stringify(row) + '\n', {mode: 0o600, flag: fs.constants.O_APPEND | fs.constants.O_CREAT | fs.constants.O_WRONLY | fs.constants.O_NOFOLLOW});
        res.sendStatus(204);
    } catch (error) { next(error); }
});
'''
}
DEST = Path('/run/ultima-code-server')


def discover():
    launcher = Path('/run/dojo/bin/code-server').resolve()
    for _ in range(5):
        text = launcher.read_text()
        entry = re.search(r'(/nix/store/[^\s"\']+/out/node/entry\.js)', text)
        if entry:
            node = re.search(r'"(/nix/store/[^"\n]+/bin/node)"', text)
            if not node:
                raise RuntimeError('Cannot locate platform Node executable')
            return Path(entry[1]).parents[2], node[1]
        nested = re.search(r'"(/nix/store/[^"\n]+/bin/code-server)"', text)
        if not nested:
            break
        launcher = Path(nested[1])
    raise RuntimeError('Unsupported platform code-server launcher')


def prepare(source, destination):
    route_path = Path('out/node/routes/vscode.js')
    html_path = Path('lib/vscode/out/vs/code/browser/workbench/workbench.html')
    route = (source / route_path).read_text()
    html = (source / html_path).read_text()
    anchor = 'exports.router = express.Router();'
    if route.count(anchor) != 1 or html.count('</head>') != 1:
        raise RuntimeError('Unsupported code-server assets; refusing to patch')
    route = route.replace(anchor, anchor + '\n' + ASSET_CONTENTS['route.js'])
    html = html.replace('</head>', '<script defer src="{{BASE}}/ultima-terminal-clipboard.js"></script>\n</head>')
    identity = json.dumps({'source': str(source), 'assets': [
        ASSET_CONTENTS[f] for f in ('browser.js', 'route.js')]})
    marker = destination / '.ultima-patch.json'
    if marker.exists() and marker.read_text() == identity:
        return
    if destination.exists():
        raise RuntimeError(f'{destination} already exists with a different patch; stop its service and remove it first')
    temp = Path(tempfile.mkdtemp(prefix='.ultima-code-', dir=destination.parent))
    try:
        # Real copies preserve Node module resolution and VS Code resource paths.
        shutil.copytree(source, temp, symlinks=True, dirs_exist_ok=True)
        for path, content in ((route_path, route), (html_path, html)):
            target = temp / path
            target.chmod(0o644)
            target.write_text(content)
        (temp / 'out/node/routes/ultima-browser.js').write_text(ASSET_CONTENTS['browser.js'])
        (temp / '.ultima-patch.json').write_text(identity)
        temp.chmod(0o755)
        temp.rename(destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def tracking_allowed(level, identity):
    # All users are eligible. Exam exclusion wins over lab/project metadata,
    # which may also be present in exam configs.
    exam = level.get('examLevel')
    if exam is not None and exam is not False and str(exam).strip() != '':
        return False
    module = str(level.get('module') or '').lower()
    challenge = str(level.get('challenge') or '').lower()
    if re.search(r'(?:^|[-_])(exam|pex|pretest)(?:[-_0-9]|$)', module):
        return False
    return bool(
        (level.get('labid') and str(level['labid']) not in {'0', '00'}) or level.get('hw') or
        re.search(r'(?:^|[-_])(?:proj(?:ect)?|grouplab|classlab|lab)(?:[-_0-9]|$)', module) or
        re.match(r'(?:classlab|grouplab|lab)[-_0-9]', challenge)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', action='store_true', help='Start code-service/code-server as hacker')
    parser.add_argument('--destination', type=Path, default=DEST)
    parser.add_argument('--pwn-college-id', required=True)
    args = parser.parse_args()
    try:
        level = json.loads(Path('/challenge/.config/level.json').read_text())
    except (OSError, ValueError):
        print('Terminal clipboard tracking skipped: unavailable level metadata', flush=True)
        return
    if not isinstance(level, dict) or not tracking_allowed(level, args.pwn_college_id):
        print('Terminal clipboard tracking skipped: activity outside tracking scope', flush=True)
        return
    source, node = discover()
    prepare(source, args.destination)
    print(f'Patched writable copy: {args.destination}', flush=True)
    if args.start:
        if os.geteuid() != 0:
            raise RuntimeError('--start must run as root from .init')
        pidfile = Path('/run/dojo/var/code-service/code-server.pid')
        if pidfile.exists():
            try:
                pid = int(pidfile.read_text())
                os.kill(pid, 0)
            except (ProcessLookupError, ValueError):
                pass
            else:
                cmdline = Path(f'/proc/{pid}/cmdline').read_bytes()
                if str(args.destination).encode() not in cmdline:
                    raise RuntimeError('Unpatched code-server already running; refusing to interrupt it')
                print('Patched service already running')
                return
        import pwd
        user = pwd.getpwnam('hacker')
        extensions = '/run/challenge/share/code/extensions'
        if not Path(extensions).is_dir():
            matches = list(Path('/nix/store').glob('*-vscode-extensions/share/vscode/extensions'))
            if len(matches) != 1:
                raise RuntimeError('Cannot unambiguously locate platform extensions')
            extensions = str(matches[0])
        command = ['/run/dojo/bin/dojo-service', 'start', 'code-service/code-server',
                   node, str(args.destination / 'out/node/entry.js'),
                   '--auth=none', '--bind-addr=0.0.0.0:8080', '--trusted-origins=*',
                   '--disable-telemetry', '--disable-update-check',
                   '--disable-getting-started-override', '--extensions-dir=' + extensions,
                   '--config=/dev/null']

        def demote():
            os.initgroups(user.pw_name, user.pw_gid)
            os.setgid(user.pw_gid)
            os.setuid(user.pw_uid)

        env = dict(os.environ, HOME=user.pw_dir, USER='hacker', LOGNAME='hacker')
        subprocess.run(command, check=True, env=env, cwd=user.pw_dir, preexec_fn=demote)
        import time
        import urllib.request
        for _ in range(50):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8080/ultima-terminal-clipboard.js', timeout=1) as response:
                    if response.status == 200:
                        print('Terminal clipboard tracking ready', flush=True)
                        return
            except OSError:
                pass
            time.sleep(0.1)
        raise RuntimeError('Patched code-server did not become ready; inspect code-service/code-server.log')


if __name__ == '__main__':
    main()

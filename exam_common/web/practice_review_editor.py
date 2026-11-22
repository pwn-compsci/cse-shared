"""A separate, narrowly scoped code-server for editable saved practice work."""
import os
import json
from pathlib import Path
import pwd
import socket
import subprocess
import time
from practice_attempts import directory

PORT = 4300
STATE = '/opt/practice-review-editor.json'
LOG = '/opt/practice-review-editor.log'
BIN = '/opt/practice-review-bin'

# Import only the logging block; bashrc also installs exam-only aliases.
HISTORY_SETUP = r'''if ! declare -F __cse_log_cmd >/dev/null; then
    __cse_review_prompt=${PROMPT_COMMAND-}
    source <(sed -n '/^# CSE_COMMAND_HISTORY_START$/,/^# CSE_COMMAND_HISTORY_END$/p' /etc/bash.bashrc)
    PROMPT_COMMAND=$__cse_review_prompt
    unset __cse_review_prompt
    if ! declare -F __cse_log_cmd >/dev/null; then
        __cse_log_cmd() {
            local current_histcmd="${HISTCMD:-}"
            [ -n "$current_histcmd" ] || return 0
            [ "$current_histcmd" != "${__cse_last_logged_histcmd:-}" ] || return 0
            __cse_last_logged_histcmd="$current_histcmd"
            history -a
            history 1 | sed "s/^/$(date '+%F %T') ${INST_ID:-unknown unknown} | /" >> "${CSE_COMMAND_HISTORY_FILE:-/home/hacker/.local/share/ultima/c.dat}" 2>/dev/null || true
        }
    fi
fi
'''


def ready():
    try:
        with socket.create_connection(('127.0.0.1', PORT), timeout=0.2):
            return True
    except OSError:
        return False



def prepare_profile():
    student = pwd.getpwnam('hacker')
    profile = Path(student.pw_dir) / '.local/share/code-server-practice-review'
    with directory(student.pw_dir) as base:
        parent = os.dup(base)
        try:
            for part in ('.local', 'share', 'code-server-practice-review'):
                created = False
                try:
                    os.mkdir(part, 0o700, dir_fd=parent)
                    created = True
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                if created:
                    os.fchown(child, student.pw_uid, student.pw_gid)
                os.close(parent)
                parent = child
            os.fchown(parent, student.pw_uid, student.pw_gid)
        finally:
            os.close(parent)

    # This profile is only for the student's saved practice code.
    with directory(profile) as profile_fd:
        created = False
        try:
            os.mkdir('User', 0o700, dir_fd=profile_fd)
            created = True
        except FileExistsError:
            pass
        user_fd = os.open('User', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=profile_fd)
        try:
            if created:
                os.fchown(user_fd, student.pw_uid, student.pw_gid)
            try:
                fd = os.open('settings.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=user_fd)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, 'w') as settings:
                    json.dump({'security.workspace.trust.enabled': False}, settings)
                    os.fchown(settings.fileno(), student.pw_uid, student.pw_gid)
        finally:
            os.close(user_fd)
    bin_dir = Path(BIN)
    bin_dir.mkdir(mode=0o755, exist_ok=True)
    if bin_dir.is_symlink():
        raise OSError('Unsafe review command directory.')
    scripts = {'tester': '#!/bin/sh\nexec /usr/bin/python3 /challenge/web/practice_review_tester.py "$@"\n',
               'history.sh': HISTORY_SETUP,
               'shell': '#!/bin/bash\nsource /opt/practice-review-bin/history.sh\nexport -f __cse_log_cmd\nexec /bin/bash --noprofile --norc "$@"\n'}
    for name, content in scripts.items():
        temporary = bin_dir / ('.' + name + '-' + os.urandom(8).hex())
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755)
            with os.fdopen(fd, 'w') as stream:
                stream.write(content)
            os.replace(temporary, bin_dir / name)
        finally:
            if temporary.exists():
                temporary.unlink()
    return student, profile


def ensure_running(home, folders, locked_file):
    """Do not widen or restart the active exam editor's Landlock sandbox."""
    folders = sorted(set(map(str, folders)))
    if not folders or any(',' in p for p in folders):
        raise ValueError('Invalid saved practice directories.')
    for folder in folders:
        with directory(folder):
            pass
    student, profile = prepare_profile()
    with locked_file(STATE) as state:
        if state.get('pid'):
            try:
                os.kill(state['pid'], 0)
                if ready() and set(folders).issubset(state.get('folders', [])):
                    return
            except ProcessLookupError:
                pass
            # Preserve already-open review tabs instead of killing another editor.
            if ready():
                raise OSError('Review editor is already serving a different directory set.')
        elif ready():
            raise OSError('Review editor port is already in use.')
        code_server = next((p for p in ('/run/ultima-code-server/ultima-code-server', '/run/dojo/bin/code-server')
                            if os.access(p, os.X_OK)), None)
        if code_server is None:
            raise OSError('Code-server is unavailable.')
        shell_files = [Path(student.pw_dir) / name for name in ('.bashrc', '.profile', '.bash_history')]
        shell_files.append(Path(home) / ('.' + Path(home).name + 'env'))
        shell_rules = [value for path in shell_files if path.is_file() for value in ('--rw', str(path))]
        command = [
            '/run/dojo/bin/landrun', '--best-effort', '--add-exec', '--unrestricted-network',
            '--env', 'PATH', '--env', 'HOME',
            '--rox', '/bin,/lib,/nix,/lib64,/opt,/sys,/usr,/sbin,/etc',
            '--rwx', '/proc,/tmp,/run,/challenge',
            '--rwx', '/dev/null,/dev/ptmx,/dev/pts,/dev/tty,/dev/urandom,/dev/random',
            '--rw', str(profile) + ',' + student.pw_dir + '/.cache,' + student.pw_dir + '/.local',
            '--rw', str(Path(home) / '.vscode'),
            '--rwx', ','.join(folders),
            *shell_rules,
            '--', code_server, '--auth=none', '--bind-addr=127.0.0.1:' + str(PORT),
            '--trusted-origins=*', '--disable-update-check', '--disable-telemetry', '--disable-workspace-trust',
            '--extensions-dir=/run/challenge/share/code/extensions',
            '--user-data-dir=' + str(profile), '--config=/dev/null',
            '--app-name=Saved practice attempt', '--ignore-last-opened', folders[0],
        ]
        environment = dict(os.environ, HOME=student.pw_dir, USER='hacker', LOGNAME='hacker',
                           PATH='/challenge:/challenge/bin:/run/challenge/bin:/run/dojo/bin:' + os.environ.get('PATH', '/usr/bin:/bin'))
        with open(LOG, 'ab') as log:
            process = subprocess.Popen(command, user=student.pw_uid, group=student.pw_gid, extra_groups=os.getgrouplist('hacker', student.pw_gid),
                env=environment, cwd=student.pw_dir, stdin=subprocess.DEVNULL,
                stdout=log, stderr=log, start_new_session=True)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise OSError('Saved-attempt editor failed to start; see its service log.')
            if ready():
                state.update(pid=process.pid, folders=folders)
                return
            time.sleep(0.15)
        process.terminate()
        raise OSError('Saved-attempt editor startup timed out.')

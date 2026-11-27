"""Indexed practice backups and bounded, symlink-safe access to student work."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import os
import json
import pwd
import re
import sqlite3
import stat
from zoneinfo import ZoneInfo

SKIP = {'system_tests', 'model', 'template', 'Desktop', '__pycache__'}
TEXT = {'.c', '.cpp', '.cc', '.h', '.hpp', '.py', '.rkt', '.scm', '.pl', '.java', '.md', '.txt', '.json', '.log', '.dat', '.csv', '.in', '.out', '.sh', '.html', '.css', '.js', '.yml', '.yaml'}


def now():
    return datetime.now(timezone.utc).isoformat()


def display_time(value):
    instant = datetime.fromisoformat(value).astimezone(ZoneInfo('America/Phoenix'))
    return instant.strftime('%b %d, %Y at %-I:%M:%S %p MST')


@contextmanager
def directory(path):
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in Path(path).absolute().parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def allowed(relative):
    parts = PurePosixPath(relative).parts
    return bool(parts) and not PurePosixPath(relative).is_absolute() and all(
        p not in ('.', '..') and not p.startswith('.') and p not in SKIP for p in parts
    ) and (Path(parts[-1]).suffix.lower() in TEXT or parts[-1] in ('Makefile', 'makefile'))


def read_work(path, relative, limit=512 * 1024):
    if not allowed(relative):
        raise ValueError('This file is not available for review.')
    parts = PurePosixPath(relative).parts
    with directory(Path(path).joinpath(*parts[:-1])) as parent:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Only ordinary saved files can be reviewed.')
            data = stream.read(limit + 1)
            if len(data) > limit or b'\0' in data:
                raise ValueError('This file is binary or too large to preview.')
            return data


def files(path):
    found = []
    # Walk using directory descriptors so swapped student symlinks are not followed.
    def visit(fd, prefix=''):
        for name in sorted(os.listdir(fd)):
            if len(found) >= 300:
                return
            if name.startswith('.') or name in SKIP:
                continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            relative = prefix + name
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    visit(child, relative + '/')
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and allowed(relative):
                found.append(relative)
    with directory(path) as fd:
        visit(fd)
    return found


def workdir(config, home):
    return Path(config.get('hwdir') or Path(home) / str(config['module'])) / str(config['level'])


def migrate_workdir(entry, config, home):
    """Copy indexed practice saves when separating a formerly shared workspace.

    Originals stay in place. Only a last launch explicitly identified as practice
    permits a snapshot of the shared active folder; actual exam work is untouched.
    """
    previous = config.get('previous_practice_hwdir')
    if not previous or entry.get('workdir_migrated') == str(workdir(config, home)):
        return
    module, level = str(config['module']), str(config['level'])
    if (not re.fullmatch(r'pex\d+', module) or not re.fullmatch(r'\d+', level)
            or Path(previous) != Path(home) / 'exam' / module[3:]
            or workdir(config, home) != Path(home) / module / level):
        raise ValueError('Invalid practice workspace migration.')
    old = Path(previous) / level
    active = workdir(config, home)
    if not old.parent.exists():
        entry['workdir_migrated'] = str(active)
        return
    owner = pwd.getpwnam('hacker')
    with directory(home) as parent:
        try:
            os.mkdir(module, 0o755, dir_fd=parent)
        except FileExistsError:
            pass
        child = os.open(module, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            os.fchown(child, owner.pw_uid, owner.pw_gid)
        finally:
            os.close(child)

    def copy_saved(source, name):
        # Publish only a fully copied source/data snapshot. Existing destinations
        # are never overwritten, including on a repeated/interrupted startup.
        with directory(active.parent) as parent:
            try:
                os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                with directory(active.parent / name):
                    return
            temporary = '.practice-migrate-' + os.urandom(8).hex()
            os.mkdir(temporary, 0o755, dir_fd=parent)
            target = active.parent / temporary
            with directory(target) as fd:
                os.fchown(fd, owner.pw_uid, owner.pw_gid)
            restore(source, target)
            os.rename(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)

    for record in entry.get('attempts', []):
        name = record.get('directory', '')
        if not re.fullmatch(re.escape(level) + r'_[A-Za-z0-9_-]+', name):
            raise ValueError('Unsafe saved practice directory.')
        source = old.parent / name
        if source.exists() or source.is_symlink():
            copy_saved(source, name)

    last = None
    try:
        for line in (Path(home) / '.vscode/starts.log').read_text().splitlines():
            fields = dict(field.split('=', 1) for field in line.split('|') if '=' in field)
            if fields.get('level') == level and fields.get('module') in (module, 'exam' + module[3:]):
                last = fields
    except FileNotFoundError:
        pass
    if last and last['module'] == module and old.is_dir():
        saved = now()
        name = level + '_' + datetime.fromisoformat(saved).strftime('%Y-%m-%d_%H%M%S_%f')
        copy_saved(old, name)
        entry.setdefault('attempts', []).append(dict(
            id=name, directory=name, variant=last.get('chosen_problem'),
            started_at=entry.get('started_at'), saved_at=saved))
    entry['workdir_migrated'] = str(active)


def discover(entry, active):
    """Keep old timestamped folders reviewable without guessing their variant."""
    known = {a['directory'] for a in entry.setdefault('attempts', [])}
    if not active.parent.exists():
        return
    with directory(active.parent) as parent:
        for name in os.listdir(parent):
            match = re.fullmatch(re.escape(active.name) + r'_(\d{4}-\d{2}-\d{2}_\d{4})(?:.*)?', name)
            if not match or name in known:
                continue
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                continue
            saved = datetime.strptime(match[1], '%Y-%m-%d_%H%M').replace(tzinfo=timezone.utc).isoformat()
            entry['attempts'].append({'id': name, 'directory': name, 'variant': None, 'saved_at': saved})


def archive(entry, active):
    if not active.exists() and not active.is_symlink():
        return
    saved = now()
    suffix = datetime.fromisoformat(saved).strftime('%Y-%m-%d_%H%M%S_%f')
    name = active.name + '_' + suffix
    with directory(active.parent) as parent:
        info = os.stat(active.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('Unsafe active practice directory.')
        os.rename(active.name, name, src_dir_fd=parent, dst_dir_fd=parent)
    entry.setdefault('attempts', []).append({
        'id': name, 'directory': name, 'variant': entry.get('current'),
        'started_at': entry.get('started_at'), 'saved_at': saved,
    })


def find_attempt(entry, attempt_id, active):
    attempt = next((a for a in entry.get('attempts', []) if a['id'] == attempt_id), None)
    if not attempt or Path(attempt['directory']).name != attempt['directory']:
        raise ValueError('Saved attempt not found.')
    path = active.parent / attempt['directory']
    with directory(path):
        pass
    return attempt, path


def restore(source, target):
    # Copy source/data files only; fresh framework, binaries and hidden tests stay intact.
    owner = pwd.getpwnam('hacker')
    for relative in files(source):
        data = read_work(source, relative, limit=2 * 1024 * 1024)
        parts = PurePosixPath(relative).parts
        with directory(target) as base:
            parent = os.dup(base)
            try:
                for name in parts[:-1]:
                    try:
                        os.mkdir(name, 0o755, dir_fd=parent)
                    except FileExistsError:
                        pass
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                    os.fchown(child, owner.pw_uid, owner.pw_gid)
                    os.close(parent)
                    parent = child
                # Replace rather than truncate: no writes through attacker hard links.
                temp = '.practice-restore-' + os.urandom(8).hex()
                fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent)
                with os.fdopen(fd, 'wb') as output:
                    output.write(data)
                    os.fchown(output.fileno(), owner.pw_uid, owner.pw_gid)
                os.rename(temp, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
            finally:
                os.close(parent)


def feedback(home, config, attempt):
    if not attempt.get('started_at'):
        return []
    path = Path(home) / '.vscode/trdb.db'
    try:
        with directory(path.parent) as parent:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                return []
            with sqlite3.connect(f'file:/proc/self/fd/{fd}?mode=ro', uri=True, timeout=1) as connection:
                connection.row_factory = sqlite3.Row
                start = datetime.fromisoformat(attempt['started_at']).strftime('%Y-%m-%d %H:%M:%S')
                end = datetime.fromisoformat(attempt['saved_at']).strftime('%Y-%m-%d %H:%M:%S')
                rows = connection.execute('SELECT timestamp, passed, failed, error_message FROM tests '
                    'WHERE module = ? AND level = ? AND timestamp >= ? AND timestamp < ? '
                    'ORDER BY timestamp DESC LIMIT 30', (str(config['module']), str(config['level']), start, end))
                return [dict(row) for row in rows]
        finally:
            os.close(fd)
    except (OSError, sqlite3.Error, ValueError):
        return []


def saved_workspace(path):
    """A native workspace opens the saved folder, without the 'Open Workspace' prompt."""
    name = '.practice-review.code-workspace'
    with directory(path) as parent:
        owner = os.fstat(parent)
        data = {}
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, 'r') as stream:
                info = os.fstat(stream.fileno())
                if stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 512 * 1024:
                    try:
                        data = json.load(stream)
                    except (ValueError, UnicodeError):
                        pass
        except FileNotFoundError:
            pass
        if not isinstance(data, dict):
            data = {}
        data['folders'] = [{'path': '.', 'name': 'Saved attempt · ' + Path(path).name}]
        if not isinstance(data.get('settings'), dict):
            data['settings'] = {}
        data['settings'].setdefault('window.title', 'Saved attempt · ${rootName}${separator}${appName}')
        # A clean review shell avoids the exam alias that discards tester arguments.
        if not isinstance(data['settings'].get('terminal.integrated.profiles.linux'), dict):
            data['settings']['terminal.integrated.profiles.linux'] = {}
        data['settings']['terminal.integrated.profiles.linux']['Saved practice shell'] = {
            'path': '/opt/practice-review-bin/shell', 'args': []}
        # Reopening an archive must not reconnect to a pre-fix shell.
        data['settings']['terminal.integrated.enablePersistentSessions'] = False
        data['settings']['terminal.integrated.defaultProfile.linux'] = 'Saved practice shell'
        if not isinstance(data['settings'].get('terminal.integrated.env.linux'), dict):
            data['settings']['terminal.integrated.env.linux'] = {}
        environment = data['settings']['terminal.integrated.env.linux']
        environment['PATH'] = '/opt/practice-review-bin:/challenge:/challenge/bin:/run/dojo/bin:${env:PATH}'
        environment['PROMPT_COMMAND'] = 'source /opt/practice-review-bin/history.sh; __cse_log_cmd'

        if not isinstance(data.get('tasks'), dict):
            data['tasks'] = {'version': '2.0.0'}
        if not isinstance(data['tasks'].get('tasks'), list):
            data['tasks']['tasks'] = []
        data['tasks'].setdefault('version', '2.0.0')
        tasks = data['tasks']['tasks']
        if not any(isinstance(task, dict) and task.get('label') == 'Test saved attempt' for task in tasks):
            tasks.append({'label': 'Test saved attempt', 'type': 'process', 'command': '/opt/practice-review-bin/tester',
                          'args': ['-u'], 'options': {'cwd': '${workspaceFolder}'}, 'problemMatcher': []})
        for task in tasks:
            if isinstance(task, dict) and task.get('label') == 'Test saved attempt' and task.get('command') == '/challenge/tester':
                task['command'] = '/opt/practice-review-bin/tester'
        names = set(os.listdir(parent))
        source = 'main.cpp' if 'main.cpp' in names else 'main.c' if 'main.c' in names else None
        if source:
            build = 'Build saved attempt for debugging'
            if not any(isinstance(task, dict) and task.get('label') == build for task in tasks) and 'Makefile' not in names:
                tasks.append({'label': build, 'type': 'process', 'command': 'g++' if source.endswith('.cpp') else 'gcc',
                              'args': ['-g', '-O0', source, '-o', 'main.bin'],
                              'options': {'cwd': '${workspaceFolder}'}, 'problemMatcher': ['$gcc']})
            config = {'name': 'Debug saved attempt', 'type': 'cppdbg', 'request': 'launch',
                      'program': '${workspaceFolder}/main.bin', 'cwd': '${workspaceFolder}',
                      'args': [], 'stopAtEntry': True, 'externalConsole': False,
                      'MIMode': 'gdb', 'miDebuggerPath': '/usr/bin/gdb'}
            if 'Makefile' not in names:
                config['preLaunchTask'] = build
            data.setdefault('launch', {'version': '0.2.0', 'configurations': [config]})
        temporary = '.practice-workspace-' + os.urandom(8).hex()
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(data, stream, indent=2)
                os.fchown(stream.fileno(), owner.st_uid, owner.st_gid)
            os.rename(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
    return str(Path(path) / name)


def active_editor_target(config, home, active):
    """Return to the original project workspace, retaining its tasks and debugger."""
    module = str(config.get('module', ''))
    hw = str(config.get('hw') or '')
    if not hw:
        match = re.search(r'(\d+)', module)
        hw = match[1] if match else ''
    if config.get('course_code') == 'cse545' and not hw:
        workspace = Path(home) / module / ('lab--' + str(config['level']) + '.code-workspace')
    elif hw:
        workspace = active.parent / ('proj-' + hw + '-' + str(config['level']) + '.code-workspace')
    else:
        workspace = Path(home) / module / 'exam.code-workspace'
    return {'workspace': str(workspace)} if workspace.is_file() else {'folder': str(active)}

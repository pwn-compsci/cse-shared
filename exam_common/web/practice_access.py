"""Startup prerequisite enforcement and editor lock screen for Practice Exam 40."""
import html
import json
import os
from pathlib import Path
import secrets
import shutil
import sys

import requests

CONFIG = Path('/challenge/.config/level.json')
STATE = Path('/opt/practice_access.json')


def destroy_templates(root=Path('/challenge')):
    # Never follow student-controlled links when deleting template trees.
    for directory, subdirs, _ in os.walk(root, followlinks=False):
        for name in list(subdirs):
            if name == 'template':
                target = Path(directory) / name
                if target.is_symlink():
                    target.unlink()
                else:
                    shutil.rmtree(target)
                subdirs.remove(name)
    stash = Path('/opt/exam_template')
    if stash.is_symlink():
        stash.unlink()
    elif stash.exists():
        shutil.rmtree(stash)


def startup(user_id, admin):
    config = json.loads(CONFIG.read_text())
    if config.get('module') != 'pex40':
        return
    from exam_attempt_reporter import API_TOKEN
    try:
        response = requests.post('https://api.cse545.com/exam-gates/checkstatus',
                                 headers={'X-API-Token': API_TOKEN},
                                 json={'pwn_college_id': user_id, 'module': 'pex40',
                                       'challenge': config.get('examLevel') or 'level-40-' + str(config['level']).zfill(2)},
                                 timeout=15)
        response.raise_for_status()
        status = response.json()
        if status.get('status') != 'success' or status.get('allowed') is not True:
            status['allowed'] = False
    except Exception:
        status = dict(allowed=False, message='Could not verify your prerequisites. Wait a few minutes and restart the challenge to try again.')
    status['admin'] = admin
    # Publish a private root-owned launch decision before starter files are copied.
    fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(status, stream)
    if not status['allowed'] and not admin:
        destroy_templates()


def register_routes(app):
    from flask import request
    bypass_token = secrets.token_urlsafe(32)
    bypassed = False

    @app.before_request
    def practice_access_gate():
        nonlocal bypassed
        try:
            config = json.loads(CONFIG.read_text())
            if config.get('module') != 'pex40':
                return None
            status = json.loads(STATE.read_text())
        except Exception:
            # A missing startup decision must never expose a pex40 editor.
            if 'config' not in locals() or config.get('module') != 'pex40':
                return None
            status = dict(allowed=False, message='Practice access has not been verified. Please restart this challenge.')
        if status.get('allowed') is True or bypassed:
            return None
        admin = status.get('admin') is True
        if admin and request.method == 'POST' and secrets.compare_digest(request.form.get('practice_admin_bypass', ''), bypass_token):
            bypassed = True
            return '<script>location.replace(location.pathname)</script>'
        items = []
        for requirement in status.get('unmet_requirements', status.get('requirements', [])):
            label = requirement.get('required_assignment_name') or requirement.get('required_assignment_module_id') or 'Required coursework'
            missing = ', '.join(str(level) for level in requirement.get('missing_levels', []))
            items.append('<li><strong>' + html.escape(str(label)) + '</strong>: ' + html.escape(missing or str(requirement.get('detail', 'Incomplete'))) + '</li>')
        control = (f'<form method="post" class="admin"><button title="Admin: bypass prerequisites and open editor" name="practice_admin_bypass" value="{bypass_token}">▪</button></form>' if admin else '')
        return ('<!doctype html><html><head><meta charset="utf-8"><title>Practice prerequisites</title>'
                '<style>body{background:#1e1e1e;color:#eee;font:16px system-ui;margin:8vh auto;padding:24px;max-width:760px;line-height:1.6}'
                'h1{color:#71baff}li{margin:12px 0}.admin{position:fixed;bottom:8px;right:8px}.admin button{background:none;border:0;color:#888;cursor:pointer}</style></head><body>'
                '<h1>Complete these prerequisites first</h1><p>This practice problem is locked until you complete its associated coursework.</p><ul>' + ''.join(items) + '</ul><p>' + html.escape(str(status.get('message') or '')) + '</p>'
                '<p>If you just submitted a needed flag, wait a few minutes for it to sync, then restart this challenge from the course page.</p>'
                '<p>Your starter code will be created on an eligible restart.</p>' + control + '</body></html>'), 200, {'Cache-Control': 'no-store'}


if __name__ == '__main__':
    if sys.argv[1] == '--startup':
        startup(sys.argv[2], sys.argv[3] == 'true')
    elif sys.argv[1] == '--cleanup' and STATE.exists():
        status = json.loads(STATE.read_text())
        if not status.get('allowed') and not status.get('admin'):
            destroy_templates()

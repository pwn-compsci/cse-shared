"""Practice 20/03 tutor bridge; credentials and identity never come from the browser."""
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
import requests
from flask import abort, jsonify, request, Response

CONFIG = Path('/challenge/.config/level.json')
SECRET = Path('/opt/practice_tutor.json')


def enabled():
    try:
        config = json.loads(CONFIG.read_text())
        return (config.get('module') == 'pex20' and config.get('challenge') == 'level-20-03'
                and bool(config.get('is_practice_exam') or config.get('practice_exam'))
                and config.get('practice_tutor', {}).get('enabled') is True
                and config['practice_tutor'].get('course_dir') == '/cse/cse240-fc26')
    except (OSError, ValueError):
        return False


def register_routes(app, identity, authenticated):
    tokens = set()

    @app.get('/exam_api/tutor/')
    def chat_page():
        check()
        return Response(Path(__file__).with_name('practice_tutor.html').read_text(), mimetype='text/html', headers={'Cache-Control': 'no-store'})

    @app.get('/exam_api/tutor/widget.js')
    def widget():
        if not enabled():
            return Response('', mimetype='text/javascript', headers={'Cache-Control':'no-store'})
        return Response(Path(__file__).with_name('practice_tutor.js').read_text(), mimetype='text/javascript', headers={'Cache-Control':'no-store'})

    def check():
        if not enabled():
            abort(404)
        if not authenticated():
            abort(403)
        # JSON-only + per-process token blocks
        # ordinary cross-site form submissions. Never enable CORS here.
        if request.method == 'POST' and request.headers.get('X-Tutor-Token') not in tokens:
            abort(403)

    @app.get('/exam_api/tutor/session')
    def session():
        check()
        token = secrets.token_urlsafe(32)
        if len(tokens) >= 100:
            tokens.clear()
        tokens.add(token)
        return jsonify(token=token), 200, {'Cache-Control': 'no-store'}

    def settings():
        try:
            result = json.loads(SECRET.read_text())
        except (OSError, ValueError):
            result = {}
        if result.get('expires_at', 0) < time.time() + 60:
            subprocess.run([sys.executable, '/opt/practice-tutor/install.py', '--credentials'],
                cwd='/', env={'PATH': '/usr/bin:/bin'}, capture_output=True, timeout=12, check=True)
            result = json.loads(SECRET.read_text())
        return result

    def collect():
        # The web service runs as root. Student-controlled paths and SQLite databases
        # must be read by hacker, never by root. Do not inherit service credentials.
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('tutor_context.py'))],
            user='hacker', group='hacker', extra_groups=[], cwd='/',
            env={'PATH': '/usr/bin:/bin', 'HOME': '/home/hacker'},
            capture_output=True, timeout=8, check=True)
        return json.loads(result.stdout)

    @app.get('/exam_api/tutor/history')
    def history():
        check()
        before = request.args.get('before')
        if before and len(before) > 200:
            abort(400)
        try:
            credentials = settings()
            payload = dict(pwn_college_id=identity(), module='pex20', challenge='level-20-03', variant='a')
            if before:
                payload['before'] = before
            reply = requests.post('https://api.cse545.com/api/chatbot/history', json=payload,
                headers={'Authorization':'Bearer ' + credentials['endpoint_key']}, timeout=(5,15))
            return jsonify(reply.json()), reply.status_code, {'Cache-Control':'no-store'}
        except Exception:
            return jsonify(error='Aita history is unavailable; please try again'), 503

    @app.post('/exam_api/tutor/context')
    def context():
        check()
        return jsonify(collect()), 200, {'Cache-Control': 'no-store'}

    @app.post('/exam_api/tutor/messages')
    def message():
        check()
        if not request.is_json or (request.content_length or 0) > 5000:
            abort(400)
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get('message'), str) or not 1 <= len(data['message'].strip()) <= 2000:
            abort(400)
        try:
            credentials = settings()
            payload = dict(pwn_college_id=identity(), module='pex20', challenge='level-20-03',
                           variant='a', message=data['message'], context=collect(),
                           conversation_id=data.get('conversation_id'))
            reply = requests.post('https://api.cse545.com/api/chatbot/messages', json=payload,
                                  headers={'Authorization': 'Bearer ' + credentials['endpoint_key']}, timeout=(5, 60))
            headers = {'Cache-Control':'no-store'}
            if reply.headers.get('Retry-After'):
                headers['Retry-After'] = reply.headers['Retry-After']
            return jsonify(reply.json()), reply.status_code, headers
        except Exception:
            return jsonify(error='Tutor unavailable; please try again shortly'), 503

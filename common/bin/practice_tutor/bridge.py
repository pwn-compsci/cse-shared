"""Practice 30/02 tutor bridge; credentials and identity never come from the browser."""
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
        import importlib.util
        spec = importlib.util.spec_from_file_location('aita_scope', Path(__file__).with_name('eligibility.py'))
        scope = importlib.util.module_from_spec(spec); spec.loader.exec_module(scope)
        config = json.loads(CONFIG.read_text())
        settings = json.loads(SECRET.read_text())
        return (scope.enabled(config) and settings.get('module') == config['module']
                and settings.get('challenge') == config['challenge'])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def target():
    try:
        config = json.loads(CONFIG.read_text())
        return dict(module=config['module'], challenge=config['challenge'], variant='a')
    except OSError:
        return dict(module='25-proj-mud', challenge='p25-level-01', variant='a')


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
        if target()['module'] != 'pex30':
            return jsonify(token=token), 200, {'Cache-Control': 'no-store'}
        try:
            selected = collect(request.args.get('attempt'))
        except Exception:
            return jsonify(error='This attempt cannot be identified. Return to practice choices and select a recorded attempt.'), 409
        return jsonify(token=token, selection=selected['selection']), 200, {'Cache-Control': 'no-store'}

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

    def collect(attempt=None):
        # The web service runs as root. Student-controlled paths and SQLite databases
        # must be read by hacker, never by root. Do not inherit service credentials.
        options = {}
        command = [sys.executable, str(Path(__file__).with_name('tutor_context.py'))]
        if target()['module'] == 'pex30':
            from tutor_selection import resolve
            options = dict(input=json.dumps(resolve(attempt)), text=True)
            command.append('--practice')
        result = subprocess.run(command, **options,
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
            selected = collect(request.args.get('attempt'))
            payload = dict(pwn_college_id=identity(), **target())
            if 'selection' in selected:
                payload['variant'] = selected['selection']['key']
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
        return jsonify(collect(request.args.get('attempt'))), 200, {'Cache-Control': 'no-store'}

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
            selected = collect(data.get('attempt'))
            if 'selection' in selected and selected['selection']['key'] != data.get('context_key'):
                return jsonify(error='The selected attempt changed. Reload Aita before sending.'), 409
            payload = dict(pwn_college_id=identity(), **target(),
                           message=data['message'], context=selected,
                           conversation_id=data.get('conversation_id'))
            if 'selection' in selected:
                payload['variant'] = selected['selection']['key']
            reply = requests.post('https://api.cse545.com/api/chatbot/messages', json=payload,
                                  headers={'Authorization': 'Bearer ' + credentials['endpoint_key']}, timeout=(5, 60))
            headers = {'Cache-Control':'no-store'}
            if reply.headers.get('Retry-After'):
                headers['Retry-After'] = reply.headers['Retry-After']
            return jsonify(reply.json()), reply.status_code, headers
        except Exception:
            return jsonify(error='Tutor unavailable; please try again shortly'), 503

"""Exercise passive timing without starting a challenge or contacting exam APIs."""
import ast
import logging
import os
from datetime import datetime, timezone
from functools import wraps
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from time import monotonic
import unittest
from unittest.mock import Mock

from flask import Flask, g, request, redirect

ROOT = Path(__file__).parent
VARIANTS = ('common', 'exam_common')


class ExamTimingTests(unittest.TestCase):
    def load_timing(self, variant):
        source = (ROOT / variant / 'web/app.py').read_text()
        tree = ast.parse(source)
        names = {'configure_exam_timing_logger', 'log_exam_timing', 'timed_exam_check', 'begin_exam_request_timing',
                 'finish_exam_request_timing'}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        namespace = dict(app=Flask(variant), g=g, request=request, wraps=wraps,
                         monotonic=monotonic, json=json, logger=Mock(), os=os, logging=logging,
                         datetime=datetime, timezone=timezone, persistent_exam_timing_logger=None)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), variant, 'exec'), namespace)
        return namespace

    def test_timings_persist_after_container_log_directory_disappears(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as home:
                ns = self.load_timing(variant)
                startup = Path(home, "startup-attempt.log")
                startup.touch()
                with tempfile.TemporaryDirectory() as container:
                    pointer = Path(container, "startup_log_path")
                    pointer.write_text(str(startup))
                    persistent = ns['configure_exam_timing_logger'](str(pointer))
                    self.assertIsNotNone(persistent)
                    ns['persistent_exam_timing_logger'] = persistent
                    ns['logger'].info.side_effect = RuntimeError('container logger unavailable')
                    ns['log_exam_timing']('request_end', status=302)
                    for handler in persistent.handlers:
                        handler.close()
                records = Path(home, "startup-attempt-web-timing.jsonl").read_text().splitlines()
                self.assertEqual(json.loads(records[0])['status'], 302)
                self.assertIsNone(ns['configure_exam_timing_logger'](str(pointer)))

    def test_proxy_log_symlink_persists_in_course_home(self):
        source = (ROOT / 'common/.examsetup').read_text()
        block = source.split('# Persist passive proxy timings', 1)[1].split('\n', 1)[1].split('# Start nginx with error checking', 1)[0]
        with tempfile.TemporaryDirectory() as home:
            startup = Path(home, 'startup-attempt.log')
            startup.touch()
            with tempfile.TemporaryDirectory() as container:
                block = block.replace('/var/log/nginx', container + '/nginx')
                result = subprocess.run(['bash', '-c', block], env={**os.environ, 'STARTUP_LOG': str(startup)}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                with Path(container, 'nginx/exam-timing.log').open('a') as log:
                    log.write('{"status":200}\n')
            self.assertEqual(json.loads(Path(home, 'startup-attempt-proxy-timing.jsonl').read_text())['status'], 200)

    def test_response_and_auth_cookie_survive_logging_failure(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                ns = self.load_timing(variant)
                app = ns['app']
                def login():
                    response = redirect('/')
                    response.set_cookie('auth_token', 'test-token', httponly=True)
                    return response
                app.add_url_rule('/login', view_func=login, methods=['POST'])
                for broken in (False, True):
                    ns['logger'].info.side_effect = RuntimeError('disk full') if broken else None
                    response = app.test_client().post('/login?secret=query-secret', data={'password': 'body-secret'})
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.headers['Location'], '/')
                    self.assertIn('auth_token=test-token', response.headers['Set-Cookie'])
                records = [json.loads(call.args[1]) for call in ns['logger'].info.call_args_list]
                self.assertEqual([r['event'] for r in records], ['request_start', 'request_end'] * 2)
                self.assertNotIn('secret', json.dumps(records))
                self.assertNotIn('test-token', json.dumps(records))

    def test_checks_preserve_results_arguments_and_exceptions(self):
        for variant in VARIANTS:
            ns = self.load_timing(variant)
            result = object()
            check = Mock(return_value=result)
            check.__name__ = 'check_password_api'
            measured = ns['timed_exam_check'](check)
            self.assertIs(measured('student', password='secret'), result)
            check.assert_called_once_with('student', password='secret')
            ns['logger'].info.side_effect = RuntimeError('log failure')
            self.assertIs(measured('student'), result)
            failure = ValueError('original failure')
            check.side_effect = failure
            with self.assertRaises(ValueError) as caught:
                measured()
            self.assertIs(caught.exception, failure)

    def test_nginx_configs_validate_and_keep_routing(self):
        nginx = shutil.which('nginx')
        self.assertIsNotNone(nginx, 'nginx is required for config validation')
        for variant in VARIANTS:
            source = (ROOT / variant / 'web/nginx.conf').read_text()
            self.assertIn('proxy_pass $upstream_target;', source)
            self.assertIn('auth_token=LETMEIN', source)
            self.assertIn('proxy_set_header Upgrade $http_upgrade;', source)
            self.assertIn('proxy_read_timeout 300;', source)
            # Validate the full template and the CSE240 desktop-stripped version.
            for course in ('cse240', 'cse545'):
                with self.subTest(variant=variant, course=course), tempfile.TemporaryDirectory() as directory:
                    config = source
                    if course == 'cse240':
                        config = re.sub(r' *# BEGIN_CSE545_DESKTOP.*?# END_CSE545_DESKTOP[^\n]*\n', '', config, flags=re.S)
                    config = config.replace('/var/log/nginx/', directory + '/')
                    config = f'pid {directory}/nginx.pid;\nerror_log {directory}/error.log;\n' + config
                    path = Path(directory) / 'nginx.conf'
                    path.write_text(config)
                    result = subprocess.run([nginx, '-t', '-p', directory + '/', '-c', str(path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_real_proxy_logs_auth_assets_and_upstream_delay(self):
        class Upstream(BaseHTTPRequestHandler):
            def do_GET(self):
                time.sleep(0.025)
                body = b"editor-ok" if self.headers.get('Cookie') else b"login-ok"
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for variant in VARIANTS:
                with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                    source = (ROOT / variant / 'web/nginx.conf').read_text()
                    source = re.sub(r' *# BEGIN_CSE545_DESKTOP.*?# END_CSE545_DESKTOP[^\n]*\n', '', source, flags=re.S)
                    # Isolated listeners and mock upstream; production routing is unchanged.
                    port_map = {}
                    def replace_listener(match):
                        with socket.socket() as sock:
                            sock.bind(('127.0.0.1', 0))
                            port = sock.getsockname()[1]
                        port_map[match.group(1)] = port
                        return f'listen 127.0.0.1:{port};'
                    source = re.sub(r'listen (\d+);', replace_listener, source)
                    for port in (4200, 5000, 7682):
                        source = re.sub(rf'127\.0\.0\.1:{port}(?![0-9])', f'127.0.0.1:{server.server_port}', source)
                    source = source.replace('/var/log/nginx/', directory + '/')
                    source = source.replace('/challenge/web/js/', directory + '/js/')
                    Path(directory, 'js').mkdir()
                    Path(directory, 'js/exam-badge.js').write_text('// badge asset')
                    source = (f'daemon off;\npid {directory}/nginx.pid;\n'
                              f'error_log {directory}/error.log;\n' + source)
                    path = Path(directory, 'nginx.conf')
                    path.write_text(source)
                    process = subprocess.Popen([shutil.which('nginx'), '-p', directory + '/', '-c', str(path)],
                                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    try:
                        for attempt in range(100):
                            try:
                                with socket.create_connection(('127.0.0.1', port_map['8080']), timeout=0.1):
                                    break
                            except OSError:
                                if process.poll() is not None:
                                    self.fail(process.stderr.read().decode())
                                time.sleep(0.01)
                        url = f"http://127.0.0.1:{port_map['8080']}"
                        for route, headers, expected in (
                            ('/?token=query-secret', {}, b'login-ok'),
                            ('/editor?token=query-secret', {'Cookie': 'auth_token=LETMEIN'}, b'editor-ok'),
                            ('/js/exam-badge.js?v=123', {}, b'// badge asset'),
                        ):
                            with urlopen(Request(url + route, headers=headers), timeout=3) as response:
                                self.assertEqual(response.status, 200)
                                self.assertEqual(response.read(), expected)
                    finally:
                        process.terminate()
                        process.communicate(timeout=5)
                    records = [json.loads(line) for line in Path(directory, 'exam-timing.log').read_text().splitlines()]
                    self.assertEqual([r['uri'] for r in records], ['/', '/editor', '/js/exam-badge.js'])
                    for record in records[:2]:
                        self.assertGreaterEqual(float(record['upstream_response_time']), 0.02)
                    self.assertNotIn('query-secret', json.dumps(records))
                    self.assertNotIn('LETMEIN', json.dumps(records))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()

"""Exercise the real exam login branches without starting services or calling APIs."""
import ast
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, mock_open

from flask import Flask, request, render_template_string, make_response, redirect


class ExamCheckinAccessTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parent / 'exam_common/web/app.py'
        tree = ast.parse(path.read_text())
        names = {'process_login', 'render_exam_checkin_required', 'is_admin_bypass_user',
                 'normalized_exam_admin_type', 'is_honorlock_exam', 'is_lockdown_browser_exam',
                 'requires_attendance_monitoring', 'requires_active_proctor_session',
                 'requires_exam_password', 'is_proctoring_only'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.app = Flask(__name__)
        self.ns = dict(request=request, render_template_string=render_template_string,
                       make_response=make_response, redirect=redirect, logger=Mock(),
                       datetime=datetime, timezone=timezone, timedelta=timedelta,
                       pwn_college_id='123456', BYPASS_RLDB_IDS={200817},
                       exam_admin_type='Proctoring plus Lockdown Browser', is_practice_exam=False,
                       exam_module='exam30', exam_challenge='exam-30-01',
                       last_session_attendance_error='No current check-in found.',
                       has_exam_admin_type_lookup_error=lambda: False,
                       can_resume_started_code_server=Mock(return_value=False),
                       check_exam_gate_status=Mock(return_value={'allowed': True}),
                       check_session_attendance=Mock(return_value=(False, None)),
                       check_password_api=Mock(return_value=True),
                       build_authenticated_redirect=Mock(return_value='resumed'),
                       check_code_server_status=Mock(return_value=True), start_exam_reporter=Mock(),
                       loginpage=Mock(return_value='password prompt'), render_gate_denied=Mock(return_value='gate denied'),
                       os=SimpleNamespace(path=SimpleNamespace(exists=lambda _: False), chown=Mock(), chmod=Mock()),
                       open=mock_open(), CODESERVER_TRACK_FILE='/test/started.dat',
                       shapass='test-only', backdoor_token_password='test-only-backdoor')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), self.ns)

    def login(self, password=None, url='/', method='GET'):
        with self.app.test_request_context(url, method=method):
            return self.ns['process_login'](password, '127.0.0.1')

    def assert_checkin_denied(self, response):
        html, status = response
        self.assertEqual(status, 403)
        self.assertIn('Exam check-in required', html)
        self.assertIn('exam files', html)
        self.ns['build_authenticated_redirect'].assert_not_called()
        self.ns['start_exam_reporter'].assert_not_called()

    def test_regular_student_missing_or_unavailable_attendance_is_blocked(self):
        for attendance in (None, (False, None)):
            for resumed in (False, True):
                with self.subTest(attendance=attendance, resumed=resumed):
                    self.ns['can_resume_started_code_server'].return_value = resumed
                    self.ns['check_session_attendance'].return_value = attendance
                    self.assert_checkin_denied(self.login())

    def test_attendance_required_exam_types_block_missing_checkin(self):
        for exam_type in ('Proctoring', 'Proctoring plus Lockdown Browser', 'Honorlock'):
            with self.subTest(exam_type=exam_type):
                self.ns['exam_admin_type'] = exam_type
                self.assert_checkin_denied(self.login())

    def test_new_attempt_still_enforces_retry_gate(self):
        self.ns['check_session_attendance'].return_value = (True, 'session-password')
        self.ns['check_exam_gate_status'].return_value = {'allowed': False}
        self.assertEqual(self.login(), 'gate denied')
        self.ns['build_authenticated_redirect'].assert_not_called()

    def test_password_cannot_override_missing_attendance(self):
        self.assert_checkin_denied(self.login(password='valid-password', method='POST'))
        self.ns['check_password_api'].assert_not_called()

    def test_browser_only_exception_still_requires_checkin(self):
        self.ns['pwn_college_id'] = '201405'
        self.assert_checkin_denied(self.login())

    def test_current_attendance_allows_resume_without_reapplying_retry_gate(self):
        self.ns['can_resume_started_code_server'].return_value = True
        self.ns['check_session_attendance'].return_value = (True, 'session-password')
        self.assertEqual(self.login(), 'resumed')
        self.ns['check_session_attendance'].assert_called_once()
        self.ns['check_exam_gate_status'].assert_not_called()

    def test_regular_checked_in_student_can_start(self):
        self.ns['check_session_attendance'].return_value = (True, 'session-password')
        response = self.login()
        self.assertEqual(response, 'resumed')
        self.ns['build_authenticated_redirect'].assert_called_once()
        self.ns['check_exam_gate_status'].assert_called_once()
        self.ns['start_exam_reporter'].assert_called_once()

    def test_admin_without_checkin_gets_explanation_before_preview(self):
        self.ns['pwn_college_id'] = '200817'
        response = self.login()
        self.assert_checkin_denied(response)
        self.assertIn('administrator access', response[0])
        self.assertIn('?admin_preview=1', response[0])
        self.ns['can_resume_started_code_server'].return_value = True
        self.assertEqual(self.login(url='/?admin_preview=1'), 'resumed')

    def test_preview_query_does_not_bypass_regular_student_attendance(self):
        self.assert_checkin_denied(self.login(url='/?admin_preview=1'))

    def test_practice_does_not_require_checkin(self):
        self.ns['is_practice_exam'] = True
        response = self.login()
        self.assertEqual(response, 'resumed')
        self.ns['check_session_attendance'].assert_not_called()

    def test_attendance_detail_is_escaped(self):
        self.ns['last_session_attendance_error'] = '<script>alert(1)</script>'
        html, _ = self.login()
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)


if __name__ == '__main__':
    unittest.main()

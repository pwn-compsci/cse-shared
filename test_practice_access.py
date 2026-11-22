import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
from flask import Flask

sys.path.insert(0, str(Path(__file__).parent / 'exam_common/web'))
import practice_access as pa


class PracticeAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / 'level.json'
        self.state = Path(self.tmp.name) / 'access.json'
        self.config.write_text(json.dumps(dict(module='pex40', examLevel='level-40-01')))
        for name, value in [('CONFIG', self.config), ('STATE', self.state)]:
            p = patch.object(pa, name, value)
            p.start()
            self.addCleanup(p.stop)

    def client(self, admin=False, allowed=False):
        self.state.write_text(json.dumps(dict(admin=admin, allowed=allowed, unmet_requirements=[dict(required_assignment_name='<MUD>', missing_levels=['p25-level-01'])])))
        app = Flask(__name__)
        pa.register_routes(app)
        app.add_url_rule('/', endpoint='editor', view_func=lambda: 'editor', methods=['GET', 'POST'])
        app.add_url_rule('/exam_api/private', endpoint='private', view_func=lambda: 'private')
        return app.test_client()

    def test_student_locked_on_all_routes_cannot_bypass(self):
        client = self.client()
        for path in ('/', '/exam_api/private'):
            response = client.get(path)
            self.assertIn(b'p25-level-01', response.data)
            self.assertIn(b'&lt;MUD&gt;', response.data)
            self.assertIn(b'wait a few minutes', response.data)
            self.assertNotIn(b'name="practice_admin_bypass"', response.data)
        self.assertNotEqual(client.post('/', data={'practice_admin_bypass': 'yes'}).data, b'editor')

    def test_admin_must_click_valid_control(self):
        import re
        client = self.client(admin=True)
        page = client.get('/').data.decode()
        token = re.search(r'name="practice_admin_bypass" value="([^"]+)"', page)[1]
        client.post('/', data={'practice_admin_bypass': token})
        self.assertEqual(client.get('/').data, b'editor')

    def test_allowed_and_other_modules(self):
        self.assertEqual(self.client(allowed=True).get('/').data, b'editor')
        self.config.write_text('{"module":"pex30"}')
        self.assertEqual(self.client().get('/').data, b'editor')

    def test_missing_state_locked(self):
        client = self.client()
        self.state.unlink()
        self.assertIn(b'not been verified', client.get('/').data)

    def test_locked_toolbar_discovery_is_forbidden(self):
        for admin in (False, True):
            client = self.client(admin=admin)
            response = client.get('/exam_api/practice-variants/available')
            self.assertEqual(response.status_code, 403)
            self.assertIn(b'Complete these prerequisites first', response.data)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.state.unlink()
            self.assertEqual(client.get('/exam_api/practice-variants/available').status_code, 403)

    def test_startup_removes_templates_only_for_denied_students(self):
        response = Mock()
        response.json.return_value = dict(status='success', allowed=False)
        with patch.object(pa.requests, 'post', return_value=response), patch.object(pa, 'destroy_templates') as destroy:
            pa.startup('123', False)
            destroy.assert_called_once()
            self.assertFalse(json.loads(self.state.read_text())['allowed'])
            destroy.reset_mock()
            pa.startup('123', True)
            destroy.assert_not_called()
        with patch.object(pa.requests, 'post', side_effect=OSError), patch.object(pa, 'destroy_templates') as destroy:
            pa.startup('123', False)
            destroy.assert_called_once()

    def test_removal_does_not_follow_template_symlink(self):
        root = Path(self.tmp.name) / 'challenge'
        root.mkdir()
        external = Path(self.tmp.name) / 'keep'
        external.mkdir()
        (external / 'main.cpp').write_text('student code')
        (root / 'template').symlink_to(external, target_is_directory=True)
        with patch.object(pa, 'Path', wraps=Path) as paths:
            # Keep cleanup's fixed private stash inside the temporary tree.
            paths.side_effect = lambda p: Path(self.tmp.name) / 'stash' if p == '/opt/exam_template' else Path(p)
            pa.destroy_templates(root)
        self.assertTrue((external / 'main.cpp').exists())
        self.assertFalse((root / 'template').is_symlink())


class DeniedLaunchLifecycleTests(unittest.TestCase):
    def test_denied_launch_preserves_existing_work_and_creates_no_archive(self):
        import shlex
        import subprocess
        root = Path(__file__).parent
        setup = (root / 'common/.examsetup').read_text()
        init = (root / 'common/.init').read_text()
        gate = setup[setup.index('# Check before selecting/generating'):setup.index('current_module=$(jq', setup.index('# Check before selecting/generating'))]
        staging = setup[setup.index('if [ -d /home/me ] ||'):setup.index('safe_mkdir_p $clevel_work_dir\n')]
        cleanup = init[init.index('# A refused launch has no persistent attempt directory'):]
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            active = base / 'levels/01'
            active.mkdir(parents=True)
            (active / 'main.cpp').write_text('existing student work')
            state = base / 'access.json'
            state.write_text('{"allowed": false, "admin": false}')
            # Use the real production decision, staging branch, and cleanup blocks.
            # Only the startup API call and absolute container paths are substituted.
            gate = gate.replace('/opt/practice_access.json', str(state)).replace('/opt/practice-denied.', str(base / 'practice-denied.'))
            cleanup = cleanup.replace('/opt/practice-denied.', str(base / 'practice-denied.'))
            script = '''set -e
jq() { echo pex40; }
cleanup_non_admin_challenge_artifacts() { :; }
python3() {
    if [ "$1" = /challenge/web/practice_access.py ]; then return 0; fi
    ''' + shlex.quote(sys.executable) + ''' "$@"
}
clevel_work_dir=''' + shlex.quote(str(active)) + '''
pwn_college_id=123
admin_access=false
STARTUP_LOG=''' + shlex.quote(str(base / 'startup.log')) + '\n' + gate + '\n' + staging + '''
test "$clevel_work_dir" != ''' + shlex.quote(str(active)) + '''
# Simulate files created by generic editor setup in its temporary directory.
printf scratch > "$clevel_work_dir/settings.json"
''' + cleanup + '\ntest ! -e "$practice_denied_work_dir"\n'
            subprocess.run(['bash', '-c', script], check=True, capture_output=True, text=True)
            self.assertEqual((active / 'main.cpp').read_text(), 'existing student work')
            self.assertEqual(list(active.parent.iterdir()), [active])
            self.assertFalse((base / 'horse.json').exists())
            self.assertFalse(list(base.glob('practice-denied.*')))


if __name__ == '__main__':
    unittest.main()

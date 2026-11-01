"""Verify the embedded terminal clipboard pilot without launching a real service."""
from pathlib import Path
import subprocess
import tempfile
import unittest


INIT = (Path(__file__).parent / 'common/.init').read_text()
SOURCE = (Path(__file__).parent / 'common/bin/terminal_clipboard.py').read_text()
PILOT = {'__name__': 'ultima_test'}
exec(compile(SOURCE, '<terminal clipboard installer>', 'exec'), PILOT)


class TerminalClipboardInitTests(unittest.TestCase):
    def test_all_students_and_activity_scope(self):
        allowed = PILOT['tracking_allowed']
        activities = [
            {'module': '25-lela-heap', 'challenge': 'lab2516-stack', 'labid': '2516'},
            {'module': '25-proj-mud', 'hw': '25-mud'},
            {'module': 'classlab01', 'labid': 'classlab01'},
            {'module': '21-grouplab-menu'},
        ]
        for identity in ('97168', '97169', '12345', '97167', 132329, ''):
            for activity in activities:
                with self.subTest(identity=identity, activity=activity):
                    self.assertTrue(allowed(activity, identity))
                    for exam in (True, '01', 'false', 1):
                        self.assertFalse(allowed(dict(activity, examLevel=exam), identity))
        for activity in (
            {}, {'module': '25-lela-heap', 'challenge': 'lec2513-the-heap'},
            {'module': 'exam20', 'labid': '20'}, {'module': 'pex23', 'hw': '23'},
            {'module': 'sandbox', 'labid': '00'},
        ):
            self.assertFalse(allowed(activity, '97168'))

    def test_patch_and_idempotence_and_changed_version_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / 'platform', root / 'patched'
            route = source / 'out/node/routes/vscode.js'
            html = source / 'lib/vscode/out/vs/code/browser/workbench/workbench.html'
            route.parent.mkdir(parents=True)
            html.parent.mkdir(parents=True)
            route.write_text('exports.router = express.Router();\nexports.wsRouter = {};')
            html.write_text('<head></head><body></body>')
            PILOT['prepare'](source, destination)
            self.assertEqual(route.read_text().count('ultima-terminal-event'), 0)
            patched = destination / route.relative_to(source)
            self.assertIn("metadataValue('pwn_college_id')", patched.read_text())
            self.assertIn('.local/share/ultima', patched.read_text())
            self.assertIn('ultima-terminal-clipboard.js',
                          (destination / html.relative_to(source)).read_text())
            PILOT['prepare'](source, destination)
            self.assertEqual(patched.read_text().count("router.post('/ultima-terminal-event'"), 1)
            (destination / '.ultima-patch.json').write_text('old-version')
            with self.assertRaisesRegex(RuntimeError, 'different patch'):
                PILOT['prepare'](source, destination)

    def test_unsupported_platform_is_not_patched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            route = root / 'out/node/routes/vscode.js'
            html = root / 'lib/vscode/out/vs/code/browser/workbench/workbench.html'
            route.parent.mkdir(parents=True)
            html.parent.mkdir(parents=True)
            route.write_text('unsupported layout')
            html.write_text('<head></head>')
            with self.assertRaisesRegex(RuntimeError, 'Unsupported'):
                PILOT['prepare'](root, root / 'patched')
            self.assertFalse((root / 'patched').exists())

    def test_shell_gate_allows_all_students_and_skips_exams(self):
        # Exercise the real shell exam guard.
        gate = INIT[INIT.index('# Terminal clipboard tracking:'):]
        gate = gate[gate.index('if [['):]
        condition = gate.split('; then', 1)[0]
        script = condition + '; then echo enabled; else echo skipped; fi'
        for identity, exam, expected in (
            ('97168', '', 'enabled'), ('97169', '', 'enabled'),
            ('97167', '', 'enabled'), ('97168', 'true', 'skipped'),
            ('97169', '01', 'skipped'), ('', '', 'enabled'),
        ):
            result = subprocess.run(['bash', '-c', script], capture_output=True,
                                    text=True, check=True,
                                    env={'pwn_college_id': identity, 'isExam': exam})
            self.assertEqual(result.stdout.strip(), expected)


if __name__ == '__main__':
    unittest.main()

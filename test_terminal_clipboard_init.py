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
            {'module': '23-proj-pointers', 'challenge': 'p23-level-01'},
            {'module': '25-proj-mud'}, {'module': '32-proj-mudshop'},
            {'module': '33-proj-pokemud'},
        ]
        for identity in ('97168', '97169', '12345', '97167', 132329, ''):
            for activity in activities:
                self.assertTrue(allowed(activity, identity))
                self.assertFalse(allowed(dict(activity, examLevel='exam-30-01'), identity))
            for module in ('pex20', 'pex30'):
                self.assertTrue(allowed({'module': module, 'examLevel': 'exam-30-01'}, identity))
        for activity in (
            {}, {'module': '25-lela-heap', 'labid': '2516'},
            {'module': 'classlab01', 'labid': 'classlab01'},
            {'module': '21-proj-c-intro-vars'}, {'module': 'exam30', 'hw': '30'},
            {'module': 'pretest'}, {'module': 'sandbox'}, {'module': 'pexploit'},
        ):
            self.assertFalse(allowed(activity, '97168'))

    def test_practice_launcher_preserves_arguments_and_sandbox(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node = root / 'mock node'
            node.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            node.chmod(0o755)
            PILOT['write_launcher'](root, node)
            result = subprocess.run([str(root / 'ultima-code-server'),
                                     '--bind-addr=127.0.0.1:4200',
                                     '--user-data-dir=/home/hacker/.local/share/code-server-exam',
                                     '/home/hacker/workspace with spaces.code-workspace'],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.splitlines(), [str(root / 'out/node/entry.js'),
                '--bind-addr=127.0.0.1:4200',
                '--user-data-dir=/home/hacker/.local/share/code-server-exam',
                '/home/hacker/workspace with spaces.code-workspace'])
        common = Path(__file__).parent / 'common'
        script = (common / 'vscode.sh').read_text()
        self.assertEqual(script, (common / 'bin/vscode.sh').read_text())
        self.assertIn('--prepare-launcher', script)
        self.assertIn('-- /run/dojo/bin/dojo-service start code-service/code-server', script)
        self.assertIn('          $clipboard_code_server', script)
        self.assertIn('--bind-addr=127.0.0.1:4200', script)
        self.assertIn('/run/dojo/bin/landrun', script)

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

    def test_editor_browser_and_route_without_clipboard_read_permission(self):
        import json
        subprocess.run(['node', str(Path(__file__).with_name('test_editor_clipboard.cjs'))],
                       input=json.dumps({'browser': PILOT['ASSET_CONTENTS']['browser.js'],
                                         'route': PILOT['ASSET_CONTENTS']['route.js']}),
                       text=True, check=True)

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

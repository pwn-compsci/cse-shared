"""Exercise the real handoff shell logic in isolated student directories."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path('/cse/intro-to-programming-languages/33-proj-pokemud/p33-level-01/.levelinit')

class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / 'work'
        self.work.mkdir()
        source = SOURCE.read_text()
        source = source[source.index('# Select a usable handoff'):]
        start = source.index('\nset -x')
        end = source.index('\nif [ -d "$latest_priorhw_level"', start)
        source = source[:start] + source[end:]
        source = source.replace('/home/hacker/cse240/32-proj-mudshop', str(self.root / 'mudshop'))
        source = source.replace('/challenge', str(self.root / 'challenge'))
        source = source.replace('/etc/bash.bashrc', str(self.root / 'bashrc'))
        source = source[:source.index('\nchown hacker:hacker')]
        (self.root / 'challenge').mkdir()
        self.script = 'hwdir=' + str(self.work) + '\n' + source

    def level(self, number, shop='implementation'):
        directory = self.root / 'mudshop' / number
        directory.mkdir(parents=True, exist_ok=True)
        for name, text in [('main.cpp', number), ('shop.cpp', shop), ('shop.h', shop)]:
            (directory / name).write_text(text)

    def run_init(self):
        return subprocess.run(['bash', '-c', self.script], capture_output=True, text=True).returncode

    def test_common_init_reaches_hook_without_source_files_and_continues(self):
        import json
        init = (Path(__file__).parent / 'common/.init').read_text()
        start = init.index("isExam=$(jq -r")
        end = init.index('# Select the build task', start)
        init = init[start:end]
        challenge = self.root / 'challenge'
        (challenge / '.config').mkdir()
        (challenge / '.config/level.json').write_text(json.dumps({'createHWDir': True}))
        (challenge / '.config/readme.html').write_text('<html><body>Requirements</body></html>')
        # Use the real prerequisite/handoff logic as the hook, with paths isolated.
        (challenge / '.levelinit').write_text(self.script)
        init = init.replace('/challenge', str(challenge))
        init = init.replace('/home/hacker', str(self.root / 'home'))
        init = init.replace('/etc/bash.bashrc', str(self.root / 'bashrc'))
        (self.root / 'home/.local/share/code-server').mkdir(parents=True)
        preamble = f"""
module=33-proj-pokemud
challenge=p33-level-01
course_code=cse240
clevel_work_dir={self.work}
STARTUP_LOG={challenge}/startup.log
admin_access=true
hw_id=33
start_time=$(date +%s)
safe_root_mutation_path() {{ return 0; }}
safe_mkdir_p() {{ mkdir -p "$@"; }}
safe_chown() {{ :; }}
copy_solve_templates_to_workdir() {{ :; }}
copy_challenge_template_to_workdir() {{ :; }}
configure_user_vscode_settings() {{ :; }}
timed_startup_step() {{ :; }}
startup_timing_begin() {{ :; }}
startup_timing_end() {{ :; }}
"""
        # Test both a new workspace and repeated launches of an empty workspace.
        for fresh in (True, False, False):
            if fresh:
                self.work.rmdir()
            result = subprocess.run(['bash', '-c', preamble + init + '\necho INIT_CONTINUED'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('INIT_CONTINUED', result.stdout)
            self.assertFalse((self.work / 'main.cpp').exists())
            log = (challenge / 'startup.log').read_text()
            self.assertIn('must complete through level 7', log)
            self.assertIn('.levelinit failed with exit code 1', log)
            self.assertIn('cse240-init-alert', (challenge / '.config/readme.html').read_text())

    def test_prefers_seven(self):
        self.level('07'); self.level('06')
        self.assertEqual(self.run_init(), 0)
        self.assertEqual((self.work / 'main.cpp').read_text(), '07')

    def test_falls_back_to_six_when_seven_is_empty(self):
        self.level('07', ''); self.level('06')
        self.assertEqual(self.run_init(), 0)
        self.assertEqual((self.work / 'main.cpp').read_text(), '06')

    def test_repeated_failure_then_recovery(self):
        self.level('07', '   \n'); self.level('01')
        for _ in range(3):
            self.assertEqual(self.run_init(), 1)
            self.assertFalse((self.work / 'main.cpp').exists())
        self.level('07')
        self.assertEqual(self.run_init(), 0)
        self.assertEqual((self.work / 'main.cpp').read_text(), '07')
        self.assertFalse((self.work / '.mudshop-handoff-pending').exists())
        subprocess.run(['bash', '-n', str(self.root / 'bashrc')], check=True)

    def test_old_warning_recovers(self):
        (self.work / 'main.cpp').write_text('// You must complete MUDShop level 1')
        self.assertEqual(self.run_init(), 1)
        self.level('07')
        self.assertEqual(self.run_init(), 0)
        self.assertEqual((self.work / 'main.cpp').read_text(), '07')

    def test_existing_work_preserved(self):
        (self.work / 'main.cpp').write_text('student edits')
        self.assertEqual(self.run_init(), 1)
        self.level('07')
        self.assertEqual(self.run_init(), 0)
        self.assertEqual((self.work / 'main.cpp').read_text(), 'student edits')

if __name__ == '__main__':
    unittest.main()

import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sqlite3
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

from flask import Flask

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "exam_common/web"))
spec = importlib.util.spec_from_file_location("practice_variants", ROOT / "exam_common/web/practice_variants.py")
pv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pv)


class SelectionTests(unittest.TestCase):
    def test_random_avoids_last_and_retains_all_encounters(self):
        entry = {}
        for i in range(30):
            previous = entry.get("last")
            chosen = pv.select(entry, ["a", "b"], str(i))
            self.assertNotEqual(previous, chosen)
        self.assertEqual(set(entry["encountered"]), {"a", "b"})

    def test_existing_cycle_visits_unseen_before_repeating(self):
        entry = {"cycle": ["a"], "last": "a", "encountered": ["a"]}
        with patch.object(pv.secrets, "choice", side_effect=lambda choices: choices[0]):
            self.assertEqual(pv.select(entry, ["a", "b", "c"], "1"), "b")
            self.assertEqual(pv.select(entry, ["a", "b", "c"], "2"), "c")
            self.assertEqual(pv.select(entry, ["a", "b", "c"], "3"), "a")
        self.assertEqual(set(entry["encountered"]), {"a", "b", "c"})

    def test_single_version(self):
        entry = {}
        for i in range(3):
            self.assertEqual(pv.select(entry, ["a"], str(i)), "a")

    def test_retry_same_variant_and_idempotent_active_attempt(self):
        entry = {}
        pv.select(entry, ["a", "b"], "first", "a")
        pv.queue(entry, ["a", "b"], "retry", "a")
        self.assertEqual(pv.select(entry, ["a", "b"], "first"), "a")
        self.assertIn("pending", entry)
        self.assertEqual(pv.select(entry, ["a", "b"], "second"), "a")
        self.assertNotIn("pending", entry)

    def test_unseen_and_removed_retries_rejected(self):
        entry = {"encountered": ["a", "retired"]}
        for variant in ("b", "retired", "../a"):
            with self.assertRaises(ValueError):
                pv.queue(entry, ["a", "b"], "retry", variant)

    def test_removed_pending_retry_falls_back_to_random(self):
        entry = {"encountered": ["retired"], "last": "retired",
                 "pending": {"mode": "retry", "variant": "retired"}}
        self.assertEqual(pv.select(entry, ["a"], "new"), "a")
        self.assertIn("retired", entry["encountered"])

    def test_random_replaces_pending_retry(self):
        entry = {"encountered": ["a"], "last": "a"}
        pv.queue(entry, ["a", "b"], "retry", "a")
        pv.queue(entry, ["a", "b"], "random", None)
        self.assertEqual(pv.select(entry, ["a", "b"], "next"), "b")


@unittest.skipUnless(os.geteuid() == 0, "root-owned persistence tests; run with sudo")
class PersistenceAndUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.runtime = self.home / "runtime.json"
        self.config = {"module": "pex23", "level": "01", "is_practice_exam": True}
        self.config_path = self.home / "level.json"
        self.config_path.write_text(json.dumps(self.config))
        self.current = pv.launch(self.config, self.home, ["a", "secret-unseen"], "first", "a", self.runtime)
        self.app = Flask(__name__)
        pv.register_routes(self.app, self.config_path, self.runtime)
        self.client = self.app.test_client()
        self.url = "/exam_api/practice-variants"

    def token(self):
        text = self.client.get(self.url).get_data(as_text=True)
        return re.search(r'name="csrf" value="([^"]+)"', text).group(1)

    def test_ui_only_shows_encountered_variants(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("New Random Variant", text)
        self.assertIn("Retry a Previous Variant", text)
        self.assertNotIn("secret-unseen", text)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        # Course interfaces may embed the workspace from another origin.
        self.assertNotIn("X-Frame-Options", response.headers)

    def test_retry_persists_and_is_consumed_only_at_next_start(self):
        response = self.client.post(self.url, data={"csrf": self.token(), "mode": "retry", "variant": "a"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Selection saved", response.get_data(as_text=True))
        self.assertEqual(pv.launch(self.config, self.home, ["a", "secret-unseen"], "first", runtime=self.runtime), "a")
        self.assertEqual(pv.launch(self.config, self.home, ["a", "secret-unseen"], "second", runtime=self.runtime), "a")
        self.assertEqual(pv.launch(self.config, self.home, ["a", "secret-unseen"], "third", runtime=self.runtime), "secret-unseen")

    def test_next_start_choice_highlight_and_dropdown_persist(self):
        text = self.client.get(self.url).get_data(as_text=True)
        self.assertIn('aria-label="Close practice and return to editor"', text)
        self.assertRegex(text, r'<button class="primary" name="mode" value="random" aria-pressed="true">')
        self.assertIn('<option value="" disabled selected>', text)
        self.assertIn('aria-pressed="false" disabled>Start this variant fresh', text)
        self.client.post(self.url, data={'csrf': self.token(), 'mode': 'retry', 'variant': 'a'})
        text = self.client.get(self.url).get_data(as_text=True)
        self.assertIn('<option value="a" selected>', text)
        self.assertIn('id="fresh-choice" class="primary"', text)
        self.assertIn('value="random" aria-pressed="false"', text)
        self.client.post(self.url, data={'csrf': self.token(), 'mode': 'random'})
        text = self.client.get(self.url).get_data(as_text=True)
        self.assertIn('<option value="" disabled selected>', text)
        self.assertNotIn('<option value="a" selected>', text)
        self.assertIn('value="random" aria-pressed="true"', text)

    def test_resume_is_not_highlighted_as_start_fresh(self):
        active, saved = self.saved_attempt()
        self.client.post(self.url, data={'csrf': self.token(), 'mode': 'resume', 'attempt': saved['id']})
        text = self.client.get(self.url).get_data(as_text=True)
        self.assertIn('<option value="a" selected>', text)
        self.assertIn('Saved work will resume', text)
        self.assertIn('id="fresh-choice" class=""', text)
        self.assertIn('value="random" aria-pressed="false"', text)
        review = self.client.get(self.url, query_string={'attempt': saved['id']}).get_data(as_text=True)
        self.assertIn('aria-label="Close practice and return to editor"', review)

    def test_csrf_and_forged_retry(self):
        self.assertEqual(self.client.post(self.url, data={"mode": "random"}).status_code, 403)
        self.assertEqual(self.client.post(self.url, data={"csrf": self.token(), "mode": "retry", "variant": "secret-unseen"}).status_code, 400)

    def test_real_exam_has_no_chooser(self):
        self.config_path.write_text('{}')
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_missing_runtime_returns_service_unavailable(self):
        self.runtime.unlink()
        self.assertEqual(self.client.get(self.url).status_code, 503)

    def test_levels_are_isolated(self):
        other = dict(self.config, level="02")
        self.assertEqual(pv.launch(other, self.home, ["b"], "other", runtime=self.runtime), "b")
        history = json.loads((self.home / ".vscode/horse.json").read_text())
        self.assertEqual(len(history[pv.METADATA]), 2)

    def test_existing_horse_and_start_log_are_reused(self):
        path = self.home / ".vscode/horse.json"
        key = json.dumps(["pex30", "01"], separators=(",", ":"))
        history = {key: ["b"], "unrelated": ["z"]}
        path.write_text(json.dumps(history))
        (self.home / ".vscode/starts.log").write_text(
            "module=pex30|level=01|chosen_problem=a|starttime=old\n"
            "module=pex30|level=01|chosen_problem=b|starttime=recent\n"
            "module=pex300|level=01|chosen_problem=secret|starttime=recent\n")
        config = dict(self.config, module="pex30")
        chosen = pv.launch(config, self.home, ["a", "b", "c", "secret"], "new", runtime=self.runtime)
        history = json.loads(path.read_text())
        entry = history[pv.METADATA][key]
        self.assertIn("a", entry["encountered"])
        self.assertIn("b", entry["encountered"])
        self.assertNotEqual(chosen, "b")
        self.assertEqual(history["unrelated"], ["z"])
        self.assertEqual(history[key], entry["cycle"])
        pv.queue(entry, ["a", "b", "c", "secret"], "retry", "a")

    def saved_attempt(self):
        active = Path(json.loads(self.runtime.read_text())["workdir"])
        active.mkdir(parents=True, exist_ok=True)
        (active / "main.cpp").write_text('int old_answer = 7; // <script>bad()</script>')
        (active / "notes.txt").write_text("Review my loop boundary.")
        pv.launch(self.config, self.home, ["a", "secret-unseen"], "second", runtime=self.runtime)
        state = json.loads(self.runtime.read_text())
        history = json.loads(Path(state["history"]).read_text())
        saved = history[pv.METADATA][state["key"]]["attempts"][-1]
        return active, saved

    def test_assigned_variant_metadata_supports_real_and_practice_exams(self):
        chosen = self.config_path.with_name('chosen_problem.dat')
        chosen.write_text('chosen_problem=a\nchosen_problem=f\n')
        self.assertEqual(self.client.get('/exam_api/assigned-variant').json, {'variant': 'f', 'practice': True})
        self.config_path.write_text(json.dumps({'examLevel': 'exam-30-01'}))
        self.assertEqual(self.client.get('/exam_api/assigned-variant').json, {'variant': 'f', 'practice': False})
        self.config_path.write_text('{}')
        self.assertEqual(self.client.get('/exam_api/assigned-variant').status_code, 404)

    def test_practice_badge_is_compact_for_single_and_multiple_variants(self):
        response = self.client.get(self.url + '/badge')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'label': 'pex23 - 01a'})
        pv.launch(self.config, self.home, ['a'], 'second', runtime=self.runtime)
        self.assertEqual(self.client.get(self.url + '/badge').json, {'label': 'pex23 - 01a'})
        self.config_path.write_text('{}')
        self.assertEqual(self.client.get(self.url + '/badge').status_code, 404)

    def test_single_variant_hides_button_availability(self):
        self.assertEqual(self.client.get(self.url + "/available").status_code, 204)
        pv.launch(self.config, self.home, ["a"], "second", runtime=self.runtime)
        response = self.client.get(self.url + "/available")
        self.assertEqual(response.status_code, 404)
        self.config_path.write_text('{}')
        self.assertEqual(self.client.get(self.url + "/available").status_code, 404)

    def test_review_files_dates_and_read_only_escaping(self):
        active, saved = self.saved_attempt()
        active.mkdir(parents=True)
        (active / "main.cpp").write_text('new active work')
        response = self.client.get(self.url, query_string={"attempt": saved["id"], "file": "main.cpp"})
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn('old_answer', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertNotIn('<script>bad()', text)
        self.assertIn('MST', text)
        self.assertEqual((active / "main.cpp").read_text(), 'new active work')
        self.assertEqual(self.client.get(self.url, query_string={"attempt": "../other"}).status_code, 404)
        self.assertEqual(self.client.get(self.url, query_string={"attempt": saved["id"], "file": "../../secret"}).status_code, 400)

    def test_resume_is_deferred_preserves_current_work_and_restores_source(self):
        active, saved = self.saved_attempt()
        active.mkdir(parents=True)
        (active / "main.cpp").write_text('new active work')
        token = self.token()
        response = self.client.post(self.url, data={"csrf": token, "mode": "resume", "attempt": saved["id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((active / "main.cpp").read_text(), 'new active work')
        self.assertEqual(pv.launch(self.config, self.home, ["a", "secret-unseen"], "third", runtime=self.runtime), 'a')
        self.assertFalse(active.exists())
        active.mkdir()
        (active / "main.cpp").write_text('starter')
        with patch.object(pv.attempts.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=65534, pw_gid=65534)):
            pv.restore_current(self.runtime)
        self.assertIn('old_answer', (active / "main.cpp").read_text())
        self.assertTrue(any(p.read_text() == 'new active work' for p in active.parent.glob(active.name + '_*/main.cpp')))
        (active / "main.cpp").write_text('continued work')
        pv.restore_current(self.runtime)
        self.assertEqual((active / "main.cpp").read_text(), 'continued work')

    def test_open_saved_attempt_redirects_to_its_directory_without_restart(self):
        from urllib.parse import parse_qs, urlparse, urljoin
        active, saved = self.saved_attempt()
        active.mkdir(parents=True)
        (active / 'main.cpp').write_text('current code stays here')
        state_before = self.runtime.read_text()
        with patch.object(pv.review_editor, 'ensure_running') as ensure:
            response = self.client.get(self.url + '/open', query_string={'attempt': saved['id']})
        ensure.assert_called_once()
        self.assertNotIn(str(active), ensure.call_args.args[1])
        self.assertEqual(response.status_code, 302)
        redirect = urljoin('https://example.test/proxy/8080' + self.url + '/open', response.location)
        self.assertEqual(urlparse(redirect).path, '/proxy/8080/practice-editor/')
        query = parse_qs(urlparse(redirect).query)
        self.assertNotIn('file', query)
        workspace = Path(query['workspace'][0])
        folder = workspace.parent
        data = json.loads(workspace.read_text())
        self.assertEqual(data['folders'][0]['path'], '.')
        self.assertEqual(data['launch']['configurations'][0]['program'], '${workspaceFolder}/main.bin')
        self.assertIn('-g', data['tasks']['tasks'][-1]['args'])
        self.assertEqual(folder, active.parent / saved['directory'])
        self.assertNotEqual(folder, active)
        self.assertTrue(folder.is_dir())
        self.assertTrue(workspace.is_file())
        self.assertEqual(self.runtime.read_text(), state_before)
        self.assertEqual((active / 'main.cpp').read_text(), 'current code stays here')
        self.assertIn('old_answer', (folder / 'main.cpp').read_text())

    def test_saved_list_defaults_to_current_variant_and_opens_in_new_tab(self):
        active, saved = self.saved_attempt()
        # saved variant a differs from the current second variant.
        text = self.client.get(self.url).get_data(as_text=True)
        self.assertNotIn(saved['id'], text)
        text = self.client.get(self.url, query_string={'show': 'all'}).get_data(as_text=True)
        self.assertIn('Open saved attempt', text)
        self.assertIn(saved['id'], text)
        self.assertIn('target="_blank" rel="noopener"', text)
        self.assertIn('Back to current variant', text)
        # Re-selecting a makes that same entry visible by default.
        pv.launch(self.config, self.home, ['a', 'secret-unseen'], 'third', 'a', self.runtime)
        self.assertIn(saved['id'], self.client.get(self.url).get_data(as_text=True))

    def test_current_history_at_bottom_and_other_variants_on_separate_page(self):
        active, saved = self.saved_attempt()
        current = self.client.get(self.url).get_data(as_text=True)
        self.assertGreater(current.index('<section class="history">'), current.index('id="fresh-choice"'))
        self.assertIn('href="practice-variants/other"', current)
        other = self.client.get(self.url + '/other').get_data(as_text=True)
        self.assertIn('Other saved variants', other)
        self.assertIn(saved['id'], other)
        self.assertIn('tester -u', other)
        self.assertNotIn('id="random-title"', other)
        self.assertIn('href="open?attempt=', other)
        self.assertIn('href="../practice-variants"', other)
        pv.launch(self.config, self.home, ['a', 'secret-unseen'], 'third', 'a', self.runtime)
        self.assertNotIn(saved['id'], self.client.get(self.url + '/other').get_data(as_text=True))

    def test_review_tester_is_scoped_and_keeps_current_attempt_untouched(self):
        active, saved = self.saved_attempt()
        token = self.client.get(self.url + '/review-test').json['token']
        directory = str(active.parent / saved['directory'])
        def execute(command, **kwargs):
            self.assertEqual(command, ['/challenge/tester', '--use-current-dir'])
            self.assertEqual(os.path.realpath(kwargs['cwd']), directory)
            return SimpleNamespace(stdout='archived result', returncode=0)
        with patch.object(pv.subprocess, 'run', side_effect=execute) as run:
            response = self.client.post(self.url + '/review-test', json={'token': token, 'directory': directory, 'args': ['-u']})
            self.assertEqual(response.json, {'output': 'archived result', 'returncode': 0})
            run.assert_called_once()
        for path, arguments in ((str(active), ['-u']), (directory, ['--source-dir', '/etc']), (directory, [])):
            with patch.object(pv.subprocess, 'run') as run:
                self.assertEqual(self.client.post(self.url + '/review-test', json={'token': token, 'directory': path, 'args': arguments}).status_code, 400)
                run.assert_not_called()
        self.config_path.write_text('{}')
        self.assertEqual(self.client.get(self.url + '/review-test').status_code, 404)

    def test_exit_preserves_the_active_project_workspace(self):
        active = Path(json.loads(self.runtime.read_text())['workdir'])
        active.parent.mkdir(parents=True, exist_ok=True)
        project = active.parent / 'proj-23-01.code-workspace'
        project.write_text('{}')
        target = pv.attempts.active_editor_target(self.config, self.home, active)
        self.assertEqual(target, {'workspace': str(project)})
        text = self.client.get(self.url).get_data(as_text=True)
        self.assertIn('proj-23-01.code-workspace', text)

    def test_saved_workspace_preserves_custom_settings_and_targets_saved_folder(self):
        active, saved = self.saved_attempt()
        folder = active.parent / saved['directory']
        workspace = folder / '.practice-review.code-workspace'
        workspace.write_text(json.dumps({'folders': [{'path': str(active)}],
            'settings': {'editor.fontSize': 18}, 'tasks': {'tasks': [{'label': 'My task'}]}}))
        pv.attempts.saved_workspace(folder)
        data = json.loads(workspace.read_text())
        self.assertEqual(data['folders'][0]['path'], '.')
        self.assertEqual(data['settings']['editor.fontSize'], 18)
        self.assertFalse(data['settings']['terminal.integrated.enablePersistentSessions'])
        self.assertEqual(data['settings']['terminal.integrated.profiles.linux']['Saved practice shell']['args'],
                         [])
        self.assertEqual(data['settings']['terminal.integrated.profiles.linux']['Saved practice shell']['path'],
                         '/opt/practice-review-bin/shell')
        self.assertIn('My task', [t['label'] for t in data['tasks']['tasks']])
        self.assertEqual(data['launch']['configurations'][0]['cwd'], '${workspaceFolder}')

    def test_review_shell_preserves_course_prompt_and_aliases_but_overrides_tester(self):
        course = self.home / 'course.bashrc'
        course.write_text("CSE240_PS1='course prompt> '; alias bat='batcat --pager=never'; alias tester=/challenge/bin/exam_tester.sh; tester() { false; }; cd /tmp\n")
        (self.home / '.bashrc').write_text("alias ll='ls -alF'\n")
        hook = self.home / 'history.sh'
        hook.write_text(pv.review_editor.HISTORY_SETUP)
        startup = self.home / 'startup.sh'
        startup.write_text(pv.review_editor.SHELL_SETUP.replace('/etc/bash.bashrc', str(course)).replace('/opt/practice-review-bin/history.sh', str(hook)))
        script = 'shopt -s expand_aliases; source "$1"; test "$PS1" = "course prompt> " && alias bat && alias ll && ! alias tester 2>/dev/null && ! declare -F tester && eval cdhw && test "$PWD" = "$2" && declare -F __cse_log_cmd'
        result = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-c', script, 'review', str(startup), str(self.home)],
                                cwd=self.home, env=dict(os.environ, HOME=str(self.home)), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_review_shell_restores_history_hook_without_exam_aliases(self):
        helper = self.home / 'history.sh'
        helper.write_text(pv.review_editor.HISTORY_SETUP)
        script = 'PROMPT_COMMAND=__cse_log_cmd; source "$1"; source "$1"; declare -F __cse_log_cmd; test "$PROMPT_COMMAND" = __cse_log_cmd; ! alias tester 2>/dev/null'
        result = subprocess.run(['/bin/bash', '--noprofile', '--init-file', str(helper), '-i', '-c', script, 'review', str(helper)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('__cse_log_cmd', result.stdout)

    def test_review_server_uses_separate_profile_and_only_saved_folder_grants(self):
        student_home = self.home / 'student'
        student_home.mkdir()
        saved = self.home / 'saved'
        saved.mkdir()
        process = Mock(pid=123456789, poll=Mock(return_value=None))
        student = SimpleNamespace(pw_dir=str(student_home), pw_uid=65534, pw_gid=65534)
        state = self.home / 'review-server.json'
        editor = pv.review_editor
        with patch.object(editor, 'STATE', str(state)), patch.object(editor, 'BIN', str(self.home / 'review-bin')), patch.object(editor, 'LOG', str(self.home / 'review.log')), patch.object(editor.pwd, 'getpwnam', return_value=student), \
             patch.object(editor.os, 'getgrouplist', return_value=[65534]), patch.object(editor.os, 'access', return_value=True), \
             patch.object(editor.subprocess, 'Popen', return_value=process) as launch, patch.object(editor, 'ready', side_effect=[False, True]):
            editor.ensure_running(self.home, [str(saved)], pv.history_file)
        args, kwargs = launch.call_args
        command = args[0]
        self.assertIn(str(saved), command)
        self.assertIn('--bind-addr=127.0.0.1:4300', command)
        self.assertIn('--user-data-dir=' + str(student_home / '.local/share/code-server-practice-review'), command)
        self.assertNotIn(str(student_home), command)
        self.assertNotIn(str(self.home), command)
        self.assertEqual(kwargs['user'], 65534)
        self.assertEqual(kwargs['extra_groups'], [65534])
        self.assertTrue(kwargs['env']['PATH'].startswith('/challenge:'))
        with patch.object(editor, 'STATE', str(state)), patch.object(editor, 'BIN', str(self.home / 'review-bin')), patch.object(editor.pwd, 'getpwnam', return_value=student), patch.object(editor.os, 'kill'), \
             patch.object(editor, 'ready', return_value=True), patch.object(editor.subprocess, 'Popen') as launch:
            editor.ensure_running(self.home, [str(saved)], pv.history_file)
            launch.assert_not_called()

    def test_open_saved_attempt_rejects_paths_and_symlink_directories(self):
        active, saved = self.saved_attempt()
        endpoint = self.url + '/open'
        self.assertEqual(self.client.get(endpoint, query_string={'attempt': '../escape'}).status_code, 404)
        directory = active.parent / saved['directory']
        directory.rename(active.parent / 'moved')
        directory.symlink_to(active.parent / 'moved', target_is_directory=True)
        self.assertEqual(self.client.get(endpoint, query_string={'attempt': saved['id']}).status_code, 404)

    def test_review_excludes_hidden_tests_symlinks_and_hardlinks(self):
        active, saved = self.saved_attempt()
        directory = active.parent / saved['directory']
        (directory / 'system_tests').mkdir()
        (directory / 'system_tests/hidden.json').write_text('secret')
        (directory / 'escape.txt').symlink_to('/etc/passwd')
        os.link(directory / 'main.cpp', directory / 'linked.cpp')
        response = self.client.get(self.url, query_string={"attempt": saved['id']})
        text = response.get_data(as_text=True)
        self.assertNotIn('escape.txt', text)
        self.assertNotIn('hidden.json', text)
        self.assertNotIn('linked.cpp', text)
        self.assertEqual(self.client.get(self.url, query_string={"attempt": saved['id'], "file": 'escape.txt'}).status_code, 400)

    def test_legacy_folder_has_readable_date_and_no_guessed_variant(self):
        active = Path(json.loads(self.runtime.read_text())['workdir'])
        old = active.parent / (active.name + '_2026-11-21_2153')
        old.mkdir(parents=True)
        (old / 'main.cpp').write_text('earlier code')
        text = self.client.get(self.url, query_string={'show': 'all'}).get_data(as_text=True)
        self.assertIn('Nov 21, 2026 at 2:53:00 PM MST', text)
        self.assertIn('variant unknown', text)
        response = self.client.post(self.url, data={'csrf': self.token(), 'mode': 'resume', 'attempt': old.name})
        self.assertEqual(response.status_code, 400)

    def test_feedback_uses_attempt_window_and_correct_level(self):
        active, saved = self.saved_attempt()
        path = self.home / '.vscode/trdb.db'
        with sqlite3.connect(path) as conn:
            conn.execute('CREATE TABLE tests (timestamp TEXT, module TEXT, level TEXT, passed INTEGER, failed INTEGER, error_message TEXT)')
            conn.execute('INSERT INTO tests VALUES (?, ?, ?, ?, ?, ?)', ('2026-11-21 21:30:00', 'pex23', '01', 2, 1, 'compile error'))
            conn.execute('INSERT INTO tests VALUES (?, ?, ?, ?, ?, ?)', ('2026-11-21 21:30:00', 'pex23', '02', 99, 0, 'wrong level'))
        saved.update(started_at='2026-11-21T21:00:00+00:00', saved_at='2026-11-21T22:00:00+00:00')
        feedback = pv.attempts.feedback(self.home, self.config, saved)
        self.assertEqual(len(feedback), 1)
        self.assertEqual(feedback[0]['failed'], 1)
        self.assertEqual(feedback[0]['error_message'], 'compile error')

    def test_launchers_preserve_history_owner_and_repair_student_files(self):
        for name in ("common/vscode.sh", "common/bin/vscode.sh",
                     "common/bin/dojo-terminal.sh", "common/bin/dojo-desktop.sh"):
            with self.subTest(launcher=name):
                source = (ROOT / name).read_text()
                block = source.split("# BEGIN practice history ownership protection", 1)[1].split(
                    "# END practice history ownership protection", 1)[0]
                path = self.home / ".vscode/horse.json"
                os.chown(path, 0, 0)
                ordinary = self.home / "answer.cpp"
                ordinary.write_text("student source")
                os.chown(ordinary, 0, 0)
                # The actual shell fragment must leave the history root-owned.
                # This host has no hacker account; use an unprivileged numeric ID.
                block = block.replace("hacker", "65534")
                subprocess.run(["bash", "-c", block], check=True,
                               env=dict(os.environ, course_home=str(self.home)))
                self.assertEqual(path.stat().st_uid, 0)
                self.assertNotEqual(ordinary.stat().st_uid, 0)
                self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_symlink_and_hardlink_history_rejected(self):
        target = self.home / "target"
        target.write_text('{}')
        link = self.home / "link"
        link.symlink_to(target)
        with self.assertRaises(OSError):
            with pv.history_file(link):
                pass
        link.unlink()
        os.link(target, link)
        with self.assertRaises(ValueError):
            with pv.history_file(link):
                pass
        self.assertEqual(target.read_text(), '{}')

    def test_student_owned_history_migrates_with_backup_and_preserves_attempts(self):
        path = self.home / '.vscode/horse.json'
        original = path.read_text()
        old_inode = path.stat().st_ino
        os.chown(path, 65534, 65534)
        os.chmod(path, 0o664)
        chosen = pv.launch(self.config, self.home, ['a', 'secret-unseen'], 'second', runtime=self.runtime)
        self.assertEqual(chosen, 'secret-unseen')
        self.assertEqual(path.stat().st_uid, 0)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(path.stat().st_ino, old_inode)
        backups = list(path.parent.glob('horse.json.legacy-*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), original)
        entry = json.loads(path.read_text())[pv.METADATA]
        self.assertIn('a', next(iter(entry.values()))['encountered'])

    def test_unsafe_legacy_path_is_not_adopted(self):
        path = self.home / '.vscode/horse.json'
        data = json.loads(path.read_text())
        entry = next(iter(data[pv.METADATA].values()))
        entry['attempts'] = [{'id': 'escape', 'directory': '../../escape'}]
        original = json.dumps(data)
        path.write_text(original)
        os.chown(path, 65534, 65534)
        with self.assertRaises(ValueError):
            pv.launch(self.config, self.home, ['a'], 'next', runtime=self.runtime)
        self.assertEqual(path.read_text(), original)
        self.assertEqual(path.stat().st_uid, 65534)

    def test_malformed_history_fails_without_overwriting(self):
        path = self.home / ".vscode/horse.json"
        path.write_text('broken')
        with self.assertRaises(ValueError):
            pv.launch(self.config, self.home, ["a"], "next", runtime=self.runtime)
        self.assertEqual(path.read_text(), 'broken')


if __name__ == "__main__":
    unittest.main()

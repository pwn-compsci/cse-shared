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
from unittest.mock import patch

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
        text = self.client.get(self.url).get_data(as_text=True)
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

    def test_malformed_history_fails_without_overwriting(self):
        path = self.home / ".vscode/horse.json"
        path.write_text('broken')
        with self.assertRaises(ValueError):
            pv.launch(self.config, self.home, ["a"], "next", runtime=self.runtime)
        self.assertEqual(path.read_text(), 'broken')


if __name__ == "__main__":
    unittest.main()

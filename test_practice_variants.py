import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

ROOT = Path(__file__).parent
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

    def test_retry_persists_and_is_consumed_only_at_next_start(self):
        response = self.client.post(self.url, data={"csrf": self.token(), "mode": "retry", "variant": "a"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Selection saved", response.get_data(as_text=True))
        self.assertEqual(pv.launch(self.config, self.home, ["a", "secret-unseen"], "first", runtime=self.runtime), "a")
        self.assertEqual(pv.launch(self.config, self.home, ["a", "secret-unseen"], "second", runtime=self.runtime), "a")
        self.assertEqual(pv.launch(self.config, self.home, ["a", "secret-unseen"], "third", runtime=self.runtime), "secret-unseen")

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

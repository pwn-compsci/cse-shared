"""Regression tests for exam .prelevelinit preservation and execution."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).parent
EXAMSETUP = (ROOT / "common" / ".examsetup").read_text()
INIT = (ROOT / "common" / ".init").read_text()


def extract_function(source, name, next_name):
    start = source.index(f"{name}()")
    end = source.index(f"{next_name}()", start)
    return source[start:end]


class PrelevelinitLifecycleTests(unittest.TestCase):
    def run_exam_cleanup(self, preserve):
        cleanup = extract_function(
            EXAMSETUP,
            "cleanup_non_admin_challenge_artifacts",
            "cleanup_non_admin_exam_source_artifacts",
        )
        with tempfile.TemporaryDirectory() as directory:
            challenge = Path(directory) / "challenge"
            nested = challenge / "problems" / "a"
            nested.mkdir(parents=True)
            for path in (
                challenge / ".prelevelinit",
                nested / ".prelevelinit",
                challenge / ".levelinit",
                challenge / ".testprobleminit",
            ):
                path.write_text("hook\n")

            script = cleanup.replace("/challenge", str(challenge)) + r'''
cleanup_non_admin_solution_artifacts() { :; }
admin_access=false
STARTUP_LOG=/dev/null
PRESERVE_LEVELINIT_UNTIL_SOURCED=true
cleanup_non_admin_challenge_artifacts
'''
            env = {
                "PATH": "/usr/bin:/bin",
                "PRESERVE_PRELEVELINIT_UNTIL_SOURCED": (
                    "true" if preserve else "false"
                ),
            }
            subprocess.run(["bash", "-c", script], check=True, env=env)
            return {
                "root_pre": (challenge / ".prelevelinit").exists(),
                "nested_pre": (nested / ".prelevelinit").exists(),
                "level": (challenge / ".levelinit").exists(),
                "test": (challenge / ".testprobleminit").exists(),
                "mode": (
                    (challenge / ".prelevelinit").stat().st_mode & 0o777
                    if (challenge / ".prelevelinit").exists()
                    else None
                ),
            }

    def test_exam_cleanup_preserves_and_protects_prelevelinit(self):
        result = self.run_exam_cleanup(preserve=True)
        self.assertTrue(result["root_pre"])
        self.assertTrue(result["nested_pre"])
        self.assertEqual(result["mode"], 0o700)
        self.assertTrue(result["level"])
        self.assertFalse(result["test"])

    def test_normal_cleanup_removes_prelevelinit(self):
        result = self.run_exam_cleanup(preserve=False)
        self.assertFalse(result["root_pre"])
        self.assertFalse(result["nested_pre"])
        self.assertTrue(result["level"])

    def test_init_preserves_hook_before_examsetup_and_removes_it_after_run(self):
        preserve = INIT.index("PRESERVE_PRELEVELINIT_UNTIL_SOURCED=true")
        examsetup = INIT.index("source /challenge/bin/.examsetup", preserve)
        run_hook = INIT.index("python3 /challenge/.prelevelinit", examsetup)
        remove_hook = INIT.index("rm -f /challenge/.prelevelinit", run_hook)
        unset = INIT.index("unset PRESERVE_PRELEVELINIT_UNTIL_SOURCED", remove_hook)
        module_hook = INIT.index('echo "[i] checking for .moduleinit"', unset)
        self.assertLess(preserve, examsetup)
        self.assertLess(examsetup, run_hook)
        self.assertLess(run_hook, remove_hook)
        self.assertLess(remove_hook, unset)
        self.assertLess(unset, module_hook)


if __name__ == "__main__":
    unittest.main()

"""Exercise browser exceptions without starting either challenge web server."""

import ast
import logging
from pathlib import Path
import unittest


def load_browser_checks(relative_path, admin_function):
    tree = ast.parse((Path(__file__).parent / relative_path).read_text())
    names = {"BYPASS_RLDB_IDS", "RLDB_ONLY_BYPASS_IDS"}
    selected = [
        node for node in tree.body
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id in names for target in node.targets)
        ) or (
            isinstance(node, ast.FunctionDef)
            and node.name in {admin_function, "check_rldb_user_agent"}
        )
    ]
    namespace = {
        "logger": logging.getLogger(__name__),
        "is_practice_exam": False,
        "exam_admin_type": "Proctoring plus Lockdown Browser",
        "is_proctoring_only": lambda: False,
        "is_honorlock_exam": lambda: False,
        "normalized_exam_admin_type": lambda: "proctoring plus lockdown browser",
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), relative_path, "exec"), namespace)
    return namespace


class RldbAllowlistTests(unittest.TestCase):
    def test_browser_only_exception_preserves_admin_and_browser_checks(self):
        for path, admin_name in (
            ("exam_common/web/app.py", "is_admin_bypass_user"),
            ("common/web/app.py", "is_admin_bypass"),
        ):
            with self.subTest(app=path):
                checks = load_browser_checks(path, admin_name)
                browser = checks["check_rldb_user_agent"]
                extra_args = ("Linux",) if path.startswith("exam_common") else ()
                self.assertNotIn(201405, checks["BYPASS_RLDB_IDS"])
                for user_id in (201405, "201405"):
                    self.assertFalse(checks[admin_name](user_id))
                    self.assertTrue(browser("Mozilla/5.0 Chrome/130", user_id, *extra_args)[0])
                self.assertTrue(checks[admin_name](95033))
                self.assertTrue(browser("Mozilla/5.0 Chrome/130", "95033", *extra_args)[0])
                for user_id in ("201406", "invalid", None):
                    self.assertFalse(browser("Mozilla/5.0 Chrome/130", user_id, *extra_args)[0])
                self.assertTrue(browser("CLDB 2.1.0; Chrome", "201406", *extra_args)[0])


if __name__ == "__main__":
    unittest.main()

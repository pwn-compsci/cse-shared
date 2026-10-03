"""Exercise the .init build selection across exam cleanup and restoration."""
from pathlib import Path
import subprocess
import tempfile
import unittest


INIT = (Path(__file__).parent / "common" / ".init").read_text()
START = INIT.index("# Select the build task before exam cleanup")
END = INIT.index("unset PRESERVE_LEVELINIT_UNTIL_SOURCED", START)


class WorkspaceBuilderTests(unittest.TestCase):
    def select_builder(self, files, *, exam=False, module="exam23"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workdir = root / "work"
            workdir.mkdir()
            for name in files:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            script = INIT[START:END].replace("/challenge/", f"{root}/challenge/")
            result = subprocess.run(
                ["bash", "-c", '''
module="$1"
clevel_work_dir="$2"
isExam="$3"
builder=java
template_dir="$4"
cleanup_non_admin_exam_source_artifacts() {
    rm -rf "$template_dir"
}
''' + script + '\nprintf "%s" "$builder"',
                 "workspace-test", module, str(workdir), "true" if exam else "",
                 str(root / "challenge" / "template")],
                check=True, capture_output=True, text=True,
            )
            if exam:
                self.assertFalse((root / "challenge" / "template").exists())
            return result.stdout

    def test_student_exam_selects_make_before_template_cleanup(self):
        # No model and an empty workdir while the session monitor waits.
        self.assertEqual(self.select_builder(
            ["challenge/template/Makefile", "challenge/template/main.c"],
            exam=True), "build-make")

    def test_admin_model_makefile(self):
        self.assertEqual(self.select_builder(
            ["challenge/model/Makefile"]), "build-make")

    def test_restored_workdir_makefile(self):
        self.assertEqual(self.select_builder(["work/Makefile"], exam=True), "build-make")

    def test_student_cpp_template(self):
        self.assertEqual(self.select_builder(
            ["challenge/template/main.cpp"], exam=True), "build-g++")

    def test_single_file_c(self):
        self.assertEqual(self.select_builder(
            ["challenge/template/main.c"], exam=True), "build-gcc")

    def test_makefile_takes_precedence_over_cpp(self):
        self.assertEqual(self.select_builder(
            ["challenge/template/Makefile", "challenge/template/main.cpp"],
            exam=True), "build-make")

    def test_pretest_preserves_java_builder(self):
        self.assertEqual(self.select_builder(
            ["challenge/template/Makefile"], exam=True, module="pretest"), "java")


if __name__ == "__main__":
    unittest.main()

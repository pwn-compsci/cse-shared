"""Regression checks for course-specific exam nginx listeners."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).parent


class ExamNginxListenerTests(unittest.TestCase):
    def configure(self, variant, course):
        setup = (ROOT / 'common/.examsetup').read_text()
        decision = re.search(
            r'if \[ "\$course_code" = "cse240" \] && \[ -f /challenge/web/nginx.conf \]; then.*?\nfi',
            setup, re.S,
        ).group()
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'nginx.conf'
            config.write_text((ROOT / variant / 'web/nginx.conf').read_text())
            subprocess.run(
                ['bash', '-c', f'course_code={course}\n' + decision.replace('/challenge/web/nginx.conf', str(config))],
                check=True,
            )
            return config.read_text()

    def test_cse240_has_editor_and_terminal_without_desktop_routing(self):
        for variant in ('common', 'exam_common'):
            with self.subTest(variant=variant):
                config = self.configure(variant, 'cse240')
                self.assertIn('listen 8080;', config)
                original = (ROOT / variant / 'web/nginx.conf').read_text()
                listeners = re.findall(r'listen (\d+);', original)
                self.assertEqual(re.findall(r'listen (\d+);', config),
                                 [port for port in listeners if port != '6080'])
                self.assertNotIn('listen 6080;', config)
                self.assertNotIn('upstream_desktop_target', config)
                self.assertNotIn('/proxy/5900', config)
                self.assertNotIn('/proxy/6080', config)
                self.assertIn('auth_token=LETMEIN', config)

    def test_cse545_keeps_authenticated_desktop(self):
        for variant in ('common', 'exam_common'):
            with self.subTest(variant=variant):
                config = self.configure(variant, 'cse545')
                self.assertIn('listen 8080;', config)
                self.assertIn('listen 6080;', config)
                self.assertIn('code_authenticated http://127.0.0.1:6200;', config)
                self.assertIn('proxy_pass $upstream_desktop_target;', config)


if __name__ == '__main__':
    unittest.main()

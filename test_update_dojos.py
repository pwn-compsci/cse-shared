"""Exercise discovery, prompts and deployment verification without network calls."""
from pathlib import Path
import subprocess
import json
import contextlib
import io
from resolve_current_dojos import resolve
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('update_dojos.sh')


class UpdateDojosTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def shell(self, code, *args, input=''):
        return subprocess.run(
            ['bash', '-c', 'source "$1"; shift; ' + code, 'test', str(SCRIPT), *map(str, args)],
            input=input, text=True, capture_output=True, timeout=15)

    def git(self, directory, *args):
        return subprocess.check_output(['git', '-C', str(directory), *args], text=True).strip()

    def dojo(self, name, shared=True):
        repo = self.root / name
        repo.mkdir()
        self.git(repo, 'init', '-q')
        (repo / 'dojo.yml').write_text('id: test\n')
        (repo / 'update_dojo.sh').write_text('#!/bin/bash\nprintf "%s" "$PWD" > ran\n')
        (repo / 'update_dojo.sh').chmod(0o755)
        url = 'git@github.com:pwn-compsci/cse-shared.git' if shared else 'https://example.com/other.git'
        (repo / '.gitmodules').write_text(
            '[submodule "cse-shared"]\n path = cse-shared\n url = ' + url + '\n')
        return repo

    def checkout(self, repo):
        shared = repo / 'cse-shared'
        shared.mkdir()
        self.git(shared, 'init', '-q')
        self.git(shared, '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                 'commit', '-q', '--allow-empty', '-m', 'fixture')
        return self.git(shared, 'rev-parse', 'HEAD')

    def test_discovery_requires_dojo_updater_and_matching_submodule(self):
        good = self.dojo('active dojo')
        self.dojo('other', shared=False)
        missing = self.dojo('missing')
        (missing / 'dojo.yml').unlink()
        disabled = self.dojo('disabled')
        (disabled / 'update_dojo.sh').chmod(0o644)
        result = self.shell('discover_dojos "$1"', self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [str(good)])

    def test_default_no_and_eof(self):
        for answer in ('\n', ''):
            result = self.shell('select_dojos false one two; printf "count=%s" "${#selected[@]}"', input=answer)
            self.assertEqual(result.stdout, 'count=0')

    def test_yes_and_prod_select_all(self):
        for prod, answer in [('false', 'Y\n'), ('true', '')]:
            result = self.shell('select_dojos "$1" one two; printf "%s\\n" "${selected[@]}"', prod, input=answer)
            self.assertEqual(result.stdout.splitlines(), ['one', 'two'])
            if prod == 'true':
                self.assertEqual(result.stderr, '')

    def test_choose_individual_with_default_no(self):
        result = self.shell('select_dojos false one two three; printf "%s\\n" "${selected[@]}"',
                            input='c\ny\n\nN\n')
        self.assertEqual(result.stdout.splitlines(), ['one'])
        for name in ('one', 'two', 'three'):
            self.assertIn(name, result.stderr)

    def test_invalid_choice_reprompts(self):
        result = self.shell('select_dojos false one; printf "%s\\n" "${selected[@]}"', input='oops\ny\n')
        self.assertEqual(result.stdout.splitlines(), ['one'])
        self.assertIn('Please enter', result.stderr)

    def test_updates_run_in_repo_and_verify_commit(self):
        repo = self.dojo('active dojo')
        expected = self.checkout(repo)
        result = self.shell('run_as=(); update_selected "$1" "$2"', expected, repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((repo / 'ran').read_text(), str(repo))

    def test_dirty_shared_checkout_prevents_updates(self):
        repo = self.dojo('active')
        expected = self.checkout(repo)
        (repo / 'cse-shared/local-work').write_text('preserve me')
        result = self.shell('run_as=(); update_selected "$1" "$2"', expected, repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((repo / 'ran').exists())

    def test_failed_update_and_wrong_commit_report_failure(self):
        repo = self.dojo('active')
        expected = self.checkout(repo)
        (repo / 'update_dojo.sh').write_text('#!/bin/bash\nexit 7\n')
        result = self.shell('run_as=(); update_selected "$1" "$2"', expected, repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Update failed', result.stderr)
        (repo / 'update_dojo.sh').write_text('#!/bin/bash\nexit 0\n')
        result = self.shell('run_as=(); update_selected wrong "$1"', repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('expected wrong', result.stderr)

    def test_list_never_publishes(self):
        repo = self.dojo('active')
        payload = self.root / 'dojos.json'
        payload.write_text(json.dumps({'year': 2026, 'semester': 'Fall', 'dojos': [
            {'pwn_dojo_hash': 'active~hash', 'pwn_college_dir': str(repo)}]}))
        result = self.shell('publish_shared() { echo BAD; return 1; }; main --list --root "$1" --api-url "$2"', self.root, payload.as_uri())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(repo), result.stdout)
        self.assertNotIn('BAD', result.stdout)
        self.assertFalse((repo / 'ran').exists())

    def test_backend_matching_deduplicates_and_reports_missing(self):
        repo = self.dojo('cse240-fb26')
        payload = {'year': 2026, 'semester': 'Fall', 'dojos': [
            {'pwn_dojo_hash': 'cse240-fb26~abc', 'pwn_college_dir': '/old/cse240-fb26'},
            {'pwn_dojo_hash': 'cse240-fb26~abc'},
            {'pwn_dojo_hash': 'missing~abc'}]}
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(resolve(payload, [repo]), [str(repo)])
        self.assertIn('missing~abc was not updated', errors.getvalue())
        payload['dojos'] = []
        self.assertEqual(resolve(payload, [repo]), [])

    def test_backend_unavailable_prevents_publishing(self):
        result = self.shell('publish_shared() { echo BAD; }; main --list --api-url "$1"',
                            (self.root / 'not-found.json').as_uri())
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('BAD', result.stdout)
        self.assertIn('lookup failed', result.stderr)

    def test_invalid_backend_data_fails(self):
        for payload in ({}, {'year': 2026, 'semester': 'Fall', 'dojos': [{}]}):
            with self.assertRaises(ValueError):
                resolve(payload, [])

    def test_updates_launch_concurrently(self):
        first = self.dojo('first')
        second = self.dojo('second')
        expected = self.checkout(first)
        subprocess.run(['git', 'clone', '-q', str(first / 'cse-shared'), str(second / 'cse-shared')], check=True)
        for repo, other in ((first, second), (second, first)):
            (repo / 'update_dojo.sh').write_text(
                '#!/bin/bash\ntouch started\n'
                'for i in {1..100}; do\n'
                f'  [[ ! -f "{other}/started" ]] || exit 0\n'
                '  sleep 0.02\ndone\nexit 1\n')
        result = self.shell('run_as=(); update_selected "$1" "$2" "$3"', expected, first, second)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bad_arguments_fail(self):
        for args in [('--root',), ('--oops',)]:
            result = self.shell('main "$@"', *args)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()

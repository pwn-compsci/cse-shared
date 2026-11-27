"""Preserve practice work while removing the shared actual-exam directory."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / 'exam_common/web'))
import practice_variants as pv


@unittest.skipUnless(os.geteuid() == 0, 'root-owned practice persistence')
class WorkspaceMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.old = self.home / 'exam/30/02'
        self.old.mkdir(parents=True)
        self.old.joinpath('main.cpp').write_text('unfinished practice')
        self.home.joinpath('.vscode').mkdir()
        self.log = self.home / '.vscode/starts.log'
        self.log.write_text('module=pex30|level=02|chosen_problem=a|starttime=2026-11-24 09:34:24\n')
        self.config = dict(module='pex30', level='02', is_practice_exam=True,
                           hwdir=str(self.home / 'pex30'),
                           previous_practice_hwdir=str(self.old.parent))
        self.owner = patch.object(pv.attempts.pwd, 'getpwnam',
                                  return_value=SimpleNamespace(pw_uid=65534, pw_gid=65534))
        self.owner.start()
        self.addCleanup(self.owner.stop)
        self.runtime = self.home / 'runtime.json'

    def migrate(self, entry):
        pv.attempts.migrate_workdir(entry, self.config, self.home)

    def test_preserves_indexed_save_and_unfinished_practice_without_touching_originals(self):
        saved = self.old.parent / '02_2026-11-23_120000_1'
        saved.mkdir()
        saved.joinpath('main.cpp').write_text('previous practice')
        entry = dict(current='a', attempts=[dict(id=saved.name, directory=saved.name, variant='a')])
        self.migrate(entry)
        active = pv.attempts.workdir(self.config, self.home)
        self.assertEqual((active.parent / saved.name / 'main.cpp').read_text(), 'previous practice')
        self.assertEqual((saved / 'main.cpp').read_text(), 'previous practice')
        snapshot = entry['attempts'][-1]
        self.assertEqual((active.parent / snapshot['directory'] / 'main.cpp').read_text(), 'unfinished practice')
        self.assertEqual(snapshot['variant'], 'a')
        self.assertEqual((self.old / 'main.cpp').read_text(), 'unfinished practice')
        self.assertFalse(active.exists())
        self.migrate(entry)
        self.assertEqual(len(entry['attempts']), 2)

    def test_actual_exam_last_launch_is_not_imported_as_practice(self):
        with self.log.open('a') as f:
            f.write('module=exam30|level=02|chosen_problem=b|starttime=2026-11-25 09:34:24\n')
            f.write('module=pex30|level=03|chosen_problem=c|starttime=2026-11-26 09:34:24\n')
        entry = {}
        self.migrate(entry)
        self.assertFalse(entry.get('attempts'))
        self.assertEqual((self.old / 'main.cpp').read_text(), 'unfinished practice')

    def test_missing_launch_history_does_not_guess_active_folder_ownership(self):
        self.log.unlink()
        entry = {}
        self.migrate(entry)
        self.assertFalse(entry.get('attempts'))
        self.assertTrue(self.old.exists())

    def test_pending_resume_survives_directory_change(self):
        saved = self.old.parent / '02_2026-11-23_120000_1'
        saved.mkdir()
        saved.joinpath('main.cpp').write_text('resume this answer')
        self.log.write_text('module=exam30|level=02|chosen_problem=b\n')
        key = '["pex30","02"]'
        entry = dict(encountered=['a'], current='a', last='a', cycle=['a'], attempt_id='old',
                     attempts=[dict(id=saved.name, directory=saved.name, variant='a', saved_at='2026-11-23T12:00:00+00:00')],
                     pending=dict(mode='retry', variant='a', attempt=saved.name))
        with pv.history_file(self.home / '.vscode/horse.json') as history:
            history[pv.METADATA] = {key: entry}
        chosen = pv.launch(self.config, self.home, ['a', 'b'], 'new', runtime=self.runtime)
        self.assertEqual(chosen, 'a')
        state = json.loads(self.runtime.read_text())
        self.assertEqual(state['resume'], str(self.home / 'pex30' / saved.name))
        active = Path(state['workdir'])
        active.mkdir()
        active.joinpath('main.cpp').write_text('fresh template')
        pv.restore_current(self.runtime)
        self.assertEqual(active.joinpath('main.cpp').read_text(), 'resume this answer')
        self.assertEqual(self.old.joinpath('main.cpp').read_text(), 'unfinished practice')

    def test_symlink_destination_is_rejected_without_writing_through_it(self):
        outside = self.home / 'outside'
        outside.mkdir()
        self.home.joinpath('pex30').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.migrate({})
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_saved_source_is_rejected(self):
        saved = self.old.parent / '02_2026-11-23_120000_1'
        saved.symlink_to(self.old, target_is_directory=True)
        entry = dict(attempts=[dict(id=saved.name, directory=saved.name)])
        with self.assertRaises(OSError):
            self.migrate(entry)
        self.assertEqual(self.old.joinpath('main.cpp').read_text(), 'unfinished practice')

    def test_existing_new_work_and_saved_copy_are_not_overwritten(self):
        active = self.home / 'pex30/02'
        active.mkdir(parents=True)
        active.joinpath('main.cpp').write_text('existing new workspace')
        saved = self.old.parent / '02_2026-11-23_120000_1'
        saved.mkdir()
        saved.joinpath('main.cpp').write_text('old saved version')
        destination = active.parent / saved.name
        destination.mkdir()
        destination.joinpath('main.cpp').write_text('edited saved version')
        self.migrate(dict(attempts=[dict(id=saved.name, directory=saved.name)]))
        self.assertEqual(active.joinpath('main.cpp').read_text(), 'existing new workspace')
        self.assertEqual(destination.joinpath('main.cpp').read_text(), 'edited saved version')
        self.assertEqual(saved.joinpath('main.cpp').read_text(), 'old saved version')

    def test_unconfigured_courses_do_not_migrate(self):
        self.config.pop('previous_practice_hwdir')
        self.migrate({})
        self.assertFalse((self.home / 'pex30').exists())


if __name__ == '__main__':
    unittest.main()

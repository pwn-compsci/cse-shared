# Practice problem variants

Practice exams reuse the existing `problems/X` directories, `.examsetup` staging,
`horse.json` selection cycles, and `starts.log`. No new challenge type, variant
manifest, database table, or separate practice module is required.

For example, `/cse/cse240-fc26/pex30/level-30-01/problems/` and
`level-30-02/problems/` already contain `a` through `j`. Each is a selectable
version of that level. Keep IDs stable: changing an ID makes it a new variant.

## Adding a variant

Add another directory such as `problems/k/` alongside the existing directories.
Use letters, digits, underscores, or hyphens for its ID. Supply the files that
version needs, for example:

```
level-30-01/
  .config/level.json
  .levelinit                 # shared setup fallback
  problems/
    a/
      template/main.cpp
      system_tests/...
    k/
      template/main.cpp
      system_tests/...
      .levelinit             # optional version-specific setup
```

The existing setup copies the selected directory's contents to `/challenge`,
then uses the existing rendering, test generation, and work-directory setup.
Keep framework scripts and common assets at challenge/shared level. Variant
files overlay that base; they do not need their own copies of the framework.
A variant's `.levelinit` takes precedence over the challenge-level fallback.
Concrete files work as in the current pex30 examples; Jinja files still use the
existing generator. One-directory problems continue to select that directory.

The level configuration must already have `examLevel` and either
`is_practice_exam: true` or `practice_exam: true`, as existing practice exams do.

## Student workflow

A normal challenge start automatically chooses a random version, preferring
versions not yet selected in the existing selection cycle. It avoids the most
recent version whenever another version is available, including when a cycle
resets. It is possible to receive an older version again after completing a
cycle; "new random" does not promise a never-before-seen version.

The editor's **Practice & review** button opens a page with two distinct actions:

- **New Random Variant** queues random selection for the next challenge start.
- **Retry a Previous Variant** lists only previously encountered, still available
  versions and queues the selected version for the next start.

Students save their work and restart the challenge from its course page after
choosing. The page explicitly explains this. No separate module is necessary.
Starting a variant fresh uses starter files. Saved attempts can also be reviewed
or resumed as described below. Resuming restores source/data files, rather than
compiled binaries, hidden tests, or a prior generator seed. Closing/reopening the editor, resetting its login,
or reloading the page does not choose another problem.

## Persistence and compatibility

`$course_home/.vscode/horse.json` remains the history file. Existing keys are JSON
encodings of `[module, level]` and retain their arrays of selections in the current
cycle. The reserved `__practice_variants__` object adds metadata under the same
keys: cumulative `encountered` IDs, `last`, `current`, `attempt_id`, `cycle`, and
optional `pending` selection. This retains compatibility with the legacy cycle
reader used by regular exams. Regular exam selection behavior is unchanged.

On first practice launch, metadata is seeded from the existing cycle and matching
entries in `$course_home/.vscode/starts.log`. This recovers earlier encounters
where records still exist. Missing or previously trimmed logs cannot reconstruct
lost encounters. Migration happens once, and subsequent cumulative history is
never reset when a cycle ends. Different modules and levels remain isolated.
Removed versions are retained in cumulative history but hidden from retry choices.
A queued version removed before the next start falls back to random selection.

The existing `/opt/exam_attempt_startup_id` pins the chosen version. Repeating
selection with the same startup ID returns the same version and leaves a pending
next-start request intact. A new challenge container/startup ID consumes that
request once; otherwise it selects randomly. An administrator's valid explicit
selection takes precedence. `/opt/practice_variant_attempt.json` holds the private
catalogue for the current container, since unselected problem directories are
removed by existing exam setup. It is not a second persistent history store.

History is locked and flushed before returning a selection. The file must be
root-owned and not group/world writable; symlink components and hard links are
rejected. Corrupt/untrusted history fails launch rather than silently ignoring a
retry. Preserve and repair that file if this occurs. There is no fallback that
silently chooses different requirements after a history error.

## Nginx and rollout

Both shared web apps register `/exam_api/practice-variants`. Existing nginx
`location /exam_api` forwards it to Flask regardless of editor login; no nginx
configuration change is necessary. Flask checks the server's practice flag,
validates retries against history and the private catalogue, and requires a
per-process CSRF token on POST. The HTTP page never includes unseen variant IDs.
The injected badge script displays the link only when the endpoint succeeds and
uses its own script URL to preserve a surrounding proxy path. Regular exams get
404 and no practice link. Existing attendance and editor access gates stay intact.

Changes live in `/cse/cse-shared`. Course repositories, including
`/cse/cse240-fc26/cse-shared`, have separate checkouts. Update those checkouts using
the normal course deployment process and rebuild/restart affected challenges to
include the shared `.examsetup`, both web apps, the new `practice_variants.py`
module (including the common-web symlink target), the new `practice_attempts.py` helper, and badge scripts together.
Updating only the web app will not create the launch catalogue. This change does
not update course checkouts or restart live student containers automatically.

## Verification

Run from this repository:

```
sudo -n /opt/class_sync/apivenv/bin/python -m unittest test_practice_variants -v
/opt/class_sync/apivenv/bin/python -m unittest discover -p 'test_exam_*.py'
node test_practice_variants_ui.js
bash -n common/.examsetup
```

Root is needed for persistence tests because production history must be owned by
root; the tests create and remove only temporary files. Pure selection tests also
run unprivileged. No live student history or services are used by these tests.


## Reviewing and resuming saved work

The **Practice & review** button is a green pill in the editor. It appears only
for practice levels with more than one available variant. The server-side
`/exam_api/practice-variants/available` check returns 404 for single-variant
practice levels and for ordinary levels/exams. Direct access to the history page
still works for a single-variant practice level.

The page lists **Saved attempts**, with a variant and a date such as
"Nov 21, 2026 at 2:53:00 PM MST". Display times use America/Phoenix explicitly;
new archive timestamps are recorded in UTC and include microseconds to prevent
same-minute backup collisions. Legacy directory timestamps are interpreted as
UTC, matching the exam container's server clock.

**Review attempt** opens a read-only file browser and previews source/text files
with HTML escaping. It does not alter the current attempt. Test summaries (passed,
failed and recorded error messages) are read from the existing `trdb.db` when a
known attempt interval can be matched by module, level and time. Missing database
records or unknown intervals are stated explicitly; terminal output that was
never saved cannot be reconstructed.

**Resume this saved attempt next start** queues its known variant and saved work.
On the next start, the active working directory is backed up first. After starter
files and level hooks finish, the selected source/data files are copied into the
new workspace. The old saved directory remains intact. Restore is applied once,
so editor reloads do not overwrite subsequent edits. The **Start this variant
fresh** action instead chooses clean starter files without restoring old code.
Binary executables, editor metadata, hidden files, framework/model directories
and system tests are neither previewed nor copied from old attempts. The current
variant's generated tests/framework remain in place; for generator-based variants,
this restores source work, not the original random seed or complete environment.

New backup directory references and attempt intervals live in the existing
`horse.json` metadata. Old timestamped directories are discovered alongside the
active level directory. Their folder timestamps alone do not prove which variant
they contained, so they are labelled **variant unknown** unless an indexed record
exists. Such folders can be reviewed but cannot automatically choose a variant
for resume. This avoids attaching old source to the wrong problem.

Backup moves, review reads and restore writes refuse symlink path components.
Previews also reject hard-linked, binary and oversized files. Hidden tests are
excluded. Requests can select only indexed attempts for the current level;
clients cannot supply arbitrary filesystem paths. Source restores replace files
rather than truncating them, preventing writes through pre-existing hard links.
Deploy `.init`, `.examsetup`, the web helper modules and badge scripts together.

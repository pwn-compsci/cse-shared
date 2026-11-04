# cse-shared

## Maintenance Notes

- Keep `common/session_monitor.py` and `common/bin/session_monitor.py` in sync.
  For now both copies are used by course/container packaging paths, so any
  behavior change or bug fix to one should be applied to the other in the same
  commit.

## Terminal clipboard tracking

`common/.init` invokes `/challenge/bin/terminal_clipboard.py` for all students
on non-exam levels when the helper is packaged. The helper independently
checks lab/project metadata, including class labs, before preparing
or launching anything. Lectures and exams are excluded. Failure is logged in
the startup log and normal initialization continues.

Eligible challenges must package a `bin/terminal_clipboard.py` symlink to
`common/bin/terminal_clipboard.py`. That single Python file embeds the browser
and server assets; no additional JavaScript files need packaging. It copies
platform code-server into `/run/ultima-code-server` and starts it as `hacker`
under the existing dojo service name before the platform launcher runs.

Copy/paste events, text, and server-read `module`, `challenge`, and
`pwn_college_id` append to `~/.local/share/ultima/terminal-clipboard.jsonl`.
Capture is best effort; unavailable text and truncation above 262,144 UTF-16
units are marked. Unsupported platform layouts or an existing unpatched service
cause the helper to refuse activation. Platform updates require a fresh copy
and browser verification.

## SSH connection history

`common/.init` installs a root-owned wrapper at `/run/dojo/bin/ssh-entrypoint`
using a private directory of links to the original dojo binaries. The directory
is fully populated before an atomic symlink replacement. Dojo waits for `.init`
to complete before creating `/run/dojo/var/ready`, so normal startup does not
expose an intermediate directory. Re-running the installer is a no-op. Installing
into an already running workspace does not record existing SSH connections or
requests that reached the old entrypoint before the swap.

All SSH connections remain allowed. The wrapper appends a timestamp, instance,
and `[SSH command]` (requested arguments) or `[SSH session] login` to
`/home/hacker/.local/share/ultima/c.dat`, then executes the original entrypoint
with unchanged arguments. Shell quoting keeps newlines and control characters
inside one record. These are connection requests, not proof of command success;
existing interactive prompt history continues separately. The wrapper does not
print to stdout or stderr, and logging errors do not prevent access. Log writes
run as the connecting user, never as initialization's root user. This file is
user-writable history, not a tamper-proof audit trail.

`common/.bashrc.config.sh` also allows ordinary interactive SSH access. Deploy
both files together. To remove the wrapper from a running workspace as root,
atomically replace `/run/dojo/bin` with a symlink to
`/run/current-system/sw/bin`; restart the challenge to pick up source changes.

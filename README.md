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

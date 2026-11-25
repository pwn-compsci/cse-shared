# Current rollout: labs and projects only

Aita is enabled on an explicit allowlist of 126 published labs/projects in
`intro-to-programming-languages` (24 modules). Lecture pages and retired challenges
are excluded. Full exams are prohibited even for admins. Practice exams are a
future rollout and are currently disabled, including the former FC26 pilot.

`common/bin/practice_tutor/targets.json` is the bundle allowlist and matches the
backend manifest. `eligibility.py` rejects assessment flags and an exam runtime
marker before installation or serving the widget. Backend validation independently
rejects exam targets and revokes old exam capabilities. Admins only bypass enrollment.

The shared `.init` prepares the eligible editor and starts it late, after workspace
setup. Already-tracked projects keep their clipboard editor; other labs/projects use
a separate Aita copy without enabling clipboard tracking. Both use the normal
code-service, port and WebSockets. Scheme/Prolog/shell/C++ header files are collected
alongside C/C++. All request, safety-review and history policies are preserved.

Validate with the project Python: `pytest test_practice_tutor.py -q` (root staging
checks require root), plus `node test_practice_tutor_ui.js` and
`node test_mud_tutor_route.js`. Run backend `test_chatbot_rollout.py` for exam-denial
and capability-revocation checks. The earlier practice pilot notes below are
historical and do not authorize practice-exam deployment.

---

# Aita practice tutor

Shared assets are in `common/bin/practice_tutor/`. Link that directory and
`common/bin/install_practice_tutor.py` into the challenge's `bin` directory.
The current server pilot accepts only FC26 `pex20/level-20-03`, variant `a`.
Its `.config/level.json` opts in with:

```json
"practice_tutor": {"enabled": true, "course_dir": "/cse/cse240-fc26"}
```

`common/.init` installs the assets before `.examsetup` starts the web service,
and snapshots the rendered starter requirements before exam cleanup. The bridge
uses the existing Flask listener behind `/exam_api`; no extra port or container
process is required. nginx's overlay script is injected only into opted-in levels.

The 💬 Aita launcher opens a chat panel with blue student and teal Aita bubbles, and `/exam_api/tutor/` opens a standalone
chat page. Both retain the current `/workspace/proxy/8080/` URL prefix.

The root installer authenticates with the image's existing `/opt/.ring` credential
to obtain a signed, student/problem-specific 24-hour capability. It writes that
capability to `/opt/practice_tutor.json` (root:root, 0600); the bridge refreshes
it when expired. No global tutor key or OpenAI key is distributed through the
course repository, and no credential reaches the browser. Provisioning failure
leaves practice access working and is retried when the tutor is used.

The collector runs as `hacker`, limits reads of current source and recent logs,
and queries recent tester results read-only. Rendered starter requirements
survive template cleanup in `/opt/practice-tutor/rendered.json`. The API strips
hidden and known injected prompt content and supplies the tutoring policy.

Validate using the project Python:

```sh
sudo /opt/class_sync/apivenv/bin/python -m pytest test_practice_tutor.py test_practice_variants.py
node test_practice_tutor_ui.js
bash -n common/.init
```

Push the shared commit, push the course submodule pointer and opt-in files,
then call the course's dojo update webhook. Restart the challenge to load it.

History is stored server-side per student/problem/variant and restored on every
open, with date/session separators and the view scrolled to the bottom. Older
turns can be loaded on demand. Enter sends and Shift+Enter inserts a newline.
Model context uses at most three recent completed exchanges, bounded to 6,000
characters; viewing full history makes no model call. The database enforces one
active request, a 10-second cooldown, 5 questions/5 minutes, 30/hour, and 100/day.
The UI displays retry countdowns returned by the API.

The chat now uses a compact drag bar with icon-only close and new-tab controls;
the launcher shrinks while open and also serves as a drag handle. Escape or an
outside click closes the popup. The standalone page loads the same saved history.
The introductory notice/visible heading were removed, and scrollbars are themed.
Requests for code/answers receive a policy warning. Backend detectors record
perceived attempts separately in `chatbot_answer_requests`, including reasons,
with counts in `chatbot_answer_request_summary` and an instructor-only report API.
These records are perceptions for review, not findings of misconduct.

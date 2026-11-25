# Practice tutor

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

The 💬 launcher opens a chat panel, and `/exam_api/tutor/` opens a standalone
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

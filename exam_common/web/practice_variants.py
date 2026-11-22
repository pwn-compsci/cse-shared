"""Practice variant selection shared by launch setup and the nginx-backed UI."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import practice_attempts as attempts

ATTEMPT = Path("/opt/practice_variant_attempt.json")
CONFIG = Path("/challenge/.config/level.json")
METADATA = "__practice_variants__"


def is_practice(config):
    return bool(config.get("practice_exam") or config.get("is_practice_exam"))


@contextmanager
def history_file(path):
    """Lock a root-owned file, refusing symlink components and hard links."""
    if os.geteuid() != 0:
        raise PermissionError("practice history requires root")
    path = Path(path)
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.absolute().parent.parts[1:]:
            try:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            except FileNotFoundError:
                os.mkdir(component, 0o755, dir_fd=parent)
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(path.name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, "r+", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("unsafe practice history")
        trusted = info.st_uid == 0 and not info.st_mode & 0o022
        if not trusted and info.st_size:
            raise ValueError("untrusted practice history")
        os.fchown(stream.fileno(), 0, 0)
        os.fchmod(stream.fileno(), 0o600)
        data = json.load(stream) if info.st_size else {}
        if not isinstance(data, dict):
            raise ValueError("invalid practice history")
        yield data
        stream.seek(0)
        json.dump(data, stream, sort_keys=True)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())


def select(entry, variants, attempt_id, override=""):
    """Mutate one history entry; repeated setup of the same attempt is idempotent."""
    if entry.get("attempt_id") == attempt_id:
        chosen = entry["current"]
        if chosen not in variants:
            raise ValueError("active variant is unavailable")
        return chosen
    pending = entry.get("pending", {})
    retry = pending.get("variant") if pending.get("mode") == "retry" else None
    encountered = entry.setdefault("encountered", [])
    if override:
        if override not in variants:
            raise ValueError("invalid administrator variant")
        chosen = override
    elif retry in variants and retry in encountered:
        chosen = retry
    else:
        cycle = [v for v in entry.get("cycle", []) if v in variants]
        remaining = [v for v in variants if v not in cycle]
        if not remaining:
            cycle, remaining = [], list(variants)
        choices = [v for v in remaining if v != entry.get("last")]
        # At a cycle boundary, avoid the last variant even if it is the only
        # unselected one (possible after an explicit retry).
        if not choices:
            choices = [v for v in variants if v != entry.get("last")]
        chosen = secrets.choice(choices or remaining)
        entry["cycle"] = cycle
    if chosen not in encountered:
        encountered.append(chosen)
    cycle = entry.setdefault("cycle", [])
    if chosen not in cycle:
        cycle.append(chosen)
    entry.update(last=chosen, current=chosen, attempt_id=attempt_id)
    entry.pop("pending", None)
    return chosen


def queue(entry, variants, mode, variant):
    if mode not in ("random", "retry"):
        raise ValueError("Choose a new random variant or a previous variant.")
    if mode == "retry" and (variant not in variants or variant not in entry.get("encountered", [])):
        raise ValueError("You can only retry an available variant you have encountered.")
    entry["pending"] = {"mode": mode, "variant": variant if mode == "retry" else None}


def launch(config, home, variants, attempt_id, override="", runtime=ATTEMPT):
    variants = sorted(set(variants))
    if not variants or any(not re.fullmatch(r"[A-Za-z0-9_-]+", v) for v in variants):
        raise ValueError("variant directory IDs must contain letters, digits, underscores or hyphens")
    key = json.dumps([config.get("module"), config.get("level")], separators=(",", ":"))
    path = str(Path(home) / ".vscode/horse.json")
    with history_file(path) as history:
        metadata = history.setdefault(METADATA, {})
        if key not in metadata:
            # Preserve the existing horse.json cycle and recover earlier
            # encounters from the existing launch log, matching fields exactly.
            cycle = history.get(key, [])
            cycle = [v for v in cycle if v in variants] if isinstance(cycle, list) else []
            entry = {"encountered": [], "cycle": cycle}
            try:
                with open(Path(home) / ".vscode/starts.log") as starts:
                    for line in starts:
                        fields = dict(field.split("=", 1) for field in line.strip().split("|") if "=" in field)
                        if fields.get("module") != str(config.get("module")) or fields.get("level") != str(config.get("level")):
                            continue
                        variant = fields.get("chosen_problem")
                        if variant in variants:
                            if variant not in entry["encountered"]:
                                entry["encountered"].append(variant)
                            entry["last"] = variant
            except FileNotFoundError:
                pass
            for variant in cycle:
                if variant not in entry["encountered"]:
                    entry["encountered"].append(variant)
            if "last" not in entry and cycle:
                entry["last"] = cycle[-1]
            metadata[key] = entry
        entry = metadata[key]
        active = attempts.workdir(config, home)
        attempts.discover(entry, active)
        same_attempt = entry.get("attempt_id") == attempt_id
        pending_resume = entry.get("pending", {}).get("attempt") if not override else None
        resume = None
        if not same_attempt:
            if pending_resume:
                record, resume_path = attempts.find_attempt(entry, pending_resume, active)
                if record.get("variant") not in variants or record.get("variant") != entry["pending"].get("variant"):
                    raise ValueError("Saved attempt does not match the requested variant.")
                resume = str(resume_path)
            attempts.archive(entry, active)
        chosen = select(entry, variants, attempt_id, override)
        if not same_attempt:
            entry["started_at"] = attempts.now()
        # Keep the legacy cycle representation usable by existing exam setup.
        history[key] = entry["cycle"]
    # This catalogue is private to the service; HTTP responses expose encountered IDs only.
    with history_file(runtime) as state:
        old_resume = state.get("resume") if same_attempt else resume
        state.clear()
        state.update(history=path, key=key, variants=variants, current=chosen,
                     home=str(home), workdir=str(active), resume=old_resume)
    return chosen


def restore_current(runtime=ATTEMPT):
    with history_file(runtime) as state:
        if state.get("resume"):
            attempts.restore(state["resume"], state["workdir"])
            state["resume"] = None


def register_routes(app, config_path=CONFIG, runtime=ATTEMPT):
    from flask import abort, make_response, render_template_string, request
    csrf_token = secrets.token_urlsafe(32)

    def context():
        with open(config_path) as stream:
            config = json.load(stream)
        if not is_practice(config):
            abort(404)
        with open(runtime) as stream:
            state = json.load(stream)
        return config, state

    @app.route("/exam_api/practice-variants/badge")
    def practice_badge():
        try:
            config, state = context()
            label = f"{config['module']} - {config['level']}{state['current']}"
            return {"label": label}, 200, {"Cache-Control": "no-store"}
        except (OSError, ValueError, KeyError):
            return "", 503, {"Cache-Control": "no-store"}

    @app.route("/exam_api/practice-variants/available")
    def practice_choices_available():
        try:
            config, state = context()
            if len(state["variants"]) <= 1:
                abort(404)
            return "", 204, {"Cache-Control": "no-store"}
        except (OSError, ValueError, KeyError):
            return "", 503, {"Cache-Control": "no-store"}

    @app.route("/exam_api/practice-variants", methods=["GET", "POST"])
    def practice_variants():
        message = ""
        try:
            config, state = context()
            with history_file(state["history"]) as history:
                entry = history[METADATA][state["key"]]
                active = Path(state.get("workdir") or attempts.workdir(config, Path(state["history"]).parent.parent))
                attempts.discover(entry, active)
                if request.method == "POST":
                    if not secrets.compare_digest(request.form.get("csrf", ""), csrf_token):
                        abort(403)
                    try:
                        mode = request.form.get("mode")
                        if mode == "resume":
                            record, saved = attempts.find_attempt(entry, request.form.get("attempt"), active)
                            queue(entry, state["variants"], "retry", record.get("variant"))
                            entry["pending"]["attempt"] = record["id"]
                        else:
                            queue(entry, state["variants"], mode, request.form.get("variant"))
                    except (ValueError, OSError) as error:
                        abort(400, str(error))
                    message = "Selection saved for your next challenge start. Save your work, then restart this challenge from the course page."
                encountered = [v for v in entry["encountered"] if v in state["variants"]]
                pending = entry.get("pending", {})
                saved_attempts = sorted(entry.get("attempts", []), key=lambda a: a["saved_at"], reverse=True)
                saved_attempts = [dict(a, label=attempts.display_time(a["saved_at"])) for a in saved_attempts]
                requested = request.args.get("attempt")
                record = saved_path = None
                if requested:
                    try:
                        record, saved_path = attempts.find_attempt(entry, requested, active)
                    except (ValueError, OSError):
                        abort(404)
            if record:
                try:
                    names = attempts.files(saved_path)
                    selected = request.args.get("file")
                    content = attempts.read_work(saved_path, selected).decode("utf-8", errors="replace") if selected else None
                except (ValueError, OSError):
                    abort(400, "This saved file cannot be reviewed.")
                home = state.get("home") or str(Path(state["history"]).parent.parent)
                feedback = attempts.feedback(home, config, record)
                for result in feedback:
                    result["label"] = attempts.display_time(result["timestamp"].replace(" ", "T") + "+00:00")
                response = make_response(render_template_string(REVIEW, record=record,
                    label=attempts.display_time(record["saved_at"]), names=names, selected=selected,
                    content=content, feedback=feedback, csrf=csrf_token,
                    resumable=record.get("variant") in encountered))
            else:
                response = make_response(render_template_string(PAGE, current=state["current"],
                    encountered=encountered, pending=pending, message=message, csrf=csrf_token,
                    saved_attempts=saved_attempts))
        except (OSError, ValueError, KeyError):
            response = make_response("Practice choices are unavailable. Your current attempt is unchanged.", 503)
        response.headers["Cache-Control"] = "no-store"
        return response


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Practice variants</title>
<style>
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#151719;color:#edf0f3;font-size:15px;line-height:1.55}
*{box-sizing:border-box}
body{margin:0;background:#151719;color:#edf0f3}
main{max-width:920px;margin:0 auto;padding:32px 24px}
header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:20px}
.eyebrow{margin:0 0 5px;color:#a8c978;font-size:11px;font-weight:700;letter-spacing:.13em;text-transform:uppercase}
h1{margin:0;font-size:28px;font-weight:650;line-height:1.2;letter-spacing:-.035em}
p{margin:0;color:#b8c1ca}
.intro{max-width:610px;margin-top:10px}
.current{flex-shrink:0;display:flex;align-items:center;gap:10px;padding:9px 12px;border:1px solid #3a4248;
  border-radius:9px;color:#c6ced6;font-size:12px;background:#202428}
.current strong{display:inline-grid;place-items:center;min-width:28px;height:28px;border-radius:6px;
  background:#344329;color:#d8f4b2;font:700 16px ui-monospace,SFMono-Regular,Consolas,monospace}
.notice{padding:13px 16px;margin-bottom:22px;border:1px solid #3b454e;border-radius:10px;background:#1c2227}
.notice p{font-size:13px}.notice strong{color:#edf0f3}
.status{margin:0 0 14px;padding:12px 16px;border:1px solid #46623c;border-radius:10px;background:#222f20;color:#d3edc9;font-size:13px}
.pending{margin:0 0 18px;color:#d3edc9;font-size:13px}.pending strong{color:#e8f5df}
.options{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{display:flex;flex-direction:column;padding:22px;border:1px solid #394149;border-radius:12px;background:#202428}
.card-number{color:#96a2ad;font-size:11px;font-weight:700;letter-spacing:.1em;margin-bottom:12px}
h2{margin:0 0 9px;font-size:19px;font-weight:600;letter-spacing:-.02em;line-height:1.3}
.card p{font-size:14px;margin-bottom:24px}
form{display:flex;flex-direction:column;gap:10px;margin-top:auto}
label{font-size:12px;font-weight:600;color:#c5ced7}
button,select{font:inherit;font-size:14px;border-radius:7px;min-height:44px;width:100%;padding:10px 13px}
select{margin-top:6px;border:1px solid #56616c;background:#151a1e;color:#f0f3f6;cursor:pointer}
option{background:#151a1e;color:#f0f3f6}
button{border:1px solid #586570;background:#2b343c;color:#f0f3f6;cursor:pointer;font-weight:600;transition:background .15s,border-color .15s}
button:hover{background:#36434d;border-color:#82929f}
.primary{background:#b4df82;color:#17230d;border-color:#b4df82}.primary:hover{background:#c7ed9c;border-color:#c7ed9c}
button:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #b4df82;outline-offset:4px}
footer{margin-top:22px;padding-top:16px;border-top:1px solid #30383e}
a{color:#c8d4df;font-size:13px;text-underline-offset:4px}a:hover{color:#fff}
.history{margin-top:28px}.history>p,.empty{font-size:13px;margin:8px 0 16px}
.attempt-row{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:15px 0;border-bottom:1px solid #394149}
.attempt-row p{font-size:12px;margin-top:4px}.review-link{color:#c7ed9c;white-space:nowrap}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#101416;border:1px solid #394149;border-radius:8px;padding:18px;font:13px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;color:#e6edf3}
.file-list{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}.file-list a{color:#c7ed9c}
.feedback{margin-top:26px}.feedback li{margin:10px 0;color:#c5ced7;font-size:13px}
@media(max-width:620px){main{padding:24px 16px}header{flex-direction:column;gap:14px}
  h1{font-size:25px}.options{grid-template-columns:1fr}.card{padding:20px}.card p{margin-bottom:18px}}
</style>
</head>
<body><main>
<header><div><p class="eyebrow">Practice your way</p><h1>Practice &amp; review</h1>
<p class="intro">Try unfamiliar requirements, or revisit a problem you have already worked on.</p></div>
<div class="current">Current variant <strong>{{ current }}</strong></div></header>
<div class="notice"><p><strong>Changes apply to your next attempt.</strong>
Save your work, then restart the challenge from the course page. Your current problem stays unchanged.</p></div>
{% if message %}<p class="status" role="status">{{ message }}</p>{% endif %}
{% if pending %}<p class="pending">Next start: <strong>{% if pending.mode == 'retry' %}{% if pending.attempt %}resume saved work for{% else %}retry{% endif %} variant {{ pending.variant }}{% else %}new random variant{% endif %}</strong>.</p>{% endif %}
<div class="options">
<section class="card" aria-labelledby="random-title"><div class="card-number">EXPLORE</div>
<h2 id="random-title">New Random Variant</h2>
<p>Test your skills on randomly selected requirements. You will get a different variant when one is available.</p>
<form method="post"><input type="hidden" name="csrf" value="{{ csrf }}">
<button class="primary" name="mode" value="random">Choose random variant</button></form></section>
<section class="card" aria-labelledby="retry-title"><div class="card-number">REVISIT</div>
<h2 id="retry-title">Retry a Previous Variant</h2><p>Pick up a familiar problem. Only variants you have already received appear here.</p>
<form method="post"><input type="hidden" name="csrf" value="{{ csrf }}">
<label for="previous-variant">Previous variant</label><select id="previous-variant" name="variant">{% for variant in encountered %}
<option value="{{ variant }}">Variant {{ variant }}</option>{% endfor %}</select>
<button name="mode" value="retry">Start this variant fresh</button></form></section>
</div>
<section class="history"><h2>Saved attempts</h2>
<p>Review your code and available test feedback, or resume an earlier attempt. Times are shown in Arizona time (MST).</p>
{% for attempt in saved_attempts %}<article class="attempt-row">
<div><strong>{% if attempt.variant %}Variant {{ attempt.variant }}{% else %}Older attempt · variant unknown{% endif %}</strong>
<p><time datetime="{{ attempt.saved_at }}">Saved {{ attempt.label }}</time></p></div>
<a class="review-link" href="?attempt={{ attempt.id|urlencode }}">Review attempt &rarr;</a></article>
{% else %}<p class="empty">Your saved work will appear here after you start another attempt.</p>{% endfor %}
</section><footer><a href="../">&larr; Return to the editor</a></footer>
</main></body></html>"""


REVIEW = PAGE.split("</head>")[0] + """</head><body><main>
<p class="eyebrow">Saved practice attempt</p><h1>{% if record.variant %}Variant {{ record.variant }}{% else %}Older attempt{% endif %}</h1>
<p class="intro">Saved {{ label }} · Arizona time</p>
<div class="notice"><p>This is a read-only review. Your active work is unchanged.
Resume copies saved source and data files into your next attempt; it does not restore compiled binaries or hidden tests.</p></div>
{% if resumable %}<form method="post" action="?">
<input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="attempt" value="{{ record.id }}">
<button class="primary" name="mode" value="resume">Resume this saved attempt next start</button></form>
{% else %}<p>The variant for this older folder is not reliably recorded, so it can be reviewed but not resumed automatically.</p>{% endif %}
<nav class="file-list" aria-label="Saved files">{% for name in names %}
<a href="?attempt={{ record.id|urlencode }}&amp;file={{ name|urlencode }}">{{ name }}</a>
{% else %}<p>No previewable source or text files were found.</p>{% endfor %}</nav>
{% if selected %}<h2>{{ selected }}</h2><pre>{{ content }}</pre>{% else %}<p>Select a file above to review it.</p>{% endif %}
<section class="feedback"><h2>Test feedback</h2><ul>{% for result in feedback %}
<li>{{ result.label }}: {% if result.passed >= 0 and result.failed >= 0 %}{{ result.passed }} passed, {{ result.failed }} failed{% else %}No completed test run{% endif %}{% if result.error_message %}<pre>{{ result.error_message }}</pre>{% endif %}</li>
{% else %}<li>No recorded test summary can be reliably linked to this attempt. Saved text logs, if present, are listed above.</li>{% endfor %}</ul></section>
<footer><a href="?">&larr; Back to practice choices</a></footer></main></body></html>"""


if __name__ == "__main__":
    if sys.argv[1:] == ["--restore"]:
        restore_current()
        sys.exit(0)
    parser = argparse.ArgumentParser()
    parser.add_argument("home")
    parser.add_argument("override")
    parser.add_argument("variants", nargs="+")
    args = parser.parse_args()
    with CONFIG.open() as stream:
        config = json.load(stream)
    attempt_id = Path("/opt/exam_attempt_startup_id").read_text().strip()
    if not attempt_id:
        raise ValueError("missing attempt ID")
    print(launch(config, args.home, args.variants, attempt_id, args.override))

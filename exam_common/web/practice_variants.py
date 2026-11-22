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
        chosen = select(entry, variants, attempt_id, override)
        # Keep the legacy cycle representation usable by existing exam setup.
        history[key] = entry["cycle"]
    # This catalogue is private to the service; HTTP responses expose encountered IDs only.
    with history_file(runtime) as state:
        state.clear()
        state.update(history=path, key=key, variants=variants, current=chosen)
    return chosen


def register_routes(app, config_path=CONFIG, runtime=ATTEMPT):
    from flask import abort, make_response, render_template_string, request
    csrf_token = secrets.token_urlsafe(32)

    @app.route("/exam_api/practice-variants", methods=["GET", "POST"])
    def practice_variants():
        with open(config_path) as stream:
            if not is_practice(json.load(stream)):
                abort(404)
        message = ""
        try:
            with open(runtime) as stream:
                state = json.load(stream)
            with history_file(state["history"]) as history:
                entry = history[METADATA][state["key"]]
                if request.method == "POST":
                    if not secrets.compare_digest(request.form.get("csrf", ""), csrf_token):
                        abort(403)
                    try:
                        queue(entry, state["variants"], request.form.get("mode"), request.form.get("variant"))
                    except ValueError as error:
                        abort(400, str(error))
                    message = "Selection saved for your next challenge start. Save your work, then restart this challenge from the course page."
                encountered = [v for v in entry["encountered"] if v in state["variants"]]
                pending = entry.get("pending", {})
            response = make_response(render_template_string(PAGE, current=state["current"],
                encountered=encountered, pending=pending, message=message, csrf=csrf_token))
        except (OSError, ValueError, KeyError):
            response = make_response("Practice variants are unavailable. Your current attempt is unchanged.", 503)
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
@media(max-width:620px){main{padding:24px 16px}header{flex-direction:column;gap:14px}
  h1{font-size:25px}.options{grid-template-columns:1fr}.card{padding:20px}.card p{margin-bottom:18px}}
</style>
</head>
<body><main>
<header><div><p class="eyebrow">Practice your way</p><h1>Practice variants</h1>
<p class="intro">Try unfamiliar requirements, or revisit a problem you have already worked on.</p></div>
<div class="current">Current variant <strong>{{ current }}</strong></div></header>
<div class="notice"><p><strong>Changes apply to your next attempt.</strong>
Save your work, then restart the challenge from the course page. Your current problem stays unchanged.</p></div>
{% if message %}<p class="status" role="status">{{ message }}</p>{% endif %}
{% if pending %}<p class="pending">Next start: <strong>{% if pending.mode == 'retry' %}retry variant {{ pending.variant }}{% else %}new random variant{% endif %}</strong>.</p>{% endif %}
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
<button name="mode" value="retry">Retry selected variant</button></form></section>
</div><footer><a href="../">&larr; Return to the editor</a></footer>
</main></body></html>"""


if __name__ == "__main__":
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

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


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<title>Practice variants</title>
<style>body{font:18px system-ui;max-width:700px;margin:3em auto;padding:1em}
button,select{font:inherit;padding:.5em}section{margin:2em 0}a{color:#2458b8}</style>
<h1>Practice variants</h1><p>Current variant: <strong>{{ current }}</strong></p>
<p>Choices apply to your next challenge start. Your current problem stays unchanged.
Save your work before restarting the challenge from the course page.</p>
{% if message %}<p role="status">{{ message }}</p>{% endif %}
{% if pending %}<p>Next start: {% if pending.mode == 'retry' %}retry {{ pending.variant }}{% else %}new random variant{% endif %}.</p>{% endif %}
<section><h2>New Random Variant</h2>
<p>Practice adapting to a randomly selected problem. A different variant is chosen when available.</p>
<form method="post"><input type="hidden" name="csrf" value="{{ csrf }}">
<button name="mode" value="random">Use a new random variant next start</button></form></section>
<section><h2>Retry a Previous Variant</h2><p>Only variants you have already received appear here.</p>
<form method="post"><input type="hidden" name="csrf" value="{{ csrf }}">
<label>Previous variant <select name="variant">{% for variant in encountered %}
<option value="{{ variant }}">{{ variant }}</option>{% endfor %}</select></label>
<button name="mode" value="retry">Retry this variant next start</button></form></section>
<p><a href="../">Return to the editor</a></p></html>"""


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

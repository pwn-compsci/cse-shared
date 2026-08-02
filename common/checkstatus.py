#!/usr/bin/env python3
"""
Hidden gate-status implementation for exam environments.

The real gate logic lives in class_sync's REST API. This command only gathers
local identity and asks what recent unfinished exam work still needs before the
student can regain access.
"""

import argparse
from datetime import datetime
import json
import os
import re
import shutil
import sys
import textwrap

import requests


API_URL = os.environ.get("EXAM_STUDENT_CHECKSTATUS_API_URL", "https://api.cse545.com/exam-gates/student-checkstatus")
DEFAULT_TOKEN = "08b26e01b8d9cb4f262da37836912504104296c33ab658dca836d032bc47b2ff"
USER_INFO_PATH = "/.user_info"
RING_PATH = "/opt/.ring"


class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


def colorize(text, color, enabled=True):
    if not enabled:
        return text
    return f"{color}{text}{Color.RESET}"


def read_api_token():
    try:
        with open(RING_PATH, "r") as token_file:
            token = token_file.read().strip()
            if token:
                return token
    except Exception:
        pass
    return os.environ.get("CSE240_API_TOKEN", DEFAULT_TOKEN)


def read_pwn_college_id():
    with open(USER_INFO_PATH, "r") as user_info:
        match = re.search(r"pwn_college_id='(\d+)'", user_info.read())
    if not match:
        raise RuntimeError(f"Could not find pwn_college_id in {USER_INFO_PATH}")
    return match.group(1)


def fetch_status(pwn_college_id, limit):
    response = requests.post(
        API_URL,
        headers={
            "Content-Type": "application/json",
            "X-API-Token": read_api_token(),
        },
        json={
            "pwn_college_id": pwn_college_id,
            "limit": limit,
        },
        timeout=15,
    )

    try:
        payload = response.json()
    except Exception:
        payload = {
            "status": "error",
            "message": response.text,
        }

    return response.status_code, payload


def terminal_width():
    return max(64, min(shutil.get_terminal_size((88, 24)).columns, 120))


def print_box(title, lines, color=Color.CYAN, color_enabled=True):
    width = terminal_width()
    inner_width = width - 4
    top = "╭" + "─" * (width - 2) + "╮"
    sep = "├" + "─" * (width - 2) + "┤"
    bottom = "╰" + "─" * (width - 2) + "╯"
    print(colorize(top, color, color_enabled))
    print(
        colorize("│ ", color, color_enabled)
        + visible_ljust(colorize(title[:inner_width], Color.BOLD, color_enabled), inner_width)
        + colorize(" │", color, color_enabled)
    )
    print(colorize(sep, color, color_enabled))
    for line in lines:
        for wrapped in wrap_visible(str(line), inner_width):
            print(
                colorize("│ ", color, color_enabled)
                + visible_ljust(wrapped, inner_width)
                + colorize(" │", color, color_enabled)
            )
    print(colorize(bottom, color, color_enabled))


def strip_ansi(text):
    return re.sub(r"\033\[[0-9;]*m", "", text)


def visible_ljust(text, width):
    return text + " " * max(0, width - len(strip_ansi(text)))


def wrap_visible(text, width):
    if not text:
        return [""]
    plain = strip_ansi(text)
    indent_match = re.match(r"^(\s+)", plain)
    subsequent_indent = indent_match.group(1) if indent_match else ""
    wrapper = textwrap.TextWrapper(
        width=width,
        replace_whitespace=False,
        drop_whitespace=False,
        subsequent_indent=subsequent_indent,
    )
    if plain == text:
        return wrapper.wrap(text) or [""]
    if len(plain) <= width:
        return [text]
    # ANSI-bearing lines are usually short status labels. If one is long, wrap
    # the plain text rather than slicing through escape sequences.
    return wrapper.wrap(plain) or [""]


def field(label, value):
    return f"{label:<18} {value}"


def requirement_label(requirement):
    req_type = requirement.get("requirement_type", "requirement")
    name = requirement.get("required_assignment_name")
    module = requirement.get("required_assignment_module_id")
    if req_type == "assignment":
        return name or "Required assignment"
    if req_type == "pwn":
        return name or module or "Required pwn.college work"
    if req_type == "consultation":
        return "Instructor or TA consultation"
    return "Required gate"


def attempt_label(attempt_number):
    try:
        attempt_number = int(attempt_number)
    except (TypeError, ValueError):
        attempt_number = 2
    if attempt_number == 0:
        return "First Attempt"
    if attempt_number == 1:
        return "Attempt 1"
    return f"Retry {attempt_number - 1}"


def requirement_mode(requirement):
    mode = requirement.get("satisfaction_mode")
    if requirement.get("requirement_type") == "assignment":
        return "full credit" if mode == "complete" else "attempt/submitted"
    if requirement.get("requirement_type") == "pwn":
        return "attempt level" if mode == "attempt" else "complete level"
    return ""


def format_access_window_remaining(deadline_date):
    if not deadline_date:
        return ""
    try:
        deadline_day = datetime.strptime(str(deadline_date), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return ""
    closes_at = datetime.combine(deadline_day, datetime.max.time().replace(microsecond=0))
    remaining = closes_at - datetime.now()
    if remaining.total_seconds() <= 0:
        return ""
    total_minutes = max(1, int(remaining.total_seconds() // 60))
    days = total_minutes // (24 * 60)
    hours = (total_minutes % (24 * 60)) // 60
    minutes = total_minutes % 60
    if days:
        return f"{days} day{'s' if days != 1 else ''}, {hours} hour{'s' if hours != 1 else ''} left"
    if hours:
        return f"{hours} hour{'s' if hours != 1 else ''}, {minutes} minute{'s' if minutes != 1 else ''} left"
    return f"{minutes} minute{'s' if minutes != 1 else ''} left"


def access_windows_by_attempt(gate_status):
    windows = {}
    for req in gate_status.get("requirements") or []:
        attempt_number = req.get("attempt_number")
        deadline = req.get("attempt_deadline_date")
        detail = req.get("attempt_deadline_detail")
        if not deadline and not detail:
            continue
        if attempt_number not in windows:
            windows[attempt_number] = {
                "passed": bool(req.get("attempt_deadline_passed")),
                "detail": detail or f"Access window closes at {deadline} 11:59 PM Arizona time",
                "deadline": deadline,
            }

    for missed in gate_status.get("missed_attempt_deadlines") or []:
        attempt_number = missed.get("attempt_number")
        windows[attempt_number] = {
            "passed": True,
            "detail": missed.get("detail") or "Access window closed",
            "deadline": missed.get("attempt_deadline_date"),
        }
    return windows


def print_status(payload, color_enabled=True):
    if payload.get("status") != "success":
        print_box(
            "Exam Check Status",
            [
                colorize("ERROR", Color.RED, color_enabled),
                payload.get("message", "Unable to check exam status."),
            ],
            color=Color.RED,
            color_enabled=color_enabled,
        )
        return 1

    student = payload.get("student_name", "Student")
    course = payload.get("course_code", "course")
    pwn_id = payload.get("pwn_college_id", "unknown")
    target = payload.get("current_target")

    if not target:
        print_box(
            "Exam Check Status",
            [
                f"{student} ({pwn_id}) in {course}",
                colorize("✅ No recent attempted exam problems are waiting on completion.", Color.GREEN, color_enabled),
                "If you expected an exam here, ask course staff to confirm the exam attempt was recorded.",
            ],
            color=Color.GREEN,
            color_enabled=color_enabled,
        )
        return 0

    module = target.get("module", "unknown module")
    challenge = target.get("challenge", "unknown challenge")
    assignment = target.get("assignment_name") or "Exam"
    challenge_name = target.get("challenge_name") or challenge
    attempts = target.get("attempt_count", 0)
    last_attempt = target.get("last_attempt_at") or "unknown time"
    gate_status = target.get("gate_status") or {}
    allowed = gate_status.get("allowed", False)

    header_lines = [
        field("Student", f"{student} ({pwn_id})"),
        field("Course", course),
        field("Exam", assignment),
        field("Problem", f"{module} / {challenge_name}"),
        field("Attempts", f"{attempts} recorded"),
        field("Last attempt", last_attempt),
    ]
    actual_attempts = gate_status.get("actual_attempt_count")
    next_attempt = gate_status.get("next_attempt_number")
    if actual_attempts is not None and next_attempt is not None:
        header_lines.append(field("Gate tier", f"{attempt_label(next_attempt)} (actual attempts: {actual_attempts})"))
    if allowed:
        header_lines.append(colorize("✅ Ready: requirements appear complete.", Color.GREEN, color_enabled))
    else:
        header_lines.append(colorize("⛔ Blocked: complete the items below before retrying.", Color.RED, color_enabled))

    print_box("Exam Access Checklist", header_lines, color=Color.CYAN if allowed else Color.YELLOW, color_enabled=color_enabled)

    missed_deadlines = gate_status.get("missed_attempt_deadlines") or []

    requirements = gate_status.get("requirements") or []
    unmet = gate_status.get("unmet_requirements") or [req for req in requirements if not req.get("satisfied")]

    if not requirements:
        print_box(
            "Requirements",
            [
                colorize("No gate requirements are configured for this exam problem.", Color.GREEN, color_enabled)
                if allowed else colorize("No detailed requirements were returned. Ask course staff for help.", Color.YELLOW, color_enabled)
            ],
            color=Color.GREEN if allowed else Color.YELLOW,
            color_enabled=color_enabled,
        )
    else:
        windows = access_windows_by_attempt(gate_status)
        groups = []
        for req in sorted(
            requirements,
            key=lambda item: (
                item.get("attempt_number") if item.get("attempt_number") is not None else 2,
                item.get("gate_requirement_id") or 0,
            )
        ):
            attempt_number = req.get("attempt_number") if req.get("attempt_number") is not None else 2
            if not groups or groups[-1]["attempt_number"] != attempt_number:
                groups.append({"attempt_number": attempt_number, "requirements": []})
            groups[-1]["requirements"].append(req)

        lines = []
        for group in groups:
            attempt_number = group["attempt_number"]
            group_requirements = group["requirements"]
            missing_count = sum(1 for req in group_requirements if not req.get("satisfied"))
            complete_count = len(group_requirements) - missing_count
            summary = (
                f"{complete_count} complete, {missing_count} still needed"
                if missing_count
                else f"{complete_count} complete"
            )
            header = colorize(f"{attempt_label(attempt_number)}", Color.CYAN, color_enabled)
            window = windows.get(attempt_number)
            if window:
                detail = str(window.get("detail") or "Access window closed")
                if window.get("passed"):
                    detail = detail.replace("Access window closed", "Access window expired", 1)
                    header += colorize(f"  ·  {detail}", Color.RED, color_enabled)
                else:
                    remaining = format_access_window_remaining(window.get("deadline"))
                    if remaining:
                        detail = f"{detail} ({remaining})"
                    header += colorize(f"  ·  {detail}", Color.RED, color_enabled)
            header += colorize(f"  ·  {summary}", Color.DIM, color_enabled)
            lines.append(header)

            for req in group_requirements:
                ok = bool(req.get("satisfied"))
                mark = colorize("✅ DONE", Color.GREEN, color_enabled) if ok else colorize("❌ TODO", Color.RED, color_enabled)
                detail = req.get("detail") or ("Complete" if ok else "Not complete")
                mode = requirement_mode(req)
                mode_suffix = f"  ·  {mode}" if mode else ""
                lines.append(f"  {mark}  {requirement_label(req)}{mode_suffix}")
                detail_color = Color.GREEN if ok else Color.YELLOW
                lines.append(colorize(f"        {detail}", detail_color, color_enabled))
                missing_levels = req.get("missing_levels") or []
                completed_levels = req.get("completed_levels") or []
                completed_label = "Attempted levels" if req.get("satisfaction_mode") == "attempt" else "Completed levels"
                if completed_levels:
                    lines.append(colorize(f"        {completed_label}: {', '.join(str(level) for level in completed_levels)}", Color.GREEN, color_enabled))
                if missing_levels:
                    lines.append(colorize(f"        Missing levels: {', '.join(str(level) for level in missing_levels)}", Color.YELLOW, color_enabled))
            lines.append("")

        print_box("Requirements", lines, color=Color.GREEN if not unmet else Color.YELLOW, color_enabled=color_enabled)

    recent = payload.get("recent_unpassed_exams") or []
    if len(recent) > 1:
        lines = []
        for exam in recent[1:]:
            gs = exam.get("gate_status") or {}
            status = "ready" if gs.get("allowed") else "blocked"
            lines.append(f"{exam.get('module')} / {exam.get('challenge')}  ({status}, attempts={exam.get('attempt_count', 0)})")
        print_box("Other Recent Unfinished Exams", lines, color=Color.BLUE, color_enabled=color_enabled)

    print(colorize("\nTip: run `checkstatus --json` if course staff asks for the raw status output.", Color.DIM, color_enabled))
    return 0 if allowed else 1


def main():
    parser = argparse.ArgumentParser(description="Show exam access gate status for your most recent unfinished exam.")
    parser.add_argument("--json", action="store_true", help="Print raw JSON from the status endpoint")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    parser.add_argument("--limit", type=int, default=5, help="Number of recent unfinished exams to include")
    args = parser.parse_args()

    try:
        pwn_college_id = read_pwn_college_id()
        status_code, payload = fetch_status(pwn_college_id, args.limit)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0 if status_code == 200 and payload.get("status") == "success" else 1
        return print_status(payload, color_enabled=not args.no_color)
    except Exception as exc:
        payload = {
            "status": "error",
            "message": str(exc),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print_box("Exam Check Status", [colorize("ERROR", Color.RED, True), str(exc)], color=Color.RED)
        return 1


if __name__ == "__main__":
    sys.exit(main())

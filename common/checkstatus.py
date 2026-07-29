#!/usr/bin/env python3
"""
Hidden gate-status implementation for exam environments.

The real gate logic lives in class_sync's REST API. This command only gathers
local identity and asks what recent unfinished exam work still needs before the
student can regain access.
"""

import argparse
import json
import os
import re
import shutil
import sys

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
    top = "+" + "-" * (width - 2) + "+"
    print(colorize(top, color, color_enabled))
    print(colorize("| ", color, color_enabled) + colorize(title[:inner_width].ljust(inner_width), Color.BOLD, color_enabled) + colorize(" |", color, color_enabled))
    print(colorize("|" + "-" * (width - 2) + "|", color, color_enabled))
    for line in lines:
        while len(strip_ansi(line)) > inner_width:
            cut = inner_width
            print(colorize("| ", color, color_enabled) + line[:cut].ljust(inner_width) + colorize(" |", color, color_enabled))
            line = line[cut:]
        print(colorize("| ", color, color_enabled) + line.ljust(inner_width) + colorize(" |", color, color_enabled))
    print(colorize(top, color, color_enabled))


def strip_ansi(text):
    return re.sub(r"\033\[[0-9;]*m", "", text)


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
        f"{student} ({pwn_id}) in {course}",
        f"Most recent unfinished exam: {assignment}",
        f"Problem: {module} / {challenge_name}",
        f"Attempts recorded: {attempts}   Last attempt: {last_attempt}",
    ]
    if allowed:
        header_lines.append(colorize("✅ Gate status: ready. Requirements appear complete.", Color.GREEN, color_enabled))
    else:
        header_lines.append(colorize("❌ Gate status: blocked. Complete the items below before retrying.", Color.RED, color_enabled))

    print_box("Exam Access Checklist", header_lines, color=Color.CYAN if allowed else Color.YELLOW, color_enabled=color_enabled)

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
        lines = []
        for req in requirements:
            ok = bool(req.get("satisfied"))
            mark = colorize("✅ DONE", Color.GREEN, color_enabled) if ok else colorize("❌ TODO", Color.RED, color_enabled)
            detail = req.get("detail") or ("Complete" if ok else "Not complete")
            lines.append(f"{mark}  {requirement_label(req)}")
            lines.append(f"      {detail}")
            missing_levels = req.get("missing_levels") or []
            if missing_levels:
                lines.append(colorize(f"      Missing levels: {', '.join(str(level) for level in missing_levels)}", Color.YELLOW, color_enabled))

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

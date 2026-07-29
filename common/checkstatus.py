#!/usr/bin/env python3
"""
Hidden gate-status implementation for exam environments.

The real gate logic lives in class_sync's REST API. This wrapper only gathers
local identity/problem metadata and delegates the decision.
"""

import json
import os
import re
import sys

import requests


API_URL = os.environ.get("EXAM_GATE_STATUS_API_URL", "https://api.cse545.com/exam-gates/checkstatus")
DEFAULT_TOKEN = "08b26e01b8d9cb4f262da37836912504104296c33ab658dca836d032bc47b2ff"
USER_INFO_PATH = "/.user_info"
LEVEL_CONFIG_PATH = "/challenge/.config/level.json"
RING_PATH = "/opt/.ring"


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


def read_exam_metadata():
    with open(LEVEL_CONFIG_PATH, "r") as level_file:
        level_config = json.load(level_file)

    module = level_config.get("module")
    challenge = level_config.get("challenge") or level_config.get("examLevel")
    if not module or not challenge:
        raise RuntimeError(f"Could not find module/challenge in {LEVEL_CONFIG_PATH}")
    return module, challenge


def main():
    try:
        pwn_college_id = read_pwn_college_id()
        module, challenge = read_exam_metadata()
        response = requests.post(
            API_URL,
            headers={
                "Content-Type": "application/json",
                "X-API-Token": read_api_token(),
            },
            json={
                "pwn_college_id": pwn_college_id,
                "module": module,
                "challenge": challenge,
            },
            timeout=15,
        )

        try:
            payload = response.json()
        except Exception:
            payload = {
                "status": "error",
                "allowed": False,
                "message": response.text,
            }

        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if response.status_code == 200 and payload.get("allowed") else 1
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "allowed": False,
            "message": str(exc),
        }, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())

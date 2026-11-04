#!/usr/bin/env python3
"""Match backend semester dojos to validated local deployment candidates on stdin."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.request import urlopen


def dojo_id(directory):
    for line in (directory / 'dojo.yml').read_text().splitlines():
        match = re.match(r'^id:\s*([^#]+)', line)
        if match:
            return match.group(1).strip().strip('\"\'')
    return None


def resolve(payload, candidates):
    if (not isinstance(payload, dict) or not isinstance(payload.get('dojos'), list)
            or not isinstance(payload.get('year'), int)
            or payload.get('semester') not in ('Spring', 'Summer', 'Fall')):
        raise ValueError('Invalid current-semester dojo response')
    selected = set()
    candidates = {Path(p).resolve() for p in candidates}
    ids = {p: dojo_id(p) for p in candidates}
    for entry in payload['dojos']:
        if not isinstance(entry, dict) or not isinstance(entry.get('pwn_dojo_hash'), str) or not entry['pwn_dojo_hash'].strip():
            raise ValueError('Invalid dojo entry')
        name = entry['pwn_dojo_hash'].strip()
        configured = entry.get('pwn_college_dir')
        if configured is not None and not isinstance(configured, str):
            raise ValueError('Invalid dojo directory')
        exact = set()
        if configured and Path(configured).is_absolute():
            exact = {p for p in candidates if p == Path(configured).resolve()}
        # Directory metadata takes precedence; otherwise match repo name or dojo id.
        aliases = {name, name.split('~', 1)[0]}
        if configured:
            aliases.add(Path(configured).name)
        matches = exact or {p for p in candidates if p.name in aliases or ids[p] in aliases}
        if len(matches) == 1:
            selected.update(matches)
        elif matches:
            print(f'{name} was not updated: multiple matching local dojo directories.', file=sys.stderr)
        else:
            print(f'{name} was not updated: no matching local directory with dojo.yml, '
                  'an executable update_dojo.sh, and a cse-shared submodule '
                  f'(configured directory: {configured or "not provided"}).', file=sys.stderr)
    return sorted(map(str, selected))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', required=True)
    args = parser.parse_args()
    try:
        with urlopen(args.api_url, timeout=20) as response:
            payload = json.load(response)
        candidates = [line.rstrip('\n') for line in sys.stdin if line.strip()]
        results = resolve(payload, candidates)
    except Exception as exc:
        print(f'Current-semester dojo lookup failed: {exc}. No deployment will run.', file=sys.stderr)
        return 1
    print(f'Backend semester: {payload["semester"]} {payload["year"]}', file=sys.stderr)
    for result in results:
        print(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())

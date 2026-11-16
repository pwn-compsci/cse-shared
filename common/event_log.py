"""Atomic skipped log updates; lock protocol shared with pwn-cpmate."""
import json
import os
import time
import uuid
from pathlib import Path


def update_event_log(file, update):
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    lock = Path(str(file) + '.lock')
    deadline = time.monotonic() + 30
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f'Log lock remains held: {lock}')
            time.sleep(.02)
    temp = Path(str(file) + '.tmp-' + uuid.uuid4().hex)
    try:
        data = {}
        if file.exists():
            raw = file.read_bytes()
            try:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError('Invalid log root')
            except (ValueError, UnicodeError):
                backup = Path(str(file) + '.malformed-' + uuid.uuid4().hex)
                with backup.open('xb') as stream:
                    stream.write(raw)
                data = {}
        update(data)
        with temp.open('x') as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, file)
    finally:
        temp.unlink(missing_ok=True)
        lock.rmdir()

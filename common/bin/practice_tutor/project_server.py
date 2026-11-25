"""Container-local lab/project tutor, behind the workspace's authenticated code proxy."""
from pathlib import Path
import re
from flask import Flask
from practice_tutor import register_routes

app = Flask(__name__)


def identity():
    text = Path('/.user_info').read_text()
    match = re.search(r"^pwn_college_id='(\d+)'$", text, re.M)
    if not match:
        raise ValueError('Missing container identity')
    return match[1]


register_routes(app, identity, lambda: True)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, threaded=True)

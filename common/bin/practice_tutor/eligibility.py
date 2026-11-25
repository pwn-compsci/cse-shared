"""Fail-closed lab/project eligibility. Practice exams are not opted in yet."""
import re


def exam_configuration(config):
    if not isinstance(config, dict):
        return True
    names = ' '.join(str(config.get(key, '')) for key in ('module', 'challenge'))
    if re.search(r'exam|(?:^|[ /_-])pex\d', names, re.I):
        return True
    # No enrollment/admin exception may override an assessment marker.
    for key, value in config.items():
        if 'exam' in key.lower() and value not in (None, False, 0, '', 'false', '0', 'none', 'null'):
            return True
    return False


def allowed_config(config, targets):
    if exam_configuration(config) or config.get('course_code') != 'cse240':
        return False
    module, challenge = config.get('module'), config.get('challenge')
    return isinstance(module, str) and isinstance(challenge, str) and challenge in targets.get(module, [])


def enabled(config):
    import json
    from pathlib import Path
    try:
        targets = json.loads(Path(__file__).with_name('targets.json').read_text())
    except (OSError, ValueError):
        return False
    return (allowed_config(config, targets)
            and config.get('practice_tutor', {}).get('enabled') is True
            and config['practice_tutor'].get('course_dir') == '/cse/intro-to-programming-languages'
            and not Path('/opt/exam_attempt_startup_id').exists())

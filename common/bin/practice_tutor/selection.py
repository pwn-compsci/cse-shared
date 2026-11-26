"""Resolve an opaque attempt ID from root-owned practice state, never a client path."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone


def resolve(attempt=None, config_path=Path('/challenge/.config/level.json'), runtime=Path('/opt/practice_variant_attempt.json')):
    import practice_attempts as attempts
    from practice_variants import history_file, METADATA
    config = json.loads(config_path.read_text())
    with history_file(runtime) as state:
        state = dict(state)
    with history_file(state['history']) as history:
        entry = history[METADATA][state['key']]
        if attempt:
            if not isinstance(attempt, str) or len(attempt) > 180:
                raise ValueError('Invalid attempt')
            record, work = attempts.find_attempt(entry, attempt, Path(state['workdir']))
            record = dict(record)
            label = 'Saved attempt ' + attempts.display_time(record['saved_at'])
        else:
            record = dict(variant=state['current'], started_at=entry.get('started_at'),
                          saved_at=datetime.now(timezone.utc).isoformat())
            work = Path(state['workdir'])
            label = 'Current attempt'
        variant = record.get('variant')
        if variant not in list('abcdefghij') or not record.get('started_at'):
            raise ValueError('This old attempt has no reliable question identity')
        key = variant + ':' + hashlib.sha256(record['started_at'].encode()).hexdigest()[:32]
        return dict(workdir=str(work), home=state['home'], record=record, config=config,
                    selection=dict(key=key, variant=variant, attempt=attempt, label=label + ' : ' + str(config.get('level', '')) + variant.upper()))

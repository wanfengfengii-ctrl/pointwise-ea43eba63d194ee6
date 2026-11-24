import json

from lab import write_transaction


def initialize_manifests(connection):
    connection.execute('''
        CREATE TABLE IF NOT EXISTS trial_manifests (
            trial_id TEXT PRIMARY KEY NOT NULL,
            definition TEXT NOT NULL
        )
    ''')


def store_manifest(connection, trial_id, definition):
    encoded = json.dumps(definition, sort_keys=True, separators=(',', ':'))
    with write_transaction(connection):
        connection.execute('''
            INSERT INTO trial_manifests (trial_id, definition) VALUES (?, ?)
            ON CONFLICT (trial_id) DO NOTHING
        ''', (trial_id, encoded))
        current = connection.execute(
            'SELECT definition FROM trial_manifests WHERE trial_id = ?', (trial_id,)
        ).fetchone()
        if current[0] != encoded:
            raise ValueError(f'trial {trial_id!r} already has a different definition')


def fetch_manifest(connection, trial_id):
    row = connection.execute(
        'SELECT definition FROM trial_manifests WHERE trial_id = ?', (trial_id,)
    ).fetchone()
    if row is None:
        raise LookupError(f'unknown trial {trial_id!r}')
    return json.loads(row[0])

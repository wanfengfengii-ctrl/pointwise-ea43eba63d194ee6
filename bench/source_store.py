from dataclasses import dataclass

from bench.readings import Reading
from lab import require_record_id, write_transaction
from trial.units import decode_fraction, encode_fraction


@dataclass(frozen=True)
class StoredRevision:
    trial_id: str
    role: str
    parent_revision_id: int | None
    readings: tuple[Reading, ...]


def initialize_source(connection):
    connection.execute('''
        CREATE TABLE IF NOT EXISTS bench_revisions (
            revision_id INTEGER PRIMARY KEY,
            trial_id TEXT NOT NULL REFERENCES trial_manifests(trial_id),
            role TEXT NOT NULL,
            parent_revision_id INTEGER REFERENCES bench_revisions(revision_id)
        )
    ''')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS bench_readings (
            revision_id INTEGER NOT NULL REFERENCES bench_revisions(revision_id),
            row_position INTEGER NOT NULL,
            segment TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (revision_id, row_position)
        )
    ''')


def insert_revision(connection, trial_id, role, parent_revision_id, readings):
    encoded = [
        (position, reading.segment, None if reading.value is None else encode_fraction(reading.value))
        for position, reading in enumerate(readings)
    ]
    with write_transaction(connection):
        cursor = connection.execute('''
            INSERT INTO bench_revisions (trial_id, role, parent_revision_id) VALUES (?, ?, ?)
        ''', (trial_id, role, parent_revision_id))
        revision_id = cursor.lastrowid
        connection.executemany('''
            INSERT INTO bench_readings (revision_id, row_position, segment, value) VALUES (?, ?, ?, ?)
        ''', ((revision_id, position, segment, value) for position, segment, value in encoded))
    return revision_id


def fetch_revision(connection, revision_id, *, include_readings=True):
    require_record_id(revision_id, 'revision ID')
    header = connection.execute('''
        SELECT trial_id, role, parent_revision_id FROM bench_revisions WHERE revision_id = ?
    ''', (revision_id,)).fetchone()
    if header is None:
        raise LookupError(f'unknown revision {revision_id}')
    readings = ()
    if include_readings:
        rows = connection.execute('''
            SELECT segment, value FROM bench_readings WHERE revision_id = ? ORDER BY row_position
        ''', (revision_id,))
        readings = tuple(Reading(segment, None if text is None else decode_fraction(text))
                         for segment, text in rows)
    return StoredRevision(*header, readings)

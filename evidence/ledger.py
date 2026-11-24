from dataclasses import dataclass
from uuid import uuid4

from evidence.payload import StationEnvelope, StationPayload, decode_payload
from lab import require_record_id, write_transaction


@dataclass(frozen=True)
class ReceivedEvidence:
    received_id: int
    envelope: StationEnvelope
    payload: StationPayload

    @property
    def origin(self):
        return self.envelope.origin


def initialize_issue_ledger(connection):
    connection.execute('''
        CREATE TABLE IF NOT EXISTS issued_evidence (
            issue_id TEXT PRIMARY KEY NOT NULL,
            revision_id INTEGER NOT NULL REFERENCES bench_revisions(revision_id),
            envelope TEXT NOT NULL
        )
    ''')


def initialize_intake_ledger(connection):
    connection.execute('''
        CREATE TABLE IF NOT EXISTS received_evidence (
            received_id INTEGER PRIMARY KEY,
            trial_id TEXT NOT NULL REFERENCES trial_manifests(trial_id),
            issue_id TEXT NOT NULL,
            envelope TEXT NOT NULL
        )
    ''')


def allocate_issue_id():
    return uuid4().hex


def save_issued(connection, envelope):
    origin = envelope.origin
    with write_transaction(connection):
        connection.execute('''
            INSERT INTO issued_evidence (issue_id, revision_id, envelope) VALUES (?, ?, ?)
        ''', (origin.issue_id, origin.revision_id, envelope.to_json()))


def save_received(connection, envelope, payload):
    with write_transaction(connection):
        cursor = connection.execute('''
            INSERT INTO received_evidence (trial_id, issue_id, envelope) VALUES (?, ?, ?)
        ''', (envelope.origin.trial_id, envelope.origin.issue_id, envelope.to_json()))
        received_id = cursor.lastrowid
    return ReceivedEvidence(received_id, envelope, payload)


def load_received(connection, received_id):
    require_record_id(received_id, 'received ID')
    row = connection.execute('''
        SELECT envelope FROM received_evidence WHERE received_id = ?
    ''', (received_id,)).fetchone()
    if row is None:
        raise LookupError(f'unknown received evidence {received_id}')
    envelope = StationEnvelope.from_json(row[0])
    return ReceivedEvidence(received_id, envelope, decode_payload(envelope.body))

from dataclasses import dataclass
from uuid import uuid4

from evidence.payload import StationEnvelope, StationPayload, decode_payload
from evidence.supplement import SupplementEnvelope, SupplementPayload, decode_supplement_body
from lab import require_record_id, write_transaction


@dataclass(frozen=True)
class ReceivedEvidence:
    received_id: int
    envelope: StationEnvelope
    payload: StationPayload

    @property
    def origin(self):
        return self.envelope.origin


@dataclass(frozen=True)
class ReceivedSupplement:
    supplement_received_id: str
    parent_received_id: int
    envelope: SupplementEnvelope
    payload: SupplementPayload


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
    connection.execute('''
        CREATE TABLE IF NOT EXISTS received_supplements (
            supplement_received_id TEXT PRIMARY KEY NOT NULL,
            parent_received_id INTEGER NOT NULL REFERENCES received_evidence(received_id),
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


def load_issued(connection, issue_id):
    if (not isinstance(issue_id, str) or len(issue_id) != 32
            or not all(character in '0123456789abcdef' for character in issue_id)):
        raise ValueError('invalid issue ID')
    row = connection.execute(
        'SELECT envelope FROM issued_evidence WHERE issue_id = ?', (issue_id,)
    ).fetchone()
    if row is None:
        raise LookupError(f'unknown issued evidence {issue_id}')
    return StationEnvelope.from_json(row[0])


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


def save_received_supplement(connection, parent_received_id, envelope, payload):
    supplement_received_id = uuid4().hex
    with write_transaction(connection):
        connection.execute('''
            INSERT INTO received_supplements (supplement_received_id, parent_received_id, envelope)
            VALUES (?, ?, ?)
        ''', (supplement_received_id, parent_received_id, envelope.to_json()))
    return ReceivedSupplement(supplement_received_id, parent_received_id, envelope, payload)


def load_supplement(connection, supplement_received_id):
    if not isinstance(supplement_received_id, str) or not supplement_received_id:
        raise ValueError('supplement received ID must be nonempty text')
    row = connection.execute('''
        SELECT parent_received_id, envelope FROM received_supplements
        WHERE supplement_received_id = ?
    ''', (supplement_received_id,)).fetchone()
    if row is None:
        raise LookupError(f'unknown received supplement {supplement_received_id}')
    envelope = SupplementEnvelope.from_json(row[1])
    return ReceivedSupplement(
        supplement_received_id, row[0], envelope, decode_supplement_body(envelope.body)
    )

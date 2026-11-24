import json
from dataclasses import dataclass

from analysis.joint_fit import BoundaryOptimum, JointDecision
from evidence.provenance import IssuedOrigin, canonical_json
from lab import require_record_id, write_transaction
from trial.order import SegmentBoundary
from trial.units import decode_fraction, encode_fraction


@dataclass(frozen=True)
class ReportParent:
    received_id: int
    origin: IssuedOrigin

    def to_data(self):
        return {'received_id': self.received_id, 'origin': self.origin.to_data()}


@dataclass(frozen=True)
class ReportSnapshot:
    report_id: int
    trial_id: str
    decision: JointDecision
    parents: tuple[ReportParent, ReportParent]


def initialize_reports(connection):
    connection.execute('''
        CREATE TABLE IF NOT EXISTS signed_reports (
            report_id INTEGER PRIMARY KEY,
            trial_id TEXT NOT NULL REFERENCES trial_manifests(trial_id),
            decision TEXT NOT NULL
        )
    ''')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS signed_report_parents (
            report_id INTEGER NOT NULL REFERENCES signed_reports(report_id),
            parent_position INTEGER NOT NULL CHECK (parent_position IN (0, 1)),
            received_id INTEGER NOT NULL REFERENCES received_evidence(received_id),
            origin TEXT NOT NULL,
            PRIMARY KEY (report_id, parent_position),
            UNIQUE (report_id, received_id)
        )
    ''')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS success_receipts (
            receipt_id INTEGER PRIMARY KEY,
            report_id INTEGER NOT NULL UNIQUE REFERENCES signed_reports(report_id)
        )
    ''')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS review_reports (
            review_id INTEGER PRIMARY KEY,
            old_report_id INTEGER NOT NULL REFERENCES signed_reports(report_id),
            clauses TEXT NOT NULL,
            basis TEXT NOT NULL,
            intervals TEXT NOT NULL
        )
    ''')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS review_receipts (
            receipt_id INTEGER PRIMARY KEY,
            review_id INTEGER NOT NULL UNIQUE REFERENCES review_reports(review_id)
        )
    ''')


def publication_transaction(connection):
    return write_transaction(connection)


def decision_to_data(decision):
    return {
        'status': decision.status,
        'minimum': None if decision.minimum is None else encode_fraction(decision.minimum),
        'optima': [
            {
                'position': optimum.boundary.position,
                'before': optimum.boundary.before,
                'after': optimum.boundary.after,
                'low_shift': encode_fraction(optimum.low_shift),
                'high_shift': encode_fraction(optimum.high_shift),
            }
            for optimum in decision.optima
        ],
    }


def _decode_decision(encoded):
    data = json.loads(encoded)
    minimum = None if data['minimum'] is None else decode_fraction(data['minimum'])
    optima = tuple(
        BoundaryOptimum(
            SegmentBoundary(item['position'], item['before'], item['after']), minimum,
            decode_fraction(item['low_shift']), decode_fraction(item['high_shift']),
        )
        for item in data['optima']
    )
    return JointDecision(data['status'], minimum, optima)


def _require_publication_transaction(connection):
    if not connection.in_transaction:
        raise RuntimeError('publication writes require a transaction')


def insert_report(connection, trial_id, decision, parents):
    _require_publication_transaction(connection)
    if len(parents) != 2:
        raise ValueError('a signed report requires two parents')
    cursor = connection.execute('''
        INSERT INTO signed_reports (trial_id, decision) VALUES (?, ?)
    ''', (trial_id, canonical_json(decision_to_data(decision))))
    report_id = cursor.lastrowid
    connection.executemany('''
        INSERT INTO signed_report_parents (report_id, parent_position, received_id, origin)
        VALUES (?, ?, ?, ?)
    ''', (
        (report_id, position, parent.received_id, canonical_json(parent.origin.to_data()))
        for position, parent in enumerate(parents)
    ))
    return ReportSnapshot(report_id, trial_id, decision, parents)


def fetch_report(connection, report_id):
    require_record_id(report_id, 'report ID')
    row = connection.execute('''
        SELECT trial_id, decision FROM signed_reports WHERE report_id = ?
    ''', (report_id,)).fetchone()
    if row is None:
        raise LookupError(f'unknown report {report_id}')
    origins = connection.execute('''
        SELECT received_id, origin FROM signed_report_parents
        WHERE report_id = ? ORDER BY parent_position
    ''', (report_id,))
    parents = tuple(ReportParent(received_id, IssuedOrigin.from_data(json.loads(origin)))
                    for received_id, origin in origins)
    if len(parents) != 2:
        raise RuntimeError(f'report {report_id} does not have its two parent snapshots')
    return ReportSnapshot(report_id, row[0], _decode_decision(row[1]), parents)


def insert_receipt(connection, report_id):
    _require_publication_transaction(connection)
    cursor = connection.execute('INSERT INTO success_receipts (report_id) VALUES (?)', (report_id,))
    return cursor.lastrowid


def fetch_receipt(connection, report_id):
    require_record_id(report_id, 'report ID')
    row = connection.execute('SELECT receipt_id FROM success_receipts WHERE report_id = ?', (report_id,)).fetchone()
    if row is None:
        raise LookupError(f'no success receipt for report {report_id}')
    return row[0]


def insert_review(connection, old_report_id, clauses, basis, intervals):
    _require_publication_transaction(connection)
    cursor = connection.execute('''
        INSERT INTO review_reports (old_report_id, clauses, basis, intervals) VALUES (?, ?, ?, ?)
    ''', (old_report_id, canonical_json(clauses), canonical_json(basis), canonical_json(intervals)))
    review_id = cursor.lastrowid
    cursor = connection.execute('INSERT INTO review_receipts (review_id) VALUES (?)', (review_id,))
    return review_id, cursor.lastrowid


def fetch_review(connection, review_id):
    require_record_id(review_id, 'review ID')
    row = connection.execute('''
        SELECT old_report_id, clauses, basis, intervals FROM review_reports WHERE review_id = ?
    ''', (review_id,)).fetchone()
    if row is None:
        raise LookupError(f'unknown review {review_id}')
    receipt = connection.execute(
        'SELECT receipt_id FROM review_receipts WHERE review_id = ?', (review_id,)
    ).fetchone()
    if receipt is None:
        raise LookupError(f'no success receipt for review {review_id}')
    return {
        'review_id': review_id,
        'receipt_id': receipt[0],
        'old_report_id': row[0],
        'clauses': json.loads(row[1]),
        'basis': json.loads(row[2]),
        'intervals': json.loads(row[3]),
    }

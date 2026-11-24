import sqlite3
from contextlib import contextmanager


@contextmanager
def write_transaction(connection):
    if connection.in_transaction:
        raise sqlite3.ProgrammingError('operation requires its own transaction')
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise


def require_record_id(value, label):
    if type(value) is not int or not 1 <= value < 2**63:
        raise ValueError(f'{label} must be a positive SQLite integer')
    return value


def _open(path, initializers):
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute('PRAGMA foreign_keys = ON')
        with write_transaction(connection):
            for initialize in initializers:
                initialize(connection)
        return connection
    except BaseException:
        connection.close()
        raise


def open_source(path):
    from bench.source_store import initialize_source
    from evidence.ledger import initialize_issue_ledger
    from trial.manifest_store import initialize_manifests

    return _open(path, (initialize_manifests, initialize_source, initialize_issue_ledger))


def open_center(path):
    from evidence.ledger import initialize_intake_ledger
    from report.register import initialize_reports
    from trial.manifest_store import initialize_manifests

    return _open(path, (initialize_manifests, initialize_intake_ledger, initialize_reports))

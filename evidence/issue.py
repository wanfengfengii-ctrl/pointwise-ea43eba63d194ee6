from fractions import Fraction

from bench.revisions import load_revision
from evidence.ledger import allocate_issue_id, load_issued, save_issued
from evidence.payload import StationEnvelope, V1_VERSION, encode_payload
from evidence.projection import project_revision
from evidence.provenance import IssuedOrigin, bind_origin
from evidence.supplement import (
    SUPPLEMENT_VERSION,
    SupplementEnvelope,
    SupplementPayload,
    SupplementReading,
    encode_supplement_body,
    parse_clause,
)


def issue(connection, revision_id):
    revision = load_revision(connection, revision_id)
    body = encode_payload(project_revision(revision))
    origin = IssuedOrigin(
        allocate_issue_id(), revision.revision_id, revision.manifest.trial_id,
        revision.manifest.manifest_key, revision.role,
    )
    envelope = StationEnvelope(V1_VERSION, origin, body, bind_origin(V1_VERSION, origin, body))
    save_issued(connection, envelope)
    return envelope


def issue_supplement(connection, issue_id, clauses):
    envelope = load_issued(connection, issue_id)
    origin = envelope.origin
    revision = load_revision(connection, origin.revision_id)
    if isinstance(clauses, (str, bytes)):
        raise ValueError('clauses must be an iterable of clause rows')
    try:
        submitted = list(clauses)
    except TypeError as exc:
        raise ValueError('clauses must be an iterable of clause rows') from exc
    if not submitted:
        raise ValueError('a supplement requires at least one clause')
    station_clauses = []
    for row in submitted:
        clause = parse_clause(revision.manifest, row)
        if clause.role != origin.role:
            raise ValueError('supplement clauses must belong to the issuing bench role')
        station_clauses.append(clause)
    station_clauses.sort(key=lambda clause: clause.to_data())
    valid = [
        (position, reading.segment, reading.value)
        for position, reading in enumerate(revision.readings)
        if reading.value is not None
    ]
    # Absolute readings and the bench zero stay at the station; only relative values leave.
    zero = valid[0][2] if valid else Fraction(0)
    payload = SupplementPayload(
        tuple(station_clauses),
        tuple(
            SupplementReading(position, segment, value - zero)
            for position, segment, value in valid
        ),
    )
    body = encode_supplement_body(payload)
    supplement = SupplementEnvelope(
        SUPPLEMENT_VERSION, origin, body, bind_origin(SUPPLEMENT_VERSION, origin, body)
    )
    return supplement.to_json()

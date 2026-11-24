from evidence.ledger import load_received, save_received, save_received_supplement
from evidence.payload import StationEnvelope, V1_VERSION, decode_payload
from evidence.provenance import verify_origin
from evidence.supplement import SUPPLEMENT_VERSION, SupplementEnvelope, decode_supplement_body
from trial.catalog import load_trial
from trial.order import segment_index
from trial.roles import require_role


def receive(connection, trial_id, station):
    manifest = load_trial(connection, trial_id)
    envelope = StationEnvelope.from_json(station) if isinstance(station, str) else station
    if not isinstance(envelope, StationEnvelope):
        raise ValueError('expected a V1 station envelope')
    if type(envelope.version) is not int or envelope.version != V1_VERSION:
        raise ValueError('unsupported station envelope version')
    verify_origin(envelope.version, envelope.origin, envelope.body, envelope.binding)
    origin = envelope.origin
    if (origin.trial_id, origin.manifest_key) != (manifest.trial_id, manifest.manifest_key):
        raise ValueError('station evidence belongs to a different manifest')
    require_role(manifest.roles, origin.role)
    payload = decode_payload(envelope.body)
    if len(payload.boundaries) != len(manifest.segments) - 1:
        raise ValueError('station body does not match the manifest boundary count')
    return save_received(connection, envelope, payload)


def receive_supplement(connection, parent_received_id, supplement):
    received = load_received(connection, parent_received_id)
    envelope = SupplementEnvelope.from_json(supplement) if isinstance(supplement, str) else supplement
    if not isinstance(envelope, SupplementEnvelope):
        raise ValueError('expected a supplement envelope')
    if type(envelope.version) is not int or envelope.version != SUPPLEMENT_VERSION:
        raise ValueError('unsupported supplement envelope version')
    verify_origin(envelope.version, envelope.origin, envelope.body, envelope.binding)
    origin = envelope.origin
    if origin != received.origin:
        raise ValueError('supplement does not match the received station evidence')
    manifest = load_trial(connection, origin.trial_id)
    if (origin.trial_id, origin.manifest_key) != (manifest.trial_id, manifest.manifest_key):
        raise ValueError('supplement belongs to a different manifest')
    payload = decode_supplement_body(envelope.body)
    for clause in payload.clauses:
        if clause.role != origin.role:
            raise ValueError('supplement clauses must belong to the station bench role')
        segment_index(manifest.segments, clause.segment)
    for reading in payload.readings:
        segment_index(manifest.segments, reading.segment)
    stored = save_received_supplement(connection, received.received_id, envelope, payload)
    return stored.supplement_received_id

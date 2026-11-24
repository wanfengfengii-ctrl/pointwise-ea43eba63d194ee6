from evidence.ledger import save_received
from evidence.payload import StationEnvelope, V1_VERSION, decode_payload
from evidence.provenance import verify_origin
from trial.catalog import load_trial
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

from bench.revisions import load_revision
from evidence.ledger import allocate_issue_id, save_issued
from evidence.payload import StationEnvelope, V1_VERSION, encode_payload
from evidence.projection import project_revision
from evidence.provenance import IssuedOrigin, bind_origin


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

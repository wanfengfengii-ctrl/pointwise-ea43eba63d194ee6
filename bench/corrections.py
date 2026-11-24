from bench.source_store import fetch_revision


def require_correction_parent(connection, trial_id, role, parent_revision_id):
    if parent_revision_id is None:
        return
    parent = fetch_revision(connection, parent_revision_id, include_readings=False)
    if (parent.trial_id, parent.role) != (trial_id, role):
        raise ValueError('correction parent must have the same trial and bench role')

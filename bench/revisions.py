from dataclasses import dataclass

from bench.corrections import require_correction_parent
from bench.readings import Reading, normalize_readings
from bench.source_store import fetch_revision, insert_revision
from trial.catalog import TrialManifest, load_trial
from trial.roles import require_role


@dataclass(frozen=True)
class BenchRevision:
    revision_id: int
    manifest: TrialManifest
    role: str
    parent_revision_id: int | None
    readings: tuple[Reading, ...]


def record_revision(connection, trial_id, role, rows, *, parent_revision_id=None):
    manifest = load_trial(connection, trial_id)
    require_role(manifest.roles, role)
    require_correction_parent(connection, trial_id, role, parent_revision_id)
    readings = normalize_readings(manifest.segments, rows)
    revision_id = insert_revision(connection, trial_id, role, parent_revision_id, readings)
    return BenchRevision(revision_id, manifest, role, parent_revision_id, readings)


def load_revision(connection, revision_id):
    stored = fetch_revision(connection, revision_id)
    manifest = load_trial(connection, stored.trial_id)
    return BenchRevision(revision_id, manifest, stored.role, stored.parent_revision_id, stored.readings)

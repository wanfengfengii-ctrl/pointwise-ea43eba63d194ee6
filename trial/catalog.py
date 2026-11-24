import hashlib
import json
from dataclasses import dataclass

from trial.manifest_store import fetch_manifest, store_manifest
from trial.order import validate_segment_order
from trial.roles import BenchRoles, validate_roles
from trial.units import MICROMETRE, require_micrometre


@dataclass(frozen=True)
class TrialManifest:
    trial_id: str
    segments: tuple[str, ...]
    roles: BenchRoles
    unit: str

    def definition(self):
        return {'segments': list(self.segments), 'roles': list(self.roles), 'unit': self.unit}

    @property
    def manifest_key(self):
        data = {'trial_id': self.trial_id, **self.definition()}
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('ascii')).hexdigest()


def _require_trial_id(trial_id):
    if not isinstance(trial_id, str) or not trial_id.strip():
        raise ValueError('trial ID must be nonempty text')


def define_trial(connection, trial_id, segments, roles, unit=MICROMETRE):
    _require_trial_id(trial_id)
    manifest = TrialManifest(
        trial_id, validate_segment_order(segments), validate_roles(roles), require_micrometre(unit)
    )
    store_manifest(connection, trial_id, manifest.definition())
    return manifest


def load_trial(connection, trial_id):
    _require_trial_id(trial_id)
    definition = fetch_manifest(connection, trial_id)
    return TrialManifest(
        trial_id, tuple(definition['segments']), tuple(definition['roles']), definition['unit']
    )

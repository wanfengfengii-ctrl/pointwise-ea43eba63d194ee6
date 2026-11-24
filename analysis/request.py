from dataclasses import dataclass

from analysis.eligibility import common_boundaries
from analysis.joint_fit import fit_joint
from evidence.ledger import ReceivedEvidence, load_received
from report.publish import ReportDraft, commit_report
from report.register import ReportParent
from trial.catalog import TrialManifest, load_trial
from trial.roles import require_distinct_roles


@dataclass(frozen=True)
class ReceivedPair:
    manifest: TrialManifest
    first: ReceivedEvidence
    second: ReceivedEvidence


def resolve_received_pair(connection, trial_id, first_received_id, second_received_id):
    manifest = load_trial(connection, trial_id)
    first = load_received(connection, first_received_id)
    second = load_received(connection, second_received_id)
    for evidence in (first, second):
        if (evidence.origin.trial_id, evidence.origin.manifest_key) != (trial_id, manifest.manifest_key):
            raise ValueError('received pair must belong to the requested manifest')
    require_distinct_roles(manifest.roles, first.origin.role, second.origin.role)
    return ReceivedPair(manifest, first, second)


def publish(connection, trial_id, first_received_id, second_received_id):
    pair = resolve_received_pair(connection, trial_id, first_received_id, second_received_id)
    candidates = common_boundaries(pair.manifest, pair.first.payload, pair.second.payload)
    decision = fit_joint(candidates)
    draft = ReportDraft(trial_id, decision, (
        ReportParent(pair.first.received_id, pair.first.origin),
        ReportParent(pair.second.received_id, pair.second.origin),
    ))
    return commit_report(connection, draft)

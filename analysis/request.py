from collections.abc import Sequence
from dataclasses import dataclass

from analysis.eligibility import common_boundaries
from analysis.joint_fit import fit_joint
from analysis.review import ReviewPlan, StationReview, compute_intervals
from evidence.ledger import ReceivedEvidence, load_received, load_supplement
from evidence.supplement import parse_clause
from report.publish import ReportDraft, commit_report
from report.register import ReportParent, fetch_report, insert_review, publication_transaction
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


def _parse_order_clauses(manifest, clauses):
    if isinstance(clauses, (str, bytes)):
        raise ValueError('clauses must be a sequence of clause rows')
    try:
        rows = list(clauses)
    except TypeError as exc:
        raise ValueError('clauses must be a sequence of clause rows') from exc
    parsed = [parse_clause(manifest, row) for row in rows]
    for role in manifest.roles:
        if not any(clause.role == role for clause in parsed):
            raise ValueError('the work order needs at least one clause per bench role')
    return parsed


def _parse_supplement_ids(supplement_ids):
    if isinstance(supplement_ids, (str, bytes)) or not isinstance(supplement_ids, Sequence):
        raise ValueError('supplement IDs must be a sequence of two nonempty strings')
    ids = list(supplement_ids)
    if len(ids) != 2 or len(set(ids)) != 2:
        raise ValueError('supplement IDs must be two distinct nonempty strings')
    if any(not isinstance(item, str) or not item for item in ids):
        raise ValueError('supplement IDs must be two distinct nonempty strings')
    return ids


def publish_review(connection, old_report_id, clauses, supplement_ids):
    snapshot = fetch_report(connection, old_report_id)
    manifest = load_trial(connection, snapshot.trial_id)
    order_clauses = _parse_order_clauses(manifest, clauses)
    ids = _parse_supplement_ids(supplement_ids)
    supplements = [load_supplement(connection, supplement_id) for supplement_id in ids]
    matched = {}
    for supplement in supplements:
        hits = [
            position for position, parent in enumerate(snapshot.parents)
            if parent.origin == supplement.envelope.origin
        ]
        if len(hits) != 1:
            raise ValueError('supplement does not match an actual parent of the old report')
        position = hits[0]
        if position in matched:
            raise ValueError('each supplement must match a different parent of the old report')
        matched[position] = supplement
    if len(matched) != len(snapshot.parents):
        raise ValueError('the work order requires a supplement for each parent')
    stations = []
    station_clause_indices = []
    role_station = {}
    for position, parent in enumerate(snapshot.parents):
        supplement = matched[position]
        role = parent.origin.role
        bound = sorted(clause.to_data() for clause in supplement.payload.clauses)
        expected = sorted(clause.to_data() for clause in order_clauses if clause.role == role)
        if bound != expected:
            raise ValueError('supplement clauses do not match the work order clauses for its role')
        role_station[role] = len(stations)
        indices = tuple(index for index, clause in enumerate(order_clauses) if clause.role == role)
        stations.append(StationReview(
            tuple(
                (reading.row, reading.segment, reading.value)
                for reading in supplement.payload.readings
            ),
            tuple(order_clauses[index] for index in indices),
        ))
        station_clause_indices.append(indices)
    options = tuple(
        tuple(sorted(
            row for row, segment, _ in stations[role_station[clause.role]].readings
            if segment == clause.segment
        ))
        for clause in order_clauses
    )
    plan = ReviewPlan(tuple(stations), tuple(station_clause_indices), options)
    segment_positions = {segment: index for index, segment in enumerate(manifest.segments)}
    intervals = compute_intervals(plan, snapshot.decision.optima, segment_positions)
    clauses_data = [clause.to_data() for clause in order_clauses]
    basis = [
        [parent.received_id, parent.origin.issue_id, matched[position].supplement_received_id]
        for position, parent in enumerate(snapshot.parents)
    ]
    with publication_transaction(connection):
        review_id, receipt_id = insert_review(
            connection, snapshot.report_id, clauses_data, basis, intervals
        )
    return {
        'review_id': review_id,
        'receipt_id': receipt_id,
        'old_report_id': snapshot.report_id,
        'clauses': clauses_data,
        'basis': basis,
        'intervals': intervals,
    }

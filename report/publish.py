from dataclasses import dataclass

from analysis.joint_fit import JointDecision
from report.history import HistoricalReport
from report.receipt import record_success_receipt
from report.register import ReportParent, insert_report, publication_transaction


@dataclass(frozen=True)
class ReportDraft:
    trial_id: str
    decision: JointDecision
    parents: tuple[ReportParent, ReportParent]


def commit_report(connection, draft):
    with publication_transaction(connection):
        snapshot = insert_report(connection, draft.trial_id, draft.decision, draft.parents)
        receipt = record_success_receipt(connection, snapshot.report_id)
    return HistoricalReport(snapshot, receipt)

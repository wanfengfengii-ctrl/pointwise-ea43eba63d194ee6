from dataclasses import dataclass

from report.receipt import SuccessReceipt, load_success_receipt
from report.register import ReportSnapshot, fetch_report


@dataclass(frozen=True)
class HistoricalReport:
    snapshot: ReportSnapshot
    receipt: SuccessReceipt


def read(connection, report_id):
    snapshot = fetch_report(connection, report_id)
    receipt = load_success_receipt(connection, report_id)
    return HistoricalReport(snapshot, receipt)

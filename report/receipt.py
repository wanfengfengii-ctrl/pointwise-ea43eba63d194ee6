from dataclasses import dataclass

from report.register import fetch_receipt, insert_receipt


@dataclass(frozen=True)
class SuccessReceipt:
    receipt_id: int
    report_id: int

    def to_data(self):
        return {'receipt_id': self.receipt_id, 'report_id': self.report_id}


def record_success_receipt(connection, report_id):
    return SuccessReceipt(insert_receipt(connection, report_id), report_id)


def load_success_receipt(connection, report_id):
    return SuccessReceipt(fetch_receipt(connection, report_id), report_id)

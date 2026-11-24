import json

from report.history import read
from report.register import decision_to_data
from trial.units import MICROMETRE


def export_report(connection, report_id):
    historical = read(connection, report_id)
    snapshot = historical.snapshot
    return json.dumps({
        'report_id': snapshot.report_id,
        'trial_id': snapshot.trial_id,
        'unit': MICROMETRE,
        'decision': decision_to_data(snapshot.decision),
        'parents': [parent.to_data() for parent in snapshot.parents],
        'receipt': historical.receipt.to_data(),
    }, sort_keys=True, ensure_ascii=True, separators=(',', ':'))

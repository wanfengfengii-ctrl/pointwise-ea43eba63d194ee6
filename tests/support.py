import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from analysis.request import publish
from bench.revisions import record_revision
from evidence.intake import receive
from evidence.issue import issue
from lab import open_center, open_source
from trial.catalog import define_trial


SEGMENTS = ('S1', 'S2', 'S3', 'S4')
ROLES = ('甲', '乙')
SAME = (0, 0, 2, 2)
OPPOSITE = (2, 2, 0, 0)


class LabCase(TestCase):
    trial_id = 'CL-TEST'

    def setUp(self):
        directory = TemporaryDirectory(prefix='coating-test-')
        self.addCleanup(directory.cleanup)
        self.source_path = Path(directory.name) / 'source.sqlite'
        self.center_path = Path(directory.name) / 'center.sqlite'
        self.source = open_source(self.source_path)
        self.center = open_center(self.center_path)
        self.addCleanup(self.source.close)
        self.addCleanup(self.center.close)
        for connection in (self.source, self.center):
            define_trial(connection, self.trial_id, SEGMENTS, ROLES)

    def reopen_source(self):
        self.source.close()
        self.source = open_source(self.source_path)
        self.addCleanup(self.source.close)

    def reopen_center(self):
        self.center.close()
        self.center = open_center(self.center_path)
        self.addCleanup(self.center.close)

    def revision(self, role, values, parent=None):
        return record_revision(self.source, self.trial_id, role, zip(SEGMENTS, values, strict=True),
                               parent_revision_id=parent)

    def intake(self, revision):
        return receive(self.center, self.trial_id, issue(self.source, revision.revision_id).to_json())

    def pair(self, second=SAME):
        return self.intake(self.revision(ROLES[0], SAME)), self.intake(self.revision(ROLES[1], second))

    def sign(self, first, second):
        return publish(self.center, self.trial_id, first.received_id, second.received_id)

    def counts(self):
        return tuple(self.center.execute(query).fetchone()[0] for query in (
            'SELECT count(*) FROM signed_reports',
            'SELECT count(*) FROM signed_report_parents',
            'SELECT count(*) FROM success_receipts',
        ))


def decision_values(report):
    decision = report.snapshot.decision
    return {
        'status': decision.status,
        'minimum': None if decision.minimum is None else str(decision.minimum),
        'bounds': [[optimum.boundary.position, str(optimum.low_shift), str(optimum.high_shift)]
                   for optimum in decision.optima],
    }


def parent_ids(report):
    return tuple(parent.received_id for parent in report.snapshot.parents)


def scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual, paths, oracle):
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id,
        'input': inputs,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': paths,
        'oracle': oracle,
    }, ensure_ascii=False, sort_keys=True))

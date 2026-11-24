import sqlite3
from fractions import Fraction

from analysis.conditional_loss import combine_responses, evaluate_response
from analysis.eligibility import common_boundaries
from analysis.request import publish
from bench.revisions import record_revision
from evidence.intake import receive
from evidence.issue import issue
from evidence.ledger import load_received
from report.history import read
from tests.support import LabCase, OPPOSITE, ROLES, SAME, SEGMENTS, decision_values, parent_ids, scenario
from trial.catalog import define_trial, load_trial


SAME_RESULT = {'status': 'fitted', 'minimum': '0', 'bounds': [[2, '2', '2']]}
OPPOSITE_RESULT = {'status': 'fitted', 'minimum': '8',
                   'bounds': [[1, '-2', '2'], [2, '-2', '2'], [3, '-2', '2']]}


class JointFitTests(LabCase):
    def test_offline_same(self):
        first, second = self.pair()
        self.source.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            self.source.execute('SELECT 1')
        signed = self.sign(first, second)
        actual = decision_values(signed)
        self.assertEqual(actual, SAME_RESULT)
        self.assertEqual(signed.receipt.report_id, signed.snapshot.report_id)
        self.assertEqual(parent_ids(signed), (first.received_id, second.received_id))
        stored = read(self.center, signed.snapshot.report_id)
        self.assertEqual(stored, signed)
        scenario('offline_same', {'甲': SAME, '乙': SAME}, SAME_RESULT, actual,
                 SAME_RESULT, decision_values(stored), ['analysis/request.py', 'analysis/joint_fit.py', 'report/history.py'],
                 'Both four-reading steps fit exactly only after S2 with jump +2.')

    def test_offline_opposite(self):
        first = self.intake(self.revision(ROLES[0], SAME))
        reverse = self.revision(ROLES[1], OPPOSITE)
        reverse_received = self.intake(reverse)
        corrected = self.intake(self.revision(ROLES[1], SAME, parent=reverse.revision_id))
        self.source.close()
        opposite_report = self.sign(first, reverse_received)
        actual = decision_values(opposite_report)
        self.assertEqual(actual['minimum'], '8', 'COMMON_SHIFT_FALSE_ZERO')
        self.assertEqual(actual, OPPOSITE_RESULT)
        corrected_report = self.sign(first, corrected)
        self.assertEqual(decision_values(corrected_report), SAME_RESULT)
        self.assertEqual(parent_ids(opposite_report), (first.received_id, reverse_received.received_id))
        self.assertEqual(parent_ids(corrected_report), (first.received_id, corrected.received_id))
        self.reopen_center()
        self.assertEqual(read(self.center, opposite_report.snapshot.report_id), opposite_report)
        scenario('offline_opposite', {'甲': SAME, '乙': OPPOSITE, '乙勘误': SAME}, OPPOSITE_RESULT, actual,
                 SAME_RESULT, decision_values(corrected_report),
                 ['evidence/projection.py', 'analysis/conditional_loss.py', 'analysis/joint_fit.py', 'report/publish.py'],
                 'The outer cuts give 4+|d−2|+|d+2|, the central one gives 2|d−2|+2|d+2|.')

    def test_interval_endpoints(self):
        first, second = self.pair(OPPOSITE)
        self.source.close()
        signed = self.sign(first, second)
        self.assertEqual(decision_values(signed), OPPOSITE_RESULT)
        stored_first = load_received(self.center, first.received_id)
        stored_second = load_received(self.center, second.received_id)
        candidates = common_boundaries(load_trial(self.center, self.trial_id), stored_first.payload, stored_second.payload)
        self.assertEqual([item.boundary.position for item in candidates], [1, 2, 3])
        for candidate in candidates:
            with self.subTest(boundary=candidate.boundary):
                combined = combine_responses(candidate.first, candidate.second)
                self.assertEqual([evaluate_response(combined, shift) for shift in (-2, Fraction(1, 3), 2)], [8, 8, 8])
                outside = 10 if candidate.boundary.position != 2 else 12
                self.assertEqual(evaluate_response(combined, 3), outside)
                self.assertEqual(evaluate_response(combined, -3), outside)

    def test_translation(self):
        first, second = self.pair(tuple(value + 100 for value in SAME))
        self.source.close()
        self.assertEqual(decision_values(self.sign(first, second)), SAME_RESULT)

    def test_request_order(self):
        first, second = self.pair()
        self.source.close()
        reports = (self.sign(first, second), self.sign(second, first))
        self.reopen_center()
        for signed, pair in zip(reports, ((first, second), (second, first)), strict=True):
            self.assertEqual(decision_values(signed), SAME_RESULT)
            self.assertEqual(parent_ids(signed), tuple(item.received_id for item in pair))
            self.assertEqual(tuple(parent.origin for parent in signed.snapshot.parents), tuple(item.origin for item in pair))
            self.assertEqual(read(self.center, signed.snapshot.report_id), signed)

    def test_bad_pair(self):
        first, second = self.pair()
        duplicate_role = self.intake(self.revision(ROLES[0], OPPOSITE))
        for connection in (self.source, self.center):
            define_trial(connection, 'another-trial', SEGMENTS, ROLES)
        another = record_revision(self.source, 'another-trial', ROLES[1], zip(SEGMENTS, SAME))
        wrong_trial = receive(self.center, 'another-trial', issue(self.source, another.revision_id))
        self.source.close()
        old = self.sign(first, second)
        before = self.counts()
        with self.assertRaises(LookupError):
            publish(self.center, self.trial_id, first.received_id, 9999)
        for wrong in (duplicate_role, wrong_trial, first):
            with self.subTest(wrong=wrong.received_id), self.assertRaises(ValueError):
                self.sign(first, wrong)
        self.assertEqual(self.counts(), before)
        self.assertEqual(read(self.center, old.snapshot.report_id), old)

    def test_no_evidence(self):
        values = (None, None, 2, None)
        first, second = self.pair(values)
        self.source.close()
        self.assertTrue(all(item is None for item in second.payload.boundaries))
        signed = self.sign(first, second)
        expected = {'status': 'no_common_evidence', 'minimum': None, 'bounds': []}
        self.assertEqual(decision_values(signed), expected)
        self.assertEqual(parent_ids(signed), (first.received_id, second.received_id))
        stored = read(self.center, signed.snapshot.report_id)
        self.assertEqual(stored, signed)
        self.assertEqual(stored.receipt.report_id, signed.snapshot.report_id)
        scenario('no_evidence', {'甲': SAME, '乙': values}, expected, decision_values(signed),
                 expected, decision_values(stored), ['analysis/eligibility.py', 'analysis/joint_fit.py', 'report/receipt.py'],
                 'A single valid reading cannot provide evidence on both sides of any cut.')

    def test_edge_missing(self):
        first, second = self.pair((None, 0, 2, None))
        self.source.close()
        self.assertEqual([item is not None for item in second.payload.boundaries], [False, True, False])
        self.assertEqual(decision_values(self.sign(first, second)), SAME_RESULT)

    def test_fraction_and_negative_shift(self):
        first = self.intake(self.revision(ROLES[0], ('2/3', '2/3', '1/6', '1/6')))
        second = self.intake(self.revision(ROLES[1], ('-2/3', '-2/3', '-7/6', '-7/6')))
        self.source.close()
        self.assertEqual(decision_values(self.sign(first, second)),
                         {'status': 'fitted', 'minimum': '0', 'bounds': [[2, '-1/2', '-1/2']]})

import json
import sqlite3
from fractions import Fraction

from analysis.request import publish_review
from evidence.intake import receive, receive_supplement
from evidence.issue import issue, issue_supplement
from report.history import read, read_review
from review_examples import CASES
from tests.support import LabCase, OPPOSITE, ROLES, SAME, scenario
from trial.catalog import define_trial


class ReviewTests(LabCase):
    def seed(self, name):
        case = CASES[name]
        trial_id = f'{self.trial_id}-{name}'
        for connection in (self.source, self.center):
            define_trial(connection, trial_id, case['segments'], ROLES)
        received = []
        for role, rows in zip(ROLES, case['rows'], strict=True):
            revision = self.revision_at(trial_id, role, rows)
            received.append(receive(self.center, trial_id,
                                    issue(self.source, revision.revision_id).to_json()))
        signed = self.sign_at(trial_id, received[0], received[1])
        return trial_id, received, signed

    def revision_at(self, trial_id, role, rows, parent=None):
        from bench.revisions import record_revision
        return record_revision(self.source, trial_id, role, rows, parent_revision_id=parent)

    def sign_at(self, trial_id, first, second):
        from analysis.request import publish
        return publish(self.center, trial_id, first.received_id, second.received_id)

    def supplements(self, signed, clauses):
        supplement_ids = []
        for parent in signed.snapshot.parents:
            role_clauses = [clause for clause in clauses if clause[0] == parent.origin.role]
            text = issue_supplement(self.source, parent.origin.issue_id, role_clauses)
            supplement_ids.append(receive_supplement(self.center, parent.received_id, text))
        return supplement_ids

    def review_counts(self):
        return tuple(self.center.execute(query).fetchone()[0] for query in (
            'SELECT count(*) FROM review_reports',
            'SELECT count(*) FROM review_receipts',
        ))

    def test_orders(self):
        histories = []
        for name, case in CASES.items():
            with self.subTest(case=name):
                _, received, signed = self.seed(name)
                for order in case['orders']:
                    self.reopen_source()
                    supplement_ids = self.supplements(signed, order['clauses'])
                    self.source.close()
                    review = publish_review(self.center, signed.snapshot.report_id,
                                            order['clauses'], supplement_ids)
                    self.assertEqual(review['intervals'], order['intervals'])
                    self.assertEqual(review['old_report_id'], signed.snapshot.report_id)
                    self.assertIsInstance(review['review_id'], int)
                    self.assertIsInstance(review['receipt_id'], int)
                    self.assertGreater(review['review_id'], 0)
                    self.assertGreater(review['receipt_id'], 0)
                    expected_clauses = [[clause[0], clause[1], clause[2],
                                         str(Fraction(clause[3]))] for clause in order['clauses']]
                    self.assertEqual(review['clauses'], expected_clauses)
                    parents = signed.snapshot.parents
                    self.assertEqual(review['basis'], [
                        [parent.received_id, parent.origin.issue_id, supplement_id]
                        for parent, supplement_id in zip(parents, supplement_ids, strict=True)
                    ])
                    self.assertEqual(read_review(self.center, review['review_id']), review)
                    histories.append(review['intervals'])
                self.reopen_source()
        expected = [order['intervals'] for case in CASES.values() for order in case['orders']]
        self.assertEqual(histories, expected)
        scenario('review_orders', {'cases': list(CASES)}, expected, histories,
                 True, all(item == expect for item, expect in zip(histories, expected)),
                 ['evidence/issue.py', 'evidence/intake.py', 'analysis/review.py',
                  'analysis/request.py', 'report/history.py'],
                 'Disconnected reviews reproduce the hand-computed intervals and their source rows.')

    def test_no_common_evidence(self):
        values = (None, None, 2, None)
        first, second = self.pair(values)
        signed = self.sign(first, second)
        clauses = [[ROLES[0], 'S1', 'over', '0'], [ROLES[1], 'S3', 'over', '0']]
        supplement_ids = self.supplements(signed, clauses)
        self.source.close()
        review = publish_review(self.center, signed.snapshot.report_id, clauses, supplement_ids)
        self.assertEqual(review['intervals'], [])
        self.assertEqual(read_review(self.center, review['review_id']), review)
        self.assertEqual(read(self.center, signed.snapshot.report_id), signed)
        scenario('review_no_common_evidence', {'乙': values}, [], review['intervals'],
                 True, review['intervals'] == [],
                 ['analysis/review.py', 'analysis/request.py', 'report/register.py'],
                 'Complete supplements still sign the empty set when the old report has no common boundary.')

    def test_reopen_and_unknown(self):
        _, received, signed = self.seed('opposed')
        order = CASES['opposed']['orders'][1]
        supplement_ids = self.supplements(signed, order['clauses'])
        self.source.close()
        review = publish_review(self.center, signed.snapshot.report_id,
                                order['clauses'], supplement_ids)
        self.reopen_center()
        self.assertEqual(read_review(self.center, review['review_id']), review)
        self.assertEqual(read(self.center, signed.snapshot.report_id), signed)
        with self.assertRaises(LookupError):
            read_review(self.center, 9999)
        with self.assertRaises(ValueError):
            read_review(self.center, '1')
        with self.assertRaises(ValueError):
            read_review(self.center, True)

    def test_issue_supplement_errors(self):
        revision = self.revision(ROLES[0], SAME)
        envelope = issue(self.source, revision.revision_id)
        issue_id = envelope.origin.issue_id
        good = [[ROLES[0], 'S1', 'over', '0']]
        with self.assertRaises(LookupError):
            issue_supplement(self.source, '0' * 32, good)
        for malformed in ('xyz', 123, None, True):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                issue_supplement(self.source, malformed, good)
        with self.assertRaises(ValueError):
            issue_supplement(self.source, issue_id, [])
        with self.assertRaises(ValueError):
            issue_supplement(self.source, issue_id, 'not-clauses')
        with self.assertRaises(ValueError):
            issue_supplement(self.source, issue_id, [[ROLES[1], 'S1', 'over', '0']])
        with self.assertRaises(ValueError):
            issue_supplement(self.source, issue_id, [[ROLES[0], 'XX', 'over', '0']])
        with self.assertRaises(ValueError):
            issue_supplement(self.source, issue_id, [[ROLES[0], 'S1', 'sideways', '0']])
        with self.assertRaises(ValueError):
            issue_supplement(self.source, issue_id, [[ROLES[0], 'S1', 'over', '-1']])
        with self.assertRaises(ValueError):
            issue_supplement(self.source, issue_id, [[ROLES[0], 'S1', 'over', 0.5]])
        with self.assertRaises(ValueError):
            issue_supplement(self.source, issue_id, [[ROLES[0], 'S1', 'over', True]])

    def test_receive_supplement_errors(self):
        first, second = self.pair(OPPOSITE)
        signed = self.sign(first, second)
        parent = signed.snapshot.parents[0]
        clauses = [[parent.origin.role, 'S1', 'over', '0']]
        text = issue_supplement(self.source, parent.origin.issue_id, clauses)
        supplement_id = receive_supplement(self.center, parent.received_id, text)
        self.assertIsInstance(supplement_id, str)
        self.assertTrue(supplement_id)
        damaged = text.replace('over', 'under', 1)
        with self.assertRaises(ValueError):
            receive_supplement(self.center, parent.received_id, damaged)
        binding_tampered = text[:-3] + ('0' if text[-3] != '0' else '1') + text[-2:]
        with self.assertRaises(ValueError):
            receive_supplement(self.center, parent.received_id, binding_tampered)
        with self.assertRaises(ValueError):
            receive_supplement(self.center, parent.received_id, '{')
        v1_text = issue(self.source, self.revision(ROLES[0], SAME).revision_id).to_json()
        with self.assertRaises(ValueError):
            receive_supplement(self.center, parent.received_id, v1_text)
        other_parent = signed.snapshot.parents[1]
        with self.assertRaises(ValueError):
            receive_supplement(self.center, other_parent.received_id, text)
        with self.assertRaises(LookupError):
            receive_supplement(self.center, 9999, text)
        for bad_id in (0, -1, '1', 1.5, True, None):
            with self.subTest(bad_id=bad_id), self.assertRaises(ValueError):
                receive_supplement(self.center, bad_id, text)
        count = self.center.execute('SELECT count(*) FROM received_supplements').fetchone()[0]
        self.assertEqual(count, 1)

    def test_reissued_revision_is_not_the_original(self):
        first, second = self.pair(OPPOSITE)
        signed = self.sign(first, second)
        parent = signed.snapshot.parents[0]
        again = issue(self.source, parent.origin.revision_id)
        self.assertNotEqual(again.origin.issue_id, parent.origin.issue_id)
        clauses = [[parent.origin.role, 'S1', 'over', '0']]
        text = issue_supplement(self.source, again.origin.issue_id, clauses)
        with self.assertRaises(ValueError):
            receive_supplement(self.center, parent.received_id, text)
        reissued = receive(self.center, self.trial_id, again.to_json())
        supplement_id = receive_supplement(self.center, reissued.received_id, text)
        second_parent = signed.snapshot.parents[1]
        second_text = issue_supplement(self.source, second_parent.origin.issue_id,
                                       [[ROLES[1], 'S3', 'over', '0']])
        second_id = receive_supplement(self.center, second_parent.received_id, second_text)
        self.source.close()
        other_clauses = clauses + [[ROLES[1], 'S3', 'over', '0']]
        with self.assertRaises(ValueError):
            publish_review(self.center, signed.snapshot.report_id, other_clauses,
                           [supplement_id, second_id])

    def test_publish_review_errors(self):
        first, second = self.pair(OPPOSITE)
        signed = self.sign(first, second)
        old_report_id = signed.snapshot.report_id
        clauses = [[ROLES[0], 'S1', 'over', '0'], [ROLES[1], 'S3', 'over', '0']]
        supplement_ids = self.supplements(signed, clauses)
        self.source.close()
        with self.assertRaises(ValueError):
            publish_review(self.center, old_report_id, clauses, supplement_ids[:1])
        with self.assertRaises(ValueError):
            publish_review(self.center, old_report_id, clauses, supplement_ids * 2)
        with self.assertRaises(ValueError):
            publish_review(self.center, old_report_id, clauses,
                           [first.received_id, second.received_id])
        with self.assertRaises(ValueError):
            publish_review(self.center, old_report_id, clauses, [supplement_ids[0]] * 2)
        with self.assertRaises(LookupError):
            publish_review(self.center, old_report_id, clauses, ['0' * 32, '1' * 32])
        with self.assertRaises(LookupError):
            publish_review(self.center, 9999, clauses, supplement_ids)
        with self.assertRaises(ValueError):
            publish_review(self.center, 'bad', clauses, supplement_ids)
        with self.assertRaises(ValueError):
            publish_review(self.center, old_report_id, clauses[:1], supplement_ids)
        with self.assertRaises(ValueError):
            publish_review(self.center, old_report_id,
                           [[ROLES[0], 'S1', 'over', '1'], clauses[1]], supplement_ids)
        with self.assertRaises(ValueError):
            publish_review(self.center, old_report_id,
                           [clauses[0], [ROLES[1], 'S3', 'over', 0.5]], supplement_ids)
        with self.assertRaises(ValueError):
            publish_review(self.center, old_report_id,
                           [clauses[0], [ROLES[1], 'S3', 'over', '-1']], supplement_ids)
        with self.assertRaises(ValueError):
            publish_review(self.center, old_report_id,
                           [clauses[0], ['丙', 'S3', 'over', '0']], supplement_ids)
        self.assertEqual(self.review_counts(), (0, 0))
        review = publish_review(self.center, old_report_id, clauses,
                                list(reversed(supplement_ids)))
        self.assertEqual(read_review(self.center, review['review_id']), review)
        self.assertEqual(self.review_counts(), (1, 1))
        self.assertEqual(read(self.center, old_report_id), signed)

    def test_review_rollback(self):
        first, second = self.pair(OPPOSITE)
        signed = self.sign(first, second)
        clauses = [[ROLES[0], 'S1', 'over', '0'], [ROLES[1], 'S3', 'over', '0']]
        supplement_ids = self.supplements(signed, clauses)
        self.source.close()
        self.center.execute('''
            CREATE TRIGGER test_refuse_review BEFORE INSERT ON review_reports
            BEGIN SELECT RAISE(ABORT, 'fixture refuses review'); END
        ''')
        with self.assertRaises(sqlite3.IntegrityError) as refusal:
            publish_review(self.center, signed.snapshot.report_id, clauses, supplement_ids)
        self.assertIn('fixture refuses review', str(refusal.exception))
        self.reopen_center()
        self.assertEqual(self.review_counts(), (0, 0))
        self.assertEqual(read(self.center, signed.snapshot.report_id), signed)

    def test_supplement_hides_absolute_readings(self):
        revision = self.revision(ROLES[0], (12345, 12345, 12347, 12347))
        envelope = issue(self.source, revision.revision_id)
        text = issue_supplement(self.source, envelope.origin.issue_id,
                                [[ROLES[0], 'S1', 'over', '0']])
        self.assertNotIn('12345', text)
        self.assertNotIn('12347', text)
        body = json.loads(json.loads(text)['body'])
        self.assertEqual([row[2] for row in body['readings']], ['0', '0', '2', '2'])
        self.assertEqual([row[0] for row in body['readings']], [0, 1, 2, 3])

    def test_all_missing_readings(self):
        first = self.intake(self.revision(ROLES[0], SAME))
        second = self.intake(self.revision(ROLES[1], (None, None, None, None)))
        signed = self.sign(first, second)
        clauses = [[ROLES[0], 'S1', 'over', '0'], [ROLES[1], 'S3', 'over', '0']]
        supplement_ids = self.supplements(signed, clauses)
        self.source.close()
        review = publish_review(self.center, signed.snapshot.report_id, clauses, supplement_ids)
        self.assertEqual(review['intervals'], [])
        self.assertEqual(read_review(self.center, review['review_id']), review)

    def test_corrected_parent_supplement(self):
        trial_id = f'{self.trial_id}-corr'
        for connection in (self.source, self.center):
            define_trial(connection, trial_id, ('P', 'Q'), ROLES)
        first = receive(self.center, trial_id,
                        issue(self.source, self.revision_at(trial_id, ROLES[0],
                                                            (('P', 0), ('Q', 2))).revision_id).to_json())
        old_revision = self.revision_at(trial_id, ROLES[1], (('P', 9), ('Q', 9)))
        corrected = self.revision_at(trial_id, ROLES[1], (('P', 2), ('Q', 0)),
                                     parent=old_revision.revision_id)
        second = receive(self.center, trial_id, issue(self.source, corrected.revision_id).to_json())
        signed = self.sign_at(trial_id, first, second)
        self.assertEqual(signed.snapshot.parents[1].origin.revision_id, corrected.revision_id)
        clauses = [[ROLES[0], 'P', 'under', '3/2'], [ROLES[0], 'Q', 'over', '1'],
                   [ROLES[1], 'P', 'over', '0']]
        supplement_ids = self.supplements(signed, clauses)
        self.source.close()
        review = publish_review(self.center, signed.snapshot.report_id, clauses, supplement_ids)
        self.assertEqual(review['intervals'], [[1, '-2', '-1/2', False, False, [0, 1, 0]]])
        self.assertEqual(read_review(self.center, review['review_id']), review)

import json
import sqlite3

from evidence.intake import receive
from evidence.issue import issue
from report.export import export_report
from report.history import read
from tests.support import LabCase, OPPOSITE, ROLES, SAME, decision_values, parent_ids, scenario


class PublicationTests(LabCase):
    def test_rollback(self):
        first, second = self.pair(OPPOSITE)
        self.source.close()
        old = self.sign(first, second)
        before = self.counts()
        with self.assertRaises(sqlite3.IntegrityError) as refusal:
            self.center.execute('''
                CREATE TRIGGER test_refuse_report BEFORE INSERT ON signed_reports
                BEGIN SELECT RAISE(ABORT, 'fixture refuses report'); END
            ''')
            self.sign(second, first)
        self.assertIn('fixture refuses report', str(refusal.exception))
        self.reopen_center()
        after = self.counts()
        self.assertEqual(before, (1, 2, 1))
        self.assertEqual(after, before)
        persisted = read(self.center, old.snapshot.report_id)
        self.assertEqual(persisted, old)
        scenario('rollback', {'operation': 'reject report insert'}, [1, 2, 1], after,
                 True, persisted == old, ['report/publish.py', 'report/register.py', 'report/history.py'],
                 'The prior report, its two parents and its receipt are the only committed rows.')

    def test_receipt_write_rollback(self):
        first, second = self.pair()
        old = self.sign(first, second)
        self.source.close()
        self.center.execute('''
            CREATE TRIGGER test_refuse_receipt BEFORE INSERT ON success_receipts
            WHEN EXISTS (SELECT 1 FROM signed_reports WHERE report_id = NEW.report_id)
            BEGIN SELECT RAISE(ABORT, 'fixture refuses receipt after report'); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'fixture refuses receipt after report'):
            self.sign(second, first)
        self.reopen_center()
        self.assertEqual(self.counts(), (1, 2, 1))
        self.assertEqual(read(self.center, old.snapshot.report_id), old)

    def test_commit_failure_rollback(self):
        first, second = self.pair()
        old = self.sign(first, second)
        self.source.close()
        self.center.execute('''
            CREATE TABLE test_deferred_reference (
                absent_report INTEGER REFERENCES signed_reports(report_id) DEFERRABLE INITIALLY DEFERRED
            )
        ''')
        self.center.execute('''
            CREATE TRIGGER test_refuse_commit AFTER INSERT ON success_receipts
            BEGIN INSERT INTO test_deferred_reference (absent_report) VALUES (-1); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            self.sign(second, first)
        self.assertFalse(self.center.in_transaction)
        self.reopen_center()
        self.assertEqual(self.counts(), (1, 2, 1))
        self.assertEqual(read(self.center, old.snapshot.report_id), old)
        self.assertEqual(self.center.execute('SELECT count(*) FROM test_deferred_reference').fetchone()[0], 0)

    def test_pinned_revision(self):
        old = self.revision(ROLES[1], OPPOSITE)
        corrected = self.revision(ROLES[1], SAME, parent=old.revision_id)
        self.assertEqual(corrected.parent_revision_id, old.revision_id)
        old_station = issue(self.source, old.revision_id)
        new_station = issue(self.source, corrected.revision_id)
        repeated_old = issue(self.source, old.revision_id)
        self.assertEqual(old_station.origin.revision_id, old.revision_id)
        self.assertEqual(new_station.origin.revision_id, corrected.revision_id)
        self.assertEqual(repeated_old.origin.revision_id, old.revision_id)
        self.assertEqual(repeated_old.body, old_station.body)
        self.assertNotEqual(old_station.body, new_station.body)
        self.assertNotEqual(repeated_old.origin.issue_id, old_station.origin.issue_id)
        self.assertEqual(receive(self.center, self.trial_id, old_station).origin, old_station.origin)

    def test_read_old_and_export_and_unknown(self):
        a = self.intake(self.revision(ROLES[0], SAME))
        old_revision = self.revision(ROLES[1], OPPOSITE)
        old_evidence = self.intake(old_revision)
        self.source.close()
        old = self.sign(a, old_evidence)
        self.reopen_source()
        new_evidence = self.intake(self.revision(ROLES[1], SAME, parent=old_revision.revision_id))
        self.source.close()
        new = self.sign(a, new_evidence)
        self.reopen_center()
        expected = [
            {'status': 'fitted', 'minimum': '8', 'bounds': [[1, '-2', '2'], [2, '-2', '2'], [3, '-2', '2']]},
            {'status': 'fitted', 'minimum': '0', 'bounds': [[2, '2', '2']]},
        ]
        history = []
        exported_values = []
        for signed, evidence, decision in zip((old, new), (old_evidence, new_evidence), expected, strict=True):
            report_id = signed.snapshot.report_id
            persisted = read(self.center, report_id)
            self.assertEqual(persisted, signed)
            actual = decision_values(persisted)
            self.assertEqual(actual, decision)
            self.assertEqual(parent_ids(persisted), (a.received_id, evidence.received_id))
            self.assertEqual([parent.origin for parent in persisted.snapshot.parents], [a.origin, evidence.origin])
            data = json.loads(export_report(self.center, report_id))
            self.assertEqual((data['report_id'], data['trial_id'], data['unit']), (report_id, self.trial_id, 'um'))
            self.assertEqual(data['decision']['minimum'], decision['minimum'])
            self.assertEqual(data['decision']['status'], decision['status'])
            self.assertEqual([[row['position'], row['low_shift'], row['high_shift']]
                              for row in data['decision']['optima']], decision['bounds'])
            expected_labels = [['S1', 'S2'], ['S2', 'S3'], ['S3', 'S4']] if signed == old else [['S2', 'S3']]
            self.assertEqual([[row['before'], row['after']] for row in data['decision']['optima']], expected_labels)
            self.assertEqual(data['receipt'], signed.receipt.to_data())
            self.assertEqual(data['parents'], [{'received_id': item.received_id, 'origin': item.origin.to_data()}
                                               for item in (a, evidence)])
            history.append(actual)
            exported_values.append(data['decision']['minimum'])
        self.assertNotEqual(old.receipt, new.receipt)
        self.assertEqual(self.counts(), (2, 4, 2))
        with self.assertRaises(LookupError):
            read(self.center, 9999)
        with self.assertRaises(LookupError):
            export_report(self.center, 9999)
        scenario('read_old', {'initial': OPPOSITE, 'correction': SAME}, expected, history,
                 ['8', '0'], exported_values, ['report/register.py', 'report/history.py', 'report/export.py'],
                 'The reverse trial admits all three cuts at loss eight. The correction has one exact step at loss zero.')

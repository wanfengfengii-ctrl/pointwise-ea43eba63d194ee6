from fractions import Fraction

from bench.precheck import precheck
from bench.readings import Reading
from bench.revisions import load_revision, record_revision
from tests.support import LabCase, ROLES, SAME, scenario
from trial.catalog import define_trial, load_trial


class BenchTests(LabCase):
    def test_precheck_ok(self):
        revision = self.revision(ROLES[0], SAME)
        checks = precheck(self.source, revision.revision_id)
        actual = [check.minimum for check in checks]
        eligible = [check.eligible for check in checks]
        self.assertEqual(actual, [2, 0, 2])
        self.assertEqual(eligible, [True, True, True])
        self.assertTrue(all(isinstance(value, Fraction) for value in actual))
        scenario('precheck_ok', {'rows': SAME}, ['2', '0', '2'], list(map(str, actual)),
                 [True, True, True], eligible, ['bench/precheck.py', 'bench/revisions.py'],
                 'Separate medians give zero in the middle and residual two at either outside cut.')

    def test_manifest_order(self):
        segments = ('C', 'A', 'D', 'B')
        define_trial(self.source, 'physical-order', segments, ROLES)
        revision = record_revision(self.source, 'physical-order', ROLES[0], zip(segments, SAME))
        result = [(item.boundary.before, item.boundary.after, item.minimum)
                  for item in precheck(self.source, revision.revision_id)]
        self.assertEqual(result, [('C', 'A', 2), ('A', 'D', 0), ('D', 'B', 2)])

    def test_manifest_reopen(self):
        segments = ('C', 'A', 'D', 'B')
        original = define_trial(self.source, 'physical-order', segments, ROLES)
        revision = record_revision(self.source, original.trial_id, ROLES[0], zip(segments, SAME))
        self.reopen_source()
        self.assertEqual(define_trial(self.source, original.trial_id, segments, ROLES), original)
        self.assertEqual(load_trial(self.source, original.trial_id).segments, segments)
        self.assertEqual(load_revision(self.source, revision.revision_id), revision)
        with self.assertRaises(ValueError):
            define_trial(self.source, original.trial_id, sorted(segments), ROLES)
        self.assertEqual(load_trial(self.source, original.trial_id), original)

    def test_manifest_rejected(self):
        invalid = (
            (('A', 'A'), ROLES, 'um'),
            (('A',), ('甲',), 'um'),
            (('A',), ('甲', '甲'), 'um'),
            (('A',), ('甲', ' '), 'um'),
            (('A',), ROLES, 'mm'),
            ({'A', 'B'}, ROLES, 'um'),
        )
        for index, (segments, roles, unit) in enumerate(invalid):
            trial_id = f'invalid-{index}'
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    define_trial(self.source, trial_id, segments, roles, unit)
                with self.assertRaises(LookupError):
                    load_trial(self.source, trial_id)

    def test_unknown_revision(self):
        with self.assertRaises(LookupError):
            precheck(self.source, 9999)

    def test_invalid_input(self):
        original = self.revision(ROLES[0], SAME)
        original_checks = precheck(self.source, original.revision_id)
        with self.assertRaises(ValueError):
            record_revision(self.source, self.trial_id, ROLES[0], [('S1', '1/3'), ('outside', 2)],
                            parent_revision_id=original.revision_id)
        self.reopen_source()
        count = self.source.execute('SELECT count(*) FROM bench_revisions').fetchone()[0]
        persisted = load_revision(self.source, original.revision_id)
        self.assertEqual(count, 1)
        self.assertEqual(persisted, original)
        self.assertEqual(precheck(self.source, original.revision_id), original_checks)
        readings = [str(row.value) for row in persisted.readings]
        self.assertEqual(readings, ['0', '0', '2', '2'])
        scenario('invalid_input', {'correction': [['S1', '1/3'], ['outside', 2]]}, 1, count,
                 ['0', '0', '2', '2'], readings,
                 ['bench/revisions.py', 'bench/readings.py', 'bench/source_store.py'],
                 'A segment absent from the fixed manifest invalidates the entire revision.')

    def test_cross_role_parent(self):
        first = self.revision(ROLES[0], SAME)
        second = self.revision(ROLES[1], SAME)
        with self.assertRaises(ValueError):
            self.revision(ROLES[1], SAME, parent=first.revision_id)
        with self.assertRaises(LookupError):
            self.revision(ROLES[1], SAME, parent=9999)
        self.assertEqual(self.source.execute('SELECT count(*) FROM bench_revisions').fetchone()[0], 2)
        self.assertEqual(load_revision(self.source, first.revision_id), first)
        self.assertEqual(load_revision(self.source, second.revision_id), second)

    def test_exact_rows_and_repetition(self):
        revision = record_revision(self.source, self.trial_id, ROLES[0], [
            ('S1', '1/3'), ('S1', '0'), ('S1', '0'), ('S2', None), ('S4', '0.5'),
        ])
        self.assertEqual(load_revision(self.source, revision.revision_id).readings, (
            Reading('S1', Fraction(1, 3)), Reading('S1', Fraction(0)), Reading('S1', Fraction(0)),
            Reading('S2', None), Reading('S4', Fraction(1, 2)),
        ))
        check = precheck(self.source, revision.revision_id)[0]
        self.assertEqual((check.before_count, check.after_count, check.minimum), (3, 1, Fraction(1, 3)))
        for invalid in (True, 0.5, '1/0'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                record_revision(self.source, self.trial_id, ROLES[0], [('S1', invalid)])

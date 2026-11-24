import json
from dataclasses import replace
from fractions import Fraction

from analysis.conditional_loss import evaluate_response
from evidence.intake import receive
from evidence.issue import issue
from evidence.ledger import load_received
from evidence.payload import StationEnvelope
from evidence.provenance import bind_origin
from tests.support import LabCase, OPPOSITE, ROLES, SAME, SEGMENTS, scenario
from trial.catalog import define_trial


class EvidenceTests(LabCase):
    def received_count(self):
        return self.center.execute('SELECT count(*) FROM received_evidence').fetchone()[0]

    def test_receive_ok(self):
        first = self.revision(ROLES[0], (12345, 12345, 12347, 12347))
        second = self.revision(ROLES[1], OPPOSITE)
        envelopes = [issue(self.source, revision.revision_id) for revision in (first, second)]
        receipts = [receive(self.center, self.trial_id, station.to_json()) for station in envelopes]
        self.source.close()
        self.reopen_center()
        self.assertEqual(len({item.received_id for item in receipts}), 2)
        self.assertNotEqual(envelopes[0].origin.issue_id, envelopes[1].origin.issue_id)
        origin_matches = []
        for revision, envelope, received in zip((first, second), envelopes, receipts, strict=True):
            persisted = load_received(self.center, received.received_id)
            self.assertEqual(persisted.envelope, envelope)
            self.assertEqual(StationEnvelope.from_json(envelope.to_json()), envelope)
            self.assertEqual((persisted.origin.revision_id, persisted.origin.role),
                             (revision.revision_id, revision.role))
            self.assertEqual(persisted.origin.manifest_key, revision.manifest.manifest_key)
            body = json.loads(envelope.body)
            self.assertEqual(set(body), {'boundaries'})
            self.assertEqual(len(body['boundaries']), 3)
            for response in body['boundaries']:
                self.assertEqual(set(response), {'points', 'left_slope', 'right_slope'})
            origin_matches.append(persisted.origin == envelope.origin)
        self.assertNotIn('12345', envelopes[0].body)
        actual_count = self.received_count()
        self.assertEqual(actual_count, 2)
        self.assertEqual(origin_matches, [True, True])
        scenario('receive_ok', {'roles': ROLES, 'issued_revisions': [first.revision_id, second.revision_id]},
                 2, actual_count, [True, True], origin_matches,
                 ['evidence/issue.py', 'evidence/intake.py', 'evidence/ledger.py'],
                 'Two physical handoffs retain their original issuance and revision identities after disconnect.')

    def test_unknown_revision_does_not_issue(self):
        with self.assertRaises(LookupError):
            issue(self.source, 9999)
        self.assertEqual(self.source.execute('SELECT count(*) FROM issued_evidence').fetchone()[0], 0)

    def test_conditional_response(self):
        reverse = self.intake(self.revision(ROLES[1], OPPOSITE))
        forward = self.intake(self.revision(ROLES[1], SAME))
        self.source.close()
        responses = [load_received(self.center, item.received_id).payload.boundaries[1]
                     for item in (reverse, forward)]
        probes = (-2, 0, 2)
        actual = [[str(evaluate_response(response, d)) for d in probes] for response in responses]
        expected = [['0', '4', '8'], ['8', '4', '0']]
        self.assertEqual(actual, expected)
        minima = [min(values) for values in actual]
        self.assertEqual(minima, ['0', '0'])
        self.assertEqual(evaluate_response(responses[0], Fraction(-7, 2)), 3)
        self.assertEqual(evaluate_response(responses[1], Fraction(5, 2)), 1)
        scenario('receive_ok.conditional_response', {'versions': [OPPOSITE, SAME], 'shifts': probes},
                 expected, actual, ['0', '0'], minima,
                 ['evidence/projection.py', 'evidence/payload.py', 'analysis/conditional_loss.py'],
                 'On the central cut the reverse and forward losses are 2|d+2| and 2|d−2|.')

    def test_provenance_mismatch(self):
        first = issue(self.source, self.revision(ROLES[1], SAME).revision_id)
        second = issue(self.source, self.revision(ROLES[1], OPPOSITE).revision_id)
        damaged_body = '{'
        damaged = replace(first, body=damaged_body,
                          binding=bind_origin(first.version, first.origin, damaged_body))
        wrong_binding = replace(first, body=second.body)
        with self.assertRaises(ValueError):
            receive(self.center, self.trial_id, damaged)
        with self.assertRaisesRegex(ValueError, 'binding mismatch'):
            receive(self.center, self.trial_id, wrong_binding)
        with self.assertRaises(ValueError):
            receive(self.center, self.trial_id, replace(first, version=True))
        with self.assertRaises(ValueError):
            receive(self.center, self.trial_id, first.to_json() + '\n')
        short_body = '{"boundaries":[]}'
        short = replace(first, body=short_body, binding=bind_origin(first.version, first.origin, short_body))
        with self.assertRaisesRegex(ValueError, 'boundary count'):
            receive(self.center, self.trial_id, short)
        self.assertEqual(self.received_count(), 0)
        self.assertEqual(receive(self.center, self.trial_id, first).origin, first.origin)

    def test_wrong_manifest(self):
        station = issue(self.source, self.revision(ROLES[0], SAME).revision_id)
        define_trial(self.center, 'lookalike', SEGMENTS, ROLES)
        with self.assertRaisesRegex(ValueError, 'different manifest'):
            receive(self.center, 'lookalike', station)
        after_rejection = self.received_count()
        self.assertEqual(after_rejection, 0)
        accepted = receive(self.center, self.trial_id, station)
        actual_trial = load_received(self.center, accepted.received_id).origin.trial_id
        self.assertEqual(actual_trial, self.trial_id)
        scenario('wrong_manifest', {'target': 'lookalike', 'source': self.trial_id}, 0, after_rejection,
                 self.trial_id, actual_trial, ['trial/catalog.py', 'evidence/intake.py', 'evidence/ledger.py'],
                 'Identical segment and role labels do not make two trial identities equal.')

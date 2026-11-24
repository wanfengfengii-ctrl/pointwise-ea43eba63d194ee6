import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.request import publish
from bench.precheck import precheck
from bench.revisions import record_revision
from evidence.intake import receive
from evidence.issue import issue
from lab import open_center, open_source
from report.export import export_report
from trial.catalog import define_trial


def load_sample(name):
    return json.loads((Path(__file__).parent / 'samples' / name).read_text(encoding='utf-8'))


def show_report(center, report_id):
    data = json.loads(export_report(center, report_id))
    # The issuance token is opaque. Show the business references and exact recorded result.
    data['parents'] = [
        {'received_id': parent['received_id'], 'role': parent['origin']['role'],
         'revision_id': parent['origin']['revision_id']}
        for parent in data['parents']
    ]
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))


def main():
    original = load_sample('opposite.json')
    correction = load_sample('correction.json')
    trial_id = original['trial_id']
    roles = original['roles']
    with TemporaryDirectory(prefix='coating-demo-') as directory:
        source_path = Path(directory) / 'source.sqlite'
        center_path = Path(directory) / 'center.sqlite'
        with closing(open_center(center_path)) as center:
            with closing(open_source(source_path)) as source:
                for connection in (source, center):
                    define_trial(connection, trial_id, original['segments'], roles, original['unit'])
                revisions = {
                    role: record_revision(source, trial_id, role, original['observations'][role])
                    for role in roles
                }
                for role, revision in revisions.items():
                    checks = precheck(source, revision.revision_id)
                    print(json.dumps({'role': role, 'precheck': [
                        {'before': check.boundary.before, 'after': check.boundary.after,
                         'eligible': check.eligible,
                         'minimum': None if check.minimum is None else str(check.minimum)}
                        for check in checks
                    ]}, ensure_ascii=False, sort_keys=True))
                initial = [receive(center, trial_id, issue(source, revisions[role].revision_id).to_json())
                           for role in roles]
            first = publish(center, trial_id, initial[0].received_id, initial[1].received_id)
            with closing(open_source(source_path)) as source:
                role = correction['role']
                revised = record_revision(
                    source, correction['trial_id'], role, correction['observations'],
                    parent_revision_id=revisions[role].revision_id,
                )
                updated = receive(center, trial_id, issue(source, revised.revision_id))
            second = publish(center, trial_id, initial[0].received_id, updated.received_id)
        with closing(open_center(center_path)) as center:
            show_report(center, first.snapshot.report_id)
            show_report(center, second.snapshot.report_id)


if __name__ == '__main__':
    main()

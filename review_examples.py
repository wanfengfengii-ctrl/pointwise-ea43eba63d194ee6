"""复测工单样例。直接运行只核对既有签报及其可用证据。"""
import json
from contextlib import closing

from analysis.request import publish
from bench.revisions import record_revision
from evidence.intake import receive
from evidence.issue import issue
from lab import open_center, open_source
from trial.catalog import define_trial


ROLES = ("甲", "乙")
CASES = {
    "opposed": {
        "segments": ("P", "Q"),
        "rows": ((("P", 0), ("Q", 2)), (("P", 2), ("Q", 0))),
        "loss": "4",
        "platforms": [[1, "-2", "2"]],
        "orders": [
            {"clauses": [["甲", "P", "under", "1"], ["甲", "Q", "over", "1"],
                         ["乙", "P", "over", "1"], ["乙", "Q", "under", "1"]],
             "intervals": []},
            {"clauses": [["甲", "P", "under", "3/2"], ["甲", "Q", "over", "1"],
                         ["乙", "P", "over", "0"]],
             "intervals": [[1, "-2", "-1/2", False, False, [0, 1, 0]]]},
        ],
    },
    "outlier-after": {
        "segments": ("P", "Q"),
        "rows": ((("P", 0), ("P", 0), ("Q", 0), ("Q", 4)),
                 (("P", 0), ("P", 0), ("P", 2), ("Q", 0))),
        "loss": "6",
        "platforms": [[1, "0", "0"]],
        "orders": [{"clauses": [["甲", "Q", "over", "3"], ["乙", "P", "over", "1"]],
                    "intervals": [[1, "0", "0", True, True, [3, 2]]]}],
    },
    "outlier-before": {
        "segments": ("P", "Q"),
        "rows": ((("P", -4), ("P", 0), ("Q", 0), ("Q", 0)),
                 (("P", 0), ("P", 0), ("P", 2), ("Q", 0))),
        "loss": "6",
        "platforms": [[1, "0", "0"]],
        "orders": [{"clauses": [["甲", "Q", "over", "3"], ["乙", "P", "over", "1"]],
                    "intervals": []}],
    },
    "missing-segment": {
        "segments": ("P", "M", "Q"),
        "rows": ((("P", 0), ("M", None), ("Q", 2)),
                 (("P", 2), ("M", None), ("Q", 0))),
        "loss": "4",
        "platforms": [[1, "-2", "2"], [2, "-2", "2"]],
        "orders": [{"clauses": [["甲", "M", "over", "0"], ["乙", "P", "over", "0"]],
                    "intervals": []}],
    },
}


def seed_case(source, center, name):
    case = CASES[name]
    for db in (source, center):
        define_trial(db, name, case["segments"], ROLES)
    received = []
    for role, rows in zip(ROLES, case["rows"], strict=True):
        revision = record_revision(source, name, role, rows)
        envelope = issue(source, revision.revision_id)
        received.append(receive(center, name, envelope.to_json()))
    return tuple(received)


def main():
    bodies = {}
    for name, case in CASES.items():
        with closing(open_center(":memory:")) as center:
            with closing(open_source(":memory:")) as source:
                first, second = seed_case(source, center, name)
                bodies[name] = first.envelope.body
            decision = publish(center, name, first.received_id, second.received_id).snapshot.decision
            platforms = [[o.boundary.position, str(o.low_shift), str(o.high_shift)] for o in decision.optima]
            result = {"case": name, "minimum": str(decision.minimum), "platforms": platforms}
            if result != {"case": name, "minimum": case["loss"], "platforms": case["platforms"]}:
                raise AssertionError(result)
            print(json.dumps(result, sort_keys=True))
    matched = bodies["outlier-after"] == bodies["outlier-before"]
    if not matched:
        raise AssertionError("legacy bodies differ")
    print(json.dumps({"legacy_bodies_equal": matched}))


if __name__ == "__main__":
    main()

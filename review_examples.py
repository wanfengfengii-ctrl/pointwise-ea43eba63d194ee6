"""复测工单样例。直接运行核对既有签报、可用证据与断源复核。"""
import json
from contextlib import closing

from analysis.request import publish, publish_review
from bench.revisions import record_revision
from evidence.intake import receive, receive_supplement
from evidence.issue import issue, issue_supplement
from lab import open_center, open_source
from report.history import read_review
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


def run_orders(center, signed, orders, supplement_ids):
    reviews = []
    for order, ids in zip(orders, supplement_ids, strict=True):
        review = publish_review(center, signed.snapshot.report_id, order["clauses"], ids)
        if review["intervals"] != order["intervals"]:
            raise AssertionError(review)
        again = read_review(center, review["review_id"])
        if again != review:
            raise AssertionError(again)
        reviews.append({"review_id": review["review_id"], "receipt_id": review["receipt_id"],
                        "intervals": review["intervals"]})
    return reviews


def main():
    bodies = {}
    for name, case in CASES.items():
        with closing(open_center(":memory:")) as center:
            with closing(open_source(":memory:")) as source:
                first, second = seed_case(source, center, name)
                bodies[name] = first.envelope.body
                signed = publish(center, name, first.received_id, second.received_id)
                supplements = []
                for order in case["orders"]:
                    ids = []
                    for parent in signed.snapshot.parents:
                        role_clauses = [clause for clause in order["clauses"]
                                        if clause[0] == parent.origin.role]
                        text = issue_supplement(source, parent.origin.issue_id, role_clauses)
                        ids.append(receive_supplement(center, parent.received_id, text))
                    supplements.append(ids)
                decision = signed.snapshot.decision
                platforms = [[o.boundary.position, str(o.low_shift), str(o.high_shift)]
                             for o in decision.optima]
            reviews = run_orders(center, signed, case["orders"], supplements)
            result = {"case": name, "minimum": str(decision.minimum), "platforms": platforms}
            if result != {"case": name, "minimum": case["loss"], "platforms": case["platforms"]}:
                raise AssertionError(result)
            print(json.dumps(result, sort_keys=True))
            print(json.dumps({"case": name, "reviews": reviews}, ensure_ascii=False, sort_keys=True))
    matched = bodies["outlier-after"] == bodies["outlier-before"]
    if not matched:
        raise AssertionError("legacy bodies differ")
    print(json.dumps({"legacy_bodies_equal": matched}))


if __name__ == "__main__":
    main()

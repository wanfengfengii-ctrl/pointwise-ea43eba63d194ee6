from dataclasses import dataclass
from fractions import Fraction

from bench.readings import split_at_boundaries
from bench.revisions import load_revision
from trial.order import SegmentBoundary


@dataclass(frozen=True)
class BoundaryCheck:
    boundary: SegmentBoundary
    before_count: int
    after_count: int
    minimum: Fraction | None

    @property
    def eligible(self):
        return self.before_count > 0 and self.after_count > 0


def median_absolute_loss(values):
    ordered = sorted(values)
    if not ordered:
        raise ValueError('at least one reading is required to fit a median')
    median = ordered[len(ordered) // 2]
    return sum((abs(value - median) for value in ordered), Fraction(0))


def precheck(connection, revision_id):
    revision = load_revision(connection, revision_id)
    checks = []
    for boundary, before, after in split_at_boundaries(revision.manifest.segments, revision.readings):
        minimum = median_absolute_loss(before) + median_absolute_loss(after) if before and after else None
        checks.append(BoundaryCheck(boundary, len(before), len(after), minimum))
    return tuple(checks)

from dataclasses import dataclass
from fractions import Fraction

from analysis.conditional_loss import combine_responses
from trial.order import SegmentBoundary


FITTED = 'fitted'
NO_COMMON_EVIDENCE = 'no_common_evidence'


@dataclass(frozen=True)
class BoundaryOptimum:
    boundary: SegmentBoundary
    minimum: Fraction
    low_shift: Fraction
    high_shift: Fraction


@dataclass(frozen=True)
class JointDecision:
    status: str
    minimum: Fraction | None
    optima: tuple[BoundaryOptimum, ...]


def minimize_boundary(candidate):
    combined = combine_responses(candidate.first, candidate.second)
    minimum = min(loss for _, loss in combined.points)
    # Convexity makes the set between the first and last minimizing knots optimal.
    shifts = [shift for shift, loss in combined.points if loss == minimum]
    return BoundaryOptimum(candidate.boundary, minimum, shifts[0], shifts[-1])


def fit_joint(candidates):
    optima = tuple(minimize_boundary(candidate) for candidate in candidates)
    if not optima:
        return JointDecision(NO_COMMON_EVIDENCE, None, ())
    minimum = min(optimum.minimum for optimum in optima)
    return JointDecision(FITTED, minimum, tuple(item for item in optima if item.minimum == minimum))

from fractions import Fraction

from bench.precheck import median_absolute_loss
from bench.readings import split_at_boundaries
from evidence.payload import BoundaryResponse, StationPayload


def build_boundary_response(before, after):
    if not before or not after:
        raise ValueError('both sides require a reading')
    # Only crossings between a fixed reading and a shifted reading can change median order.
    shifts = sorted({right - left for left in before for right in after})
    points = tuple(
        (shift, median_absolute_loss([*before, *(right - shift for right in after)]))
        for shift in shifts
    )
    tail_slope = Fraction(min(len(before), len(after)))
    return BoundaryResponse(points, -tail_slope, tail_slope)


def project_revision(revision):
    return StationPayload(tuple(
        build_boundary_response(before, after) if before and after else None
        for _, before, after in split_at_boundaries(revision.manifest.segments, revision.readings)
    ))

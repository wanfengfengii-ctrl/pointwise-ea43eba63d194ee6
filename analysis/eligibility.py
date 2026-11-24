from dataclasses import dataclass

from evidence.payload import BoundaryResponse
from trial.order import SegmentBoundary, ordered_boundaries


@dataclass(frozen=True)
class EligibleBoundary:
    boundary: SegmentBoundary
    first: BoundaryResponse
    second: BoundaryResponse


def common_boundaries(manifest, first, second):
    return tuple(
        EligibleBoundary(boundary, first_response, second_response)
        for boundary, first_response, second_response in zip(
            ordered_boundaries(manifest.segments), first.boundaries, second.boundaries, strict=True
        )
        if first_response is not None and second_response is not None
    )

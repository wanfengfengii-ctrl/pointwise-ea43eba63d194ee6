from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction

from evidence.payload import BoundaryResponse
from trial.units import parse_reading


@dataclass(frozen=True)
class CombinedLoss:
    points: tuple[tuple[Fraction, Fraction], ...]
    left_slope: Fraction
    right_slope: Fraction


def evaluate_response(response: BoundaryResponse | CombinedLoss, shift):
    shift = parse_reading(shift)
    points = response.points
    index = bisect_right(points, shift, key=lambda point: point[0])
    if index == 0:
        x, y = points[0]
        return y + (shift - x) * response.left_slope
    x, y = points[index - 1]
    if index == len(points):
        return y + (shift - x) * response.right_slope
    next_x, next_y = points[index]
    return y + (shift - x) * (next_y - y) / (next_x - x)


def combine_responses(first, second):
    shifts = {shift for shift, _ in first.points}
    shifts.update(shift for shift, _ in second.points)
    points = tuple(
        (shift, evaluate_response(first, shift) + evaluate_response(second, shift))
        for shift in sorted(shifts)
    )
    return CombinedLoss(points, first.left_slope + second.left_slope, first.right_slope + second.right_slope)

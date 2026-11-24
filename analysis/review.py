from dataclasses import dataclass
from fractions import Fraction
from itertools import product


@dataclass(frozen=True)
class StationReview:
    readings: tuple
    clauses: tuple


@dataclass(frozen=True)
class ReviewPlan:
    stations: tuple
    station_clause_indices: tuple
    options: tuple

    def combination_feasible_at(self, sides_list, combo, d):
        for station, sides, indices in zip(self.stations, sides_list, self.station_clause_indices):
            rows = tuple(combo[index] for index in indices)
            if not combination_feasible(station, sides, d, rows):
                return False
        return True


def _median_interval(values):
    ordered = sorted(values)
    count = len(ordered)
    return ordered[(count - 1) // 2], ordered[count // 2]


def _window_open(lo, hi, m_lo, m_hi):
    if lo is not None and hi is not None and not lo < hi:
        return False
    if lo is not None and not lo < m_hi:
        return False
    if hi is not None and not m_lo < hi:
        return False
    return True


def _adjusted(station, sides, d):
    return tuple(
        value - d if after else value
        for (_, _, value), after in zip(station.readings, sides)
    )


def station_feasible(station, sides, d):
    if not station.readings:
        return False
    adjusted = _adjusted(station, sides, d)
    m_lo, m_hi = _median_interval(adjusted)
    lo = hi = None
    for clause in station.clauses:
        segment_values = [
            value for value, (_, segment, _) in zip(adjusted, station.readings)
            if segment == clause.segment
        ]
        if not segment_values:
            return False
        if clause.direction == 'over':
            bound = max(segment_values) - clause.tolerance
            hi = bound if hi is None else min(hi, bound)
        else:
            bound = min(segment_values) + clause.tolerance
            lo = bound if lo is None else max(lo, bound)
    return _window_open(lo, hi, m_lo, m_hi)


def combination_feasible(station, sides, d, rows):
    if not station.readings:
        return False
    adjusted = _adjusted(station, sides, d)
    m_lo, m_hi = _median_interval(adjusted)
    by_row = {row: value for (row, _, _), value in zip(station.readings, adjusted)}
    lo = hi = None
    for clause, row in zip(station.clauses, rows):
        value = by_row[row]
        if clause.direction == 'over':
            bound = value - clause.tolerance
            hi = bound if hi is None else min(hi, bound)
        else:
            bound = value + clause.tolerance
            lo = bound if lo is None else max(lo, bound)
    return _window_open(lo, hi, m_lo, m_hi)


def _offsets(station):
    offsets = {Fraction(0)}
    tolerances = [clause.tolerance for clause in station.clauses]
    for first in tolerances:
        offsets.update((first, -first, 2 * first, -2 * first))
        for second in tolerances:
            offsets.update((first + second, first - second, -first + second, -first - second))
    return offsets


def _breakpoints(station, sides, low, high):
    after_values = [value for (_, _, value), after in zip(station.readings, sides) if after]
    before_values = [value for (_, _, value), after in zip(station.readings, sides) if not after]
    points = set()
    for after_value in after_values:
        for before_value in before_values:
            base = after_value - before_value
            for offset in _offsets(station):
                point = base + offset
                if low <= point <= high:
                    points.add(point)
    return points


def _ordered_points(stations, sides_list, low, high):
    points = {low, high}
    for station, sides in zip(stations, sides_list):
        points.update(_breakpoints(station, sides, low, high))
    return sorted(points)


def feasible_intervals(stations, sides_list, low, high):
    ordered = _ordered_points(stations, sides_list, low, high)

    def feasible(d):
        return all(station_feasible(station, sides, d) for station, sides in zip(stations, sides_list))

    point_ok = [feasible(point) for point in ordered]
    slab_ok = [
        feasible((first + second) / 2)
        for first, second in zip(ordered, ordered[1:])
    ]
    intervals = []
    current = None
    for index, point in enumerate(ordered):
        if point_ok[index]:
            if current is None:
                current = [point, True, point, True]
            else:
                current[2] = point
                current[3] = True
        elif current is not None:
            intervals.append(tuple(current))
            current = None
        if index + 1 < len(ordered):
            if slab_ok[index]:
                if current is None:
                    current = [point, False, ordered[index + 1], False]
                else:
                    current[2] = ordered[index + 1]
                    current[3] = False
            elif current is not None:
                intervals.append(tuple(current))
                current = None
    if current is not None:
        intervals.append(tuple(current))
    return intervals


def _probes(plan, sides_list, interval):
    low, low_inc, high, high_inc = interval
    interior = [
        point for point in _ordered_points(plan.stations, sides_list, low, high)
        if low < point < high
    ]
    probes = list(interior)
    if low_inc:
        probes.append(low)
    if high_inc:
        probes.append(high)
    bounds = [low, *interior, high]
    probes.extend((first + second) / 2 for first, second in zip(bounds, bounds[1:]))
    return probes


def find_covering_combination(plan, sides_list, interval):
    probes = _probes(plan, sides_list, interval)
    for combo in product(*plan.options):
        if all(plan.combination_feasible_at(sides_list, combo, d) for d in probes):
            return list(combo)
    return None


def subdivide_interval(plan, sides_list, interval):
    low, low_inc, high, high_inc = interval
    interior = [
        point for point in _ordered_points(plan.stations, sides_list, low, high)
        if low < point < high
    ]
    bounds = [low, *interior, high]
    pieces = []
    for index, point in enumerate(bounds):
        if (point != low or low_inc) and (point != high or high_inc):
            pieces.append((True, point, point, point))
        if index + 1 < len(bounds):
            pieces.append((False, point, bounds[index + 1], (point + bounds[index + 1]) / 2))
    combos = list(product(*plan.options))
    groups = []
    current = None
    for is_point, start, end, probe in pieces:
        covering = {combo for combo in combos if plan.combination_feasible_at(sides_list, combo, probe)}
        if current is not None and covering & current[4]:
            current[2] = end
            current[3] = is_point
            current[4] &= covering
        else:
            if current is not None:
                groups.append(current)
            current = [start, is_point, end, is_point, covering]
    if current is not None:
        groups.append(current)
    return [
        (group[0], group[1], group[2], group[3], list(min(group[4])))
        for group in groups if group[4]
    ]


def compute_intervals(plan, optima, segment_positions):
    items = []
    for optimum in optima:
        position = optimum.boundary.position
        low, high = optimum.low_shift, optimum.high_shift
        sides_list = tuple(
            tuple(
                segment_positions[segment] >= position
                for _, segment, _ in station.readings
            )
            for station in plan.stations
        )
        for low_v, low_inc, high_v, high_inc in feasible_intervals(plan.stations, sides_list, low, high):
            interval = (low_v, low_inc, high_v, high_inc)
            rows = find_covering_combination(plan, sides_list, interval)
            if rows is not None:
                items.append([position, str(low_v), str(high_v), low_inc, high_inc, rows])
            else:
                for sub_low, sub_low_inc, sub_high, sub_high_inc, sub_rows in subdivide_interval(
                    plan, sides_list, interval
                ):
                    items.append([position, str(sub_low), str(sub_high), sub_low_inc, sub_high_inc, sub_rows])
    return items

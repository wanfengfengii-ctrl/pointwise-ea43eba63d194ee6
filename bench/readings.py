from dataclasses import dataclass
from fractions import Fraction

from trial.order import ordered_boundaries, segment_index
from trial.units import parse_reading


@dataclass(frozen=True)
class Reading:
    segment: str
    value: Fraction | None


def normalize_readings(segments, rows):
    try:
        submitted = iter(rows)
    except TypeError as exc:
        raise ValueError('readings must be an iterable of rows') from exc
    normalized = []
    for row in submitted:
        if isinstance(row, Reading):
            segment, value = row.segment, row.value
        elif isinstance(row, (tuple, list)) and len(row) == 2:
            segment, value = row
        else:
            raise ValueError('each row must contain a segment and a reading')
        segment_index(segments, segment)
        normalized.append(Reading(segment, None if value is None else parse_reading(value)))
    return tuple(normalized)


def split_at_boundaries(segments, readings):
    grouped = {segment: [] for segment in segments}
    for reading in readings:
        if reading.value is not None:
            grouped[reading.segment].append(reading.value)
    values = tuple(value for segment in segments for value in grouped[segment])
    offset = 0
    for boundary in ordered_boundaries(segments):
        offset += len(grouped[boundary.before])
        yield boundary, values[:offset], values[offset:]

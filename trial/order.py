from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentBoundary:
    position: int
    before: str
    after: str


def validate_segment_order(segments):
    if isinstance(segments, (str, bytes)) or not isinstance(segments, Sequence):
        raise ValueError('segments must be an ordered sequence')
    names = tuple(segments)
    if not names or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError('at least one named segment is required')
    if len(set(names)) != len(names):
        raise ValueError('segment names must be unique')
    return names


def segment_index(segments, segment):
    if not isinstance(segment, str):
        raise ValueError('segment name must be text')
    try:
        return segments.index(segment)
    except ValueError as exc:
        raise ValueError(f'unknown segment {segment!r}') from exc


def ordered_boundaries(segments):
    return tuple(
        SegmentBoundary(position, before, after)
        for position, (before, after) in enumerate(zip(segments, segments[1:]), 1)
    )

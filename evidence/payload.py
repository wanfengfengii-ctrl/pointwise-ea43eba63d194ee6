import json
from dataclasses import dataclass
from fractions import Fraction

from evidence.provenance import IssuedOrigin, canonical_json
from trial.units import decode_fraction, encode_fraction


V1_VERSION = 1


@dataclass(frozen=True)
class BoundaryResponse:
    points: tuple[tuple[Fraction, Fraction], ...]
    left_slope: Fraction
    right_slope: Fraction

    def to_data(self):
        return {
            'points': [[encode_fraction(shift), encode_fraction(loss)] for shift, loss in self.points],
            'left_slope': encode_fraction(self.left_slope),
            'right_slope': encode_fraction(self.right_slope),
        }

    @classmethod
    def from_data(cls, data):
        if not isinstance(data, dict) or set(data) != {'points', 'left_slope', 'right_slope'}:
            raise ValueError('invalid boundary response fields')
        if not isinstance(data['points'], list) or not data['points']:
            raise ValueError('a boundary response requires at least one point')
        points = []
        for point in data['points']:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError('invalid boundary response point')
            shift, loss = map(decode_fraction, point)
            if loss < 0 or (points and shift <= points[-1][0]):
                raise ValueError('boundary points require increasing shifts and nonnegative losses')
            points.append((shift, loss))
        left_slope = decode_fraction(data['left_slope'])
        right_slope = decode_fraction(data['right_slope'])
        if not left_slope < 0 < right_slope:
            raise ValueError('boundary response must increase away from its tails')
        slopes = [left_slope]
        slopes.extend((v2 - v1) / (d2 - d1) for (d1, v1), (d2, v2) in zip(points, points[1:]))
        slopes.append(right_slope)
        if any(a > b for a, b in zip(slopes, slopes[1:])):
            raise ValueError('boundary response must be convex')
        return cls(tuple(points), left_slope, right_slope)


@dataclass(frozen=True)
class StationPayload:
    boundaries: tuple[BoundaryResponse | None, ...]


def encode_payload(payload):
    return canonical_json({
        'boundaries': [response.to_data() if response is not None else None for response in payload.boundaries]
    })


def decode_payload(body):
    if not isinstance(body, str):
        raise ValueError('station body must be text')
    data = json.loads(body)
    if (not isinstance(data, dict) or set(data) != {'boundaries'}
            or not isinstance(data['boundaries'], list)):
        raise ValueError('invalid station body fields')
    payload = StationPayload(tuple(
        None if item is None else BoundaryResponse.from_data(item) for item in data['boundaries']
    ))
    if encode_payload(payload) != body:
        raise ValueError('station body must use canonical encoding')
    return payload


@dataclass(frozen=True)
class StationEnvelope:
    version: int
    origin: IssuedOrigin
    body: str
    binding: str

    def to_json(self):
        return canonical_json({
            'version': self.version,
            'origin': self.origin.to_data(),
            'body': self.body,
            'binding': self.binding,
        })

    @classmethod
    def from_json(cls, text):
        if not isinstance(text, str):
            raise ValueError('station envelope must be text')
        data = json.loads(text)
        if not isinstance(data, dict) or set(data) != {'version', 'origin', 'body', 'binding'}:
            raise ValueError('invalid station envelope fields')
        envelope = cls(data['version'], IssuedOrigin.from_data(data['origin']), data['body'], data['binding'])
        if envelope.to_json() != text:
            raise ValueError('station envelope must use canonical encoding')
        return envelope

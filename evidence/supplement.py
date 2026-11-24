import json
from dataclasses import dataclass
from fractions import Fraction

from evidence.provenance import IssuedOrigin, canonical_json
from trial.order import segment_index
from trial.roles import require_role
from trial.units import decode_fraction, encode_fraction, parse_reading


SUPPLEMENT_VERSION = 2
DIRECTIONS = ('over', 'under')


@dataclass(frozen=True)
class SupplementClause:
    role: str
    segment: str
    direction: str
    tolerance: Fraction

    def to_data(self):
        return [self.role, self.segment, self.direction, encode_fraction(self.tolerance)]


def parse_clause(manifest, row):
    if not isinstance(row, (list, tuple)) or len(row) != 4:
        raise ValueError('each clause must contain role, segment, direction and tolerance')
    role, segment, direction, tolerance = row
    require_role(manifest.roles, role)
    segment_index(manifest.segments, segment)
    if direction not in DIRECTIONS:
        raise ValueError(f'unknown clause direction {direction!r}')
    value = parse_reading(tolerance)
    if value < 0:
        raise ValueError('clause tolerance must be nonnegative')
    return SupplementClause(role, segment, direction, value)


@dataclass(frozen=True)
class SupplementReading:
    row: int
    segment: str
    value: Fraction


@dataclass(frozen=True)
class SupplementPayload:
    clauses: tuple[SupplementClause, ...]
    readings: tuple[SupplementReading, ...]


def encode_supplement_body(payload):
    return canonical_json({
        'clauses': [clause.to_data() for clause in payload.clauses],
        'readings': [
            [reading.row, reading.segment, encode_fraction(reading.value)]
            for reading in payload.readings
        ],
    })


def decode_supplement_body(body):
    if not isinstance(body, str):
        raise ValueError('supplement body must be text')
    data = json.loads(body)
    if (not isinstance(data, dict) or set(data) != {'clauses', 'readings'}
            or not isinstance(data['clauses'], list) or not isinstance(data['readings'], list)):
        raise ValueError('invalid supplement body fields')
    if not data['clauses']:
        raise ValueError('a supplement requires at least one clause')
    clauses = []
    for row in data['clauses']:
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError('invalid supplement clause')
        role, segment, direction, tolerance = row
        if any(not isinstance(item, str) for item in (role, segment, direction)):
            raise ValueError('invalid supplement clause')
        if direction not in DIRECTIONS:
            raise ValueError(f'unknown clause direction {direction!r}')
        value = decode_fraction(tolerance)
        if value < 0:
            raise ValueError('clause tolerance must be nonnegative')
        clauses.append(SupplementClause(role, segment, direction, value))
    if [clause.to_data() for clause in clauses] != sorted(clause.to_data() for clause in clauses):
        raise ValueError('supplement clauses must use canonical order')
    readings = []
    previous = None
    for row in data['readings']:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError('invalid supplement reading')
        position, segment, value = row
        if type(position) is not int or position < 0:
            raise ValueError('invalid supplement reading row')
        if not isinstance(segment, str):
            raise ValueError('invalid supplement reading segment')
        if previous is not None and position <= previous:
            raise ValueError('supplement readings must keep increasing rows')
        previous = position
        readings.append(SupplementReading(position, segment, decode_fraction(value)))
    payload = SupplementPayload(tuple(clauses), tuple(readings))
    if encode_supplement_body(payload) != body:
        raise ValueError('supplement body must use canonical encoding')
    return payload


@dataclass(frozen=True)
class SupplementEnvelope:
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
            raise ValueError('supplement envelope must be text')
        data = json.loads(text)
        if not isinstance(data, dict) or set(data) != {'version', 'origin', 'body', 'binding'}:
            raise ValueError('invalid supplement envelope fields')
        envelope = cls(data['version'], IssuedOrigin.from_data(data['origin']), data['body'], data['binding'])
        if envelope.to_json() != text:
            raise ValueError('supplement envelope must use canonical encoding')
        return envelope

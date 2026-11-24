import hashlib
import hmac
import json
from dataclasses import dataclass

from lab import require_record_id


def canonical_json(data):
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _is_hex(text, length):
    return isinstance(text, str) and len(text) == length and all(c in '0123456789abcdef' for c in text)


@dataclass(frozen=True)
class IssuedOrigin:
    issue_id: str
    revision_id: int
    trial_id: str
    manifest_key: str
    role: str

    def to_data(self):
        return {
            'issue_id': self.issue_id,
            'revision_id': self.revision_id,
            'trial_id': self.trial_id,
            'manifest_key': self.manifest_key,
            'role': self.role,
        }

    @classmethod
    def from_data(cls, data):
        fields = {'issue_id', 'revision_id', 'trial_id', 'manifest_key', 'role'}
        if not isinstance(data, dict) or set(data) != fields:
            raise ValueError('invalid station origin fields')
        origin = cls(**data)
        origin.validate()
        return origin

    def validate(self):
        if not _is_hex(self.issue_id, 32) or not _is_hex(self.manifest_key, 64):
            raise ValueError('invalid station issue ID or manifest key')
        require_record_id(self.revision_id, 'source revision ID')
        if any(not isinstance(s, str) or not s.strip() for s in (self.trial_id, self.role)):
            raise ValueError('station origin requires a trial and bench role')


def bind_origin(version, origin, body):
    origin.validate()
    if not isinstance(body, str):
        raise ValueError('station body must be text')
    material = canonical_json({'version': version, 'origin': origin.to_data(), 'body': body})
    return hashlib.sha256(material.encode('ascii')).hexdigest()


def verify_origin(version, origin, body, binding):
    if not isinstance(origin, IssuedOrigin) or not _is_hex(binding, 64):
        raise ValueError('invalid station origin or binding')
    if not hmac.compare_digest(bind_origin(version, origin, body), binding):
        raise ValueError('station body and origin binding mismatch')

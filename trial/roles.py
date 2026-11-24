from collections.abc import Sequence


BenchRoles = tuple[str, str]


def validate_roles(roles) -> BenchRoles:
    if isinstance(roles, (str, bytes)) or not isinstance(roles, Sequence) or len(roles) != 2:
        raise ValueError('exactly two bench roles are required')
    first, second = roles
    if any(not isinstance(role, str) or not role.strip() for role in (first, second)):
        raise ValueError('bench roles must have names')
    if first == second:
        raise ValueError('bench roles must be distinct')
    return first, second


def require_role(roles: BenchRoles, role):
    if not isinstance(role, str) or role not in roles:
        raise ValueError(f'unknown bench role {role!r}')
    return role


def require_distinct_roles(roles: BenchRoles, first, second):
    require_role(roles, first)
    require_role(roles, second)
    if first == second:
        raise ValueError('a pair must use different bench roles')

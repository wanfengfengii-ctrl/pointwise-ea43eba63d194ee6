from fractions import Fraction


MICROMETRE = 'um'


def require_micrometre(unit):
    if unit != MICROMETRE:
        raise ValueError('measurement unit must be um')
    return MICROMETRE


def parse_reading(value):
    if isinstance(value, Fraction):
        return value
    if type(value) is int:
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f'invalid rational reading {value!r}') from exc
    raise ValueError('readings must be integers, exact strings or Fraction values')


def encode_fraction(value):
    return str(parse_reading(value))


def decode_fraction(text):
    if not isinstance(text, str):
        raise ValueError('expected a canonical rational string')
    value = parse_reading(text)
    if str(value) != text:
        raise ValueError('noncanonical rational string')
    return value

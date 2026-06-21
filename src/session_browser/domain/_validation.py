"""Small validation helpers for domain POJOs."""

from __future__ import annotations

from enum import Enum
from typing import TypeVar

E = TypeVar("E", bound=Enum)


def enum_value(value) -> str:
    """Return the JSON/string value for enum-like fields."""
    return value.value if isinstance(value, Enum) else str(value)


def coerce_enum(enum_cls: type[E], value, field_name: str) -> E:
    """Coerce a string/enum value to ``enum_cls`` with a precise error."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_cls)
        raise ValueError(f"{field_name} must be one of: {allowed}; got {value!r}") from exc


def non_negative_int(field_name: str, value) -> int:
    """Coerce ``value`` to int and reject negative counts/tokens."""
    try:
        result = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer-compatible value") from exc
    if result < 0:
        raise ValueError(f"{field_name} must be >= 0; got {result}")
    return result


def non_negative_float(field_name: str, value) -> float:
    """Coerce ``value`` to float and reject negative durations."""
    try:
        result = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a float-compatible value") from exc
    if result < 0:
        raise ValueError(f"{field_name} must be >= 0; got {result}")
    return result


def ratio_0_to_1(field_name: str, value) -> float:
    """Coerce a ratio and require it to be inside [0, 1]."""
    try:
        result = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a ratio-compatible value") from exc
    if result < 0 or result > 1:
        raise ValueError(f"{field_name} must be between 0 and 1; got {result}")
    return result

"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TypeVar

E = TypeVar('E', bound=Enum)


def enum_value(value: Any) -> str:
    """enum_value function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        value: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    return value.value if isinstance(value, Enum) else str(value)


def coerce_enum(enum_cls: type[E], value: Any, field_name: str) -> E:
    """coerce_enum function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        enum_cls: Input value supplied by the caller for this pipeline step.
        value: Input value supplied by the caller for this pipeline step.
        field_name: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.

    Raises:
        ValueError: Raised when validation or file lookup rejects the input.
    """
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except ValueError as exc:
        allowed = ', '.join(member.value for member in enum_cls)
        raise ValueError(f'{field_name} must be one of: {allowed}; got {value!r}') from exc


def non_negative_int(field_name: str, value: Any) -> int:
    """non_negative_int function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        field_name: Input value supplied by the caller for this pipeline step.
        value: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.

    Raises:
        ValueError: Raised when validation or file lookup rejects the input.
    """
    try:
        result = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} must be an integer-compatible value') from exc
    if result < 0:
        raise ValueError(f'{field_name} must be >= 0; got {result}')
    return result


def non_negative_float(field_name: str, value: Any) -> float:
    """non_negative_float function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        field_name: Input value supplied by the caller for this pipeline step.
        value: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.

    Raises:
        ValueError: Raised when validation or file lookup rejects the input.
    """
    try:
        result = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} must be a float-compatible value') from exc
    if result < 0:
        raise ValueError(f'{field_name} must be >= 0; got {result}')
    return result


def ratio_0_to_1(field_name: str, value: Any) -> float:
    """ratio_0_to_1 function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        field_name: Input value supplied by the caller for this pipeline step.
        value: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.

    Raises:
        ValueError: Raised when validation or file lookup rejects the input.
    """
    try:
        result = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} must be a ratio-compatible value') from exc
    if result < 0 or result > 1:
        raise ValueError(f'{field_name} must be between 0 and 1; got {result}')
    return result

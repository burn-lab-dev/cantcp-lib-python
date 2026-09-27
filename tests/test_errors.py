"""Tests of the error classes."""

from __future__ import annotations

import pytest

from cantcp.errors import (
    BadDLCError,
    BadFlagsError,
    BadIDError,
    BadLenError,
    BadTypeError,
    CantcpError,
    FrameLenError,
    ReservedError,
    ShortWriteError,
    TruncatedError,
)

CASES = [
    (FrameLenError, "cantcp: frame length is not 16 or 72 bytes"),
    (BadDLCError, "cantcp: can_dlc > 8"),
    (BadLenError, "cantcp: invalid canfd length"),
    (BadTypeError, "cantcp: unknown frame type"),
    (BadFlagsError, "cantcp: flags are not valid for the frame type"),
    (BadIDError, "cantcp: identifier does not fit the addressing mode"),
    (ReservedError, "cantcp: reserved bytes are not zero"),
    (TruncatedError, "cantcp: stream truncated in the middle of a packet"),
    (ShortWriteError, "cantcp: short write"),
]


@pytest.mark.parametrize(
    ("error_class", "message"), CASES, ids=[case[0].__name__ for case in CASES]
)
def test_error_message(error_class: type[CantcpError], message: str) -> None:
    error = error_class()
    assert str(error) == message
    assert error.args == (message,)
    assert isinstance(error, CantcpError)
    assert isinstance(error, Exception)


@pytest.mark.parametrize(
    ("error_class", "message"), CASES, ids=[case[0].__name__ for case in CASES]
)
def test_error_is_catchable_by_base_class(error_class: type[CantcpError], message: str) -> None:
    with pytest.raises(CantcpError) as excinfo:
        raise error_class()
    assert type(excinfo.value) is error_class
    assert str(excinfo.value) == message


def test_errors_are_distinct_classes() -> None:
    classes = [case[0] for case in CASES]
    assert len(set(classes)) == len(classes)
    assert all(issubclass(error_class, CantcpError) for error_class in classes)
    assert CantcpError in {error_class.__base__ for error_class in classes}

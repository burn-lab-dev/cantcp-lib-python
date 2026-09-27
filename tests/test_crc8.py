"""Tests of the internal CRC-8 calculator."""

from __future__ import annotations

import pytest

from cantcp.crc8 import _CRC8


@pytest.mark.parametrize(
    ("poly", "data", "expected"),
    [
        (0x07, b"", 0x00),
        (0x07, b"123456789", 0xF4),
        (0x1D, b"123456789", 0x37),
        (0x07, bytes(16), 0x00),
        (0x00, b"\x01", 0x00),
        (0xFF, b"\x80", 0x40),
    ],
    ids=["empty", "check", "poly-1d", "zeros", "poly-00", "poly-ff"],
)
def test_sum(poly: int, data: bytes, expected: int) -> None:
    assert _CRC8(poly).sum(data) == expected


def test_tables_are_independent() -> None:
    default = _CRC8(0x07)
    custom = _CRC8(0x1D)
    assert default.sum(b"123456789") == 0xF4
    assert custom.sum(b"123456789") == 0x37
    assert default.sum(b"123456789") == 0xF4

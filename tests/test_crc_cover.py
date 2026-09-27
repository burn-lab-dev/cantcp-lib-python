"""Tests of the CrcCover enum."""

from __future__ import annotations

from cantcp.crc_cover import CrcCover


def test_values() -> None:
    assert CrcCover.HEADER.value == "magic+type+frame"
    assert CrcCover.FRAME.value == "frame"
    assert list(CrcCover) == [CrcCover.HEADER, CrcCover.FRAME]

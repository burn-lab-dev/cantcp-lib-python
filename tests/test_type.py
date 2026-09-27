"""Tests of the Type enum."""

from __future__ import annotations

import pytest

from cantcp.type import Type


def test_values() -> None:
    assert int(Type.CLASSIC) == 0x01
    assert int(Type.FD) == 0x02
    assert list(Type) == [Type.CLASSIC, Type.FD]


@pytest.mark.parametrize(
    ("member", "text"),
    [(Type.CLASSIC, "CAN"), (Type.FD, "CAN FD")],
    ids=["classic", "fd"],
)
def test_str(member: Type, text: str) -> None:
    assert str(member) == text
    assert f"{member}" == text
    assert format(member, "") == text


def test_int_roundtrip() -> None:
    assert Type(0x01) is Type.CLASSIC
    assert Type(0x02) is Type.FD
    with pytest.raises(ValueError):
        Type(0x03)


def test_is_int() -> None:
    assert isinstance(Type.CLASSIC, int)
    assert Type.CLASSIC + 1 == 2
    assert Type.CLASSIC.name == "CLASSIC"

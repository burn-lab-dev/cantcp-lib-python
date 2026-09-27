"""Tests of the Flag set."""

from __future__ import annotations

import pytest

from cantcp.flags import Flag

ALL_NAMES = ["EFF", "RTR", "ERR", "BRS", "ESI"]


def test_bit_values() -> None:
    assert Flag.EFF == 1 << 0
    assert Flag.RTR == 1 << 1
    assert Flag.ERR == 1 << 2
    assert Flag.BRS == 1 << 3
    assert Flag.ESI == 1 << 4
    assert [int(flag) for flag in Flag] == [1, 2, 4, 8, 16]


@pytest.mark.parametrize(
    ("flags", "names"),
    [
        (Flag(0), []),
        (Flag.EFF, ["EFF"]),
        (Flag.RTR, ["RTR"]),
        (Flag.ERR, ["ERR"]),
        (Flag.BRS, ["BRS"]),
        (Flag.ESI, ["ESI"]),
        (Flag.EFF | Flag.RTR, ["EFF", "RTR"]),
        (Flag.BRS | Flag.ESI, ["BRS", "ESI"]),
        (Flag.EFF | Flag.RTR | Flag.ERR | Flag.BRS | Flag.ESI, ["EFF", "RTR", "ERR", "BRS", "ESI"]),
    ],
)
def test_combine(flags: Flag, names: list[str]) -> None:
    assert set(names) <= set(ALL_NAMES)
    for name in ALL_NAMES:
        if name in names:
            assert flags & Flag[name] == Flag[name]
        else:
            assert flags & Flag[name] == 0
    assert int(flags) == sum(int(Flag[name]) for name in names)

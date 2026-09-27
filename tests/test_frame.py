"""Tests of the Frame object."""

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
)
from cantcp.flags import Flag
from cantcp.frame import Frame
from cantcp.type import Type
from cantcp.validate import validate_raw
from tests.helpers import classic_raw, fd_raw

CAN_EFF = 0x80000000
CAN_RTR = 0x40000000
CAN_ERR = 0x20000000

FRAME_ERRORS = [
    ("length 0", b"", FrameLenError),
    ("length 15", bytes(15), FrameLenError),
    ("length 17", bytes(17), FrameLenError),
    ("length 73", bytes(73), FrameLenError),
    ("classic dlc 9", classic_raw(dlc=9), BadDLCError),
    ("classic pad", classic_raw(pad=1), ReservedError),
    ("classic res0", classic_raw(res0=1), ReservedError),
    ("classic res1", classic_raw(res1=1), ReservedError),
    ("classic id above sff", classic_raw(raw_id=0x800), BadIDError),
    ("classic err with eff", classic_raw(raw_id=CAN_ERR | CAN_EFF), BadFlagsError),
    ("classic err with rtr", classic_raw(raw_id=CAN_ERR | CAN_RTR), BadFlagsError),
    ("fd rtr", fd_raw(raw_id=CAN_RTR), BadFlagsError),
    ("fd err with eff", fd_raw(raw_id=CAN_ERR | CAN_EFF), BadFlagsError),
    ("fd err with rtr", fd_raw(raw_id=CAN_ERR | CAN_RTR), BadFlagsError),
    ("fd len 9", fd_raw(length=9), BadLenError),
    ("fd len 11", fd_raw(length=11), BadLenError),
    ("fd len 65", fd_raw(length=65), BadLenError),
    ("fd unknown flags", fd_raw(flags=0x04), BadFlagsError),
    ("fd res0", fd_raw(res0=1), ReservedError),
    ("fd res1", fd_raw(res1=1), ReservedError),
]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(case[1], case[2]) for case in FRAME_ERRORS],
    ids=[case[0] for case in FRAME_ERRORS],
)
def test_from_raw_errors(raw: bytes, expected: type[CantcpError]) -> None:
    with pytest.raises(expected) as excinfo:
        Frame.from_raw(raw)
    assert str(excinfo.value) == str(expected())
    with pytest.raises(expected):
        validate_raw(raw)


@pytest.mark.parametrize(
    ("name", "raw", "expected"),
    [
        ("classic dlc before reserved", classic_raw(dlc=9, pad=1), BadDLCError),
        ("classic err before dlc", classic_raw(raw_id=CAN_ERR | CAN_EFF, dlc=9), BadFlagsError),
        ("fd rtr before length", fd_raw(raw_id=CAN_RTR, length=9), BadFlagsError),
        ("fd length before flags", fd_raw(length=9, flags=0x04), BadLenError),
        ("fd length before reserved", fd_raw(length=9, res0=1), BadLenError),
    ],
)
def test_from_raw_error_priority(name: str, raw: bytes, expected: type[CantcpError]) -> None:
    with pytest.raises(expected):
        Frame.from_raw(raw)


def test_from_raw_classic_fields() -> None:
    raw = classic_raw(raw_id=0x123, dlc=2, data=b"\xde\xad", tail=b"\x01\x02")
    frame = Frame.from_raw(raw)
    assert frame.type is Type.CLASSIC
    assert frame.id == 0x123
    assert frame.eff is False
    assert frame.rtr is False
    assert frame.err is False
    assert frame.brs is False
    assert frame.esi is False
    assert frame.data == b"\xde\xad"
    assert frame.raw == raw
    assert validate_raw(raw) is Type.CLASSIC


def test_from_raw_classic_ignores_tail() -> None:
    raw = classic_raw(raw_id=0x123, dlc=2, data=b"\xde\xad", tail=b"\x01\x02")
    frame = Frame.from_raw(raw)
    assert frame.to_raw() == classic_raw(raw_id=0x123, dlc=2, data=b"\xde\xad")
    assert frame.to_raw() != raw


def test_from_raw_extended() -> None:
    frame = Frame.from_raw(classic_raw(raw_id=CAN_EFF | 0x1ABCDE, dlc=0))
    assert frame.type is Type.CLASSIC
    assert frame.id == 0x1ABCDE
    assert frame.eff is True
    assert frame.flags == Flag.EFF


def test_from_raw_remote() -> None:
    frame = Frame.from_raw(classic_raw(raw_id=CAN_RTR | 0x123, dlc=8))
    assert frame.id == 0x123
    assert frame.rtr is True
    assert frame.flags == Flag.RTR


def test_from_raw_error_frame() -> None:
    frame = Frame.from_raw(classic_raw(raw_id=CAN_ERR | 0x12345678, dlc=0))
    assert frame.err is True
    assert frame.eff is False
    assert frame.rtr is False
    assert frame.id == 0x12345678


def test_from_raw_fd_fields() -> None:
    raw = fd_raw(raw_id=0x123, length=2, flags=0x03, data=b"\x01\x02", tail=b"\xaa")
    frame = Frame.from_raw(raw)
    assert frame.type is Type.FD
    assert frame.id == 0x123
    assert frame.brs is True
    assert frame.esi is True
    assert frame.data == b"\x01\x02"
    assert validate_raw(raw) is Type.FD


def test_from_raw_fd_full_payload() -> None:
    frame = Frame.from_raw(fd_raw(length=64, data=bytes(64)))
    assert len(frame.data) == 64


def test_from_raw_returns_independent_frames() -> None:
    raw = classic_raw(raw_id=7, dlc=1, data=b"\x01")
    first = Frame.from_raw(raw)
    second = Frame.from_raw(raw)
    assert first == second
    assert first is not second
    assert first.data == second.data


TO_RAW_ERRORS = [
    ("no type", Frame(), BadTypeError),
    ("classic dlc 9", Frame(type=Type.CLASSIC, data=bytes(9)), BadDLCError),
    ("classic brs", Frame(type=Type.CLASSIC, brs=True), BadFlagsError),
    ("classic esi", Frame(type=Type.CLASSIC, esi=True), BadFlagsError),
    ("fd rtr", Frame(type=Type.FD, rtr=True), BadFlagsError),
    ("fd len 9", Frame(type=Type.FD, data=bytes(9)), BadLenError),
    ("fd len 11", Frame(type=Type.FD, data=bytes(11)), BadLenError),
    ("fd len 63", Frame(type=Type.FD, data=bytes(63)), BadLenError),
    ("fd len 65", Frame(type=Type.FD, data=bytes(65)), BadLenError),
    ("err with eff", Frame(type=Type.CLASSIC, err=True, eff=True), BadFlagsError),
    ("err with rtr", Frame(type=Type.CLASSIC, err=True, rtr=True), BadFlagsError),
    ("classic id above sff", Frame(type=Type.CLASSIC, id=0x800), BadIDError),
    ("classic negative id", Frame(type=Type.CLASSIC, id=-1), BadIDError),
    ("fd id above sff", Frame(type=Type.FD, id=0x800), BadIDError),
    ("eff id above mask", Frame(type=Type.FD, id=0x20000000, eff=True), BadIDError),
]


@pytest.mark.parametrize(
    ("frame", "expected"),
    [(case[1], case[2]) for case in TO_RAW_ERRORS],
    ids=[case[0] for case in TO_RAW_ERRORS],
)
def test_to_raw_errors(frame: Frame, expected: type[CantcpError]) -> None:
    with pytest.raises(expected) as excinfo:
        frame.to_raw()
    assert str(excinfo.value) == str(expected())
    assert frame.raw is None


def test_to_raw_classic() -> None:
    frame = Frame(type=Type.CLASSIC, id=0x123, data=b"\xde\xad")
    raw = frame.to_raw()
    assert raw.hex() == "2301000002000000dead000000000000"
    assert frame.raw == raw


def test_to_raw_classic_limits() -> None:
    assert len(Frame(type=Type.CLASSIC, id=0x7FF, data=bytes(8)).to_raw()) == 16
    assert len(Frame(type=Type.CLASSIC).to_raw()) == 16


def test_to_raw_extended_remote() -> None:
    frame = Frame(type=Type.CLASSIC, id=0x1ABCDE, eff=True, rtr=True)
    assert frame.to_raw()[:4].hex() == "debc1ac0"


def test_to_raw_error_frame() -> None:
    frame = Frame(type=Type.CLASSIC, id=0x12345678, err=True)
    assert frame.to_raw()[:4].hex() == "78563432"


def test_to_raw_fd() -> None:
    frame = Frame(type=Type.FD, id=0x123, brs=True, data=b"\x01\x02")
    raw = frame.to_raw()
    assert raw.hex() == "2301000002010000" + "0102" + "00" * 62
    assert len(raw) == 72
    assert frame.raw == raw


def test_to_raw_fd_esi() -> None:
    frame = Frame(type=Type.FD, id=1, esi=True)
    assert frame.to_raw()[5] == 0x02


def test_to_raw_fd_max_payload() -> None:
    frame = Frame(type=Type.FD, data=bytes(64))
    assert len(frame.to_raw()) == 72


def test_to_raw_updates_raw() -> None:
    frame = Frame(type=Type.CLASSIC, id=1)
    first = frame.to_raw()
    frame.id = 2
    second = frame.to_raw()
    assert frame.raw == second
    assert first != second


@pytest.mark.parametrize(
    ("type_", "flags", "expected"),
    [
        (Type.CLASSIC, Flag(0), Flag(0)),
        (Type.CLASSIC, Flag.EFF | Flag.RTR, Flag.EFF | Flag.RTR),
        (Type.CLASSIC, Flag.ERR, Flag.ERR),
        (Type.CLASSIC, int(Flag.EFF), Flag.EFF),
        (Type.FD, Flag(0), Flag(0)),
        (Type.FD, Flag.EFF | Flag.BRS | Flag.ESI, Flag.EFF | Flag.BRS | Flag.ESI),
        (Type.FD, Flag.ERR, Flag.ERR),
    ],
)
def test_set_flags(type_: Type, flags: int | Flag, expected: Flag) -> None:
    frame = Frame(type=type_)
    frame.set_flags(flags)
    assert frame.flags == expected
    assert frame.eff == (Flag.EFF in expected)
    assert frame.rtr == (Flag.RTR in expected)
    assert frame.err == (Flag.ERR in expected)
    assert frame.brs == (Flag.BRS in expected)
    assert frame.esi == (Flag.ESI in expected)


SET_FLAGS_ERRORS = [
    ("classic brs", Type.CLASSIC, Flag.BRS, BadFlagsError),
    ("classic esi", Type.CLASSIC, Flag.ESI, BadFlagsError),
    ("classic unknown bit", Type.CLASSIC, 0x80, BadFlagsError),
    ("classic err with eff", Type.CLASSIC, Flag.ERR | Flag.EFF, BadFlagsError),
    ("classic err with rtr", Type.CLASSIC, Flag.ERR | Flag.RTR, BadFlagsError),
    ("fd rtr", Type.FD, Flag.RTR, BadFlagsError),
    ("fd err with eff", Type.FD, Flag.ERR | Flag.EFF, BadFlagsError),
    ("fd err with rtr", Type.FD, Flag.ERR | Flag.RTR, BadFlagsError),
    ("fd unknown bit", Type.FD, 0x80, BadFlagsError),
]


@pytest.mark.parametrize(
    ("type_", "flags", "expected"),
    [(case[1], case[2], case[3]) for case in SET_FLAGS_ERRORS],
    ids=[case[0] for case in SET_FLAGS_ERRORS],
)
def test_set_flags_errors(type_: Type, flags: int | Flag, expected: type[CantcpError]) -> None:
    frame = Frame(type=type_, eff=True, rtr=True, err=True, brs=True, esi=True)
    with pytest.raises(expected):
        frame.set_flags(flags)
    assert frame.flags == Flag.EFF | Flag.RTR | Flag.ERR | Flag.BRS | Flag.ESI


def test_set_flags_without_type() -> None:
    frame = Frame()
    with pytest.raises(BadTypeError):
        frame.set_flags(Flag.EFF)
    assert frame.flags == Flag(0)


def test_flags_property() -> None:
    frame = Frame(type=Type.CLASSIC, eff=True, err=True)
    assert frame.flags == Flag.EFF | Flag.ERR
    frame.set_flags(0)
    assert frame.flags == Flag(0)


STR_CASES = [
    (Frame(), "Frame{Type:unknown, ID:0x0, Flags:none, DLC:0, Data:}"),
    (
        Frame(type=Type.CLASSIC, id=0x123, data=b"\xde\xad"),
        "Frame{Type:CAN, ID:0x123, Flags:none, DLC:2, Data:dead}",
    ),
    (
        Frame(type=Type.CLASSIC, id=0x1ABCDE, eff=True, rtr=True),
        "Frame{Type:CAN, ID:0x1abcde, Flags:EFF|RTR, DLC:0, Data:}",
    ),
    (
        Frame(type=Type.FD, id=0x1, brs=True, esi=True, data=b"\x01\x02"),
        "Frame{Type:CAN FD, ID:0x1, Flags:BRS|ESI, Len:2, Data:0102}",
    ),
    (
        Frame(type=Type.CLASSIC, id=1, eff=True, rtr=True, err=True, brs=True, esi=True),
        "Frame{Type:CAN, ID:0x1, Flags:EFF|RTR|ERR|BRS|ESI, DLC:0, Data:}",
    ),
    (
        Frame(type=Type.FD, id=1, err=True),
        "Frame{Type:CAN FD, ID:0x1, Flags:ERR, Len:0, Data:}",
    ),
]


@pytest.mark.parametrize(("frame", "expected"), STR_CASES, ids=[case[1][:20] for case in STR_CASES])
def test_str(frame: Frame, expected: str) -> None:
    assert str(frame) == expected


def test_raw_property() -> None:
    frame = Frame()
    assert frame.raw is None
    raw = classic_raw(raw_id=1, dlc=1, data=b"\x02")
    parsed = Frame.from_raw(raw)
    assert parsed.raw == raw
    assert Frame(type=Type.CLASSIC, id=1).raw is None


def test_equality_ignores_raw() -> None:
    raw = classic_raw(raw_id=0x123, dlc=1, data=b"\x01")
    parsed = Frame.from_raw(raw)
    built = Frame(type=Type.CLASSIC, id=0x123, data=b"\x01")
    assert parsed == built
    assert built != Frame(type=Type.CLASSIC, id=0x123, data=b"\x02")

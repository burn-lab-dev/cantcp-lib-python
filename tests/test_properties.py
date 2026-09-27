"""Property-based tests: the fuzz analogue of the Go test suite."""

from __future__ import annotations

import contextlib
import io
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cantcp.decoder import Decoder
from cantcp.errors import CantcpError
from cantcp.frame import Frame
from cantcp.parser import Parser
from cantcp.type import Type
from cantcp.validate import validate_raw

VALID_FD_LENS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64]

SETTINGS = settings(
    deadline=None,
    max_examples=150,
    suppress_health_check=[HealthCheck.too_slow],
    database=None,
)


@st.composite
def classic_raw_frames(draw: Any) -> bytes:
    """A valid raw classic can_frame."""
    raw_id = draw(st.integers(min_value=0, max_value=0x7FF))
    dlc = draw(st.integers(min_value=0, max_value=8))
    data = draw(st.binary(min_size=dlc, max_size=dlc))
    raw = bytearray(16)
    raw[0:4] = raw_id.to_bytes(4, "little")
    raw[4] = dlc
    raw[8 : 8 + dlc] = data
    return bytes(raw)


@st.composite
def fd_raw_frames(draw: Any) -> bytes:
    """A valid raw canfd_frame."""
    if draw(st.booleans()):
        raw_id = draw(st.integers(min_value=0, max_value=0x7FF))
    else:
        raw_id = draw(st.integers(min_value=0, max_value=0x1FFFFFFF)) | 0x80000000
    length = draw(st.sampled_from(VALID_FD_LENS))
    flags = draw(st.integers(min_value=0, max_value=3))
    data = draw(st.binary(min_size=length, max_size=length))
    raw = bytearray(72)
    raw[0:4] = raw_id.to_bytes(4, "little")
    raw[4] = length
    raw[5] = flags
    raw[8 : 8 + length] = data
    return bytes(raw)


@SETTINGS
@given(classic_raw_frames())
def test_classic_roundtrip(raw: bytes) -> None:
    frame = Frame.from_raw(raw)
    assert frame.type is Type.CLASSIC
    assert frame.to_raw() == raw
    assert validate_raw(raw) is Type.CLASSIC


@SETTINGS
@given(fd_raw_frames())
def test_fd_roundtrip(raw: bytes) -> None:
    frame = Frame.from_raw(raw)
    assert frame.type is Type.FD
    assert frame.to_raw() == raw
    assert validate_raw(raw) is Type.FD


@SETTINGS
@given(st.one_of(classic_raw_frames(), fd_raw_frames()))
def test_encode_split_roundtrip(raw: bytes) -> None:
    parser = Parser()
    packet = parser.encode(raw)
    assert len(packet) == len(raw) + 4
    assert parser.split(packet, True) == (len(packet), raw)


@SETTINGS
@given(
    classic_raw_frames(),
    st.integers(min_value=0, max_value=15),
    st.integers(min_value=0, max_value=255),
)
def test_mutated_classic_never_raises_unexpected(raw: bytes, index: int, value: int) -> None:
    mutated = bytearray(raw)
    mutated[index] = value
    with contextlib.suppress(CantcpError):
        Frame.from_raw(bytes(mutated))


@SETTINGS
@given(
    fd_raw_frames(), st.integers(min_value=0, max_value=71), st.integers(min_value=0, max_value=255)
)
def test_mutated_fd_never_raises_unexpected(raw: bytes, index: int, value: int) -> None:
    mutated = bytearray(raw)
    mutated[index] = value
    with contextlib.suppress(CantcpError):
        Frame.from_raw(bytes(mutated))


@SETTINGS
@given(st.binary(max_size=80))
def test_from_raw_never_raises_unexpected(data: bytes) -> None:
    with contextlib.suppress(CantcpError):
        Frame.from_raw(data)


@SETTINGS
@given(st.binary(max_size=300))
def test_decoder_never_raises_unexpected(data: bytes) -> None:
    decoder = Decoder(io.BytesIO(data))
    try:
        while decoder.decode() is not None:
            pass
    except CantcpError:
        pass


@SETTINGS
@given(st.binary(max_size=200))
def test_split_never_raises_unexpected(data: bytes) -> None:
    parser = Parser()
    with contextlib.suppress(CantcpError):
        parser.split(data, True)

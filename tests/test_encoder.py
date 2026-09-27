"""Tests of the Encoder object."""

from __future__ import annotations

import io
from unittest.mock import Mock

import pytest

from cantcp.crc_cover import CrcCover
from cantcp.encoder import Encoder
from cantcp.errors import (
    BadDLCError,
    BadLenError,
    BadTypeError,
    CantcpError,
    FrameLenError,
    ShortWriteError,
)
from cantcp.frame import Frame
from cantcp.policy import BadFramePolicy
from cantcp.type import Type
from tests.helpers import classic_raw, fd_raw, make_packet

CLASSIC_FRAME = classic_raw(raw_id=0x123, dlc=2, data=b"\xde\xad")
FD_FRAME = fd_raw(raw_id=0x123, length=2, data=b"\xde\xad")
CLASSIC_PACKET = make_packet(CLASSIC_FRAME)
FD_PACKET = make_packet(FD_FRAME, type_byte=2)


def test_encode_classic() -> None:
    stream = io.BytesIO()
    Encoder(stream).encode(CLASSIC_FRAME)
    assert stream.getvalue() == CLASSIC_PACKET


def test_encode_fd() -> None:
    stream = io.BytesIO()
    Encoder(stream).encode(FD_FRAME)
    assert stream.getvalue() == FD_PACKET


def test_encode_appends() -> None:
    stream = io.BytesIO()
    encoder = Encoder(stream)
    encoder.encode(CLASSIC_FRAME)
    encoder.encode(FD_FRAME)
    assert stream.getvalue() == CLASSIC_PACKET + FD_PACKET


def test_encode_frame() -> None:
    stream = io.BytesIO()
    Encoder(stream).encode_frame(Frame.from_raw(CLASSIC_FRAME))
    assert stream.getvalue() == CLASSIC_PACKET


ENCODE_ERRORS = [
    ("length 0", b"", FrameLenError),
    ("length 15", bytes(15), FrameLenError),
    ("classic dlc 9", classic_raw(dlc=9), BadDLCError),
    ("fd len 65", fd_raw(length=65), BadLenError),
]


@pytest.mark.parametrize(
    ("frame", "expected"),
    [(case[1], case[2]) for case in ENCODE_ERRORS],
    ids=[case[0] for case in ENCODE_ERRORS],
)
def test_encode_errors_leave_stream_untouched(frame: bytes, expected: type[CantcpError]) -> None:
    stream = io.BytesIO()
    with pytest.raises(expected):
        Encoder(stream).encode(frame)
    assert stream.getvalue() == b""


FRAME_ERRORS = [
    ("no type", Frame(), BadTypeError),
    ("bad dlc", Frame(type=Type.CLASSIC, data=bytes(9)), BadDLCError),
    ("bad len", Frame(type=Type.FD, data=bytes(9)), BadLenError),
]


@pytest.mark.parametrize(
    ("frame", "expected"),
    [(case[1], case[2]) for case in FRAME_ERRORS],
    ids=[case[0] for case in FRAME_ERRORS],
)
def test_encode_frame_errors_leave_stream_untouched(
    frame: Frame, expected: type[CantcpError]
) -> None:
    writer = Mock()
    encoder = Encoder(writer)
    with pytest.raises(expected):
        encoder.encode_frame(frame)
    assert writer.write.call_count == 0


def test_encode_reaches_the_writer() -> None:
    writer = Mock()
    writer.write.return_value = len(CLASSIC_PACKET)
    Encoder(writer).encode(CLASSIC_FRAME)
    writer.write.assert_called_once_with(CLASSIC_PACKET)


def test_short_write_raises() -> None:
    writer = Mock()
    writer.write.return_value = 1
    with pytest.raises(ShortWriteError) as excinfo:
        Encoder(writer).encode(CLASSIC_FRAME)
    assert str(excinfo.value) == "cantcp: short write"


def test_write_returning_none_raises() -> None:
    writer = Mock()
    writer.write.return_value = None
    with pytest.raises(ShortWriteError):
        Encoder(writer).encode(CLASSIC_FRAME)


def test_write_error_propagates() -> None:
    writer = Mock()
    writer.write.side_effect = OSError("boom")
    with pytest.raises(OSError, match="boom"):
        Encoder(writer).encode(CLASSIC_FRAME)


def test_custom_options() -> None:
    stream = io.BytesIO()
    encoder = Encoder(
        stream,
        magic=b"\x11\x22",
        crc_poly=0x1D,
        crc_cover=CrcCover.FRAME,
        bad_frame_policy=BadFramePolicy.FAIL,
    )
    encoder.encode(CLASSIC_FRAME)
    assert stream.getvalue() == make_packet(
        CLASSIC_FRAME, magic=b"\x11\x22", poly=0x1D, cover_header=False
    )


def test_writer_is_not_closed() -> None:
    stream = io.BytesIO()
    Encoder(stream).encode(CLASSIC_FRAME)
    assert not stream.closed

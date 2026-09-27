"""Tests of the Decoder object."""

from __future__ import annotations

import io
import logging
from unittest.mock import Mock

import pytest

from cantcp.crc_cover import CrcCover
from cantcp.decoder import Decoder
from cantcp.errors import BadDLCError, BadLenError, BadTypeError, TruncatedError
from cantcp.frame import Frame
from cantcp.logger import TRACE
from cantcp.policy import BadFramePolicy
from tests.helpers import classic_raw, fd_raw, make_packet

CLASSIC_FRAME = classic_raw(raw_id=0x123, dlc=2, data=b"\xde\xad")
FD_FRAME = fd_raw(raw_id=0x123, length=2, data=b"\xde\xad")
CLASSIC_PACKET = make_packet(CLASSIC_FRAME)
FD_PACKET = make_packet(FD_FRAME, type_byte=2)


class ChunkedReader(io.BytesIO):
    """A stream that returns at most ``chunk`` bytes per read call."""

    def __init__(self, data: bytes, chunk: int = 1) -> None:
        super().__init__(data)
        self._chunk = chunk

    def read(self, size: int | None = -1) -> bytes:
        limit = min(size, self._chunk) if size is not None and size >= 0 else self._chunk
        return super().read(limit)


class BrokenReader(io.BytesIO):
    """A stream that fails on every read call."""

    def read(self, size: int | None = -1) -> bytes:
        raise OSError("boom")


def test_decode_frames() -> None:
    decoder = Decoder(io.BytesIO(CLASSIC_PACKET + FD_PACKET))
    assert decoder.decode() == CLASSIC_FRAME
    assert decoder.decode() == FD_FRAME
    assert decoder.decode() is None
    assert decoder.decode() is None


def test_decode_frame() -> None:
    decoder = Decoder(io.BytesIO(CLASSIC_PACKET + FD_PACKET))
    assert decoder.decode_frame() == Frame.from_raw(CLASSIC_FRAME)
    assert decoder.decode_frame() == Frame.from_raw(FD_FRAME)
    assert decoder.decode_frame() is None


def test_iteration() -> None:
    decoder = Decoder(io.BytesIO(CLASSIC_PACKET + FD_PACKET))
    frames = list(decoder)
    assert frames == [Frame.from_raw(CLASSIC_FRAME), Frame.from_raw(FD_FRAME)]
    assert list(decoder) == []


def test_next_raises_stop_iteration() -> None:
    decoder = Decoder(io.BytesIO(b""))
    with pytest.raises(StopIteration):
        next(decoder)


@pytest.mark.parametrize("chunk", [1, 2, 3, 7, 19, 20, 76, 255], ids=str)
def test_reads_in_chunks(chunk: int) -> None:
    reader = ChunkedReader(CLASSIC_PACKET + FD_PACKET, chunk)
    decoder = Decoder(reader)
    assert decoder.decode() == CLASSIC_FRAME
    assert decoder.decode() == FD_FRAME
    assert decoder.decode() is None


def test_truncated_error_is_sticky() -> None:
    decoder = Decoder(io.BytesIO(CLASSIC_PACKET[:19]))
    with pytest.raises(TruncatedError):
        decoder.decode()
    assert decoder.stats.truncated == 19
    with pytest.raises(TruncatedError):
        decoder.decode()
    assert decoder.stats.truncated == 19


def test_bad_type_fails() -> None:
    packet = make_packet(CLASSIC_FRAME, type_byte=3)
    decoder = Decoder(io.BytesIO(packet), bad_frame_policy=BadFramePolicy.FAIL)
    with pytest.raises(BadTypeError):
        decoder.decode()
    assert decoder.stats.bad_type == 1


def test_bad_dlc_fails() -> None:
    packet = make_packet(classic_raw(dlc=9))
    decoder = Decoder(io.BytesIO(packet), bad_frame_policy=BadFramePolicy.FAIL)
    with pytest.raises(BadDLCError):
        decoder.decode()


def test_bad_dlc_skipped() -> None:
    decoder = Decoder(io.BytesIO(make_packet(classic_raw(dlc=9)) + CLASSIC_PACKET))
    assert decoder.decode() == CLASSIC_FRAME
    assert decoder.stats.bad_dlc == 1


def test_bad_fd_len_fails() -> None:
    packet = make_packet(fd_raw(length=65), type_byte=2)
    decoder = Decoder(io.BytesIO(packet), bad_frame_policy=BadFramePolicy.FAIL)
    with pytest.raises(BadLenError):
        decoder.decode()


def test_decode_frame_is_strict_for_tolerant_splitter() -> None:
    packet = make_packet(fd_raw(length=9), type_byte=2)
    decoder = Decoder(io.BytesIO(packet))
    assert decoder.decode() == fd_raw(length=9)
    decoder = Decoder(io.BytesIO(packet))
    with pytest.raises(BadLenError):
        decoder.decode_frame()


def test_garbage_only() -> None:
    decoder = Decoder(io.BytesIO(b"\x01\x02\x03"))
    assert decoder.decode() is None
    assert decoder.stats.skipped == 3


def test_reader_error_propagates() -> None:
    decoder = Decoder(BrokenReader())
    with pytest.raises(OSError, match="boom"):
        decoder.decode()


def test_reader_is_not_closed() -> None:
    stream = io.BytesIO(CLASSIC_PACKET)
    Decoder(stream).decode()
    assert not stream.closed


def test_custom_options() -> None:
    packet = make_packet(CLASSIC_FRAME, magic=b"\x11\x22", poly=0x1D, cover_header=False)
    decoder = Decoder(
        io.BytesIO(packet),
        magic=b"\x11\x22",
        crc_poly=0x1D,
        crc_cover=CrcCover.FRAME,
    )
    assert decoder.decode() == CLASSIC_FRAME


def test_logger_is_passed_through() -> None:
    logger = Mock(spec=logging.Logger)
    logger.isEnabledFor.return_value = True
    decoder = Decoder(io.BytesIO(b"\x01\x02"), logger=logger, log_level=TRACE)
    assert decoder.decode() is None
    logger.isEnabledFor.assert_called_with(TRACE)
    assert logger.log.call_count == 1


def test_stats_and_reset() -> None:
    decoder = Decoder(io.BytesIO(b"\x01" + CLASSIC_PACKET))
    assert decoder.decode() == CLASSIC_FRAME
    assert decoder.stats.skipped == 1
    stats = decoder.stats
    stats.skipped = 100
    assert decoder.stats.skipped == 1
    decoder.reset_stats()
    assert decoder.stats.skipped == 0


def test_decoded_frames_survive_next_call() -> None:
    decoder = Decoder(io.BytesIO(CLASSIC_PACKET + FD_PACKET))
    first = decoder.decode_frame()
    assert first is not None
    second = decoder.decode_frame()
    assert first.data == b"\xde\xad"
    assert first.raw == CLASSIC_FRAME
    assert second is not None
    assert second.raw == FD_FRAME

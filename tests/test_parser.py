"""Tests of the Parser object."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import Mock, call

import pytest

from cantcp.crc8 import _CRC8
from cantcp.crc_cover import CrcCover
from cantcp.errors import (
    BadDLCError,
    BadLenError,
    BadTypeError,
    CantcpError,
    FrameLenError,
    TruncatedError,
)
from cantcp.logger import TRACE
from cantcp.parser import Parser
from cantcp.policy import BadFramePolicy
from cantcp.stats import Stats
from tests.helpers import classic_raw, corrupt_crc, fd_raw, make_packet

CLASSIC_FRAME = classic_raw(raw_id=0x123, dlc=2, data=b"\xde\xad")
FD_FRAME = fd_raw(raw_id=0x123, length=2, data=b"\xde\xad")
CLASSIC_PACKET = make_packet(CLASSIC_FRAME)
FD_PACKET = make_packet(FD_FRAME, type_byte=2)


def enabled_logger(level: int = TRACE) -> Mock:
    """A logger mock that reports enabled for levels at or above ``level``."""
    logger = Mock(spec=logging.Logger)
    logger.isEnabledFor.side_effect = lambda value: value >= level
    return logger


def test_defaults() -> None:
    parser = Parser()
    packet = parser.encode(bytes(16))
    assert packet[:2] == b"\xc3\x3c"
    assert packet[2] == 1
    assert packet[-1] == _CRC8(0x07).sum(packet[:-1])
    assert len(packet) == 20


def test_encode_classic() -> None:
    assert Parser().encode(CLASSIC_FRAME) == CLASSIC_PACKET


def test_encode_fd() -> None:
    assert Parser().encode(FD_FRAME) == FD_PACKET


ENCODE_ERRORS = [
    ("length 0", b"", FrameLenError),
    ("length 15", bytes(15), FrameLenError),
    ("length 17", bytes(17), FrameLenError),
    ("length 73", bytes(73), FrameLenError),
    ("classic dlc 9", classic_raw(dlc=9), BadDLCError),
    ("fd len 65", fd_raw(length=65), BadLenError),
]


@pytest.mark.parametrize(
    ("frame", "expected"),
    [(case[1], case[2]) for case in ENCODE_ERRORS],
    ids=[case[0] for case in ENCODE_ERRORS],
)
def test_encode_errors(frame: bytes, expected: type[CantcpError]) -> None:
    with pytest.raises(expected) as excinfo:
        Parser().encode(frame)
    assert str(excinfo.value) == str(expected())


def test_encode_limits() -> None:
    assert len(Parser().encode(classic_raw(dlc=8))) == 20
    assert len(Parser().encode(fd_raw(length=64))) == 76


def test_split_classic() -> None:
    assert Parser().split(CLASSIC_PACKET, False) == (20, CLASSIC_FRAME)


def test_split_fd() -> None:
    assert Parser().split(FD_PACKET, False) == (76, FD_FRAME)


def test_split_complete_at_eof() -> None:
    assert Parser().split(CLASSIC_PACKET, True) == (20, CLASSIC_FRAME)


NEED_MORE = [
    ("empty", b"", 0),
    ("one magic byte", b"\xc3", 0),
    ("two magic bytes", b"\xc3\x3c", 0),
    ("type byte", b"\xc3\x3c\x01", 0),
    ("partial classic", CLASSIC_PACKET[:19], 0),
    ("partial fd", FD_PACKET[:75], 0),
    ("garbage only", b"\x01\x02", 2),
    ("false magic start", b"\xc3\xc3\x01", 3),
]


@pytest.mark.parametrize(
    ("data", "advance"),
    [(case[1], case[2]) for case in NEED_MORE],
    ids=[case[0] for case in NEED_MORE],
)
def test_split_needs_more_data(data: bytes, advance: int) -> None:
    parser = Parser()
    got_advance, token = parser.split(data, False)
    assert token is None
    assert got_advance == advance


def test_split_skip_false_magic_byte() -> None:
    parser = Parser()
    assert parser.split(b"\xc3\x00" + CLASSIC_PACKET, False) == (22, CLASSIC_FRAME)
    assert parser.stats.skipped == 2


TRUNCATED = [
    ("one magic byte", b"\xc3"),
    ("two magic bytes", b"\xc3\x3c"),
    ("type byte", b"\xc3\x3c\x01"),
    ("partial classic", CLASSIC_PACKET[:19]),
    ("partial fd", FD_PACKET[:75]),
]


@pytest.mark.parametrize(
    ("data", "lost"),
    [(case[1], len(case[1])) for case in TRUNCATED],
    ids=[case[0] for case in TRUNCATED],
)
def test_split_truncated(data: bytes, lost: int) -> None:
    parser = Parser()
    with pytest.raises(TruncatedError) as excinfo:
        parser.split(data, True)
    assert str(excinfo.value) == str(TruncatedError())
    assert parser.stats.truncated == lost


def test_split_garbage_at_eof() -> None:
    parser = Parser()
    assert parser.split(b"\x01\x02\x03", True) == (3, None)
    assert parser.stats.skipped == 3


def test_split_garbage_around_frames() -> None:
    parser = Parser()
    stream = b"\x01\x02" + CLASSIC_PACKET + b"\x03" + FD_PACKET + b"\x04"
    assert parser.split(stream, False) == (22, CLASSIC_FRAME)
    assert parser.split(stream[22:], False) == (77, FD_FRAME)
    assert parser.split(stream[99:], False) == (1, None)
    assert parser.stats.skipped == 4


def test_split_unknown_type_skipped() -> None:
    parser = Parser()
    stream = make_packet(CLASSIC_FRAME, type_byte=3) + CLASSIC_PACKET
    assert parser.split(stream, False) == (40, CLASSIC_FRAME)
    assert parser.stats.bad_type == 1
    assert parser.stats.skipped == 20


def test_split_unknown_type_fails() -> None:
    parser = Parser(bad_frame_policy=BadFramePolicy.FAIL)
    with pytest.raises(BadTypeError):
        parser.split(make_packet(CLASSIC_FRAME, type_byte=3), False)
    assert parser.stats.bad_type == 1
    assert parser.stats.skipped == 0


def test_split_bad_dlc_skipped() -> None:
    parser = Parser()
    stream = make_packet(classic_raw(dlc=9)) + CLASSIC_PACKET
    assert parser.split(stream, False) == (40, CLASSIC_FRAME)
    assert parser.stats.bad_dlc == 1
    assert parser.stats.skipped == 20


def test_split_bad_dlc_fails() -> None:
    parser = Parser(bad_frame_policy=BadFramePolicy.FAIL)
    with pytest.raises(BadDLCError):
        parser.split(make_packet(classic_raw(dlc=9)), False)
    assert parser.stats.bad_dlc == 1
    assert parser.stats.skipped == 0


def test_split_bad_fd_len_skipped() -> None:
    parser = Parser()
    stream = make_packet(fd_raw(length=65), type_byte=2) + FD_PACKET
    assert parser.split(stream, False) == (152, FD_FRAME)
    assert parser.stats.bad_len == 1
    assert parser.stats.skipped == 76


def test_split_bad_fd_len_fails() -> None:
    parser = Parser(bad_frame_policy=BadFramePolicy.FAIL)
    with pytest.raises(BadLenError):
        parser.split(make_packet(fd_raw(length=65), type_byte=2), False)
    assert parser.stats.bad_len == 1
    assert parser.stats.skipped == 0


def test_split_crc_mismatch_resynchronizes() -> None:
    parser = Parser()
    stream = corrupt_crc(CLASSIC_PACKET) + CLASSIC_PACKET
    assert parser.split(stream, False) == (40, CLASSIC_FRAME)
    assert parser.stats.dropped == 1
    assert parser.stats.skipped == 20


def test_split_crc_mismatch_garbage_only() -> None:
    parser = Parser()
    assert parser.split(corrupt_crc(CLASSIC_PACKET), True) == (20, None)
    assert parser.stats.dropped == 1
    assert parser.stats.skipped == 20


def test_split_custom_magic_and_poly() -> None:
    parser = Parser(magic=b"\x11\x22", crc_poly=0x1D)
    packet = parser.encode(CLASSIC_FRAME)
    assert packet[:2] == b"\x11\x22"
    assert packet == make_packet(CLASSIC_FRAME, magic=b"\x11\x22", poly=0x1D)
    assert parser.split(packet, True) == (20, CLASSIC_FRAME)


def test_split_crc_cover_frame_only() -> None:
    parser = Parser(crc_cover=CrcCover.FRAME)
    packet = parser.encode(CLASSIC_FRAME)
    assert packet[-1] == _CRC8(0x07).sum(CLASSIC_FRAME)
    assert packet == make_packet(CLASSIC_FRAME, cover_header=False)
    assert parser.split(packet, True) == (20, CLASSIC_FRAME)


def test_encode_and_split_agree_with_options() -> None:
    parser = Parser(magic=b"\x00\xff", crc_poly=0x31, crc_cover=CrcCover.FRAME)
    packet = parser.encode(FD_FRAME)
    assert parser.split(packet, False) == (76, FD_FRAME)


INIT_ERRORS = [
    ("magic empty", {"magic": b""}, "magic must be exactly 2 bytes"),
    ("magic long", {"magic": b"\x00\x01\x02"}, "magic must be exactly 2 bytes"),
    ("poly negative", {"crc_poly": -1}, "crc_poly must fit one byte"),
    ("poly above byte", {"crc_poly": 256}, "crc_poly must fit one byte"),
]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [(case[1], case[2]) for case in INIT_ERRORS],
    ids=[case[0] for case in INIT_ERRORS],
)
def test_init_errors(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Parser(**kwargs)


def test_init_poly_boundaries() -> None:
    for poly in (0, 0xFF):
        parser = Parser(crc_poly=poly)
        assert parser.split(parser.encode(CLASSIC_FRAME), True) == (20, CLASSIC_FRAME)


def test_stats_returns_copy() -> None:
    parser = Parser()
    parser.split(b"\x01\x02", False)
    stats = parser.stats
    assert stats.skipped == 2
    stats.skipped = 100
    assert parser.stats.skipped == 2


def test_reset_stats() -> None:
    parser = Parser()
    parser.split(b"\x01\x02", False)
    parser.reset_stats()
    assert parser.stats == Stats()


def test_logging_trace_skip() -> None:
    logger = enabled_logger(TRACE)
    parser = Parser(logger=logger, log_level=TRACE)
    parser.split(b"\x01\x02", False)
    logger.log.assert_called_once_with(TRACE, "garbage skipped", extra={"bytes": 2})


def test_logging_crc_mismatch() -> None:
    logger = enabled_logger(TRACE)
    parser = Parser(logger=logger, log_level=TRACE)
    parser.split(corrupt_crc(CLASSIC_PACKET), False)
    assert call(TRACE, "crc mismatch", extra={"candidate": 1}) in logger.log.call_args_list


def test_logging_truncated() -> None:
    logger = enabled_logger(logging.WARNING)
    parser = Parser(logger=logger, log_level=logging.WARNING)
    with pytest.raises(TruncatedError):
        parser.split(b"\xc3", True)
    logger.log.assert_called_once_with(logging.WARNING, "stream truncated", extra={"bytes": 1})


def test_logging_unknown_type() -> None:
    logger = enabled_logger(logging.WARNING)
    parser = Parser(logger=logger, log_level=logging.WARNING)
    parser.split(make_packet(CLASSIC_FRAME, type_byte=3), False)
    assert (
        call(logging.WARNING, "unknown packet type", extra={"type": 3}) in logger.log.call_args_list
    )


def test_logging_bad_dlc() -> None:
    logger = enabled_logger(logging.WARNING)
    parser = Parser(logger=logger, log_level=logging.WARNING)
    parser.split(make_packet(classic_raw(dlc=9)), False)
    assert call(logging.WARNING, "can_dlc > 8", extra={"dlc": 9}) in logger.log.call_args_list


def test_logging_bad_fd_len() -> None:
    logger = enabled_logger(logging.WARNING)
    parser = Parser(logger=logger, log_level=logging.WARNING)
    parser.split(make_packet(fd_raw(length=65), type_byte=2), False)
    assert call(logging.WARNING, "canfd len > 64", extra={"len": 65}) in logger.log.call_args_list


def test_logging_frame_parsed() -> None:
    logger = enabled_logger(TRACE)
    parser = Parser(logger=logger, log_level=TRACE)
    parser.split(CLASSIC_PACKET, True)
    logger.log.assert_called_once_with(
        TRACE,
        "frame parsed",
        extra={"type": 1, "length": 2, "frame": CLASSIC_FRAME.hex()},
    )


def test_logging_level_filter() -> None:
    logger = enabled_logger(TRACE)
    parser = Parser(logger=logger, log_level=logging.ERROR)
    parser.split(b"\x01\x02", False)
    assert logger.log.call_count == 0


def test_logging_disabled_logger() -> None:
    logger = enabled_logger(logging.CRITICAL)
    parser = Parser(logger=logger, log_level=TRACE)
    parser.split(b"\x01\x02", False)
    assert logger.log.call_count == 0


def test_logging_without_logger() -> None:
    parser = Parser()
    assert parser.split(b"\x01\x02", False) == (2, None)

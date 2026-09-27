"""The Parser object: stream framing of raw CAN frames."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Final

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
from cantcp.frame import (
    _DLC_OFFSET,
    _FD_FRAME_LEN,
    _FRAME_LEN,
    _MAX_DLC,
    _MAX_FD_DATA_LEN,
)
from cantcp.logger import TRACE
from cantcp.policy import BadFramePolicy
from cantcp.stats import Stats
from cantcp.type import Type

_MAGIC_LEN: Final = 2
_TYPE_LEN: Final = 1
_CRC_LEN: Final = 1

_TYPE_OFFSET: Final = _MAGIC_LEN
_FRAME_OFFSET: Final = _MAGIC_LEN + _TYPE_LEN
_CLASSIC_PACKET_LEN: Final = _FRAME_OFFSET + _FRAME_LEN + _CRC_LEN
_FD_PACKET_LEN: Final = _FRAME_OFFSET + _FD_FRAME_LEN + _CRC_LEN


class Parser:
    """Decode a byte stream of framed CAN packets.

        [magic 2 bytes][type 1 byte][struct can_frame 16 | canfd_frame 72][CRC-8 1]

    The type byte is :attr:`cantcp.Type.CLASSIC` or :attr:`cantcp.Type.FD` and
    selects the frame size. The parser keeps its own configuration, its own
    CRC-8 table and stream counters. It is not safe for concurrent use: use
    one parser per stream.

        >>> parser = Parser()
        >>> advance, frame = parser.split(parser.encode(bytes(16)), True)
        >>> advance, len(frame)
        (20, 16)
    """

    __slots__ = (
        "_bad_frame_policy",
        "_cover_header",
        "_crc",
        "_log",
        "_log_level",
        "_magic",
        "_stats",
    )

    def __init__(
        self,
        *,
        magic: bytes = b"\xc3\x3c",
        crc_poly: int = 0x07,
        crc_cover: CrcCover = CrcCover.HEADER,
        bad_frame_policy: BadFramePolicy = BadFramePolicy.SKIP,
        logger: logging.Logger | None = None,
        log_level: int = logging.INFO,
    ) -> None:
        """Create a parser.

        Defaults: magic ``C3 3C``, CRC-8 polynomial ``0x07`` covering
        magic+type+frame, :attr:`cantcp.BadFramePolicy.SKIP` and logging
        disabled. A ``logger`` is any :class:`logging.Logger`; per-packet
        tracing is enabled with ``log_level=TRACE``.

        Raises :class:`ValueError` when ``magic`` is not exactly two bytes or
        ``crc_poly`` does not fit one byte.
        """
        if len(magic) != _MAGIC_LEN:
            raise ValueError("magic must be exactly 2 bytes")
        if not 0 <= crc_poly <= 0xFF:
            raise ValueError("crc_poly must fit one byte")
        self._magic = magic
        self._crc = _CRC8(crc_poly)
        self._cover_header = crc_cover is CrcCover.HEADER
        self._bad_frame_policy = bad_frame_policy
        self._log = logger
        self._log_level = log_level
        self._stats = Stats()

    def split(self, data: bytes, at_eof: bool) -> tuple[int, bytes | None]:
        """Split off the next raw frame from ``data``.

        Returns ``(advance, token)``: the caller must consume ``advance``
        bytes and, when ``token`` is not ``None``, has one raw frame
        (16 bytes for classic CAN, 72 bytes for CAN FD). ``(0, None)`` means
        more data is needed; at the end of the stream pass ``at_eof=True`` to
        flush the buffer.

        Garbage is discarded, CRC mismatches resynchronize one byte forward
        and a structurally invalid packet follows
        :class:`cantcp.BadFramePolicy`: with :attr:`~cantcp.BadFramePolicy.SKIP`
        it is counted and dropped, with :attr:`~cantcp.BadFramePolicy.FAIL`
        :class:`cantcp.BadTypeError`, :class:`cantcp.BadDLCError` or
        :class:`cantcp.BadLenError` is raised. A packet cut off at the end of
        the stream raises :class:`cantcp.TruncatedError`.
        """
        advance = 0
        while True:
            # 1. Skip garbage up to the first magic byte.
            if data and data[0] != self._magic[0]:
                index = data.find(self._magic[0])
                if index < 0:
                    self._stats.skipped += len(data)
                    self._log_at(TRACE, "garbage skipped", bytes=len(data))
                    return advance + len(data), None
                self._stats.skipped += index
                self._log_at(TRACE, "garbage skipped", bytes=index)
                advance += index
                data = data[index:]

            # 2. Match the second magic byte.
            if len(data) < _MAGIC_LEN:
                if not at_eof or not data:
                    return advance, None
                self._stats.truncated += len(data)
                self._log_at(logging.WARNING, "stream truncated", bytes=len(data))
                raise TruncatedError()

            if data[1] != self._magic[1]:
                self._stats.skipped += 1
                advance += 1
                data = data[1:]
                continue

            # 3. Wait for the type byte.
            if len(data) < _FRAME_OFFSET:
                if not at_eof:
                    return advance, None
                self._stats.truncated += len(data)
                self._log_at(logging.WARNING, "stream truncated", bytes=len(data))
                raise TruncatedError()

            # 4. Validate the packet type and pick the frame layout.
            packet_type = data[_TYPE_OFFSET]
            if packet_type == Type.CLASSIC:
                frame_size, packet_len = _FRAME_LEN, _CLASSIC_PACKET_LEN
            elif packet_type == Type.FD:
                frame_size, packet_len = _FD_FRAME_LEN, _FD_PACKET_LEN
            else:
                self._stats.bad_type += 1
                self._log_at(logging.WARNING, "unknown packet type", type=packet_type)
                if self._bad_frame_policy is BadFramePolicy.FAIL:
                    raise BadTypeError()
                self._stats.skipped += 1
                advance += 1
                data = data[1:]
                continue

            # 5. Wait for the whole packet.
            if len(data) < packet_len:
                if not at_eof:
                    return advance, None
                self._stats.truncated += len(data)
                self._log_at(logging.WARNING, "stream truncated", bytes=len(data))
                raise TruncatedError()

            packet = data[:packet_len]

            # 6. Verify the CRC. A mismatch steps one byte forward so that a
            # real header overlapping the false candidate is not lost.
            if self._crc.sum(self._crc_span(packet, packet_len)) != packet[packet_len - 1]:
                self._stats.dropped += 1
                self._stats.skipped += 1
                self._log_at(TRACE, "crc mismatch", candidate=self._stats.dropped)
                advance += 1
                data = data[1:]
                continue

            # 7. Validate the frame length field.
            frame = packet[_FRAME_OFFSET : _FRAME_OFFSET + frame_size]
            error = self._length_error(frame, frame_size)
            if error is not None:
                if self._bad_frame_policy is BadFramePolicy.FAIL:
                    raise error
                self._stats.skipped += 1
                advance += 1
                data = data[1:]
                continue

            self._log_at(
                TRACE,
                "frame parsed",
                type=packet_type,
                length=frame[_DLC_OFFSET],
                frame=frame.hex(),
            )
            return advance + packet_len, frame

    def encode(self, frame: bytes) -> bytes:
        """Build a packet carrying the raw ``frame``.

        The frame length selects the packet type: 16 bytes build a classic
        packet, 72 bytes a CAN FD one. The CRC-8 and its coverage follow the
        parser configuration, so a packet built by :meth:`encode` is always
        accepted by :meth:`split` of a parser with the same options.

        A frame of any other length raises :class:`cantcp.FrameLenError`,
        ``can_dlc > 8`` raises :class:`cantcp.BadDLCError`` and a CAN FD
        length greater than 64 raises :class:`cantcp.BadLenError`.
        """
        length = len(frame)
        if length == _FRAME_LEN:
            if frame[_DLC_OFFSET] > _MAX_DLC:
                raise BadDLCError()
            packet_type = Type.CLASSIC
        elif length == _FD_FRAME_LEN:
            if frame[_DLC_OFFSET] > _MAX_FD_DATA_LEN:
                raise BadLenError()
            packet_type = Type.FD
        else:
            raise FrameLenError()
        packet_len = _FRAME_OFFSET + length + _CRC_LEN
        packet = self._magic + bytes((packet_type,)) + frame
        return packet + bytes((self._crc.sum(self._crc_span(packet, packet_len)),))

    @property
    def stats(self) -> Stats:
        """A copy of the stream counters."""
        return replace(self._stats)

    def reset_stats(self) -> None:
        """Zero the stream counters."""
        self._stats = Stats()

    def _length_error(self, frame: bytes, frame_size: int) -> CantcpError | None:
        """Check the length field of a raw frame, counting and logging it."""
        length = frame[_DLC_OFFSET]
        if frame_size == _FRAME_LEN:
            if length <= _MAX_DLC:
                return None
            self._stats.bad_dlc += 1
            self._log_at(logging.WARNING, "can_dlc > 8", dlc=length)
            return BadDLCError()
        if length <= _MAX_FD_DATA_LEN:
            return None
        self._stats.bad_len += 1
        self._log_at(logging.WARNING, "canfd len > 64", len=length)
        return BadLenError()

    def _crc_span(self, packet: bytes, packet_len: int) -> bytes:
        """Return the part of a packet covered by the CRC-8."""
        if self._cover_header:
            return packet[: packet_len - _CRC_LEN]
        return packet[_FRAME_OFFSET : packet_len - _CRC_LEN]

    def _log_at(self, level: int, message: str, **fields: object) -> None:
        """Log ``message`` at ``level`` when the logger is enabled for it."""
        if self._log is None or level < self._log_level or not self._log.isEnabledFor(level):
            return
        self._log.log(level, message, extra=fields)

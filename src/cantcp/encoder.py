"""The Encoder object: writing framed CAN frames to a binary stream."""

from __future__ import annotations

import logging
from typing import BinaryIO

from cantcp.crc_cover import CrcCover
from cantcp.errors import ShortWriteError
from cantcp.frame import Frame
from cantcp.parser import Parser
from cantcp.policy import BadFramePolicy


class Encoder:
    """Write framed CAN packets to a binary stream.

        [magic 2 bytes][type 1 byte][struct can_frame 16 | canfd_frame 72][CRC-8 1]

    The encoder wraps :meth:`cantcp.Parser.encode`: the frame length selects
    the packet type, the CRC-8 and its coverage follow the parser
    configuration, so a packet written by an encoder is always accepted by a
    decoder created with the same options. An encoder is not safe for
    concurrent use: use one encoder per stream.

        >>> import io
        >>> stream = io.BytesIO()
        >>> Encoder(stream).encode(bytes(16))
        >>> stream.getvalue().hex()
        'c33c010000000000000000000000000000000064'
    """

    __slots__ = ("_parser", "_writer")

    def __init__(
        self,
        writer: BinaryIO,
        *,
        magic: bytes = b"\xc3\x3c",
        crc_poly: int = 0x07,
        crc_cover: CrcCover = CrcCover.HEADER,
        bad_frame_policy: BadFramePolicy = BadFramePolicy.SKIP,
        logger: logging.Logger | None = None,
        log_level: int = logging.INFO,
    ) -> None:
        """Create an encoder writing to ``writer``.

        Options configure the internal parser exactly like
        :class:`cantcp.Parser`; ``bad_frame_policy``, ``logger`` and
        ``log_level`` are accepted for symmetry with the reader side and do
        not affect writing. The writer is owned by the caller: the encoder
        never closes it.
        """
        self._writer = writer
        self._parser = Parser(
            magic=magic,
            crc_poly=crc_poly,
            crc_cover=crc_cover,
            bad_frame_policy=bad_frame_policy,
            logger=logger,
            log_level=log_level,
        )

    def encode(self, frame: bytes) -> None:
        """Write one packet carrying the raw ``frame``.

        Validation errors of :meth:`cantcp.Parser.encode`
        (:class:`cantcp.FrameLenError`, :class:`cantcp.BadDLCError`,
        :class:`cantcp.BadLenError`) leave the stream untouched. A write that
        stored fewer bytes than requested raises
        :class:`cantcp.ShortWriteError`; a write error is propagated unchanged
        and leaves the stream in an unknown state.
        """
        packet = self._parser.encode(frame)
        written = self._writer.write(packet)
        if written is None or written < len(packet):
            raise ShortWriteError()

    def encode_frame(self, frame: Frame) -> None:
        """Write one packet carrying ``frame``.

        The frame is marshalled with :meth:`cantcp.Frame.to_raw`; its errors
        (:class:`cantcp.BadTypeError`, :class:`cantcp.BadIDError`,
        :class:`cantcp.BadFlagsError`, :class:`cantcp.BadDLCError`,
        :class:`cantcp.BadLenError`) leave the stream untouched.
        """
        self.encode(frame.to_raw())

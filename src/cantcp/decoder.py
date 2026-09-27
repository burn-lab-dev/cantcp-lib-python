"""The Decoder object: reading framed CAN frames from a binary stream."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import BinaryIO

from cantcp.crc_cover import CrcCover
from cantcp.errors import CantcpError
from cantcp.frame import Frame
from cantcp.parser import _FD_PACKET_LEN, Parser
from cantcp.policy import BadFramePolicy
from cantcp.stats import Stats


class Decoder:
    """Read framed CAN packets from a binary stream.

        [magic 2 bytes][type 1 byte][struct can_frame 16 | canfd_frame 72][CRC-8 1]

    Garbage and packets rejected by the CRC are dropped, stream counters are
    collected and every call returns one raw frame. A decoder is not safe for
    concurrent use: use one decoder per stream.

        >>> import io
        >>> raw = bytes(16)
        >>> decoder = Decoder(io.BytesIO(Parser().encode(raw)))
        >>> decoder.decode() == raw
        True
        >>> decoder.decode() is None
        True

    Iteration yields parsed :class:`cantcp.Frame` objects:

        >>> import io
        >>> stream = io.BytesIO(Parser().encode(bytes(16)))
        >>> print(next(iter(Decoder(stream))))
        Frame{Type:CAN, ID:0x0, Flags:none, DLC:0, Data:}
    """

    __slots__ = ("_buffer", "_failure", "_parser", "_reader")

    def __init__(
        self,
        reader: BinaryIO,
        *,
        magic: bytes = b"\xc3\x3c",
        crc_poly: int = 0x07,
        crc_cover: CrcCover = CrcCover.HEADER,
        bad_frame_policy: BadFramePolicy = BadFramePolicy.SKIP,
        logger: logging.Logger | None = None,
        log_level: int = logging.INFO,
    ) -> None:
        """Create a decoder reading from ``reader``.

        Options configure the internal parser exactly like
        :class:`cantcp.Parser`. The reader is owned by the caller: the decoder
        never closes it.
        """
        self._reader = reader
        self._parser = Parser(
            magic=magic,
            crc_poly=crc_poly,
            crc_cover=crc_cover,
            bad_frame_policy=bad_frame_policy,
            logger=logger,
            log_level=log_level,
        )
        self._buffer = bytearray()
        self._failure: CantcpError | None = None

    def decode(self) -> bytes | None:
        """Return the next raw frame or ``None`` at the end of the stream.

        The returned bytes are independent of the decoder buffer and stay
        valid after the next call. A packet cut off in the middle raises
        :class:`cantcp.TruncatedError`; errors of the underlying reader are
        propagated unchanged. After a terminal error every call raises the
        same error, like a spent scanner.
        """
        return self._next_raw()

    def decode_frame(self) -> Frame | None:
        """Return the next frame parsed into a :class:`cantcp.Frame`.

        The parsing is as strict as :meth:`cantcp.Frame.from_raw`: a CAN FD
        length the 4-bit DLC field cannot encode raises
        :class:`cantcp.BadLenError` even though the splitter accepted the
        packet. ``None`` reports the end of the stream.
        """
        raw = self._next_raw()
        if raw is None:
            return None
        return Frame.from_raw(raw)

    def __iter__(self) -> Iterator[Frame]:
        """Iterate over the frames of the stream."""
        return self

    def __next__(self) -> Frame:
        """Return the next frame or raise :class:`StopIteration` at the end."""
        frame = self.decode_frame()
        if frame is None:
            raise StopIteration
        return frame

    @property
    def stats(self) -> Stats:
        """A copy of the stream counters."""
        return self._parser.stats

    def reset_stats(self) -> None:
        """Zero the stream counters."""
        self._parser.reset_stats()

    def _next_raw(self) -> bytes | None:
        """Return the next raw frame, reading from the stream as needed."""
        if self._failure is not None:
            raise self._failure
        final = False
        while True:
            try:
                advance, token = self._parser.split(bytes(self._buffer), final)
            except CantcpError as exc:
                self._failure = exc
                raise
            if advance:
                del self._buffer[:advance]
            if token is not None:
                return token
            if final:
                return None
            chunk = self._reader.read(_FD_PACKET_LEN)
            if not chunk:
                final = True
                continue
            self._buffer.extend(chunk)

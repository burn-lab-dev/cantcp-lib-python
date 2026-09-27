r"""Python library for the cantcp protocol.

The package carries CAN frames only: stream framing of raw SocketCAN frames
in a byte stream, plus parsing, encoding and decoding of Linux SocketCAN
frames. Connection setup is plain TCP: handshakes, subscriptions, keepalives,
statistics and health checks are not part of the protocol.

Quick start:

    >>> import io
    >>> import cantcp
    >>> stream = io.BytesIO()
    >>> frame = cantcp.Frame(type=cantcp.Type.CLASSIC, id=0x123, data=bytes.fromhex("dead"))
    >>> cantcp.Encoder(stream).encode_frame(frame)
    >>> print(next(iter(cantcp.Decoder(io.BytesIO(stream.getvalue())))))
    Frame{Type:CAN, ID:0x123, Flags:none, DLC:2, Data:dead}
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from cantcp.crc_cover import CrcCover
from cantcp.decoder import Decoder
from cantcp.encoder import Encoder
from cantcp.errors import (
    BadDLCError,
    BadFlagsError,
    BadIDError,
    BadLenError,
    BadTypeError,
    CantcpError,
    FrameLenError,
    ReservedError,
    ShortWriteError,
    TruncatedError,
)
from cantcp.flags import Flag
from cantcp.frame import Frame
from cantcp.logger import TRACE
from cantcp.parser import Parser
from cantcp.policy import BadFramePolicy
from cantcp.stats import Stats
from cantcp.type import Type
from cantcp.validate import validate_raw

try:
    __version__ = version("cantcp")
except PackageNotFoundError:  # pragma: no cover - the package is not installed
    __version__ = "0.0.0"

__all__ = [
    "TRACE",
    "BadDLCError",
    "BadFlagsError",
    "BadFramePolicy",
    "BadIDError",
    "BadLenError",
    "BadTypeError",
    "CantcpError",
    "CrcCover",
    "Decoder",
    "Encoder",
    "Flag",
    "Frame",
    "FrameLenError",
    "Parser",
    "ReservedError",
    "ShortWriteError",
    "Stats",
    "TruncatedError",
    "Type",
    "validate_raw",
]

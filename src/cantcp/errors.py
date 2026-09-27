"""Errors raised by the cantcp package.

Every protocol error is a subclass of :class:`CantcpError` with a static
message; the texts are identical to the Go implementation of the library, so
logs of both languages match. Catch a concrete class with ``except`` or the
base class to handle all of them:

    from cantcp import BadDLCError, CantcpError

    try:
        frame.to_raw()
    except BadDLCError as exc:
        print(exc)  # cantcp: can_dlc > 8
    except CantcpError:
        ...  # any other protocol error
"""

from __future__ import annotations


class CantcpError(Exception):
    """Base class for all errors raised by the cantcp package."""


class FrameLenError(CantcpError):
    """A frame is neither 16 (can_frame) nor 72 (canfd_frame) bytes."""

    def __init__(self) -> None:
        super().__init__("cantcp: frame length is not 16 or 72 bytes")


class BadDLCError(CantcpError):
    """A classic can_frame whose can_dlc is greater than 8."""

    def __init__(self) -> None:
        super().__init__("cantcp: can_dlc > 8")


class BadLenError(CantcpError):
    """An invalid CAN FD length: greater than 64 or not encodable in DLC."""

    def __init__(self) -> None:
        super().__init__("cantcp: invalid canfd length")


class BadTypeError(CantcpError):
    """An unknown frame type: not classic CAN and not CAN FD."""

    def __init__(self) -> None:
        super().__init__("cantcp: unknown frame type")


class BadFlagsError(CantcpError):
    """Flags that are not valid for the frame type."""

    def __init__(self) -> None:
        super().__init__("cantcp: flags are not valid for the frame type")


class BadIDError(CantcpError):
    """An identifier that does not fit the addressing mode."""

    def __init__(self) -> None:
        super().__init__("cantcp: identifier does not fit the addressing mode")


class ReservedError(CantcpError):
    """Non-zero reserved or padding bytes of a frame."""

    def __init__(self) -> None:
        super().__init__("cantcp: reserved bytes are not zero")


class TruncatedError(CantcpError):
    """An incomplete packet at the end of the stream."""

    def __init__(self) -> None:
        super().__init__("cantcp: stream truncated in the middle of a packet")


class ShortWriteError(CantcpError):
    """A write wrote fewer bytes than requested."""

    def __init__(self) -> None:
        super().__init__("cantcp: short write")

"""Validation of raw SocketCAN frames without the cantcp stream envelope."""

from __future__ import annotations

from cantcp.frame import _check_raw
from cantcp.type import Type


def validate_raw(raw: bytes) -> Type:
    """Validate a raw frame and report its type.

    16 bytes are decoded as a struct can_frame (:class:`cantcp.Type.CLASSIC`),
    72 bytes as a struct canfd_frame (:class:`cantcp.Type.FD`); any other
    length raises :class:`cantcp.FrameLenError`. The layout is selected by the
    length only: a raw SocketCAN frame carries no separate CAN FD marker, the
    frame type is defined by the socket it was read from.

    The rules are the same as :meth:`cantcp.Frame.from_raw`, which shares the
    implementation; the first error is raised. The type is derivable from
    ``len(raw)`` even when an error is raised, because it is selected by the
    length.

        >>> validate_raw(bytes(16)).name
        'CLASSIC'
        >>> validate_raw(bytes(72)).name
        'FD'
    """
    frame_type, _ = _check_raw(raw)
    return frame_type

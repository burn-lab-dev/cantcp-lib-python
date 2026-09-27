"""The Type of a frame: classic CAN or CAN FD."""

from __future__ import annotations

from enum import IntEnum


class Type(IntEnum):
    """Selects the frame layout.

    The same values are used as the packet type byte of the stream framing.
    """

    CLASSIC = 0x01
    """struct can_frame, 16 bytes."""

    FD = 0x02
    """struct canfd_frame, 72 bytes."""

    def __str__(self) -> str:
        """Return ``CAN`` or ``CAN FD``."""
        return "CAN" if self is Type.CLASSIC else "CAN FD"

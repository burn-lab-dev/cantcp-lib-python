"""The Flag bits of a Frame."""

from __future__ import annotations

from enum import IntFlag


class Flag(IntFlag):
    """Flag bits of a Frame, combined with bitwise OR.

    ``EFF``, ``RTR`` and ``ERR`` come from the CAN identifier word; ``BRS``
    and ``ESI`` come from the CAN FD flags byte. The constants are the
    argument of :meth:`cantcp.Frame.set_flags`:

        frame.set_flags(Flag.EFF | Flag.RTR)
    """

    EFF = 1 << 0
    """Extended (29-bit) identifier."""

    RTR = 1 << 1
    """Remote transmission request (classic CAN only)."""

    ERR = 1 << 2
    """Error frame (carries no addressing mode)."""

    BRS = 1 << 3
    """CAN FD bit rate switch."""

    ESI = 1 << 4
    """CAN FD error state indicator."""

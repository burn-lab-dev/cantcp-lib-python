"""Which part of a packet the CRC-8 covers."""

from __future__ import annotations

from enum import Enum


class CrcCover(Enum):
    """The byte span covered by the CRC-8 of a packet."""

    HEADER = "magic+type+frame"
    """Magic, packet type byte and the raw frame (the default)."""

    FRAME = "frame"
    """The raw frame only."""

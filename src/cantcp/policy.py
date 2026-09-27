"""How the parser reacts to a structurally invalid packet."""

from __future__ import annotations

from enum import Enum


class BadFramePolicy(Enum):
    """Reaction to an unknown packet type byte or a bad frame length field."""

    SKIP = "skip"
    """Drop the invalid packet, count it and keep parsing (the default)."""

    FAIL = "fail"
    """Stop parsing and raise BadTypeError, BadDLCError or BadLenError."""

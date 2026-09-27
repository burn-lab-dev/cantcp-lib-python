"""Stream counters collected by a parser or a decoder."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Stats:
    """Counters of a stream since the last reset.

    A snapshot is returned by :attr:`cantcp.Parser.stats` and
    :attr:`cantcp.Decoder.stats`; mutating the snapshot does not change the
    counters of the object itself. Python integers are unbounded, so the
    counters never saturate (the Go implementation saturates at MaxInt).
    """

    skipped: int = 0
    """Bytes discarded while resynchronizing."""

    dropped: int = 0
    """Candidates rejected by the CRC-8."""

    bad_type: int = 0
    """Packets with an unknown type byte."""

    bad_dlc: int = 0
    """Classic frames with can_dlc greater than 8."""

    bad_len: int = 0
    """CAN FD frames with a length greater than 64."""

    truncated: int = 0
    """Bytes lost to a packet cut off at the end of the stream."""

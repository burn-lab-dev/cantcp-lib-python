"""Shared test helpers: raw frame builders and packet builders."""

from __future__ import annotations

from cantcp.crc8 import _CRC8

CLASSIC_LEN = 16
FD_LEN = 72
DLC_OFFSET = 4
DATA_OFFSET = 8

DEFAULT_MAGIC = b"\xc3\x3c"
DEFAULT_POLY = 0x07


def classic_raw(
    *,
    raw_id: int = 0,
    dlc: int = 0,
    pad: int = 0,
    res0: int = 0,
    res1: int = 0,
    data: bytes = b"",
    tail: bytes = b"",
) -> bytes:
    """Build a 16-byte struct can_frame with the given fields."""
    raw = bytearray(CLASSIC_LEN)
    raw[0:4] = raw_id.to_bytes(4, "little")
    raw[4] = dlc
    raw[5] = pad
    raw[6] = res0
    raw[7] = res1
    raw[DATA_OFFSET : DATA_OFFSET + len(data)] = data
    raw[DATA_OFFSET + len(data) : DATA_OFFSET + len(data) + len(tail)] = tail
    return bytes(raw)


def fd_raw(
    *,
    raw_id: int = 0,
    length: int = 0,
    flags: int = 0,
    res0: int = 0,
    res1: int = 0,
    data: bytes = b"",
    tail: bytes = b"",
) -> bytes:
    """Build a 72-byte struct canfd_frame with the given fields."""
    raw = bytearray(FD_LEN)
    raw[0:4] = raw_id.to_bytes(4, "little")
    raw[4] = length
    raw[5] = flags
    raw[6] = res0
    raw[7] = res1
    raw[DATA_OFFSET : DATA_OFFSET + len(data)] = data
    raw[DATA_OFFSET + len(data) : DATA_OFFSET + len(data) + len(tail)] = tail
    return bytes(raw)


def make_packet(
    frame: bytes,
    *,
    type_byte: int = 1,
    magic: bytes = DEFAULT_MAGIC,
    poly: int = DEFAULT_POLY,
    cover_header: bool = True,
) -> bytes:
    """Build a cantcp packet around a raw frame with a correct CRC-8."""
    body = magic + bytes((type_byte,)) + frame
    span = body if cover_header else frame
    return body + bytes((_CRC8(poly).sum(span),))


def corrupt_crc(packet: bytes) -> bytes:
    """Flip the CRC byte of a packet."""
    return packet[:-1] + bytes((packet[-1] ^ 0xFF,))

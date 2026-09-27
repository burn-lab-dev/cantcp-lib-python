"""Table-driven CRC-8 with a configurable polynomial.

The default polynomial 0x07 is CRC-8/SMBus: init 0x00, no input or output
reflection, no final XOR. The table is built per instance, nothing is shared
globally.
"""

from __future__ import annotations

_TABLE_SIZE = 256
_BITS_PER_BYTE = 8
_BYTE_MASK = 0xFF
_TOP_BIT = 0x80


class _CRC8:
    """A CRC-8 calculator with its own lookup table."""

    __slots__ = ("_table",)

    def __init__(self, poly: int) -> None:
        table = []
        for index in range(_TABLE_SIZE):
            value = index
            for _ in range(_BITS_PER_BYTE):
                if value & _TOP_BIT:
                    value = (value << 1) ^ poly
                else:
                    value <<= 1
                value &= _BYTE_MASK
            table.append(value)
        self._table = tuple(table)

    def sum(self, data: bytes) -> int:
        """Return the CRC-8 of ``data``."""
        value = 0
        for byte in data:
            value = self._table[value ^ byte]
        return value

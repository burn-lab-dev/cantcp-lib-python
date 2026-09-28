"""The Frame object: a parsed CAN or CAN FD frame."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from cantcp.errors import (
    BadDLCError,
    BadFlagsError,
    BadIDError,
    BadLenError,
    BadTypeError,
    FrameLenError,
    ReservedError,
)
from cantcp.flags import Flag
from cantcp.type import Type

_FRAME_LEN: Final = 16
"""sizeof(struct can_frame)."""

_FD_FRAME_LEN: Final = 72
"""sizeof(struct canfd_frame)."""

_DLC_OFFSET: Final = 4
"""can_dlc (classic) and len (CAN FD) offset."""

_PAD_OFFSET: Final = 5
"""Classic __pad offset; must be zero."""

_FD_FLAGS_OFFSET: Final = 5
"""canfd_frame flags offset (BRS 0x01, ESI 0x02; the kernel's FD marker
CANFD_FDF 0x04 is accepted on input and ignored)."""

_RES0_OFFSET: Final = 6
"""__res0 offset; must be zero in both layouts."""

_RES1_OFFSET: Final = 7
"""Classic len8_dlc and canfd __res1 offset; must be zero."""

_DATA_OFFSET: Final = 8
"""data[] offset in both layouts."""

_MAX_DLC: Final = 8
"""CAN_MAX_DLEN: the largest classic payload."""

_MAX_FD_DATA_LEN: Final = 64
"""CANFD_MAX_DLEN: the largest CAN FD payload."""

_CAN_EFF_FLAG: Final = 0x80000000
_CAN_RTR_FLAG: Final = 0x40000000
_CAN_ERR_FLAG: Final = 0x20000000
_CAN_EFF_MASK: Final = 0x1FFFFFFF
_CAN_SFF_MASK: Final = 0x000007FF

_CANFD_BRS: Final = 0x01
_CANFD_ESI: Final = 0x02
# _CANFD_FDF: the kernel sets the FD marker when it delivers a CAN FD frame.
# The bit is accepted on input and ignored; encoding never writes it.
_CANFD_FDF: Final = 0x04
_CANFD_MASK: Final = _CANFD_BRS | _CANFD_ESI | _CANFD_FDF

_VALID_FD_DATA_LENS: Final = frozenset({0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64})
"""CAN FD data lengths encodable in the 4-bit DLC field."""

_BYTE_ORDER: Final = "little"


def _check_raw(raw: bytes) -> tuple[Type, int]:
    """Validate a raw frame and return its type and can_id word.

    The single source of truth of raw frame validation: both
    :meth:`Frame.from_raw` and :func:`cantcp.validate_raw` go through it. The
    type is selected by the length only: 16 bytes are a struct can_frame, 72
    bytes a struct canfd_frame. On error a :class:`cantcp.CantcpError` subclass
    is raised; the frame is not touched.
    """
    length = len(raw)
    if length == _FRAME_LEN:
        frame_type = Type.CLASSIC
    elif length == _FD_FRAME_LEN:
        frame_type = Type.FD
    else:
        raise FrameLenError()

    raw_id = int.from_bytes(raw[0:4], _BYTE_ORDER)
    eff = bool(raw_id & _CAN_EFF_FLAG)
    rtr = bool(raw_id & _CAN_RTR_FLAG)
    is_err = bool(raw_id & _CAN_ERR_FLAG)

    # An error frame carries no addressing mode: can_err_mask_t keeps bits
    # 29-31 zero, so CAN_EFF_FLAG and CAN_RTR_FLAG are not valid with it.
    if is_err and (eff or rtr):
        raise BadFlagsError()
    # RTR has no CAN FD layout.
    if frame_type == Type.FD and rtr:
        raise BadFlagsError()
    # A standard frame fits 11 bits; an error frame carries a 29-bit error
    # class mask, so only non-error frames are checked against CAN_SFF_MASK.
    if not eff and not is_err and raw_id & _CAN_EFF_MASK > _CAN_SFF_MASK:
        raise BadIDError()

    if frame_type == Type.CLASSIC:
        if raw[_DLC_OFFSET] > _MAX_DLC:
            raise BadDLCError()
        # Byte 7 is len8_dlc in the modern kernel layout; DLC 9..15 is not
        # supported by this protocol, so it must be zero here.
        if raw[_PAD_OFFSET] | raw[_RES0_OFFSET] | raw[_RES1_OFFSET] != 0:
            raise ReservedError()
        return frame_type, raw_id

    if raw[_DLC_OFFSET] not in _VALID_FD_DATA_LENS:
        raise BadLenError()
    if raw[_FD_FLAGS_OFFSET] & ~_CANFD_MASK != 0:
        raise BadFlagsError()
    if raw[_RES0_OFFSET] | raw[_RES1_OFFSET] != 0:
        raise ReservedError()
    return frame_type, raw_id


@dataclass(slots=True)
class Frame:
    r"""A parsed CAN or CAN FD frame.

    The object is independent of the cantcp stream framing:
    :meth:`to_raw` and :meth:`from_raw` work with the raw Linux SocketCAN
    layouts (struct can_frame, 16 bytes, and struct canfd_frame, 72 bytes)
    only. The raw frame parsed or built last is kept and returned by the
    :attr:`raw` property.

    An error frame carries a 29-bit error class mask in :attr:`id` instead of
    an identifier; ``err`` combined with ``eff`` or ``rtr`` is rejected.
    ``rtr`` is not valid for CAN FD.

        >>> frame = Frame(type=Type.CLASSIC, id=0x123, data=bytes.fromhex("dead"))
        >>> print(frame)
        Frame{Type:CAN, ID:0x123, Flags:none, DLC:2, Data:dead}
        >>> frame.to_raw().hex()
        '2301000002000000dead000000000000'
        >>> print(Frame.from_raw(bytes.fromhex("2301000002000000dead000000000000")))
        Frame{Type:CAN, ID:0x123, Flags:none, DLC:2, Data:dead}
    """

    id: int = 0
    """Identifier: 11-bit standard, 29-bit with ``eff``; an error frame
    carries a 29-bit error class mask."""

    type: Type | None = None
    """:class:`cantcp.Type` selecting the frame layout."""

    eff: bool = False
    """Extended (29-bit) identifier."""

    rtr: bool = False
    """Remote transmission request (classic CAN only)."""

    err: bool = False
    """Error frame."""

    brs: bool = False
    """CAN FD bit rate switch."""

    esi: bool = False
    """CAN FD error state indicator."""

    data: bytes = b""
    """Payload; ``len(data)`` is the frame length field (can_dlc or len)."""

    _raw: bytes | None = field(default=None, init=False, repr=False, compare=False)

    @classmethod
    def from_raw(cls, raw: bytes) -> Frame:
        """Parse a raw frame: 16 bytes as can_frame, 72 bytes as canfd_frame.

        Parsing is strict and goes through the same validation as
        :func:`cantcp.validate_raw`: a frame of any other length raises
        :class:`cantcp.FrameLenError`, ``can_dlc > 8`` raises
        :class:`cantcp.BadDLCError`, an invalid CAN FD length raises
        :class:`cantcp.BadLenError`, non-zero padding and reserved bytes raise
        :class:`cantcp.ReservedError`, invalid flags raise
        :class:`cantcp.BadFlagsError`, and an identifier that does not fit
        the addressing mode raises :class:`cantcp.BadIDError`.

        Bytes of the data area beyond the length field are not part of
        :attr:`data` and are not preserved: :meth:`to_raw` writes zeroes
        there.
        """
        frame_type, raw_id = _check_raw(raw)
        frame = cls()
        eff = bool(raw_id & _CAN_EFF_FLAG)
        is_err = bool(raw_id & _CAN_ERR_FLAG)
        frame.type = frame_type
        frame.id = raw_id & (_CAN_EFF_MASK if eff or is_err else _CAN_SFF_MASK)
        frame.eff = eff
        frame.rtr = bool(raw_id & _CAN_RTR_FLAG)
        frame.err = is_err
        if frame_type == Type.FD:
            frame.brs = bool(raw[_FD_FLAGS_OFFSET] & _CANFD_BRS)
            frame.esi = bool(raw[_FD_FLAGS_OFFSET] & _CANFD_ESI)
        frame.data = bytes(raw[_DATA_OFFSET : _DATA_OFFSET + raw[_DLC_OFFSET]])
        frame._raw = bytes(raw)
        return frame

    def to_raw(self) -> bytes:
        """Build the raw frame and store it.

        Returns 16 bytes for ``Type.CLASSIC`` or 72 bytes for ``Type.FD``;
        the data area beyond ``len(data)`` is zeroed. The result is stored and
        returned by the :attr:`raw` property.

        Raises :class:`cantcp.BadTypeError` for an unset type,
        :class:`cantcp.BadIDError` for an identifier that does not fit the
        addressing mode (11 bits for a standard frame, 29 with ``eff`` or in
        an error frame, never negative), :class:`cantcp.BadFlagsError` for
        flags not valid for the type (``brs`` and ``esi`` in classic CAN,
        ``rtr`` in CAN FD, ``err`` with ``eff`` or ``rtr``),
        :class:`cantcp.BadDLCError` for a classic payload longer than 8 bytes
        and :class:`cantcp.BadLenError` for a CAN FD length the 4-bit DLC
        field cannot encode.
        """
        data_len = len(self.data)
        if self.type == Type.CLASSIC:
            if data_len > _MAX_DLC:
                raise BadDLCError()
            if self.brs or self.esi:
                raise BadFlagsError()
            length = _FRAME_LEN
        elif self.type == Type.FD:
            if data_len > _MAX_FD_DATA_LEN or data_len not in _VALID_FD_DATA_LENS:
                raise BadLenError()
            if self.rtr:
                raise BadFlagsError()
            length = _FD_FRAME_LEN
        else:
            raise BadTypeError()

        if self.err and (self.eff or self.rtr):
            raise BadFlagsError()
        limit = _CAN_EFF_MASK if self.eff or self.err else _CAN_SFF_MASK
        if self.id < 0 or self.id > limit:
            raise BadIDError()

        raw_id = self.id
        if self.eff:
            raw_id |= _CAN_EFF_FLAG
        if self.rtr:
            raw_id |= _CAN_RTR_FLAG
        if self.err:
            raw_id |= _CAN_ERR_FLAG

        raw = bytearray(length)
        raw[0:4] = raw_id.to_bytes(4, _BYTE_ORDER)
        raw[_DLC_OFFSET] = data_len
        if self.type == Type.FD:
            if self.brs:
                raw[_FD_FLAGS_OFFSET] |= _CANFD_BRS
            if self.esi:
                raw[_FD_FLAGS_OFFSET] |= _CANFD_ESI
        raw[_DATA_OFFSET : _DATA_OFFSET + data_len] = self.data
        result = bytes(raw)
        self._raw = result
        return result

    def set_flags(self, flags: int | Flag) -> None:
        """Replace all flags with the given bit set.

        Build the set from the :class:`cantcp.Flag` constants:

            frame.set_flags(Flag.EFF | Flag.RTR)

        Flags that are unknown or not valid for the current ``type`` raise
        :class:`cantcp.BadFlagsError`: ``BRS`` and ``ESI`` are valid for CAN FD
        only, ``RTR`` is not valid for CAN FD, and an error frame carries no
        addressing mode, so ``ERR`` excludes ``EFF`` and ``RTR``. An unset
        type raises :class:`cantcp.BadTypeError`.
        """
        value = int(flags)
        if self.type == Type.CLASSIC:
            mask = int(Flag.EFF | Flag.RTR | Flag.ERR)
        elif self.type == Type.FD:
            mask = int(Flag.EFF | Flag.ERR | Flag.BRS | Flag.ESI)
        else:
            raise BadTypeError()
        if value & ~mask != 0:
            raise BadFlagsError()
        if value & int(Flag.ERR) != 0 and value & int(Flag.EFF | Flag.RTR) != 0:
            raise BadFlagsError()
        self.eff = bool(value & int(Flag.EFF))
        self.rtr = bool(value & int(Flag.RTR))
        self.err = bool(value & int(Flag.ERR))
        self.brs = bool(value & int(Flag.BRS))
        self.esi = bool(value & int(Flag.ESI))

    @property
    def flags(self) -> Flag:
        """The flags as a :class:`cantcp.Flag` set."""
        value = Flag(0)
        if self.eff:
            value |= Flag.EFF
        if self.rtr:
            value |= Flag.RTR
        if self.err:
            value |= Flag.ERR
        if self.brs:
            value |= Flag.BRS
        if self.esi:
            value |= Flag.ESI
        return value

    @property
    def raw(self) -> bytes | None:
        """A copy of the raw frame parsed or built last, or ``None``."""
        if self._raw is None:
            return None
        return bytes(self._raw)

    def __str__(self) -> str:
        """Return a single-line representation.

        For example::

            Frame{Type:CAN, ID:0x123, Flags:EFF|RTR, DLC:2, Data:0a0b}
        """
        type_name = "unknown" if self.type is None else str(self.type)
        length_name = "Len" if self.type == Type.FD else "DLC"
        return (
            f"Frame{{Type:{type_name}, ID:0x{self.id:x}, Flags:{self._flags_text()}, "
            f"{length_name}:{len(self.data)}, Data:{self.data.hex()}}}"
        )

    def _flags_text(self) -> str:
        names = []
        if self.eff:
            names.append("EFF")
        if self.rtr:
            names.append("RTR")
        if self.err:
            names.append("ERR")
        if self.brs:
            names.append("BRS")
        if self.esi:
            names.append("ESI")
        return "|".join(names) if names else "none"

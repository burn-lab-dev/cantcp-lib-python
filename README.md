# cantcp-lib-python

[![CI](https://github.com/burn-lab-dev/cantcp-lib-python/actions/workflows/ci.yml/badge.svg)](https://github.com/burn-lab-dev/cantcp-lib-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cantcp.svg)](https://pypi.org/project/cantcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/cantcp.svg)](https://pypi.org/project/cantcp/)

Python library for the **cantcp** protocol: encoding and decoding of Linux
SocketCAN frames, stream framing with CRC-8, plus a parsed CAN / CAN FD frame
model.

> **Status: WIP.** The API is not stable, the protocol is in development (`v0`).

Russian documentation: [README.ru.md](README.ru.md). Security notes:
[SECURITY.md](SECURITY.md).

Developed by **[BURN-LAB](https://burn-lab.ru)** — embedded software
development: Linux, drivers, CAN and industrial telemetry.

## Scope

The package carries CAN frames only: stream framing, frame parsing and the
codec. Connection setup is plain TCP: handshakes, subscriptions, keepalives,
statistics and health checks are not part of the protocol. A server exposes
them over its own API (for example HTTP) and clients poll that API when they
need them.

The package depends on the standard library only. The protocol canon and its
byte-for-byte test vectors live in
[cantcp-spec](https://github.com/burn-lab-dev/cantcp-spec) and are shared
with the other implementations.

## Stream framing

A packet in the byte stream:

```
[magic 2 bytes][type 1 byte][can_frame 16 | canfd_frame 72][CRC-8 1 byte]
```

The packet type byte selects the frame layout:

| Value | Constant | Frame | Size |
|---|---|---|---|
| `0x01` | `Type.CLASSIC` | `struct can_frame` | 16 |
| `0x02` | `Type.FD` | `struct canfd_frame` | 72 |

Classic frame (`can_frame`):

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | `can_id` (little-endian) |
| 4 | 1 | `can_dlc` |
| 5 | 1 | `__pad` (must be zero) |
| 6 | 1 | `__res0` (must be zero) |
| 7 | 1 | `__res1` (must be zero) |
| 8 | 8 | `data` |

CAN FD frame (`canfd_frame`):

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | `can_id` (little-endian) |
| 4 | 1 | `len` |
| 5 | 1 | `flags` (`BRS` 0x01, `ESI` 0x02; the kernel's `CANFD_FDF` 0x04 is accepted on input and ignored) |
| 6 | 1 | `__res0` (must be zero) |
| 7 | 1 | `__res1` (must be zero) |
| 8 | 64 | `data` |

The reserved bytes take part in the CRC: the sender must write zeroes there.
By default the CRC-8 (polynomial `0x07`, SMBus) covers `magic+type+frame`;
`CrcCover.FRAME` makes it cover the raw frame only.

`Parser.split` returns the raw frame as the token: 16 bytes for classic CAN,
72 bytes for CAN FD. Every returned object is a new `bytes`, independent of
the input buffer. `Parser.encode` builds a packet and selects the type by the
frame length: 16 bytes build a classic packet, 72 bytes a CAN FD one.

## Quick start

Reading with a decoder:

```python
import socket

import cantcp

HOST, PORT = "192.168.1.10", 29536  # the default cantcp gateway port

with socket.create_connection((HOST, PORT)) as conn:
    decoder = cantcp.Decoder(conn.makefile("rb", buffering=0))
    try:
        for frame in decoder:
            print(frame)  # Frame{Type:CAN FD, ID:0x123, Flags:BRS, Len:2, Data:0102}
    except cantcp.TruncatedError as exc:
        print("decode:", exc)  # stream truncated in the middle of a packet
    except OSError as exc:
        print("stream:", exc)  # the peer closed the connection or the network failed
    print(f"skipped={decoder.stats.skipped} dropped={decoder.stats.dropped}")
```

Writing with an encoder:

```python
with socket.create_connection((HOST, PORT)) as conn:
    writer = conn.makefile("wb")
    encoder = cantcp.Encoder(writer)
    frame = cantcp.Frame(type=cantcp.Type.CLASSIC, id=0x123, data=b"\xde\xad")
    encoder.encode_frame(frame)
    writer.flush()
```

A socket is wrapped with `socket.makefile("rb", buffering=0)` for reading and
`socket.makefile("wb")` for writing: the raw reader returns as soon as bytes
are available, while a buffered reader would block until the requested size is
filled. Any binary stream with `read(size)` and
`write(data)` works.

Low-level `Parser.split` / `Parser.encode` stay available for custom readers
and writers; see the API reference below.

## Install

```bash
pip install cantcp
```

From the source tag:

```bash
pip install "cantcp @ git+https://github.com/burn-lab-dev/cantcp-lib-python@v0.1.0"
```

# API reference

The package API is built from three kinds of objects and plain functions:

- `Parser` is the **parser**: created by the constructor and configured by
  keyword arguments, used through its exported methods;
- `Decoder` and `Encoder` wrap the parser with a binary stream API: created by
  the constructor and configured by the same keyword arguments;
- `Frame` is the parsed-frame object; `Type`, `Flag`, `Stats`,
  `BadFramePolicy`, `CrcCover`, `TRACE` and the `CantcpError` subclasses
  complete the surface;
- plain functions: `validate_raw`.

## `Parser` — the parser

```python
cantcp.Parser(*, magic=b"\xc3\x3c", crc_poly=0x07, crc_cover=CrcCover.HEADER,
              bad_frame_policy=BadFramePolicy.SKIP, logger=None, log_level=logging.INFO)
```

Decodes a byte stream of framed CAN packets; keeps its own configuration, its
own CRC-8 table and stream counters. It is not safe for concurrent use: use
one parser per stream. `magic` must be exactly two bytes and `crc_poly` must
fit one byte, otherwise `ValueError` is raised.

Defaults: magic `C3 3C`, CRC-8 polynomial `0x07` covering `magic+type+frame`,
`BadFramePolicy.SKIP` and logging disabled.

```python
parser = cantcp.Parser(log_level=cantcp.TRACE)
packet = parser.encode(bytes(16))
advance, raw = parser.split(packet, at_eof=True)  # 20, 16 raw bytes
```

### Parser settings

The keyword arguments below configure `Parser`; the same arguments configure
`Decoder` and `Encoder`, so a packet written with one option set is always
accepted by a reader created with the same set.

| Argument | Default | Description |
|---|---|---|
| `magic` | `b"\xc3\x3c"` | Two-byte packet header |
| `crc_poly` | `0x07` (SMBus) | CRC-8 polynomial |
| `crc_cover` | `CrcCover.HEADER` | CRC covers `magic+type+frame` or the frame only |
| `bad_frame_policy` | `BadFramePolicy.SKIP` | Reaction to an invalid packet |
| `logger` | `None` | Any `logging.Logger`; `None` disables logging |
| `log_level` | `logging.INFO` | Minimum level to log; `TRACE` enables per-packet tracing |

#### `magic`

The two-byte packet header, replacing the default `C3 3C`. The magic is
always exactly two bytes.

```python
parser = cantcp.Parser(magic=b"\x11\x22")
packet = parser.encode(bytes(16))
print(packet[:2].hex())  # 1122
```

#### `crc_poly`

The CRC-8 polynomial (default `0x07`); the lookup table is rebuilt per parser.

```python
parser = cantcp.Parser(crc_poly=0x1D)
advance, raw = parser.split(parser.encode(bytes(16)), at_eof=True)
print(advance, len(raw))  # 20 16
```

#### `crc_cover`

Makes the CRC cover the raw frame only (`CrcCover.FRAME`) instead of
`magic+type+frame` (the default `CrcCover.HEADER`).

```python
parser = cantcp.Parser(crc_cover=cantcp.CrcCover.FRAME)
advance, raw = parser.split(parser.encode(bytes(72)), at_eof=True)
print(advance, len(raw))  # 76 72
```

#### `bad_frame_policy`

Selects how `Parser.split` reacts to an unknown packet type byte or a bad
frame length field (`can_dlc > 8`, `canfd len > 64`); see `BadFramePolicy`.

```python
parser = cantcp.Parser(bad_frame_policy=cantcp.BadFramePolicy.FAIL)
try:
    parser.split(b"\xc3\x3c\x7f", at_eof=False)
except cantcp.BadTypeError as exc:
    print(exc)  # cantcp: unknown frame type
```

#### `logger`

Sets the logger, any `logging.Logger`. `None` (the default) disables logging
completely.

```python
import logging

parser = cantcp.Parser(logger=logging.getLogger("cantcp"))
```

#### `log_level`

Sets the minimum level to log (default `logging.INFO`). Use `TRACE` to trace
every parsed frame, garbage skip, CRC mismatch and rejected packet type.

> **Warning:** `TRACE` writes the full hex of the raw frame to the log,
> **including the payload** — machine telemetry and commands. This is sensitive
> data: tracing is meant for debugging on an isolated bench only. Do not enable
> `TRACE` in production, and treat traced logs as sensitive.

```python
parser = cantcp.Parser(logger=logging.getLogger("cantcp"), log_level=logging.WARNING)
# per-frame tracing is off, only warnings are logged
```

### Parser methods

#### `split`

```python
split(data: bytes, at_eof: bool) -> tuple[int, bytes | None]
```

Splits off the next raw frame from `data`. Returns `(advance, token)`: the
caller must consume `advance` bytes and, when `token` is not `None`, has one
raw frame (16 bytes for classic CAN, 72 bytes for CAN FD). `(0, None)` means
more data is needed; at the end of the stream pass `at_eof=True` to flush the
buffer.

Garbage is discarded, a CRC mismatch resynchronizes one byte forward and a
structurally invalid packet follows `bad_frame_policy`: with
`BadFramePolicy.SKIP` it is counted and dropped, with `BadFramePolicy.FAIL`
`BadTypeError`, `BadDLCError` or `BadLenError` is raised. A packet cut off at
the end of the stream raises `TruncatedError`.

```python
parser = cantcp.Parser()
packet = parser.encode(bytes(16))
advance, raw = parser.split(packet, at_eof=True)
print(advance, len(raw))  # 20 16
```

For whole streams use `Decoder`, which wraps `split` with a binary stream API.

#### `encode`

```python
encode(frame: bytes) -> bytes
```

Builds a packet carrying the raw `frame`. The frame length selects the packet
type: 16 bytes build a classic packet, 72 bytes a CAN FD one. The CRC-8 and
its coverage follow the parser configuration, so a packet built by `encode` is
always accepted by `split` of a parser with the same options.

A frame of any other length raises `FrameLenError`, `can_dlc > 8` raises
`BadDLCError` and a CAN FD length greater than 64 raises `BadLenError`.

```python
parser = cantcp.Parser()
frame = cantcp.Frame(type=cantcp.Type.FD, id=0x123, brs=True, data=b"\x01\x02")
packet = parser.encode(frame.to_raw())
print(len(packet))  # 76
```

#### `stats`, `reset_stats`

`stats` returns a copy of the counters since the last reset, `reset_stats()`
zeroes them. See `Stats` for the counter fields.

```python
parser = cantcp.Parser()
parser.split(b"\x01\x02", at_eof=False)
print("skipped:", parser.stats.skipped)  # skipped: 2
parser.reset_stats()
print("after reset:", parser.stats.skipped)  # after reset: 0
```

## `Decoder` — the decoder

```python
cantcp.Decoder(reader, **parser_options)
```

Reads framed packets from a binary stream. Garbage and packets rejected by
the CRC are dropped, stream counters are collected and every call returns one
raw frame or a parsed `Frame`. The reader is owned by the caller: the decoder
never closes it. It is not safe for concurrent use: use one decoder per
stream.

```python
decoder = cantcp.Decoder(conn.makefile("rb", buffering=0), logger=logging.getLogger("cantcp"))
```

### Decoder methods

#### `decode`

```python
decode() -> bytes | None
```

Returns the next raw frame: 16 bytes for classic CAN, 72 bytes for CAN FD.
`None` reports the end of the stream. The returned bytes are independent of
the decoder buffer and stay valid after the next call.

A packet cut off in the middle raises `TruncatedError`; errors of the
underlying reader are propagated unchanged, so a closed connection surfaces as
`OSError`. After a terminal error every call raises the same error, like a
spent scanner.

```python
decoder = cantcp.Decoder(conn.makefile("rb", buffering=0))
try:
    while (raw := decoder.decode()) is not None:
        handle_raw(raw)
except cantcp.TruncatedError as exc:
    print("decode:", exc)
except OSError as exc:
    print("stream:", exc)
```

#### `decode_frame`

```python
decode_frame() -> Frame | None
```

Returns the next frame parsed into a `Frame`; `None` reports the end of the
stream. The returned frame is independent of the decoder: it keeps its own
raw frame, so `data` stays valid after the next call.

The parsing is as strict as `Frame.from_raw`: a CAN FD length the 4-bit DLC
field cannot encode raises `BadLenError` even though the tolerant splitter
accepted the packet. The error returns of `decode` apply unchanged.

```python
decoder = cantcp.Decoder(conn.makefile("rb", buffering=0))
while (frame := decoder.decode_frame()) is not None:
    use(frame)
```

#### Iteration

A decoder is iterable and yields parsed frames; the iteration ends at the end
of the stream.

```python
for frame in cantcp.Decoder(conn.makefile("rb", buffering=0)):
    use(frame)
```

#### `stats`, `reset_stats`

`stats` returns a copy of the stream counters, `reset_stats()` zeroes them.
See `Stats` for the counter fields.

```python
decoder = cantcp.Decoder(conn.makefile("rb", buffering=0))
if (frame := decoder.decode_frame()) is None:
    print("stream closed")
else:
    use(frame)
print("skipped:", decoder.stats.skipped)
decoder.reset_stats()
print("after reset:", decoder.stats.skipped)
```

## `Encoder` — the encoder

```python
cantcp.Encoder(writer, **parser_options)
```

Writes framed packets to a binary stream. The encoder wraps
`Parser.encode`: the frame length selects the packet type, the CRC-8 and its
coverage follow the parser configuration, so a packet written by an encoder is
always accepted by a decoder created with the same options. `bad_frame_policy`,
`logger` and `log_level` are accepted for symmetry with the reader side and do
not affect writing. The writer is owned by the caller: the encoder never
closes it.

```python
writer = conn.makefile("wb")
encoder = cantcp.Encoder(writer)
```

### Encoder methods

#### `encode`

```python
encode(frame: bytes) -> None
```

Writes a packet carrying the raw frame: 16 bytes build a classic packet,
72 bytes a CAN FD one. Validation errors of `Parser.encode` (`FrameLenError`,
`BadDLCError`, `BadLenError`) leave the stream untouched.

A write that stored fewer bytes than requested raises `ShortWriteError`; a
write error is propagated unchanged and leaves the stream in an unknown state.

```python
raw = bytes(16)  # struct can_frame
encoder.encode(raw)
writer.flush()
```

#### `encode_frame`

```python
encode_frame(frame: Frame) -> None
```

Marshals `frame` with `Frame.to_raw` and writes the packet. Marshal errors
(`BadTypeError`, `BadIDError`, `BadFlagsError`, `BadDLCError`, `BadLenError`)
leave the stream untouched.

```python
frame = cantcp.Frame(type=cantcp.Type.FD, id=0x123, brs=True, data=b"\x01\x02")
encoder.encode_frame(frame)
writer.flush()
```

## `Frame` — the parsed frame object

```python
Frame(id=0, type=None, eff=False, rtr=False, err=False, brs=False, esi=False, data=b"")
```

`Frame` is a parsed CAN or CAN FD frame, independent of the cantcp stream
framing: `from_raw` and `to_raw` work with the raw Linux SocketCAN layouts
(struct can_frame, 16 bytes, and struct canfd_frame, 72 bytes) only.

Public fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | `int` | Identifier: 11-bit standard, 29-bit with `eff`; an error frame carries a 29-bit error class mask |
| `type` | `Type \| None` | `Type.CLASSIC` or `Type.FD`; selects the frame layout |
| `eff` | `bool` | Extended (29-bit) identifier |
| `rtr` | `bool` | Remote transmission request (classic CAN only) |
| `err` | `bool` | Error frame |
| `brs` | `bool` | CAN FD bit rate switch |
| `esi` | `bool` | CAN FD error state indicator |
| `data` | `bytes` | Payload; `len(data)` is the frame length field (`can_dlc` / `len`) |

### `Frame.from_raw`

```python
Frame.from_raw(raw: bytes) -> Frame
```

Parses a raw frame: 16 bytes as `can_frame`, 72 bytes as `canfd_frame`, any
other length raises `FrameLenError`. Parsing is strict: `BadDLCError`,
`BadLenError` (a CAN FD length not encodable in the 4-bit DLC field: only
`0..8, 12, 16, 20, 24, 32, 48, 64` are valid), `ReservedError` (non-zero
padding/reserved bytes), `BadFlagsError` (`rtr` in CAN FD, `eff` or `rtr` with
`err`, unknown bits of the CAN FD flags byte; the kernel's `CANFD_FDF` 0x04
is accepted and ignored), `BadIDError` (an identifier
that does not fit the addressing mode).

Bytes of the data area beyond the length field are not part of `data` and are
not preserved: `to_raw` writes zeroes there.

```python
raw = bytearray(16)
raw[0], raw[1] = 0x23, 0x01  # can_id = 0x123 (little-endian)
raw[4] = 2  # can_dlc
raw[8:10] = b"\xde\xad"
frame = cantcp.Frame.from_raw(bytes(raw))
print(frame)  # Frame{Type:CAN, ID:0x123, Flags:none, DLC:2, Data:dead}
```

### `Frame.to_raw`

```python
Frame.to_raw() -> bytes
```

Builds the raw frame (16 bytes for `Type.CLASSIC`, 72 bytes for `Type.FD`),
stores it and returns it. The data area beyond `len(data)` is zeroed.

Errors: `BadTypeError` (unset type), `BadIDError` (an identifier that does
not fit the addressing mode: 11 bits for a standard frame, 29 with `eff` or
in an error frame, never negative), `BadFlagsError` (`brs` and `esi` in
classic CAN, `rtr` in CAN FD, `err` with `eff` or `rtr`), `BadDLCError` and
`BadLenError`.

```python
frame = cantcp.Frame(type=cantcp.Type.FD, id=0x123, brs=True, data=b"\x01\x02")
raw = frame.to_raw()
print(len(raw))  # 72
print(raw[:6].hex())  # 230100000201
```

### `Frame.set_flags`

```python
Frame.set_flags(flags: int | Flag) -> None
```

Replaces all flags. Build the set from the `Flag` constants:

```python
frame = cantcp.Frame(type=cantcp.Type.CLASSIC, id=0x123)
frame.set_flags(cantcp.Flag.EFF | cantcp.Flag.RTR)
print(frame)  # Frame{Type:CAN, ID:0x123, Flags:EFF|RTR, DLC:0, Data:}
```

Flags that are unknown or not valid for the current type raise
`BadFlagsError`: `BRS` and `ESI` are valid for CAN FD only, `RTR` is not
valid for CAN FD, and an error frame carries no addressing mode, so `ERR`
excludes `EFF` and `RTR`. An unset type raises `BadTypeError`.

### `Frame.flags`

```python
Frame.flags -> Flag
```

The flags as a `Flag` set.

```python
frame = cantcp.Frame(type=cantcp.Type.FD, id=0x123, brs=True, esi=True)
print(frame.flags == (cantcp.Flag.BRS | cantcp.Flag.ESI))  # True
```

### `Frame.raw`

```python
Frame.raw -> bytes | None
```

A copy of the raw frame parsed or built last, or `None` if no frame was
parsed or built yet.

```python
frame = cantcp.Frame.from_raw(bytes(16))
print(len(frame.raw))  # 16
```

### `Frame.__str__`

`str(frame)` returns a human-readable single-line representation with the
same format as the Go library:

```python
frame = cantcp.Frame(type=cantcp.Type.CLASSIC, id=0x1ABCDE, eff=True, data=b"\xde\xad")
print(frame)  # Frame{Type:CAN, ID:0x1abcde, Flags:EFF, DLC:2, Data:dead}
```

## `Type`

```python
class Type(IntEnum):
    CLASSIC = 0x01  # struct can_frame, 16 bytes
    FD = 0x02  # struct canfd_frame, 72 bytes
```

Selects the frame layout. The same values are used as the packet type byte of
the stream framing. `str(Type.FD)` is `"CAN FD"`, `str(Type.CLASSIC)` is
`"CAN"`; an unknown value cannot be constructed (`Type(3)` raises
`ValueError`).

```python
print(cantcp.Type.CLASSIC, cantcp.Type.FD)  # CAN CAN FD
```

## Flags

`Flag` constants describe a `Frame`; combine them with bitwise OR and pass the
result to `Frame.set_flags`. `EFF`, `RTR` and `ERR` come from the CAN
identifier word; `BRS` and `ESI` come from the CAN FD flags byte. The values
are internal to the object: `to_raw` and `from_raw` map them to and from the
raw SocketCAN bit positions.

| Constant | Raw bit | Meaning |
|---|---|---|
| `Flag.EFF` | `can_id` 0x80000000 | extended (29-bit) identifier |
| `Flag.RTR` | `can_id` 0x40000000 | remote transmission request (classic only) |
| `Flag.ERR` | `can_id` 0x20000000 | error frame |
| `Flag.BRS` | `canfd flags` 0x01 | CAN FD bit rate switch |
| `Flag.ESI` | `canfd flags` 0x02 | CAN FD error state indicator |

```python
frame = cantcp.Frame(type=cantcp.Type.FD, id=0x123, brs=True, data=b"\x01\x02")
frame.set_flags(cantcp.Flag.EFF | cantcp.Flag.BRS)
print(frame)  # Frame{Type:CAN FD, ID:0x123, Flags:EFF|BRS, Len:2, Data:0102}
```

## `Stats`

The counter object returned by `stats` of a parser or a decoder. A snapshot:
mutating it does not change the counters of the object itself. Python
integers are unbounded, so the counters never saturate.

```python
@dataclass(slots=True)
class Stats:
    skipped: int = 0  # bytes discarded while resynchronizing
    dropped: int = 0  # candidates rejected by the CRC
    bad_type: int = 0  # packets with an unknown type byte
    bad_dlc: int = 0  # classic frames with can_dlc > 8
    bad_len: int = 0  # CAN FD frames with canfd len > 64
    truncated: int = 0  # bytes lost to a packet cut off at the end
```

```python
parser = cantcp.Parser()
parser.split(b"\x01\x02", at_eof=False)
stats = parser.stats
print(stats.skipped, stats.dropped)  # 2 0
```

## `BadFramePolicy`, `CrcCover`

`BadFramePolicy` selects how `Parser.split` reacts to a structurally invalid
packet; set with the `bad_frame_policy` argument.

```python
class BadFramePolicy(Enum):
    SKIP = "skip"  # drop, count and keep parsing (default)
    FAIL = "fail"  # stop and raise BadTypeError/BadDLCError/BadLenError
```

```python
parser = cantcp.Parser(bad_frame_policy=cantcp.BadFramePolicy.SKIP)
parser.split(b"\xc3\x3c\x7f", at_eof=False)
print(parser.stats.bad_type)  # 1
```

`CrcCover` selects the byte span covered by the CRC-8; set with the
`crc_cover` argument.

```python
class CrcCover(Enum):
    HEADER = "magic+type+frame"  # the default
    FRAME = "frame"  # the raw frame only
```

## `Logger`, `TRACE`

The parser logs through any standard `logging.Logger`; `None` disables
logging. `TRACE` (`5`) is the per-packet tracing level, lower than
`logging.DEBUG` so it can be enabled on its own.

> **Warning:** `TRACE` writes the full hex of the raw frame to the log,
> **including the payload** — machine telemetry and commands. This is sensitive
> data: tracing is meant for debugging on an isolated bench only. Do not
> enable `TRACE` in production, and treat traced logs as sensitive.

```python
import logging

import cantcp

parser = cantcp.Parser(logger=logging.getLogger("cantcp"), log_level=cantcp.TRACE)
# every parsed frame, skipped byte, CRC mismatch and rejected type is traced
```

## `validate_raw`

```python
validate_raw(raw: bytes) -> Type
```

Validates a raw frame without the cantcp stream envelope and reports its type:
16 bytes are `Type.CLASSIC`, 72 bytes `Type.FD`, any other length raises
`FrameLenError`. The layout is selected by the length only: a raw SocketCAN
frame carries no separate CAN FD marker, the frame type is defined by the
socket it was read from.

The rules are the same as `Frame.from_raw`, which shares the implementation:
`BadIDError`, `BadDLCError`, `BadLenError`, `BadFlagsError`, `ReservedError`;
the first error is raised. The type is derivable from `len(raw)` even when an
error is raised, because it is selected by the length.

```python
raw = bytearray(16)
raw[4] = 9  # can_dlc > 8
try:
    cantcp.validate_raw(bytes(raw))
except cantcp.BadDLCError as exc:
    print(exc)  # cantcp: can_dlc > 8
```

## Errors

All errors are classes derived from `CantcpError`; the messages are identical
to the Go implementation. Catch a concrete class or the base class.

| Error | Meaning |
|---|---|
| `FrameLenError` | frame length is not 16 or 72 bytes |
| `BadDLCError` | classic `can_dlc > 8` |
| `BadLenError` | invalid CAN FD length (> 64 or not encodable in the 4-bit DLC field) |
| `BadTypeError` | unknown packet/frame type |
| `BadFlagsError` | flags not valid for the frame type |
| `BadIDError` | identifier does not fit the addressing mode |
| `ReservedError` | non-zero reserved bytes |
| `TruncatedError` | packet cut off at the end of the stream |
| `ShortWriteError` | a write stored fewer bytes than requested |

```python
try:
    cantcp.Frame(type=cantcp.Type.CLASSIC, data=bytes(9)).to_raw()
except cantcp.BadDLCError as exc:
    print(exc)  # cantcp: can_dlc > 8
except cantcp.CantcpError as exc:
    print("protocol error:", exc)
```

## CAN FD data lengths

CAN FD data lengths are encoded in the 4-bit DLC field with a discrete scale,
so only the following lengths exist; any other length is rejected with
`BadLenError`. `Parser.split` and `Decoder.decode` stay tolerant
(`len <= 64`) for raw pass-through.

| DLC | 0..8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
|---|---|---|---|---|---|---|---|---|
| bytes | 0..8 | 12 | 16 | 20 | 24 | 32 | 48 | 64 |

## Security

cantcp is a transport, not a security layer. It is designed to run **inside a
trusted perimeter** (a closed network segment). Authentication, channel
encryption, integrity protection and replay protection are not tasks of the
library: they are the responsibility of whoever applies it — TLS/mTLS, VPN,
network segmentation and application-level peer authentication. The CRC-8 is a
framing sanity check, not cryptographic integrity; a peer that can write to
the stream can forge, modify or replay any frame. `TRACE` logs the raw frame
including the payload and must not be enabled in production.

See [SECURITY.md](SECURITY.md) for the threat model, the CPU amplification
note and the deployment checklist. Russian translation:
[SECURITY.ru.md](SECURITY.ru.md).

A complete TLS 1.3 server and client with mutual TLS — `ssl.SSLContext` for
both sides, certificate loading and the cantcp codec over the connection —
lives in [examples/tls](examples/tls/). The OpenSSL commands that generate
the certificates are in the cantcp documentation (`docs/TLS-KEYS.md` in the
[cantcp](https://github.com/burn-lab-dev/cantcp) repository).

## Notes

- `Parser.split` is a self-synchronizing splitter: after a corrupt candidate
  the resynchronization may find a valid frame even inside its data area. This
  is intended.
- `Parser.encode` only frames the bytes it is given: it does not sanitize
  padding, reserved bytes or flags, while `Frame` is the strict model. The
  layers are intentionally separate.
- Every slice returned by `split` and `decode` is a new `bytes`, independent
  of the input buffer; a `Frame` keeps its own raw frame, so `Frame.data`
  stays valid after the next decode call.
- The CRC-8 is a framing sanity check, not cryptographic integrity: about one
  in 256 random candidates passes it.
- `TRACE` logs the raw frame including its data (payload): it is a debugging
  tool for an isolated bench, not a production logging level; see
  [SECURITY.md](SECURITY.md).
- An error frame carries no addressing mode: `err` combined with `eff` or
  `rtr` is rejected with `BadFlagsError`, and its 29-bit error class mask is
  accepted in `id` instead of an 11-bit identifier. `rtr` is classic-only. An
  identifier that does not fit the addressing mode is an error, not silently
  masked.
- `validate_raw` and `Frame.from_raw` share one validation core, so both
  accept and reject exactly the same raw frames; `Parser.split` stays
  tolerant and performs only the stream-level checks.
- `Decoder.decode` returns `None` at the end of the stream; a terminal error
  (truncation, fail policy) is raised on every subsequent call.
- `Stats` counters never saturate (the Go implementation saturates at
  `MaxInt`).
- `Frame.raw` is `None` until a frame was parsed or built, instead of
  returning zero bytes for a partially filled value.

## Dependencies

Standard library only. No external dependencies.

## License

MIT — see [LICENSE](LICENSE).

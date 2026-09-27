"""Replay of the shared test vectors: the canon of the protocol."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from cantcp.crc8 import _CRC8
from cantcp.crc_cover import CrcCover
from cantcp.decoder import Decoder
from cantcp.encoder import Encoder
from cantcp.errors import (
    BadDLCError,
    BadFlagsError,
    BadIDError,
    BadLenError,
    BadTypeError,
    CantcpError,
    FrameLenError,
    ReservedError,
    TruncatedError,
)
from cantcp.flags import Flag
from cantcp.frame import Frame
from cantcp.parser import Parser
from cantcp.policy import BadFramePolicy
from cantcp.type import Type
from cantcp.validate import validate_raw

VECTORS_PATH = Path(__file__).parent / "vectors.json"

ERROR_CLASSES: dict[str, type[CantcpError]] = {
    "ErrFrameLen": FrameLenError,
    "ErrBadDLC": BadDLCError,
    "ErrBadLen": BadLenError,
    "ErrBadType": BadTypeError,
    "ErrBadFlags": BadFlagsError,
    "ErrBadID": BadIDError,
    "ErrReserved": ReservedError,
    "ErrTruncated": TruncatedError,
}

FLAG_NAMES = {
    "eff": Flag.EFF,
    "rtr": Flag.RTR,
    "err": Flag.ERR,
    "brs": Flag.BRS,
    "esi": Flag.ESI,
}


def load_vectors() -> dict[str, Any]:
    """Load the canon and check its protocol marker."""
    parsed: dict[str, Any] = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    assert parsed["protocol"] == "cantcp"
    assert parsed["version"] == "v0"
    return parsed


VECTORS = load_vectors()


def test_vector_config() -> None:
    config = VECTORS["config"]
    parser = Parser()
    packet = parser.encode(bytes(16))
    assert packet[:2].hex() == config["magic"]
    assert packet[2] == Type.CLASSIC
    assert packet[-1] == _CRC8(config["crc_poly"]).sum(packet[:-1])
    assert CrcCover.HEADER.value == config["crc_cover"]


@pytest.mark.parametrize("case", VECTORS["crc8"], ids=[case["name"] for case in VECTORS["crc8"]])
def test_crc8_vector(case: dict[str, Any]) -> None:
    assert _CRC8(case["poly"]).sum(bytes.fromhex(case["input"])) == case["sum"]


def test_vector_error_names_are_known() -> None:
    for case in VECTORS["frames"] + VECTORS["packets"]:
        assert case["error"] == "" or case["error"] in ERROR_CLASSES


@pytest.mark.parametrize(
    "case", VECTORS["frames"], ids=[case["name"] for case in VECTORS["frames"]]
)
def test_frame_vector(case: dict[str, Any]) -> None:
    raw = bytes.fromhex(case["raw"])
    if case["error"]:
        expected = ERROR_CLASSES[case["error"]]
        with pytest.raises(expected) as excinfo:
            Frame.from_raw(raw)
        assert str(excinfo.value) == str(expected())
        with pytest.raises(expected):
            validate_raw(raw)
        return

    frame = Frame.from_raw(raw)
    assert validate_raw(raw) is frame.type
    fields = case["fields"]
    assert frame.type is (Type.CLASSIC if fields["type"] == "classic" else Type.FD)
    assert frame.id == fields["id"]
    assert frame.data.hex() == fields["data"]
    expected_flags = Flag(0)
    for name in fields["flags"]:
        expected_flags |= FLAG_NAMES[name]
    assert frame.flags == expected_flags

    canonical = bytes.fromhex(case["canonical"] or case["raw"])
    assert frame.to_raw() == canonical
    assert frame.raw == canonical


@pytest.mark.parametrize(
    "case", VECTORS["packets"], ids=[case["name"] for case in VECTORS["packets"]]
)
def test_packet_vector(case: dict[str, Any]) -> None:
    stream = bytes.fromhex(case["stream"])
    options: dict[str, Any] = {}
    policy = case["bad_frame_policy"]
    if policy == "fail":
        options["bad_frame_policy"] = BadFramePolicy.FAIL
    else:
        assert policy in ("", "skip")

    decoder = Decoder(io.BytesIO(stream), **options)
    frames: list[bytes] = []
    error: CantcpError | None = None
    while True:
        try:
            raw = decoder.decode()
        except CantcpError as exc:
            error = exc
            break
        if raw is None:
            break
        frames.append(raw)

    if case["error"]:
        assert error is not None
        assert type(error) is ERROR_CLASSES[case["error"]]
        assert str(error) == str(ERROR_CLASSES[case["error"]]())
    else:
        assert error is None

    assert [frame.hex() for frame in frames] == case["frames"]
    stats = decoder.stats
    for name, value in case["stats"].items():
        assert getattr(stats, name) == value

    # A stream that is exactly one valid packet without any dropped bytes is
    # the inverse of Encode.
    if (
        case["error"] == ""
        and len(frames) == 1
        and all(value == 0 for value in case["stats"].values())
    ):
        output = io.BytesIO()
        Encoder(output, **options).encode(frames[0])
        assert output.getvalue() == stream

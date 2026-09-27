"""Tests of the vectors sync script."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "sync_vectors.py"
VECTORS_PATH = Path(__file__).parent / "vectors.json"
CHECKSUM_PATH = Path(__file__).parent / "vectors.sha256"


def load_script() -> ModuleType:
    """Import the sync script as a module without running main()."""
    spec = importlib.util.spec_from_file_location("sync_vectors_tested", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT = load_script()


def test_checksum_matches_vectors() -> None:
    digest, name = CHECKSUM_PATH.read_text(encoding="ascii").split()
    assert name == "vectors.json"
    assert digest == hashlib.sha256(VECTORS_PATH.read_bytes()).hexdigest()


def test_check_in_sync() -> None:
    assert SCRIPT.main(["--source", str(VECTORS_PATH), "--check"]) == 0


def test_check_drift(tmp_path: Path) -> None:
    parsed = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    other = tmp_path / "vectors.json"
    other.write_text(json.dumps(parsed, indent=4), encoding="utf-8")
    assert SCRIPT.main(["--source", str(other), "--check"]) == 1


def test_missing_source(tmp_path: Path) -> None:
    assert SCRIPT.main(["--source", str(tmp_path / "missing.json"), "--check"]) == 2


def test_load_source_requires_a_source() -> None:
    with pytest.raises(ValueError, match="either --source or --url"):
        SCRIPT.load_source(None, None)


VALID = json.dumps(
    {"protocol": "cantcp", "version": "v0", "crc8": [{}], "frames": [{}], "packets": [{}]}
)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"not json", "not valid JSON"),
        (b"[]", "must be a JSON object"),
        (json.dumps({"protocol": "other", "version": "v0"}).encode(), "must be cantcp v0"),
        (json.dumps({"protocol": "cantcp", "version": "v1"}).encode(), "must be cantcp v0"),
        (
            json.dumps(
                {"protocol": "cantcp", "version": "v0", "crc8": [], "frames": [], "packets": []}
            ).encode(),
            "empty",
        ),
        (
            json.dumps(
                {"protocol": "cantcp", "version": "v0", "crc8": [{}], "frames": []}
            ).encode(),
            "empty",
        ),
    ],
    ids=[
        "not-json",
        "not-object",
        "wrong-protocol",
        "wrong-version",
        "empty-sections",
        "missing-section",
    ],
)
def test_validate_canon_errors(data: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        SCRIPT.validate_canon(data)


def test_validate_canon_ok() -> None:
    parsed = SCRIPT.validate_canon(VALID.encode())
    assert parsed["protocol"] == "cantcp"
    assert SCRIPT.describe(parsed) == "cantcp v0 (crc8=1, frames=1, packets=1)"


def test_write_target(tmp_path: Path) -> None:
    target = tmp_path / "vectors.json"
    checksum = tmp_path / "vectors.sha256"
    data = VECTORS_PATH.read_bytes()
    assert SCRIPT.write_target(data, target, checksum) is True
    assert target.read_bytes() == data
    assert (
        checksum.read_text(encoding="ascii")
        == f"{hashlib.sha256(data).hexdigest()}  vectors.json\n"
    )
    assert SCRIPT.write_target(data, target, checksum) is False


def test_main_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "vectors.json"
    checksum = tmp_path / "vectors.sha256"
    monkeypatch.setattr(SCRIPT, "TARGET", target)
    monkeypatch.setattr(SCRIPT, "CHECKSUM", checksum)
    assert SCRIPT.main(["--source", str(VECTORS_PATH)]) == 0
    assert target.read_bytes() == VECTORS_PATH.read_bytes()
    assert "updated" in capsys.readouterr().out
    assert SCRIPT.main(["--source", str(VECTORS_PATH)]) == 0
    assert "already current" in capsys.readouterr().out


def test_main_reports_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert SCRIPT.main(["--source", str(tmp_path / "missing.json")]) == 2
    assert "cannot read the canon" in capsys.readouterr().err


def test_check_args_defaults() -> None:
    args: Any = SCRIPT.parse_args([])
    assert args.source is None
    assert args.url is None
    assert args.check is False

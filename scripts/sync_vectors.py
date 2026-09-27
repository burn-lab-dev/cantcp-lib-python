#!/usr/bin/env python3
"""Sync tests/vectors.json with the canon of the Go repository.

The canon of the protocol lives in ``testdata/vectors.json`` of
``cantcp-lib-go``. This script copies it byte-for-byte into
``tests/vectors.json`` and records its SHA-256 in ``tests/vectors.sha256``, so
both implementations are checked against exactly the same bytes.

Usage:

    uv run python scripts/sync_vectors.py                 # sibling Go repo
    uv run python scripts/sync_vectors.py --url URL       # raw canon from GitHub
    uv run python scripts/sync_vectors.py --check         # fail on a difference
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT.parent / "cantcp-lib-go" / "testdata" / "vectors.json"
DEFAULT_URL = (
    "https://raw.githubusercontent.com/burn-lab-dev/cantcp-lib-go/main/testdata/vectors.json"
)
TARGET = REPO_ROOT / "tests" / "vectors.json"
CHECKSUM = REPO_ROOT / "tests" / "vectors.sha256"

PROTOCOL = "cantcp"
VERSION = "v0"
SECTIONS = ("crc8", "frames", "packets")

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_ERROR = 2


def load_source(source: Path | None, url: str | None) -> bytes:
    """Read the canon bytes from a local path or a URL."""
    if url is not None:
        with urlopen(url) as response:
            data: bytes = response.read()
        return data
    if source is None:
        raise ValueError("either --source or --url is required")
    try:
        return source.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read the canon at {source}: {exc}") from exc


def validate_canon(data: bytes) -> dict[str, object]:
    """Check the protocol marker and that every section is present."""
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"the canon is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("the canon must be a JSON object")
    if parsed.get("protocol") != PROTOCOL or parsed.get("version") != VERSION:
        raise ValueError(
            f"the canon must be {PROTOCOL} {VERSION}, got "
            f"{parsed.get('protocol')!r} {parsed.get('version')!r}"
        )
    for section in SECTIONS:
        if not parsed.get(section):
            raise ValueError(f"the canon section {section!r} is empty")
    return parsed


def digest(data: bytes) -> str:
    """The SHA-256 of the canon bytes."""
    return hashlib.sha256(data).hexdigest()


def describe(parsed: dict[str, object]) -> str:
    """A one-line summary of the canon contents."""
    counts = []
    for section in SECTIONS:
        value = parsed.get(section)
        counts.append(f"{section}={len(value) if isinstance(value, list) else 0}")
    return f"{parsed['protocol']} {parsed['version']} ({', '.join(counts)})"


def write_target(data: bytes, target: Path, checksum: Path) -> bool:
    """Write the canon and its checksum; return whether anything changed."""
    changed = not target.exists() or target.read_bytes() != data
    target.write_bytes(data)
    checksum.write_text(f"{digest(data)}  {target.name}\n", encoding="ascii")
    return changed


def check_target(data: bytes, target: Path) -> bool:
    """Return whether the target matches the canon bytes."""
    return target.exists() and target.read_bytes() == data


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help=f"path to the canon JSON (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--url", default=None, help=f"URL of the canon JSON (default: {DEFAULT_URL})"
    )
    parser.add_argument("--check", action="store_true", help="verify without writing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the sync; see the module docstring."""
    args = parse_args(argv)
    source = args.source if args.source is not None else (None if args.url else DEFAULT_SOURCE)
    try:
        data = load_source(source, args.url)
        parsed = validate_canon(data)
    except ValueError as exc:
        print(f"sync_vectors: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.check:
        if check_target(data, TARGET):
            print(f"sync_vectors: {TARGET.name} is in sync with the canon, {describe(parsed)}")
            return EXIT_OK
        print(
            f"sync_vectors: {TARGET.name} differs from the canon, run without --check",
            file=sys.stderr,
        )
        return EXIT_DRIFT

    changed = write_target(data, TARGET, CHECKSUM)
    state = "updated" if changed else "already current"
    print(f"sync_vectors: {state}, {describe(parsed)}, sha256={digest(data)}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

# Contributing

This document is for maintainers and contributors: development commands, the
shared test vectors and the Go ↔ Python API map. Users should read
[README.md](README.md) instead.

Russian translation: [CONTRIBUTING.ru.md](CONTRIBUTING.ru.md).

## Requirements

- Python 3.10 or newer;
- [uv](https://docs.astral.sh/uv/) for the environment and dependencies.

Runtime of the package is the standard library only; external dependencies live
in the `dev` dependency group.

## Setup and checks

```bash
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

Format the code in place with `uv run ruff format .`. `mypy` runs in strict
mode over `src`, `tests` and `scripts`. `pytest` runs unit tests, doctests of
`src/cantcp` and the hypothesis property tests; **100% line and branch
coverage is required** (`fail_under = 100` in `pyproject.toml`).

## Layout

| Path | Contents |
|---|---|
| `src/cantcp/` | the package: one object per module, `py.typed` marker |
| `tests/` | tests, `helpers.py` with raw frame builders, the vectors copy |
| `scripts/sync_vectors.py` | refreshes the vectors copy from the canon |
| `.github/workflows/ci.yml` | CI: checks on Python 3.10–3.14, nightly property job |

## Test vectors

The protocol canon lives in
[cantcp-spec](https://github.com/burn-lab-dev/cantcp-spec). The Python
repository keeps a byte-for-byte copy in `tests/vectors.json` with its SHA-256
in `tests/vectors.sha256`, and `tests/test_vectors.py` replays the whole file
(streams, raw frames, field values, counters and errors). The CI fails when
the copy diverges from the canon.

Refresh the copy from the sibling `cantcp-spec` checkout or from GitHub:

```bash
uv run python scripts/sync_vectors.py                 # ../cantcp-spec by default
uv run python scripts/sync_vectors.py --url URL       # raw canon from GitHub
uv run python scripts/sync_vectors.py --check         # fail on a difference
```

When the canon changes, update the Go vectors first, then run the script and
commit the refreshed copy together with the code changes. Exit codes: `0` in
sync, `1` drift in `--check` mode, `2` source or canon error.

## Go ↔ Python API map

| cantcp-lib-go | cantcp-lib-python |
|---|---|
| `New(opts ...option)` | `Parser(**options)` |
| `WithMagic`, `WithCRCPoly`, `WithCRCCoverFrameOnly`, `WithBadFramePolicy`, `WithLogger`, `WithLogLevel` | constructor keywords `magic`, `crc_poly`, `crc_cover`, `bad_frame_policy`, `logger`, `log_level` |
| `Parser.Split(data, atEOF) (advance, token, err)` | `Parser.split(data, at_eof) -> (advance, token)`, errors are raised |
| `Parser.Encode(dst, frame)` | `Parser.encode(frame) -> bytes` |
| `Parser.Stats`, `ResetStats` | `Parser.stats`, `reset_stats()` |
| `NewDecoder(r)`, `Decode`, `DecodeFrame`, `DecodeFrameInto`, `Stats`, `ResetStats` | `Decoder(r)`, `decode()`, `decode_frame()`, iteration; `decode()` returns `None` at EOF, errors are raised and sticky |
| `NewEncoder(w)`, `Encode`, `EncodeFrame` | `Encoder(w)`, `encode()`, `encode_frame()` |
| `Frame{ID, Type, EFF, RTR, ERR, BRS, ESI, Data}` | `Frame(id=..., type=..., eff=..., rtr=..., err=..., brs=..., esi=..., data=...)` |
| `Frame.UnmarshalBinary` | `Frame.from_raw` |
| `Frame.MarshalBinary` | `Frame.to_raw` |
| `Frame.SetFlags` | `Frame.set_flags` |
| `Frame.GetRaw` | `Frame.raw` |
| `Frame.String` | `Frame.__str__` |
| `ValidateRaw` | `validate_raw` |
| `TypeClassic`, `TypeFd` | `Type.CLASSIC`, `Type.FD` |
| `Flag*` constants | `Flag` members |
| `BadFrameSkip`, `BadFrameFail` | `BadFramePolicy.SKIP`, `BadFramePolicy.FAIL` |
| `Stats` fields | the same snake_case fields |
| `LevelTrace` | `TRACE` |
| `Logger` interface | stdlib `logging.Logger` |
| `Err...` sentinels + `errors.Is` | `CantcpError` subclasses + `except` |

Behavior differences, on purpose:

- Python errors are exceptions, not sentinel values; the messages are the same
  strings, so logs of both languages match;
- `Decoder.decode` returns `None` at the end of the stream instead of `io.EOF`;
  a closed stream is an error of the reader and propagates unchanged;
- `Stats` counters never saturate (Python integers are unbounded);
- `Frame.raw` is `None` until a frame was parsed or built, instead of
  returning zero bytes for a partially filled value.

## CI

Every push and pull request runs `ruff format --check`, `ruff check`, `mypy`
and `pytest` on Python 3.10–3.14. The nightly job and manual runs execute the
hypothesis property tests separately.

## License

By contributing you agree that your changes are licensed under the MIT License
(see [LICENSE](LICENSE)).

# Testing

**English** | [Русский](TESTING.ru.md)

Developed by **[BURN-LAB](https://burn-lab.ru)** — embedded software
development: Linux, drivers, CAN and industrial telemetry.

## Unit tests

```sh
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

`pytest` enforces **100% line and branch coverage** (`fail_under=100`); the
property tests (`hypothesis`) live in `tests/test_properties.py` and run in
the nightly CI.

## Test vectors and the canon

The protocol canon lives in
[cantcp-spec](https://github.com/burn-lab-dev/cantcp-spec); this repository
keeps a synced copy in `tests/vectors.json` with `tests/vectors.sha256` and
checks it in CI:

```sh
uv run python scripts/sync_vectors.py --check
uv run python scripts/sync_vectors.py --check --url https://raw.githubusercontent.com/burn-lab-dev/cantcp-spec/main/vectors.json
(cd tests && sha256sum -c vectors.sha256)
```

## End-to-end against the daemon

The library does not open sockets; `examples/client.py` does — it is a full
listen/send client for the `cantcpd` daemon, plain or TLS/mTLS. The bus (a
virtual CAN interface) and the daemon come from the
[cantcp](https://github.com/burn-lab-dev/cantcp) repository:

```sh
# in ../cantcp: build the daemon and start a virtual bus (see its TESTING.md)
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set vcan0 mtu 72 && sudo ip link set up vcan0
../cantcp/bin/cantcpd --can vcan0 &

# here: watch the frames and send one through the same daemon
uv run python examples/client.py listen --count 5
uv run python examples/client.py send --id 123 --data 11223344
```

`scripts/vcan-smoke.sh` in the daemon repository runs this interop check
automatically when this checkout has a virtualenv next to it.

Stream note: the codec works with binary streams. A socket must be wrapped
with `socket.makefile("rb", buffering=0)` for reading (a buffered reader
blocks until the requested size is filled) and `socket.makefile("wb")` for
writing, with an explicit flush.

## CI

| Job | What it runs |
|---|---|
| `test` | ruff, mypy, pytest on Python 3.10–3.14 |
| `canon` | the vectors copy against `cantcp-spec` + the local checksum |
| `properties` | the hypothesis property tests, nightly |

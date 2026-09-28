# Тестирование

[English](TESTING.md) | **Русский**

Разрабатывается **[BURN-LAB](https://burn-lab.ru)** — встраиваемый Linux:
драйверы, CAN и промышленная телеметрия.

## Юнит-тесты

```sh
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

`pytest` требует **покрытие 100% по строкам и ветвям**
(`fail_under=100`); property-тесты (`hypothesis`) лежат в
`tests/test_properties.py` и идут в ночном CI.

## Тестовые векторы и канон

Канон протокола живёт в
[cantcp-spec](https://github.com/burn-lab-dev/cantcp-spec); этот репозиторий
держит синхронизированную копию в `tests/vectors.json` с
`tests/vectors.sha256` и сверяет её в CI:

```sh
uv run python scripts/sync_vectors.py --check
uv run python scripts/sync_vectors.py --check --url https://raw.githubusercontent.com/burn-lab-dev/cantcp-spec/main/vectors.json
(cd tests && sha256sum -c vectors.sha256)
```

## End-to-end с демоном

Библиотека сокеты не открывает; `examples/client.py` открывает — это полный
клиент listen/send для демона `cantcpd`, в plain- и TLS/mTLS-режимах. Шина
(виртуальный интерфейс CAN) и демон — из репозитория
[cantcp](https://github.com/burn-lab-dev/cantcp):

```sh
# в ../cantcp: собрать демон и поднять виртуальную шину (см. его TESTING.ru.md)
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set vcan0 mtu 72 && sudo ip link set up vcan0
../cantcp/bin/cantcpd --can vcan0 &

# здесь: смотреть кадры и отправить один через тот же демон
uv run python examples/client.py listen --count 5
uv run python examples/client.py send --id 123 --data 11223344
```

`scripts/vcan-smoke.sh` в репозитории демона прогоняет эту interop-проверку
автоматически, когда рядом с чекаутом есть виртуальное окружение.

Замечание о потоках: кодек работает с бинарными потоками. Сокет нужно
оборачивать через `socket.makefile("rb", buffering=0)` для чтения
(буферизованный reader ждёт заполнения запрошенного размера) и
`socket.makefile("wb")` для записи, с явным flush.

## CI

| Джоба | Что запускает |
|---|---|
| `test` | ruff, mypy, pytest на Python 3.10–3.14 |
| `canon` | копию векторов против `cantcp-spec` + локальную контрольную сумму |
| `properties` | property-тесты hypothesis, ночью |

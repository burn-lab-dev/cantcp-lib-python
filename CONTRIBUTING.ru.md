# Участие в разработке

Этот документ — для мейнтейнеров и контрибьюторов: команды разработки, общие
тестовые векторы и карта API Go ↔ Python. Пользователям читать
[README.ru.md](README.ru.md).

Документация на английском: [CONTRIBUTING.md](CONTRIBUTING.md).

## Требования

- Python 3.10 или новее;
- [uv](https://docs.astral.sh/uv/) для окружения и зависимостей.

Рантайм пакета — только стандартная библиотека; внешние зависимости живут в
dev-группе.

## Установка и проверки

```bash
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

Форматирование на месте — `uv run ruff format .`. `mypy` работает в strict-
режиме по `src`, `tests` и `scripts`. `pytest` гоняет модульные тесты,
doctest из `src/cantcp` и property-тесты hypothesis; **требуется 100% покрытие
line и branch** (`fail_under = 100` в `pyproject.toml`).

## Структура

| Путь | Содержимое |
|---|---|
| `src/cantcp/` | пакет: один объект — один модуль, маркер `py.typed` |
| `tests/` | тесты, `helpers.py` со сборщиками сырых фреймов, копия векторов |
| `scripts/sync_vectors.py` | обновляет копию векторов из канона |
| `.github/workflows/ci.yml` | CI: проверки на Python 3.10–3.14, ночной property-джоб |

## Тестовые векторы

Канон протокола лежит в репозитории
[cantcp-spec](https://github.com/burn-lab-dev/cantcp-spec). Python-репозиторий
хранит побайтовую копию в `tests/vectors.json` с SHA-256 в
`tests/vectors.sha256`, а `tests/test_vectors.py` реплеит весь файл (потоки,
сырые фреймы, значения полей, счётчики и ошибки). CI падает, когда копия
расходится с каноном.

Обновление копии из соседнего `cantcp-spec` или с GitHub:

```bash
uv run python scripts/sync_vectors.py                 # по умолчанию ../cantcp-spec
uv run python scripts/sync_vectors.py --url URL       # сырой канон с GitHub
uv run python scripts/sync_vectors.py --check         # ошибка при расхождении
```

При изменении канона сначала обновите векторы в Go-репозитории, затем
прогоните скрипт и закоммитьте обновлённую копию вместе с изменениями кода.
Exit-коды: `0` — синхронно, `1` — расхождение в режиме `--check`, `2` — ошибка
источника или канона.

## Карта API Go ↔ Python

| cantcp-lib-go | cantcp-lib-python |
|---|---|
| `New(opts ...option)` | `Parser(**options)` |
| `WithMagic`, `WithCRCPoly`, `WithCRCCoverFrameOnly`, `WithBadFramePolicy`, `WithLogger`, `WithLogLevel` | ключевые аргументы `magic`, `crc_poly`, `crc_cover`, `bad_frame_policy`, `logger`, `log_level` |
| `Parser.Split(data, atEOF) (advance, token, err)` | `Parser.split(data, at_eof) -> (advance, token)`, ошибки возбуждаются |
| `Parser.Encode(dst, frame)` | `Parser.encode(frame) -> bytes` |
| `Parser.Stats`, `ResetStats` | `Parser.stats`, `reset_stats()` |
| `NewDecoder(r)`, `Decode`, `DecodeFrame`, `DecodeFrameInto`, `Stats`, `ResetStats` | `Decoder(r)`, `decode()`, `decode_frame()`, итерация; `decode()` возвращает `None` в конце, ошибки возбуждаются и залипают |
| `NewEncoder(w)`, `Encode`, `EncodeFrame` | `Encoder(w)`, `encode()`, `encode_frame()` |
| `Frame{ID, Type, EFF, RTR, ERR, BRS, ESI, Data}` | `Frame(id=..., type=..., eff=..., rtr=..., err=..., brs=..., esi=..., data=...)` |
| `Frame.UnmarshalBinary` | `Frame.from_raw` |
| `Frame.MarshalBinary` | `Frame.to_raw` |
| `Frame.SetFlags` | `Frame.set_flags` |
| `Frame.GetRaw` | `Frame.raw` |
| `Frame.String` | `Frame.__str__` |
| `ValidateRaw` | `validate_raw` |
| `TypeClassic`, `TypeFd` | `Type.CLASSIC`, `Type.FD` |
| константы `Flag*` | члены `Flag` |
| `BadFrameSkip`, `BadFrameFail` | `BadFramePolicy.SKIP`, `BadFramePolicy.FAIL` |
| поля `Stats` | те же поля в snake_case |
| `LevelTrace` | `TRACE` |
| интерфейс `Logger` | стандартный `logging.Logger` |
| sentinel'ы `Err...` + `errors.Is` | наследники `CantcpError` + `except` |

Отличия в поведении — намеренные:

- ошибки в Python — исключения, а не sentinel-значения; тексты сообщений
  одинаковые, поэтому логи обеих реализаций совпадают;
- `Decoder.decode` возвращает `None` в конце потока вместо `io.EOF`; закрытый
  поток — ошибка читателя и передаётся без изменений;
- счётчики `Stats` не насыщаются (целые в Python неограниченны);
- `Frame.raw` равен `None`, пока фрейм не разобран или не собран, вместо
  нулевых байт для частично заполненного значения.

## CI

Каждый push и pull request прогоняет `ruff format --check`, `ruff check`,
`mypy` и `pytest` на Python 3.10–3.14. Ночной джоб и ручные запуски отдельно
выполняют property-тесты hypothesis.

## Лицензия

Отправляя изменения, вы соглашаетесь, что они распространяются под лицензией
MIT (см. [LICENSE](LICENSE)).

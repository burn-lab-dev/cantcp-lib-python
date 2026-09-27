# cantcp-lib-python

[![CI](https://github.com/burn-lab-dev/cantcp-lib-python/actions/workflows/ci.yml/badge.svg)](https://github.com/burn-lab-dev/cantcp-lib-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cantcp.svg)](https://pypi.org/project/cantcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/cantcp.svg)](https://pypi.org/project/cantcp/)

Python-библиотека протокола **cantcp**: упаковка и распаковка фреймов Linux
SocketCAN, потоковая разметка с CRC-8, плюс модель разобранного CAN / CAN FD
фрейма.

> **Статус: WIP.** API не стабилизирован, протокол в разработке (`v0`).

Документация на английском: [README.md](README.md). Безопасность:
[SECURITY.ru.md](SECURITY.ru.md).

Разрабатывается в **[BURN-LAB](https://burn-lab.ru)** — разработка
встраиваемого ПО: Linux, драйверы, CAN и промышленная телеметрия.

## Что входит в пакет

Пакет гоняет только кадры CAN: потоковая разметка, разбор кадра и кодек.
Соединение — обычный TCP: handshake, подписки, keepalive, статистика и health
не входят в протокол. Сервер отдаёт их по своему API (например, HTTP), а
клиенты забирают по необходимости.

Пакет зависит только от стандартной библиотеки. Канон протокола и общие
побайтовые тестовые векторы — с Go-реализацией
([cantcp-lib-go](https://github.com/burn-lab-dev/cantcp-lib-go)).

## Потоковая разметка

Пакет в потоке байт:

```
[magic 2 байта][type 1 байт][can_frame 16 | canfd_frame 72][CRC-8 1 байт]
```

Байт типа пакета выбирает раскладку фрейма:

| Значение | Константа | Фрейм | Размер |
|---|---|---|---|
| `0x01` | `Type.CLASSIC` | `struct can_frame` | 16 |
| `0x02` | `Type.FD` | `struct canfd_frame` | 72 |

Classic-фрейм (`can_frame`):

| Смещение | Размер | Поле |
|---|---|---|
| 0 | 4 | `can_id` (little-endian) |
| 4 | 1 | `can_dlc` |
| 5 | 1 | `__pad` (должен быть нулём) |
| 6 | 1 | `__res0` (должен быть нулём) |
| 7 | 1 | `__res1` (должен быть нулём) |
| 8 | 8 | `data` |

CAN FD фрейм (`canfd_frame`):

| Смещение | Размер | Поле |
|---|---|---|
| 0 | 4 | `can_id` (little-endian) |
| 4 | 1 | `len` |
| 5 | 1 | `flags` (`BRS` 0x01, `ESI` 0x02) |
| 6 | 1 | `__res0` (должен быть нулём) |
| 7 | 1 | `__res1` (должен быть нулём) |
| 8 | 64 | `data` |

Зарезервированные байты участвуют в CRC: отправитель обязан писать туда
нули. По умолчанию CRC-8 (полином `0x07`, SMBus) покрывает
`magic+type+frame`; `CrcCover.FRAME` — только сырой фрейм.

`Parser.split` возвращает сырой фрейм как токен: 16 байт для classic CAN,
72 байта для CAN FD. Каждый возвращённый объект — новый `bytes`, независимый
от входного буфера. `Parser.encode` собирает пакет и выбирает тип по длине
фрейма: 16 байт — classic-пакет, 72 байта — CAN FD.

## Быстрый старт

Чтение декодером:

```python
import socket

import cantcp

HOST, PORT = "192.168.1.10", 29536  # порт шлюза cantcp по умолчанию

with socket.create_connection((HOST, PORT)) as conn:
    decoder = cantcp.Decoder(conn.makefile("rb"))
    try:
        for frame in decoder:
            print(frame)  # Frame{Type:CAN FD, ID:0x123, Flags:BRS, Len:2, Data:0102}
    except cantcp.TruncatedError as exc:
        print("decode:", exc)  # обрубок пакета в потоке
    except OSError as exc:
        print("stream:", exc)  # участник закрыл соединение или сбой сети
    print(f"skipped={decoder.stats.skipped} dropped={decoder.stats.dropped}")
```

Запись энкодером:

```python
with socket.create_connection((HOST, PORT)) as conn:
    writer = conn.makefile("wb")
    encoder = cantcp.Encoder(writer)
    frame = cantcp.Frame(type=cantcp.Type.CLASSIC, id=0x123, data=b"\xde\xad")
    encoder.encode_frame(frame)
    writer.flush()
```

Сокет оборачивается через `socket.makefile("rb")` для чтения и
`socket.makefile("wb")` для записи; подойдёт любой бинарный поток с
`read(size)` и `write(data)`.

Низкоуровневые `Parser.split` / `Parser.encode` остаются доступны для
собственных читателей и писателей; см. справочник API ниже.

## Установка

```bash
pip install cantcp
```

Из исходников по тегу:

```bash
pip install "cantcp @ git+https://github.com/burn-lab-dev/cantcp-lib-python@v0.1.0"
```

# Справочник API

API пакета состоит из трёх видов объектов и обычных функций:

- `Parser` — **парсер**: создаётся конструктором и настраивается ключевыми
  аргументами, используется через свои методы;
- `Decoder` и `Encoder` оборачивают парсер в API бинарного потока:
  создаются конструктором и настраиваются теми же аргументами;
- `Frame` — объект разобранного фрейма; `Type`, `Flag`, `Stats`,
  `BadFramePolicy`, `CrcCover`, `TRACE` и наследники `CantcpError`
  дополняют поверхность;
- обычные функции: `validate_raw`.

## `Parser` — парсер

```python
cantcp.Parser(*, magic=b"\xc3\x3c", crc_poly=0x07, crc_cover=CrcCover.HEADER,
              bad_frame_policy=BadFramePolicy.SKIP, logger=None, log_level=logging.INFO)
```

Разбирает поток байт из пакетов; хранит собственную конфигурацию, свою
таблицу CRC-8 и счётчики. Не безопасен для конкурентного использования: один
парсер на поток. `magic` — ровно два байта, `crc_poly` — один байт, иначе
`ValueError`.

По умолчанию: magic `C3 3C`, полином CRC-8 `0x07` с покрытием
`magic+type+frame`, `BadFramePolicy.SKIP`, логирование выключено.

```python
parser = cantcp.Parser(log_level=cantcp.TRACE)
packet = parser.encode(bytes(16))
advance, raw = parser.split(packet, at_eof=True)  # 20, 16 сырых байт
```

### Настройки парсера

Ключевые аргументы ниже настраивают `Parser`; те же аргументы настраивают
`Decoder` и `Encoder`, поэтому пакет, записанный с одним набором опций,
всегда принимается читателем с тем же набором.

| Аргумент | По умолчанию | Описание |
|---|---|---|
| `magic` | `b"\xc3\x3c"` | Двухбайтовый заголовок пакета |
| `crc_poly` | `0x07` (SMBus) | Полином CRC-8 |
| `crc_cover` | `CrcCover.HEADER` | CRC покрывает `magic+type+frame` или только фрейм |
| `bad_frame_policy` | `BadFramePolicy.SKIP` | Реакция на невалидный пакет |
| `logger` | `None` | Любой `logging.Logger`; `None` выключает логирование |
| `log_level` | `logging.INFO` | Минимальный уровень; `TRACE` включает трассировку кадров |

#### `magic`

Двухбайтовый заголовок пакета вместо дефолтного `C3 3C`. Magic всегда ровно
два байта.

```python
parser = cantcp.Parser(magic=b"\x11\x22")
packet = parser.encode(bytes(16))
print(packet[:2].hex())  # 1122
```

#### `crc_poly`

Полином CRC-8 (по умолчанию `0x07`); таблица пересобирается для каждого
парсера.

```python
parser = cantcp.Parser(crc_poly=0x1D)
advance, raw = parser.split(parser.encode(bytes(16)), at_eof=True)
print(advance, len(raw))  # 20 16
```

#### `crc_cover`

Заставляет CRC покрывать только сырой фрейм (`CrcCover.FRAME`) вместо
`magic+type+frame` (по умолчанию `CrcCover.HEADER`).

```python
parser = cantcp.Parser(crc_cover=cantcp.CrcCover.FRAME)
advance, raw = parser.split(parser.encode(bytes(72)), at_eof=True)
print(advance, len(raw))  # 76 72
```

#### `bad_frame_policy`

Выбирает, как `Parser.split` реагирует на неизвестный байт типа пакета или
плохое поле длины (`can_dlc > 8`, `canfd len > 64`); см. `BadFramePolicy`.

```python
parser = cantcp.Parser(bad_frame_policy=cantcp.BadFramePolicy.FAIL)
try:
    parser.split(b"\xc3\x3c\x7f", at_eof=False)
except cantcp.BadTypeError as exc:
    print(exc)  # cantcp: unknown frame type
```

#### `logger`

Задаёт логгер, любой `logging.Logger`. `None` (по умолчанию) полностью
выключает логирование.

```python
import logging

parser = cantcp.Parser(logger=logging.getLogger("cantcp"))
```

#### `log_level`

Минимальный уровень логирования (по умолчанию `logging.INFO`). `TRACE`
включает трассировку каждого разобранного кадра, пропуска мусора, несовпадения
CRC и отклонённого типа пакета.

> **Внимание:** `TRACE` пишет в лог полный hex сырого кадра, **включая
> данные (payload)** — телеметрию и команды с техники. Это чувствительные
> данные: трассировка предназначена только для отладки на изолированном
> стенде. Не включайте `TRACE` в проде и считайте такие логи чувствительными.

```python
parser = cantcp.Parser(logger=logging.getLogger("cantcp"), log_level=logging.WARNING)
# трассировка кадров выключена, пишутся только предупреждения
```

### Методы парсера

#### `split`

```python
split(data: bytes, at_eof: bool) -> tuple[int, bytes | None]
```

Отделяет следующий сырой фрейм от `data`. Возвращает `(advance, token)`:
потребить `advance` байт и, если `token` не `None`, один сырой фрейм
(16 байт classic, 72 байта CAN FD). `(0, None)` — нужно больше данных; в конце
потока передайте `at_eof=True`, чтобы сбросить буфер.

Мусор отбрасывается, при несовпадении CRC выполняется ресинк на байт вперёд, а
структурно невалидный пакет подчиняется `bad_frame_policy`: при
`BadFramePolicy.SKIP` он учитывается и отбрасывается, при
`BadFramePolicy.FAIL` возбуждается `BadTypeError`, `BadDLCError` или
`BadLenError`. Обрубок пакета в конце потока возбуждает `TruncatedError`.

```python
parser = cantcp.Parser()
packet = parser.encode(bytes(16))
advance, raw = parser.split(packet, at_eof=True)
print(advance, len(raw))  # 20 16
```

Для целых потоков используйте `Decoder` — он оборачивает `split` в API
бинарного потока.

#### `encode`

```python
encode(frame: bytes) -> bytes
```

Собирает пакет с сырым `frame`. Длина фрейма выбирает тип пакета: 16 байт —
classic-пакет, 72 байта — CAN FD. CRC-8 и его покрытие берутся из
конфигурации парсера, поэтому пакет из `encode` всегда принимается `split`
парсера с теми же опциями.

Другая длина — `FrameLenError`, `can_dlc > 8` — `BadDLCError`, длина CAN FD
больше 64 — `BadLenError`.

```python
parser = cantcp.Parser()
frame = cantcp.Frame(type=cantcp.Type.FD, id=0x123, brs=True, data=b"\x01\x02")
packet = parser.encode(frame.to_raw())
print(len(packet))  # 76
```

#### `stats`, `reset_stats`

`stats` возвращает копию счётчиков с последнего сброса, `reset_stats()`
обнуляет их. Поля счётчиков — в разделе `Stats`.

```python
parser = cantcp.Parser()
parser.split(b"\x01\x02", at_eof=False)
print("skipped:", parser.stats.skipped)  # skipped: 2
parser.reset_stats()
print("after reset:", parser.stats.skipped)  # after reset: 0
```

## `Decoder` — декодер

```python
cantcp.Decoder(reader, **parser_options)
```

Читает пакеты из бинарного потока. Мусор и пакеты, отклонённые CRC,
отбрасываются, счётчики собираются, каждый вызов возвращает сырой фрейм или
разобранный `Frame`. Поток принадлежит вызывающему: декодер его не закрывает.
Не безопасен для конкурентного использования: один декодер на поток.

```python
decoder = cantcp.Decoder(conn.makefile("rb"), logger=logging.getLogger("cantcp"))
```

### Методы декодера

#### `decode`

```python
decode() -> bytes | None
```

Возвращает следующий сырой фрейм: 16 байт для classic CAN, 72 байта для
CAN FD. `None` означает конец потока. Возвращённые байты независимы от буфера
декодера и живут после следующего вызова.

Обрубок пакета возбуждает `TruncatedError`; ошибки потока передаются без
изменений, поэтому закрытое соединение приходит как `OSError`. После
терминальной ошибки каждый вызов возбуждает ту же ошибку — как исчерпанный
сканер.

```python
decoder = cantcp.Decoder(conn.makefile("rb"))
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

Возвращает следующий фрейм, разобранный в `Frame`; `None` означает конец
потока. Возвращённый фрейм независим от декодера: он хранит свой сырой фрейм,
поэтому `data` живёт после следующего вызова.

Разбор так же строг, как `Frame.from_raw`: длина CAN FD, не кодируемая
4-битным DLC, возбуждает `BadLenError`, хотя толерантный сплиттер пакет
принял. Ошибки `decode` действуют без изменений.

```python
decoder = cantcp.Decoder(conn.makefile("rb"))
while (frame := decoder.decode_frame()) is not None:
    use(frame)
```

#### Итерация

Декодер итерируем и отдаёт разобранные фреймы; итерация заканчивается в конце
потока.

```python
for frame in cantcp.Decoder(conn.makefile("rb")):
    use(frame)
```

#### `stats`, `reset_stats`

`stats` возвращает копию счётчиков потока, `reset_stats()` обнуляет их. Поля
счётчиков — в разделе `Stats`.

```python
decoder = cantcp.Decoder(conn.makefile("rb"))
if (frame := decoder.decode_frame()) is None:
    print("stream closed")
else:
    use(frame)
print("skipped:", decoder.stats.skipped)
decoder.reset_stats()
print("after reset:", decoder.stats.skipped)
```

## `Encoder` — энкодер

```python
cantcp.Encoder(writer, **parser_options)
```

Пишет пакеты в бинарный поток. Энкодер оборачивает `Parser.encode`: длина
фрейма выбирает тип пакета, CRC-8 и его покрытие берутся из конфигурации
парсера, поэтому пакет из энкодера всегда принимается декодером с теми же
опциями. `bad_frame_policy`, `logger` и `log_level` принимаются для симметрии
с читателем и на запись не влияют. Поток принадлежит вызывающему: энкодер его
не закрывает.

```python
writer = conn.makefile("wb")
encoder = cantcp.Encoder(writer)
```

### Методы энкодера

#### `encode`

```python
encode(frame: bytes) -> None
```

Пишет пакет с сырым фреймом: 16 байт — classic-пакет, 72 байта — CAN FD.
Ошибки валидации `Parser.encode` (`FrameLenError`, `BadDLCError`,
`BadLenError`) не трогают поток.

Запись, сохранившая меньше байт, чем запрошено, возбуждает
`ShortWriteError`; ошибка записи передаётся без изменений и оставляет поток в
неизвестном состоянии.

```python
raw = bytes(16)  # struct can_frame
encoder.encode(raw)
writer.flush()
```

#### `encode_frame`

```python
encode_frame(frame: Frame) -> None
```

Собирает `frame` через `Frame.to_raw` и пишет пакет. Ошибки сборки
(`BadTypeError`, `BadIDError`, `BadFlagsError`, `BadDLCError`,
`BadLenError`) не трогают поток.

```python
frame = cantcp.Frame(type=cantcp.Type.FD, id=0x123, brs=True, data=b"\x01\x02")
encoder.encode_frame(frame)
writer.flush()
```

## `Frame` — объект разобранного фрейма

```python
Frame(id=0, type=None, eff=False, rtr=False, err=False, brs=False, esi=False, data=b"")
```

`Frame` — разобранный CAN или CAN FD фрейм, независимый от потоковой разметки
cantcp: `from_raw` и `to_raw` работают только с сырыми раскладками Linux
SocketCAN (struct can_frame, 16 байт, и struct canfd_frame, 72 байта).

Публичные поля:

| Поле | Тип | Значение |
|---|---|---|
| `id` | `int` | Идентификатор: 11-битный стандартный, 29-битный с `eff`; error-фрейм несёт 29-битную маску класса ошибки |
| `type` | `Type \| None` | `Type.CLASSIC` или `Type.FD`; выбирает раскладку |
| `eff` | `bool` | Расширенный (29-битный) идентификатор |
| `rtr` | `bool` | Remote transmission request (только classic CAN) |
| `err` | `bool` | Error-фрейм |
| `brs` | `bool` | CAN FD bit rate switch |
| `esi` | `bool` | CAN FD error state indicator |
| `data` | `bytes` | Данные; `len(data)` — поле длины фрейма (`can_dlc` / `len`) |

### `Frame.from_raw`

```python
Frame.from_raw(raw: bytes) -> Frame
```

Разбирает сырой фрейм: 16 байт как `can_frame`, 72 байта как `canfd_frame`,
другая длина — `FrameLenError`. Разбор строгий: `BadDLCError`, `BadLenError`
(длина CAN FD, не кодируемая 4-битным DLC: валидны только
`0..8, 12, 16, 20, 24, 32, 48, 64`), `ReservedError` (ненулевые
pad/reserved), `BadFlagsError` (`rtr` в CAN FD, `eff` или `rtr` с `err`,
чужие биты flags CAN FD), `BadIDError` (идентификатор не влезает в режим
адресации).

Байты области данных за пределами поля длины не входят в `data` и не
сохраняются: `to_raw` пишет туда нули.

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

Собирает сырой фрейм (16 байт для `Type.CLASSIC`, 72 байта для `Type.FD`),
сохраняет его и возвращает. Область данных за пределами `len(data)`
обнуляется.

Ошибки: `BadTypeError` (тип не задан), `BadIDError` (идентификатор не влезает
в режим адресации: 11 бит для стандартного фрейма, 29 с `eff` или в
error-фрейме, никогда не отрицательный), `BadFlagsError` (`brs` и `esi` в
classic CAN, `rtr` в CAN FD, `err` с `eff` или `rtr`), `BadDLCError` и
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

Заменяет все флаги. Набор собирается из констант `Flag`:

```python
frame = cantcp.Frame(type=cantcp.Type.CLASSIC, id=0x123)
frame.set_flags(cantcp.Flag.EFF | cantcp.Flag.RTR)
print(frame)  # Frame{Type:CAN, ID:0x123, Flags:EFF|RTR, DLC:0, Data:}
```

Неизвестные или недопустимые для текущего типа флаги возбуждают
`BadFlagsError`: `BRS` и `ESI` допустимы только для CAN FD, `RTR` недопустим
для CAN FD, а error-фрейм не несёт режима адресации, поэтому `ERR` исключает
`EFF` и `RTR`. Незаданный тип возбуждает `BadTypeError`.

### `Frame.flags`

```python
Frame.flags -> Flag
```

Флаги как набор `Flag`.

```python
frame = cantcp.Frame(type=cantcp.Type.FD, id=0x123, brs=True, esi=True)
print(frame.flags == (cantcp.Flag.BRS | cantcp.Flag.ESI))  # True
```

### `Frame.raw`

```python
Frame.raw -> bytes | None
```

Копия последнего разобранного или собранного сырого фрейма, либо `None`, если
фрейм ещё не разбирался и не собирался.

```python
frame = cantcp.Frame.from_raw(bytes(16))
print(len(frame.raw))  # 16
```

### `Frame.__str__`

`str(frame)` возвращает человекочитаемое однострочное представление в том же
формате, что Go-библиотека:

```python
frame = cantcp.Frame(type=cantcp.Type.CLASSIC, id=0x1ABCDE, eff=True, data=b"\xde\xad")
print(frame)  # Frame{Type:CAN, ID:0x1abcde, Flags:EFF, DLC:2, Data:dead}
```

## `Type`

```python
class Type(IntEnum):
    CLASSIC = 0x01  # struct can_frame, 16 байт
    FD = 0x02  # struct canfd_frame, 72 байта
```

Выбирает раскладку фрейма. Те же значения используются как байт типа пакета в
потоковой разметке. `str(Type.FD)` — `"CAN FD"`, `str(Type.CLASSIC)` —
`"CAN"`; неизвестное значение создать нельзя (`Type(3)` возбуждает
`ValueError`).

```python
print(cantcp.Type.CLASSIC, cantcp.Type.FD)  # CAN CAN FD
```

## Флаги

Константы `Flag` описывают `Frame`; комбинируйте их битовым OR и передавайте
результат в `Frame.set_flags`. `EFF`, `RTR` и `ERR` приходят из слова
идентификатора CAN; `BRS` и `ESI` — из байта flags CAN FD. Значения
внутренние для объекта: `to_raw` и `from_raw` отображают их в сырые битовые
позиции SocketCAN и обратно.

| Константа | Сырой бит | Значение |
|---|---|---|
| `Flag.EFF` | `can_id` 0x80000000 | расширенный (29-битный) идентификатор |
| `Flag.RTR` | `can_id` 0x40000000 | remote transmission request (только classic) |
| `Flag.ERR` | `can_id` 0x20000000 | error-фрейм |
| `Flag.BRS` | `canfd flags` 0x01 | CAN FD bit rate switch |
| `Flag.ESI` | `canfd flags` 0x02 | CAN FD error state indicator |

```python
frame = cantcp.Frame(type=cantcp.Type.FD, id=0x123, brs=True, data=b"\x01\x02")
frame.set_flags(cantcp.Flag.EFF | cantcp.Flag.BRS)
print(frame)  # Frame{Type:CAN FD, ID:0x123, Flags:EFF|BRS, Len:2, Data:0102}
```

## `Stats`

Объект счётчиков, возвращаемый `stats` парсера или декодера. Это снимок:
мутация снимка не меняет счётчики объекта. Целые в Python неограниченны,
поэтому счётчики не насыщаются.

```python
@dataclass(slots=True)
class Stats:
    skipped: int = 0  # байты, отброшенные при ресинхронизации
    dropped: int = 0  # кандидаты, отклонённые CRC
    bad_type: int = 0  # пакеты с неизвестным байтом типа
    bad_dlc: int = 0  # classic-фреймы с can_dlc > 8
    bad_len: int = 0  # CAN FD фреймы с canfd len > 64
    truncated: int = 0  # байты, потерянные на обрубке в конце потока
```

```python
parser = cantcp.Parser()
parser.split(b"\x01\x02", at_eof=False)
stats = parser.stats
print(stats.skipped, stats.dropped)  # 2 0
```

## `BadFramePolicy`, `CrcCover`

`BadFramePolicy` выбирает, как `Parser.split` реагирует на структурно
невалидный пакет; задаётся аргументом `bad_frame_policy`.

```python
class BadFramePolicy(Enum):
    SKIP = "skip"  # отбросить, посчитать и продолжить (по умолчанию)
    FAIL = "fail"  # остановиться с BadTypeError/BadDLCError/BadLenError
```

```python
parser = cantcp.Parser(bad_frame_policy=cantcp.BadFramePolicy.SKIP)
parser.split(b"\xc3\x3c\x7f", at_eof=False)
print(parser.stats.bad_type)  # 1
```

`CrcCover` выбирает байтовый диапазон, покрываемый CRC-8; задаётся
аргументом `crc_cover`.

```python
class CrcCover(Enum):
    HEADER = "magic+type+frame"  # по умолчанию
    FRAME = "frame"  # только сырой фрейм
```

## `Logger`, `TRACE`

Парсер пишет через любой стандартный `logging.Logger`; `None` выключает
логирование. `TRACE` (`5`) — уровень трассировки кадров, ниже
`logging.DEBUG`, поэтому включается отдельно.

> **Внимание:** `TRACE` пишет в лог полный hex сырого кадра, **включая
> данные (payload)** — телеметрию и команды с техники. Это чувствительные
> данные: трассировка предназначена только для отладки на изолированном
> стенде. Не включайте `TRACE` в проде и считайте такие логи чувствительными.

```python
import logging

import cantcp

parser = cantcp.Parser(logger=logging.getLogger("cantcp"), log_level=cantcp.TRACE)
# трассируются каждый разобранный кадр, пропуск мусора, несовпадение CRC и
# отклонённый тип
```

## `validate_raw`

```python
validate_raw(raw: bytes) -> Type
```

Проверяет сырой фрейм без обёртки cantcp и возвращает его тип: 16 байт —
`Type.CLASSIC`, 72 байта — `Type.FD`, другая длина — `FrameLenError`.
Раскладка выбирается только длиной: сырой фрейм SocketCAN не несёт отдельного
маркера CAN FD, тип определяется сокетом, из которого фрейм прочитан.

Правила те же, что у `Frame.from_raw` (общая реализация): `BadIDError`,
`BadDLCError`, `BadLenError`, `BadFlagsError`, `ReservedError`; возбуждается
первая ошибка. Тип выводится из `len(raw)` даже при ошибке, потому что
выбирается по длине.

```python
raw = bytearray(16)
raw[4] = 9  # can_dlc > 8
try:
    cantcp.validate_raw(bytes(raw))
except cantcp.BadDLCError as exc:
    print(exc)  # cantcp: can_dlc > 8
```

## Ошибки

Все ошибки — классы-наследники `CantcpError`; тексты идентичны Go-реализации.
Ловите конкретный класс или базовый.

| Ошибка | Значение |
|---|---|
| `FrameLenError` | длина фрейма не 16 и не 72 байта |
| `BadDLCError` | classic `can_dlc > 8` |
| `BadLenError` | невалидная длина CAN FD (> 64 или не кодируется 4-битным DLC) |
| `BadTypeError` | неизвестный тип пакета/фрейма |
| `BadFlagsError` | флаги недопустимы для типа фрейма |
| `BadIDError` | идентификатор не влезает в режим адресации |
| `ReservedError` | ненулевые зарезервированные байты |
| `TruncatedError` | обрубок пакета в конце потока |
| `ShortWriteError` | запись сохранила меньше байт, чем запрошено |

```python
try:
    cantcp.Frame(type=cantcp.Type.CLASSIC, data=bytes(9)).to_raw()
except cantcp.BadDLCError as exc:
    print(exc)  # cantcp: can_dlc > 8
except cantcp.CantcpError as exc:
    print("protocol error:", exc)
```

## Длины данных CAN FD

Длины данных CAN FD кодируются 4-битным полем DLC по дискретной шкале,
поэтому существуют только следующие длины; любая другая отклоняется с
`BadLenError`. `Parser.split` и `Decoder.decode` остаются толерантными
(`len <= 64`) для сырого pass-through.

| DLC | 0..8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
|---|---|---|---|---|---|---|---|---|
| байт | 0..8 | 12 | 16 | 20 | 24 | 32 | 48 | 64 |

## Безопасность

cantcp — транспорт, а не слой безопасности. Он рассчитан на работу **внутри
доверенного периметра** (закрытого сегмента сети). Аутентификация, шифрование
канала, защита целостности и защита от повторов — не задачи библиотеки: это
ответственность того, кто её применяет — TLS/mTLS, VPN, сегментация сети и
аутентификация сторон на уровне приложения. CRC-8 — проверка целостности
разметки, а не криптографическая целостность; участник, способный писать в
поток, может подделать, изменить или повторить любой кадр. `TRACE` пишет в
лог сырой кадр вместе с payload и не должен включаться в проде.

Модель угроз, замечание про CPU-амплификацию и чек-лист развёртывания — в
[SECURITY.ru.md](SECURITY.ru.md). Английская версия:
[SECURITY.md](SECURITY.md).

## Замечания

- `Parser.split` — самосинхронизирующийся сплиттер: после сбойного кандидата
  ресинхронизация может найти валидный кадр даже внутри его data-области. Это
  осознанное свойство.
- `Parser.encode` только упаковывает переданные байты: он не санирует pad,
  reserved и флаги, а `Frame` — строгая модель. Слои разделены намеренно.
- Каждый срез, возвращённый `split` и `decode`, — новый `bytes`, независимый
  от входного буфера; `Frame` хранит собственный сырой фрейм, поэтому
  `Frame.data` живёт после следующего вызова декодера.
- CRC-8 — проверка целостности разметки, а не криптографическая целостность:
  примерно 1 из 256 случайных кандидатов её проходит.
- `TRACE` пишет в лог сырой кадр вместе с данными (payload): это инструмент
  отладки на изолированном стенде, а не продовый уровень логирования; см.
  [SECURITY.ru.md](SECURITY.ru.md).
- Error-фрейм не несёт режима адресации: `err` вместе с `eff` или `rtr`
  отклоняется с `BadFlagsError`, а его 29-битная маска класса ошибки
  принимается в `id` вместо 11-битного идентификатора. `rtr` — только для
  classic. Идентификатор, не влезающий в режим адресации, — ошибка, а не
  молчаливое маскирование.
- `validate_raw` и `Frame.from_raw` делят одно ядро валидации, поэтому
  принимают и отклоняют ровно одни и те же сырые фреймы; `Parser.split`
  остаётся толерантным и делает только проверки уровня потока.
- `Decoder.decode` возвращает `None` в конце потока; терминальная ошибка
  (обрубок, fail-политика) возбуждается при каждом следующем вызове.
- Счётчики `Stats` не насыщаются (в Go-реализации — насыщение на `MaxInt`).
- `Frame.raw` равен `None`, пока фрейм не разобран или не собран, вместо
  нулевых байт для частично заполненного значения.

## Зависимости

Только стандартная библиотека. Внешних зависимостей нет.

## Лицензия

MIT — см. [LICENSE](LICENSE).

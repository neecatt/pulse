"""Minimal TensorBoard event-file reader: scalar summaries only, no TensorFlow.

An event file is a sequence of TFRecords (``uint64 length, uint32 crc,
bytes data, uint32 crc``), each holding an ``Event`` protobuf. We decode just
the fields we need:

    Event   { double wall_time = 1; int64 step = 2; Summary summary = 5; }
    Summary { repeated Value value = 1; }
    Value   { string tag = 1; float simple_value = 2; TensorProto tensor = 8; }
    TensorProto { DataType dtype = 1; bytes tensor_content = 4;
                  repeated float float_val = 5; repeated double double_val = 6;
                  repeated int32 int_val = 7; repeated int64 int64_val = 10; }

``simple_value`` covers PyTorch/tensorboardX; one-element tensors cover TF2.
Images, histograms and text are multi-element or non-numeric and are skipped.
"""

import struct
from collections.abc import Iterator
from datetime import UTC, datetime

from pulse.metrics.model import ParsedChunk, Point

_HEADER = 12  # uint64 length + uint32 length crc
_FOOTER = 4  # uint32 data crc
_DT_FLOAT, _DT_DOUBLE, _DT_INT32, _DT_INT64 = 1, 2, 3, 9


def parse_tfevents(data: bytes) -> ParsedChunk:
    chunk = ParsedChunk()
    pos = 0
    while pos + _HEADER <= len(data):
        (length,) = struct.unpack_from("<Q", data, pos)
        end = pos + _HEADER + length + _FOOTER
        if end > len(data):
            break  # partial record: wait for the rest
        chunk.points.extend(_event_points(data[pos + _HEADER : pos + _HEADER + length]))
        pos = end
    chunk.consumed = pos
    return chunk


def _event_points(event: bytes) -> list[Point]:
    wall_time: datetime | None = None
    step = 0  # protobuf omits default values, so a missing step means step 0
    summaries: list[bytes] = []
    for field, value in _fields(event):
        if field == 1 and isinstance(value, float):
            wall_time = datetime.fromtimestamp(value, UTC)
        elif field == 2 and isinstance(value, int):
            step = _signed(value)
        elif field == 5 and isinstance(value, bytes):
            summaries.append(value)
    points = []
    for summary in summaries:
        for field, value in _fields(summary):
            if field == 1 and isinstance(value, bytes):
                scalar = _summary_value(value)
                if scalar is not None:
                    points.append(Point(scalar[0], scalar[1], step, wall_time))
    return points


def _summary_value(data: bytes) -> tuple[str, float] | None:
    tag: str | None = None
    number: float | None = None
    for field, value in _fields(data):
        if field == 1 and isinstance(value, bytes):
            tag = value.decode("utf-8", "replace")
        elif field == 2 and isinstance(value, bytes):  # fixed32 float
            (number,) = struct.unpack("<f", value)
        elif field == 8 and isinstance(value, bytes):
            number = _scalar_tensor(value)
    if tag is None or number is None or number != number:  # drop NaN
        return None
    return tag, float(number)


def _scalar_tensor(data: bytes) -> float | None:
    dtype = 0
    values: list[float] = []
    content = b""
    for field, value in _fields(data):
        if field == 1 and isinstance(value, int):
            dtype = value
        elif field == 4 and isinstance(value, bytes):
            content = value
        elif field == 5:
            values.extend(_packed(value, "<f", 4))
        elif field == 6:
            values.extend(_packed(value, "<d", 8))
        elif field in (7, 10):
            values.extend(_signed(v) for v in _packed_varints(value))
    if content:
        fmt = {_DT_FLOAT: "<f", _DT_DOUBLE: "<d", _DT_INT32: "<i", _DT_INT64: "<q"}.get(dtype)
        if fmt is None:
            return None
        size = struct.calcsize(fmt)
        if len(content) % size:
            return None
        values = [v for (v,) in struct.iter_unpack(fmt, content)]
    return float(values[0]) if len(values) == 1 else None


# Protobuf wire format


def _fields(data: bytes) -> Iterator[tuple[int, int | float | bytes]]:
    """Yield (field number, value): varints as int, fixed64 as float (double),
    length-delimited and fixed32 as raw bytes. Stops quietly on malformed input."""
    pos = 0
    try:
        while pos < len(data):
            key, pos = _varint(data, pos)
            field, wire = key >> 3, key & 7
            if wire == 0:
                value, pos = _varint(data, pos)
                yield field, value
            elif wire == 1:
                yield field, struct.unpack_from("<d", data, pos)[0]
                pos += 8
            elif wire == 2:
                length, pos = _varint(data, pos)
                yield field, data[pos : pos + length]
                pos += length
            elif wire == 5:
                yield field, data[pos : pos + 4]
                pos += 4
            else:
                return
    except (IndexError, struct.error):
        return


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _signed(value: int) -> int:
    return value - (1 << 64) if value >= 1 << 63 else value


def _packed(value: int | float | bytes, fmt: str, size: int) -> list[float]:
    # Repeated scalars arrive packed (bytes) or, rarely, one per field.
    if isinstance(value, bytes):
        if len(value) % size:
            return []
        return [v for (v,) in struct.iter_unpack(fmt, value)]
    return [float(value)]


def _packed_varints(value: int | float | bytes) -> list[int]:
    if not isinstance(value, bytes):
        return [int(value)]
    out, pos = [], 0
    while pos < len(value):
        number, pos = _varint(value, pos)
        out.append(number)
    return out

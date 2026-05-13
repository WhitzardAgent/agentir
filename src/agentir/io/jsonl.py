from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import orjson


def read_jsonl(path: Path, *, limit: int | None = None) -> Iterator[dict[str, Any]]:
    count = 0
    with open(path, "rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield orjson.loads(line)
            count += 1
            if limit is not None and count >= limit:
                break


def write_jsonl(path: Path, records: Iterator[dict[str, Any]], *, append: bool = False) -> int:
    mode = "ab" if append else "wb"
    count = 0
    with open(path, mode) as f:
        for record in records:
            f.write(orjson.dumps(record, option=orjson.OPT_APPEND_NEWLINE))
            count += 1
    return count


def write_jsonl_record(f: Any, record: dict[str, Any]) -> None:
    f.write(orjson.dumps(record, option=orjson.OPT_APPEND_NEWLINE))

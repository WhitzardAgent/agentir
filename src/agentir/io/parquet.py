from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


def read_parquet(
    path: Path, *, limit: int | None = None, batch_size: int = 1000
) -> Iterator[dict[str, Any]]:
    pf = pq.ParquetFile(path)
    count = 0
    for batch in pf.iter_batches(batch_size=batch_size):
        for row in batch.to_pylist():
            yield row
            count += 1
            if limit is not None and count >= limit:
                return


def write_parquet(path: Path, records: list[dict[str, Any]], *, batch_size: int = 1000) -> int:
    if not records:
        return 0
    table = pa.Table.from_pylist(records)
    pq.write_table(table, path, row_group_size=batch_size)
    return len(records)

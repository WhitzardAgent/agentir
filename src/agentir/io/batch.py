from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentir.io.jsonl import write_jsonl_record


@dataclass
class BatchConfig:
    """Configuration for batch processing."""

    batch_size: int = 256
    max_errors: int | None = None
    quarantine_path: str | None = None
    halt_on_error: bool = False


@dataclass
class QuarantineRecord:
    """A single record that failed processing, quarantined for inspection."""

    row_index: int
    record_id: str
    error: str
    raw_data: dict[str, Any]
    stage: str


@dataclass
class RecordBatch:
    """A batch of records with positional metadata."""

    records: list[dict[str, Any]]
    batch_index: int
    start_row: int
    end_row: int


def read_jsonl_batched(
    path: Path,
    *,
    batch_size: int = 256,
    limit: int | None = None,
) -> Iterator[RecordBatch]:
    """Read a JSONL file and yield RecordBatch instances.

    Reads records via `read_jsonl` and aggregates them into batches of
    `batch_size`.  Each yielded RecordBatch carries a zero-based batch
    index as well as the inclusive start and exclusive end row numbers.
    """
    from agentir.io.jsonl import read_jsonl

    batch: list[dict[str, Any]] = []
    start = 0
    idx = 0
    for i, record in enumerate(read_jsonl(path, limit=limit)):
        batch.append(record)
        if len(batch) >= batch_size:
            yield RecordBatch(
                records=batch,
                batch_index=idx,
                start_row=start,
                end_row=i + 1,
            )
            idx += 1
            batch = []
            start = i + 1

    if batch:
        yield RecordBatch(
            records=batch,
            batch_index=idx,
            start_row=start,
            end_row=start + len(batch),
        )


class ErrorQuarantine:
    """Collects failed-record metadata and can persist it to disk."""

    def __init__(self) -> None:
        self._records: list[QuarantineRecord] = []

    def add(
        self,
        row_index: int,
        record_id: str,
        error: str,
        raw_data: dict[str, Any],
        *,
        stage: str = "process",
    ) -> None:
        self._records.append(
            QuarantineRecord(
                row_index=row_index,
                record_id=record_id,
                error=error,
                raw_data=raw_data,
                stage=stage,
            )
        )

    def write_to_file(self, path: str | Path) -> int:
        """Write all quarantined records to a JSONL file.

        Returns the number of records written.
        """
        path = Path(path)
        count = 0
        with open(path, "wb") as f:
            for entry in self._records:
                write_jsonl_record(
                    f,
                    {
                        "row_index": entry.row_index,
                        "record_id": entry.record_id,
                        "error": entry.error,
                        "raw_data": entry.raw_data,
                        "stage": entry.stage,
                    },
                )
                count += 1
        return count

    def summary(self) -> dict[str, Any]:
        """Return a summary dict with counts by stage and total.

        Example return:
            {"total_quarantined": 5, "by_stage": {"parse": 3, "process": 2}}
        """
        by_stage: dict[str, int] = {}
        for entry in self._records:
            by_stage[entry.stage] = by_stage.get(entry.stage, 0) + 1
        return {
            "total_quarantined": len(self._records),
            "by_stage": by_stage,
        }

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[QuarantineRecord]:
        return iter(self._records)


def process_with_quarantine(
    records: list[dict[str, Any]],
    processor_fn: Callable[[dict[str, Any], int], Any],
    quarantine: ErrorQuarantine | None = None,
    stage: str = "process",
) -> list[Any]:
    """Call *processor_fn* on each record, catching exceptions.

    Successful results are collected into a list.  Failed records are
    added to *quarantine* (if supplied).  The *stage* label propagates
    into each `QuarantineRecord`.
    """
    if quarantine is None:
        quarantine = ErrorQuarantine()

    results: list[Any] = []
    for idx, rec in enumerate(records):
        try:
            results.append(processor_fn(rec, idx))
        except Exception as exc:
            quarantine.add(
                row_index=idx,
                record_id=rec.get("id", ""),
                error=str(exc),
                raw_data=rec,
                stage=stage,
            )
    return results

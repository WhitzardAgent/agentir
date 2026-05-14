from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from agentir.frontends.base import FrontendContext, FrontendResult
from agentir.io.batch import ErrorQuarantine, RecordBatch


class _ParseRecord(Protocol):
    """Structural protocol for frontends that implement `parse_record`."""

    def parse_record(self, sample: dict[str, Any], ctx: FrontendContext) -> FrontendResult: ...


@dataclass
class StreamingConfig:
    """Configuration for streaming conversion."""

    max_records_in_memory: int = 1000
    prefetch_depth: int = 2
    enable_parallel: bool = False
    max_workers: int = 4


class StreamingConverter:
    """Converts raw records via a frontend in a streaming fashion.

    Yields `FrontendResult` objects one at a time so that memory
    pressure stays bounded.
    """

    def __init__(
        self,
        frontend: _ParseRecord,
        config: StreamingConfig | None = None,
        quarantine: ErrorQuarantine | None = None,
    ) -> None:
        self.frontend = frontend
        self.config = config or StreamingConfig()
        self.quarantine = quarantine or ErrorQuarantine()

    def convert_stream(
        self,
        records: Iterator[dict[str, Any]],
        ctx_builder: FrontendContext | None = None,
    ) -> Iterator[FrontendResult]:
        """Yield one `FrontendResult` per record, quarantining failures."""
        ctx = ctx_builder or FrontendContext()
        for i, rec in enumerate(records):
            ctx = ctx.model_copy(update={"row_index": i})
            try:
                result = self.frontend.parse_record(rec, ctx)
                yield result
            except Exception as exc:
                self.quarantine.add(
                    row_index=i,
                    record_id=rec.get("id", ""),
                    error=str(exc),
                    raw_data=rec,
                    stage="stream",
                )
                # Yield an empty result so the consumer still gets
                # one item per input record.
                yield FrontendResult()

    def convert_batch(
        self,
        batch: RecordBatch,
        ctx_builder: FrontendContext | None = None,
    ) -> list[FrontendResult]:
        """Convert a full batch and collect all results into a list.

        This consumes the iterator in-memory and is useful when the
        caller wants a materialised list instead of a generator.
        """
        base_ctx = ctx_builder or FrontendContext()
        results: list[FrontendResult] = []
        for rec in batch.records:
            idx = batch.start_row + len(results)
            ctx = base_ctx.model_copy(update={"row_index": idx})
            try:
                results.append(self.frontend.parse_record(rec, ctx))
            except Exception as exc:
                self.quarantine.add(
                    row_index=idx,
                    record_id=rec.get("id", ""),
                    error=str(exc),
                    raw_data=rec,
                    stage="batch",
                )
                results.append(FrontendResult())
        return results

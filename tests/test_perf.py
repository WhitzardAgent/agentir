"""Tests for batch processing, quarantine, and streaming I/O."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agentir.io.batch import (
    BatchConfig,
    ErrorQuarantine,
    QuarantineRecord,
    RecordBatch,
    process_with_quarantine,
    read_jsonl_batched,
)
from agentir.io.jsonl import read_jsonl
from agentir.io.streaming import StreamingConfig, StreamingConverter
from agentir.frontends.base import FrontendContext, FrontendResult
from agentir.ir.record import AgentIRRecord
from agentir.ir.base import IRLevel
from agentir.ir.source import SourceRef


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: str, records: list[dict[str, Any]]) -> str:
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


# ---------------------------------------------------------------------------
# read_jsonl_batched
# ---------------------------------------------------------------------------

class TestReadJsonlBatched:
    def test_batching_100_into_30(self):
        """100 records, batch_size=30 -> 4 batches (30+30+30+10)."""
        records = [{"i": i} for i in range(100)]
        path = tempfile.mktemp(suffix=".jsonl")
        _write_jsonl(path, records)

        batches = list(read_jsonl_batched(Path(path), batch_size=30))
        os.unlink(path)

        assert len(batches) == 4
        assert batches[0].batch_index == 0
        assert batches[0].start_row == 0
        assert batches[0].end_row == 30
        assert len(batches[0].records) == 30

        assert batches[1].batch_index == 1
        assert batches[1].start_row == 30
        assert batches[1].end_row == 60
        assert len(batches[1].records) == 30

        assert batches[2].batch_index == 2
        assert batches[2].start_row == 60
        assert batches[2].end_row == 90
        assert len(batches[2].records) == 30

        assert batches[3].batch_index == 3
        assert batches[3].start_row == 90
        assert batches[3].end_row == 100
        assert len(batches[3].records) == 10

        # Verify all records accounted for
        all_records = []
        for b in batches:
            all_records.extend(b.records)
        assert len(all_records) == 100
        assert all_records[0] == {"i": 0}
        assert all_records[99] == {"i": 99}

    def test_exact_divisible(self):
        """batch_size evenly divides total -> no partial batch."""
        records = [{"i": i} for i in range(9)]
        path = tempfile.mktemp(suffix=".jsonl")
        _write_jsonl(path, records)

        batches = list(read_jsonl_batched(Path(path), batch_size=3))
        os.unlink(path)

        assert len(batches) == 3
        for b in batches:
            assert len(b.records) == 3

    def test_limit_respected(self):
        """limit=5 should only produce 5 records total."""
        records = [{"i": i} for i in range(20)]
        path = tempfile.mktemp(suffix=".jsonl")
        _write_jsonl(path, records)

        batches = list(read_jsonl_batched(Path(path), batch_size=30, limit=5))
        os.unlink(path)

        assert len(batches) == 1
        assert len(batches[0].records) == 5


# ---------------------------------------------------------------------------
# ErrorQuarantine
# ---------------------------------------------------------------------------

class TestErrorQuarantine:
    def test_add_and_summary(self):
        q = ErrorQuarantine()
        q.add(0, "id-a", "err1", {"x": 1}, stage="parse")
        q.add(1, "id-b", "err2", {"x": 2}, stage="parse")
        q.add(2, "id-c", "err3", {"x": 3}, stage="process")

        s = q.summary()
        assert s["total_quarantined"] == 3
        assert s["by_stage"] == {"parse": 2, "process": 1}

    def test_len_and_iter(self):
        q = ErrorQuarantine()
        q.add(0, "a", "e", {}, stage="s")
        q.add(1, "b", "e", {}, stage="s")

        assert len(q) == 2
        entries = list(q)
        assert entries[0].record_id == "a"
        assert entries[1].record_id == "b"

    def test_write_to_file(self):
        q = ErrorQuarantine()
        q.add(0, "id-1", "boom", {"raw": True}, stage="test")

        path = tempfile.mktemp(suffix=".jsonl")
        count = q.write_to_file(path)

        assert count == 1
        lines = list(read_jsonl(Path(path)))
        os.unlink(path)

        assert len(lines) == 1
        assert lines[0]["row_index"] == 0
        assert lines[0]["record_id"] == "id-1"
        assert lines[0]["error"] == "boom"
        assert lines[0]["raw_data"] == {"raw": True}
        assert lines[0]["stage"] == "test"


# ---------------------------------------------------------------------------
# process_with_quarantine
# ---------------------------------------------------------------------------

class TestProcessWithQuarantine:
    @staticmethod
    def _raise_every_3rd(rec: dict[str, Any], idx: int) -> dict[str, Any]:
        if idx % 3 == 0:
            raise ValueError(f"fail at {idx}")
        return rec

    def test_successes_and_quarantine(self):
        records = [{"i": i, "id": f"r{i}"} for i in range(9)]
        q = ErrorQuarantine()
        results = process_with_quarantine(records, self._raise_every_3rd, quarantine=q)

        # Indices 0, 3, 6 fail -> 3 in quarantine, 6 in results
        assert len(results) == 6
        assert len(q) == 3

        # Verify successful results
        for r in results:
            assert "i" in r

        # Verify quarantined entries
        quarantined_indices = {er.row_index for er in q}
        assert quarantined_indices == {0, 3, 6}

    def test_accepts_default_quarantine(self):
        records = [{"i": 0, "id": "r0"}]
        results = process_with_quarantine(
            records, lambda rec, idx: f"ok-{rec['i']}"
        )
        assert results == ["ok-0"]

    def test_quarantine_stage_label(self):
        records = [{"i": 0}]
        q = ErrorQuarantine()

        def _fail(_rec: dict[str, Any], _idx: int) -> None:
            raise RuntimeError("oops")

        process_with_quarantine(records, _fail, quarantine=q, stage="testing-stage")
        assert len(q) == 1
        entry = list(q)[0]
        assert entry.stage == "testing-stage"


# ---------------------------------------------------------------------------
# StreamingConverter
# ---------------------------------------------------------------------------

class _MockFrontend:
    """Minimal frontend that returns valid AgentIRRecord instances."""

    def parse_record(self, sample: dict[str, Any], ctx: FrontendContext) -> FrontendResult:
        # Simulate a frontend that fails on row_index=2
        if ctx.row_index == 2:
            raise RuntimeError("mock parse error")
        record = AgentIRRecord(
            record_id=sample.get("id", f"mock-{ctx.row_index}"),
            level=IRLevel.PARSED,
            source=SourceRef(),
        )
        return FrontendResult(record=record)


class TestStreamingConverter:
    def test_convert_stream_yields_results(self):
        fe = _MockFrontend()
        converter = StreamingConverter(fe)
        records = iter([{"n": 0}, {"n": 1}, {"n": 2}, {"n": 3}, {"n": 4}])

        results = list(converter.convert_stream(records))
        assert len(results) == 5

        # Record at row_index 2 fails -> result.record is None
        assert results[0].record is not None
        assert results[0].record.record_id == "mock-0"  # type: ignore[union-attr]
        assert results[1].record is not None
        assert results[1].record.record_id == "mock-1"  # type: ignore[union-attr]
        assert results[2].record is None  # quarantined
        assert results[3].record is not None
        assert results[3].record.record_id == "mock-3"  # type: ignore[union-attr]
        assert results[4].record is not None
        assert results[4].record.record_id == "mock-4"  # type: ignore[union-attr]

        # Check quarantine
        assert len(converter.quarantine) == 1
        entry = list(converter.quarantine)[0]
        assert entry.row_index == 2
        assert entry.stage == "stream"

    def test_convert_batch(self):
        fe = _MockFrontend()
        converter = StreamingConverter(fe)

        batch = RecordBatch(
            records=[{"n": 0}, {"n": 1}, {"n": 2}, {"n": 3}],
            batch_index=2,
            start_row=10,
            end_row=14,
        )

        results = converter.convert_batch(batch)
        assert len(results) == 4

        # The mock frontend is keyed on ctx.row_index == 2, and here
        # row_index starts at 10, so none of the records should fail.
        assert results[0].record is not None
        assert results[1].record is not None
        assert results[2].record is not None
        assert results[3].record is not None

        # No quarantine for convert_batch in this test
        assert len(converter.quarantine) == 0

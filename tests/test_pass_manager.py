"""Tests for the PassManager: validate_order, run_pipeline_batch,
pipeline_stats, print_summary, and PASS_GROUPS.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.base import (
    DiagnosticSeverity,
    IRLevel,
    OutcomeStatus,
)
from agentir.ir.episode import Episode
from agentir.ir.event import Event
from agentir.ir.outcome import Outcome
from agentir.ir.record import AgentIRRecord
from agentir.ir.source import SourceRef
from agentir.ir.visibility import Visibility
from agentir.passes.base import PassContext, PassResult
from agentir.passes.manager import PASS_GROUPS, PassManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_SOURCE = SourceRef(dataset="test", framework="test-framework")


def _record(record_id: str = "r01") -> AgentIRRecord:
    """Minimal record with no episodes."""
    return AgentIRRecord(
        record_id=record_id,
        level=IRLevel.RAW,
        source=_BASE_SOURCE,
        episodes=[],
        raw={},
        metadata={},
        outcome=None,
        artifacts=[],
    )


def _record_with_outcome(
    record_id: str = "r01",
    outcome_status: OutcomeStatus = OutcomeStatus.SUCCESS,
    metadata: dict | None = None,
) -> AgentIRRecord:
    """Minimal record that already has an outcome set."""
    return AgentIRRecord(
        record_id=record_id,
        level=IRLevel.RAW,
        source=_BASE_SOURCE,
        episodes=[],
        raw={},
        metadata=metadata or {},
        outcome=Outcome(status=outcome_status),
        artifacts=[],
    )


# ---------------------------------------------------------------------------
# validate_order
# ---------------------------------------------------------------------------


class TestValidateOrder:

    def test_valid_passes_returned_in_order(self) -> None:
        mgr = PassManager()
        result = mgr.validate_order(["normalize-outcome", "verify"])
        assert result == ["normalize-outcome", "verify"]

    def test_invalid_pass_raises_value_error(self) -> None:
        mgr = PassManager()
        with pytest.raises(ValueError, match="Unknown pass"):
            mgr.validate_order(["normalize-outcome", "not-a-pass"])

    def test_empty_list_returns_empty(self) -> None:
        mgr = PassManager()
        assert mgr.validate_order([]) == []


# ---------------------------------------------------------------------------
# run_pipeline_batch
# ---------------------------------------------------------------------------


class TestRunPipelineBatch:

    def test_batch_returns_one_result_per_record(self) -> None:
        mgr = PassManager()
        records = [
            _record_with_outcome("r01", metadata={"reward": 1.0}),
            _record_with_outcome("r02", metadata={"reward": 0.0}),
        ]
        ctx = PassContext()
        results = mgr.run_pipeline_batch(
            records, ["normalize-outcome", "verify"], ctx
        )
        assert len(results) == 2
        assert all(isinstance(r, PassResult) for r in results)
        assert results[0].record.record_id == "r01"
        assert results[1].record.record_id == "r02"

    def test_batch_empty_records(self) -> None:
        mgr = PassManager()
        results = mgr.run_pipeline_batch([], ["verify"], PassContext())
        assert results == []


# ---------------------------------------------------------------------------
# pipeline_stats
# ---------------------------------------------------------------------------


class TestPipelineStats:

    def _make_pass_result(
        self,
        diag_severities: list[DiagnosticSeverity] | None = None,
        metrics: dict[str, Any] | None = None,
        record_id: str = "r01",
    ) -> PassResult:
        record = _record(record_id)
        diagnostics = []
        for sev in (diag_severities or []):
            diagnostics.append(
                Diagnostic(
                    code="TEST",
                    severity=sev,
                    message="mock",
                )
            )
        return PassResult(
            record=record,
            diagnostics=diagnostics,
            metrics=metrics or {},
        )

    def test_empty_results_returns_count_zero(self) -> None:
        mgr = PassManager()
        stats = mgr.pipeline_stats([])
        assert stats == {"count": 0}

    def test_counts_severity_by_level(self) -> None:
        mgr = PassManager()
        results = [
            self._make_pass_result(
                diag_severities=[
                    DiagnosticSeverity.ERROR,
                    DiagnosticSeverity.WARNING,
                    DiagnosticSeverity.WARNING,
                ],
                record_id="a",
            ),
            self._make_pass_result(
                diag_severities=[DiagnosticSeverity.INFO],
                record_id="b",
            ),
        ]
        stats = mgr.pipeline_stats(results)
        assert stats["count"] == 2
        assert stats["total_diagnostics"] == 4
        sev = stats["severity_counts"]
        assert sev.get("error") == 1
        assert sev.get("warning") == 2
        assert sev.get("info") == 1

    def test_sums_elapsed_metrics(self) -> None:
        mgr = PassManager()
        results = [
            self._make_pass_result(
                metrics={"parse-sharegpt.elapsed_ms": 12.5, "verify.elapsed_ms": 3.0},
                record_id="r01",
            ),
            self._make_pass_result(
                metrics={"parse-sharegpt.elapsed_ms": 7.3, "verify.elapsed_ms": 0.8},
                record_id="r02",
            ),
        ]
        stats = mgr.pipeline_stats(results)
        assert stats["total_elapsed_ms"] == pytest.approx(12.5 + 3.0 + 7.3 + 0.8, rel=0.01)
        avg = stats["avg_metrics"]
        assert "parse-sharegpt.elapsed_ms" in avg
        assert avg["parse-sharegpt.elapsed_ms"] == pytest.approx((12.5 + 7.3) / 2, rel=0.01)

    def test_counts_events_across_records(self) -> None:
        mgr = PassManager()
        e1 = Event(
            event_id="evt-1",
            idx=0,
            event_type="user_message",
            visibility=Visibility(),
        )
        e2 = Event(
            event_id="evt-2",
            idx=1,
            event_type="assistant_message",
            visibility=Visibility(),
        )
        ep = Episode(episode_id="ep-01", events=[e1, e2])
        record = AgentIRRecord(
            record_id="r-evt",
            level=IRLevel.PARSED,
            source=_BASE_SOURCE,
            episodes=[ep],
            raw={},
            metadata={},
            outcome=None,
            artifacts=[],
        )
        results = [PassResult(record=record)]
        stats = mgr.pipeline_stats(results)
        assert stats["total_events"] == 2
        assert stats["total_episodes"] == 1


# ---------------------------------------------------------------------------
# print_summary
# ---------------------------------------------------------------------------


class TestPrintSummary:

    def test_returns_non_empty_string(self) -> None:
        mgr = PassManager()
        record = _record("summary-test")
        diag = Diagnostic(
            code="INFO001",
            severity=DiagnosticSeverity.INFO,
            message="Test diagnostic",
        )
        pr = PassResult(
            record=record,
            diagnostics=[diag],
            metrics={"normalize-outcome.elapsed_ms": 1.5},
        )
        summary = mgr.print_summary([pr])
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "AgentIR Pipeline Summary" in summary
        assert "Records processed" in summary

    def test_empty_results_produces_valid_summary(self) -> None:
        mgr = PassManager()
        summary = mgr.print_summary([])
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "AgentIR Pipeline Summary" in summary


# ---------------------------------------------------------------------------
# PASS_GROUPS
# ---------------------------------------------------------------------------


class TestPassGroups:

    def test_groups_has_expected_keys(self) -> None:
        expected_keys = {"default", "training", "minimal", "full"}
        assert set(PASS_GROUPS.keys()) == expected_keys

    def test_default_group_contains_verify(self) -> None:
        assert "verify" in PASS_GROUPS["default"]

    def test_training_group_contains_redact_reasoning(self) -> None:
        assert "redact-reasoning" in PASS_GROUPS["training"]

    def test_minimal_has_two_passes(self) -> None:
        assert PASS_GROUPS["minimal"] == ["normalize-outcome", "verify"]

    def test_full_is_larger_than_default(self) -> None:
        assert len(PASS_GROUPS["full"]) >= len(PASS_GROUPS["default"])

    def test_all_groups_contain_only_registered_passes(self) -> None:
        """Every pass name in every group must be registered."""
        from agentir.passes.registry import get_pass

        for group_name, pass_list in PASS_GROUPS.items():
            for pass_name in pass_list:
                assert get_pass(pass_name) is not None, (
                    f"Pass '{pass_name}' in group '{group_name}' is not registered"
                )

from __future__ import annotations

import time
from collections import defaultdict

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.base import DiagnosticSeverity
from agentir.ir.record import AgentIRRecord
from agentir.passes.base import PassContext, PassResult
from agentir.passes.registry import get_pass, list_passes

# ---------------------------------------------------------------------------
# Pre-defined pass groups
# ---------------------------------------------------------------------------

# Import all pass modules so that the registry is fully populated before
# we build PASS_GROUPS.  Without these imports the registry may be empty
# when manager.py is the first module loaded.
import agentir.passes.canonicalize_tools  # noqa: E402, F401
import agentir.passes.extract_patches  # noqa: E402, F401
import agentir.passes.normalize_outcome  # noqa: E402, F401
import agentir.passes.pair_tool_results  # noqa: E402, F401
import agentir.passes.parse_claude_log  # noqa: E402, F401
import agentir.passes.parse_hermes_xml  # noqa: E402, F401
import agentir.passes.parse_openhands_tool_calls  # noqa: E402, F401
import agentir.passes.parse_sharegpt  # noqa: E402, F401
import agentir.passes.redact_reasoning  # noqa: E402, F401
import agentir.passes.slice_training  # noqa: E402, F401
import agentir.passes.verify  # noqa: E402, F401

_all_passes = sorted(list_passes())

PASS_GROUPS: dict[str, list[str]] = {
    "default": [
        "parse-sharegpt",
        "canonicalize-tools",
        "pair-tool-results",
        "normalize-outcome",
        "verify",
    ],
    "training": [
        "parse-sharegpt",
        "canonicalize-tools",
        "pair-tool-results",
        "normalize-outcome",
        "redact-reasoning",
        "slice-training",
        "verify",
    ],
    "minimal": ["normalize-outcome", "verify"],
    "full": _all_passes,
}


class PassManager:
    """Orchestrate AgentIR passes over one or more records.

    Supports single-record pipelines, batch processing, validation of pass
    ordering, timing instrumentation, and aggregated statistics.
    """

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_order(self, pass_names: list[str]) -> list[str]:
        """Return the ordered list of passes, validating all exist.

        Raises ``ValueError`` if any pass name is unknown.
        """
        ordered: list[str] = []
        for name in pass_names:
            if get_pass(name) is None:
                raise ValueError(f"Unknown pass: {name}")
            ordered.append(name)
        return ordered

    # ------------------------------------------------------------------
    # Single-record pipeline
    # ------------------------------------------------------------------

    def run_pipeline(
        self, record: AgentIRRecord, passes: list[str], ctx: PassContext
    ) -> PassResult:
        current = record
        all_diagnostics: list[Diagnostic] = []
        all_analysis: dict = {}
        all_metrics: dict = {}

        for pass_name in passes:
            pass_inst = get_pass(pass_name)
            if pass_inst is None:
                raise ValueError(f"Unknown pass: {pass_name}")

            t0 = time.perf_counter()
            result = pass_inst.run(current, ctx)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            all_metrics[f"{pass_name}.elapsed_ms"] = round(elapsed_ms, 3)

            current = result.record
            all_diagnostics.extend(result.diagnostics)
            all_analysis.update(result.analysis)
            all_metrics.update(result.metrics)

        return PassResult(
            record=current,
            diagnostics=all_diagnostics,
            analysis=all_analysis,
            metrics=all_metrics,
        )

    # ------------------------------------------------------------------
    # Batch pipeline
    # ------------------------------------------------------------------

    def run_pipeline_batch(
        self,
        records: list[AgentIRRecord],
        passes: list[str],
        ctx: PassContext,
    ) -> list[PassResult]:
        """Process multiple records through the same pipeline.

        Returns one ``PassResult`` per input record (same order).
        """
        results: list[PassResult] = []
        for record in records:
            results.append(self.run_pipeline(record, passes, ctx))
        return results

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def pipeline_stats(self, results: list[PassResult]) -> dict:
        """Aggregate statistics from multiple PassResults."""
        if not results:
            return {"count": 0}

        severity_counts: dict[str, int] = defaultdict(int)
        total_elapsed_ms = 0.0
        pass_elapsed_sums: dict[str, float] = defaultdict(float)
        total_diagnostics = 0
        total_analysis_keys: set[str] = set()
        total_metric_keys: set[str] = set()
        total_artifacts = 0
        total_events = 0
        total_episodes = 0

        for pr in results:
            for diag in pr.diagnostics:
                severity_counts[diag.severity.value] += 1
                total_diagnostics += 1

            for key, value in pr.metrics.items():
                total_metric_keys.add(key)
                if key.endswith(".elapsed_ms") and isinstance(value, (int, float)):
                    pass_elapsed_sums[key] += value

            for key in pr.analysis:
                total_analysis_keys.add(key)

            total_elapsed_ms += sum(
                v for k, v in pr.metrics.items()
                if k.endswith(".elapsed_ms") and isinstance(v, (int, float))
            )

            total_artifacts += len(pr.record.artifacts)
            for ep in pr.record.episodes:
                total_events += len(ep.events)
                total_episodes += 1

        avg_metrics: dict[str, float] = {}
        n = len(results)
        for key in total_metric_keys:
            values = [pr.metrics.get(key) for pr in results if key in pr.metrics]
            numeric = [v for v in values if isinstance(v, (int, float))]
            if numeric:
                avg_metrics[key] = sum(numeric) / len(numeric)

        return {
            "count": n,
            "total_diagnostics": total_diagnostics,
            "severity_counts": dict(severity_counts),
            "total_elapsed_ms": round(total_elapsed_ms, 3),
            "total_events": total_events,
            "total_episodes": total_episodes,
            "total_artifacts": total_artifacts,
            "avg_metrics": avg_metrics,
            "total_analysis_keys": sorted(total_analysis_keys),
        }

    # ------------------------------------------------------------------
    # Human-readable summary
    # ------------------------------------------------------------------

    def print_summary(self, results: list[PassResult]) -> str:
        """Return a human-readable pipeline run summary string."""
        stats = self.pipeline_stats(results)
        lines: list[str] = []

        lines.append("=" * 60)
        lines.append("  AgentIR Pipeline Summary")
        lines.append("=" * 60)
        lines.append(f"  Records processed : {stats.get('count', 0)}")
        lines.append(f"  Total diagnostics  : {stats.get('total_diagnostics', 0)}")

        sev = stats.get("severity_counts", {})
        if sev:
            for level_name in ("info", "warning", "error", "fatal"):
                cnt = sev.get(level_name, 0)
                if cnt:
                    label = level_name.upper().ljust(8)
                    lines.append(f"    {label}: {cnt}")

        lines.append(f"  Total elapsed (ms) : {stats.get('total_elapsed_ms', 0):.2f}")
        lines.append(f"  Total events       : {stats.get('total_events', 0)}")
        lines.append(f"  Total episodes     : {stats.get('total_episodes', 0)}")
        lines.append(f"  Total artifacts    : {stats.get('total_artifacts', 0)}")

        avg = stats.get("avg_metrics", {})
        if avg:
            lines.append("  -- Average Metrics --")
            for key in sorted(avg):
                lines.append(f"    {key}: {avg[key]:.4f}")

        lines.append("=" * 60)
        return "\n".join(lines)

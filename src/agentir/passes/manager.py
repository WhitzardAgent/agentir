from __future__ import annotations

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.record import AgentIRRecord
from agentir.passes.base import PassContext, PassResult
from agentir.passes.registry import get_pass


class PassManager:
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

            result = pass_inst.run(current, ctx)
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

"""Pass that normalizes rewards and pass/fail markers into Outcome."""

from __future__ import annotations

from typing import Any

from agentir.diagnostics.codes import DiagnosticCodes, make_diagnostic
from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.base import FailureReason, OutcomeStatus, PassKind
from agentir.ir.outcome import Outcome, VerifierResult
from agentir.ir.record import AgentIRRecord
from agentir.passes.base import AgentIRPass, PassContext, PassResult
from agentir.passes.registry import register_pass


class NormalizeOutcomePass(AgentIRPass):
    """Normalize reward signals and pass/fail metadata into a unified Outcome.

    This pass inspects raw metadata from various upstream dataset formats
    (AgentTrove, OpenHands, Codex SWE-bench, Claude Code) and populates the
    canonical ``Outcome`` model on the record.

    Conflict detection:  if *reward* and *passed* disagree (e.g. reward > 0
    but passed=False, or reward <= 0 but passed=True), an ``OUTCOME001``
    diagnostic is emitted and *passed* is treated as authoritative.
    """

    name = "normalize-outcome"
    kind = PassKind.CANONICALIZE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult:
        diagnostics: list[Diagnostic] = []

        # Start from existing outcome or create a fresh one.
        outcome = record.outcome or Outcome()

        # 1. AgentTrove reward ------------------------------------------------
        reward = self._extract_agenttrove_reward(record)
        if reward is not None:
            outcome.reward = reward

        # 2. OpenHands success metadata ---------------------------------------
        oh_passed = self._extract_openhands_passed(record)
        if oh_passed is not None:
            outcome.passed = oh_passed

        # 3. Codex SWE-bench trial stats --------------------------------------
        verifier = self._extract_codex_swebench(record)
        if verifier is not None:
            outcome.verifier = verifier

        # 4. Claude Code has_empty_response -----------------------------------
        failure_reason = self._extract_claude_code_failure(record)
        if failure_reason is not None:
            outcome.failure_reason = failure_reason

        # 5. Conflict detection -----------------------------------------------
        if outcome.reward is not None and outcome.passed is not None:
            if self._reward_passed_conflict(outcome.reward, outcome.passed):
                diag = make_diagnostic(
                    DiagnosticCodes.OUTCOME001,
                    field="outcome",
                    suggestion="passed is treated as authoritative over reward",
                )
                diagnostics.append(diag)

        # 6. Derive status ----------------------------------------------------
        outcome.status = self._derive_status(outcome)

        # Commit the outcome back to the record.
        record.outcome = outcome

        return PassResult(record=record, diagnostics=diagnostics)

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_agenttrove_reward(record: AgentIRRecord) -> float | None:
        """Extract reward from AgentTrove-style metadata."""
        # AgentTrove stores reward at metadata["reward"] or raw["reward"].
        for src in (record.metadata, record.raw):
            val = src.get("reward")
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _extract_openhands_passed(record: AgentIRRecord) -> bool | None:
        """Extract success flag from OpenHands metadata.

        OpenHands typically exposes ``metadata["success"]`` or
        ``raw["test_result"]["passed"]``.
        """
        # metadata.success
        success = record.metadata.get("success")
        if isinstance(success, bool):
            return success

        # raw.test_result.passed
        test_result = record.raw.get("test_result")
        if isinstance(test_result, dict):
            passed = test_result.get("passed")
            if isinstance(passed, bool):
                return passed

        return None

    @staticmethod
    def _extract_codex_swebench(record: AgentIRRecord) -> VerifierResult | None:
        """Extract Codex SWE-bench trial stats into a VerifierResult.

        Codex stores trial information under ``raw["trial"]`` or
        ``metadata["swebench"]`` with fields like ``resolved``,
        ``test_result``, and ``patch_applied``.
        """
        src: dict[str, Any] | None = None
        for candidate in (
            record.raw.get("trial"),
            record.metadata.get("swebench"),
        ):
            if isinstance(candidate, dict):
                src = candidate
                break

        if src is None:
            return None

        resolved = src.get("resolved")
        if resolved is None:
            return None

        command = src.get("command") or src.get("test_command")
        output = src.get("test_output") or src.get("output")

        # Build a score from resolved (True -> 1.0, False -> 0.0) if an
        # explicit numeric score is not provided.
        score = src.get("score")
        if score is None and isinstance(resolved, bool):
            score = 1.0 if resolved else 0.0

        return VerifierResult(
            type="swebench",
            command=str(command) if command is not None else None,
            output=str(output) if output is not None else None,
            passed=bool(resolved),
            score=float(score) if score is not None else None,
            metadata={
                k: v
                for k, v in src.items()
                if k
                not in {"resolved", "command", "test_command", "output", "test_output", "score"}
            },
        )

    @staticmethod
    def _extract_claude_code_failure(record: AgentIRRecord) -> FailureReason | None:
        """Map Claude Code ``has_empty_response`` to FailureReason.EMPTY_RESPONSE."""
        for src in (record.metadata, record.raw):
            val = src.get("has_empty_response")
            if val is True:
                return FailureReason.EMPTY_RESPONSE
        return None

    # ------------------------------------------------------------------
    # Status derivation
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_status(outcome: Outcome) -> OutcomeStatus:
        """Derive OutcomeStatus from the available signals.

        Rules (applied in order):
          - passed=True  -> SUCCESS
          - passed=False -> FAILURE
          - reward is not None and passed is None -> PARTIAL
          - otherwise    -> UNKNOWN

        We do NOT infer success from reward alone unless dataset semantics
        explicitly define a threshold, which is not the case here.
        """
        if outcome.passed is True:
            return OutcomeStatus.SUCCESS
        if outcome.passed is False:
            return OutcomeStatus.FAILURE
        if outcome.reward is not None and outcome.passed is None:
            return OutcomeStatus.PARTIAL
        return OutcomeStatus.UNKNOWN

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    @staticmethod
    def _reward_passed_conflict(reward: float, passed: bool) -> bool:
        """Return True when reward and passed contradict each other.

        A conflict is defined as:
          - reward > 0  but passed=False
          - reward <= 0 but passed=True
        """
        if reward > 0 and not passed:
            return True
        if reward <= 0 and passed:
            return True
        return False


register_pass(NormalizeOutcomePass())

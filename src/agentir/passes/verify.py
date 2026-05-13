"""Verify pass: runs verifier checks on an AgentIR record."""

from __future__ import annotations

from agentir.diagnostics.codes import DiagnosticCodes, make_diagnostic
from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.base import EventType, PassKind
from agentir.ir.record import AgentIRRecord
from agentir.passes.base import AgentIRPass, PassContext, PassResult
from agentir.passes.registry import register_pass


class VerifyPass(AgentIRPass):
    """Pass that verifies structural integrity and consistency of an AgentIR record.

    The pass does NOT modify the record; it only adds diagnostics.
    """

    name = "verify"
    kind = PassKind.VERIFY

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult:
        diagnostics: list[Diagnostic] = []

        artifact_ids = {a.artifact_id for a in record.artifacts}

        for episode in record.episodes:
            self._check_episode(episode, artifact_ids, diagnostics)

        if ctx.strict:
            self._check_strict(record, artifact_ids, diagnostics)

        return PassResult(record=record, diagnostics=diagnostics)

    # ------------------------------------------------------------------
    # Default (always-run) checks
    # ------------------------------------------------------------------

    def _check_episode(
        self,
        episode,
        artifact_ids: set[str],
        diagnostics: list[Diagnostic],
    ) -> None:
        seen_ids: set[str] = set()
        prev_idx: int | None = None

        # Build event-id set for parent validation (pre-scan).
        episode_event_ids = {e.event_id for e in episode.events}

        # Build tool_call_id map for strict-mode pairing (pre-scan).
        tool_call_ids: set[str] = set()
        for event in episode.events:
            if (
                event.event_type == EventType.TOOL_CALL
                and event.action
                and event.action.tool_call_id
            ):
                tool_call_ids.add(event.action.tool_call_id)

        for event in episode.events:
            # --- Unique event IDs ---
            if event.event_id in seen_ids:
                diagnostics.append(
                    make_diagnostic(
                        DiagnosticCodes.VERIFY001,
                        event_id=event.event_id,
                        field="event_id",
                        suggestion="Event IDs must be unique within an episode.",
                    )
                )
            seen_ids.add(event.event_id)

            # --- Monotonic event indices ---
            if prev_idx is not None and event.idx <= prev_idx:
                diagnostics.append(
                    make_diagnostic(
                        DiagnosticCodes.VERIFY001,
                        event_id=event.event_id,
                        field="idx",
                        suggestion=(
                            f"Event index {event.idx} is not monotonic (previous was {prev_idx})."
                        ),
                    )
                )
            prev_idx = event.idx

            # --- Valid parent event IDs ---
            for parent_id in event.parent_event_ids:
                if parent_id not in episode_event_ids:
                    diagnostics.append(
                        make_diagnostic(
                            DiagnosticCodes.VERIFY002,
                            event_id=event.event_id,
                            field="parent_event_ids",
                            suggestion=(
                                f"Parent event ID '{parent_id}' does not exist "
                                f"in episode '{episode.episode_id}'."
                            ),
                        )
                    )

            # --- Tool calls have names ---
            if event.event_type == EventType.TOOL_CALL and event.action is not None:
                if not event.action.tool_name:
                    diagnostics.append(
                        make_diagnostic(
                            DiagnosticCodes.VERIFY002,
                            event_id=event.event_id,
                            field="action.tool_name",
                            suggestion="Tool call events must have a tool_name.",
                        )
                    )

            # --- Artifacts referenced by events exist in record ---
            for artifact_ref in event.artifacts:
                if artifact_ref not in artifact_ids:
                    diagnostics.append(
                        make_diagnostic(
                            DiagnosticCodes.VERIFY003,
                            event_id=event.event_id,
                            field="artifacts",
                            suggestion=(
                                f"Referenced artifact '{artifact_ref}' "
                                f"not found in record.artifacts."
                            ),
                        )
                    )

            # --- Reasoning events have visibility policy ---
            if event.event_type == EventType.REASONING:
                if event.visibility.policy is None:
                    diagnostics.append(
                        make_diagnostic(
                            DiagnosticCodes.VERIFY004,
                            event_id=event.event_id,
                            field="visibility.policy",
                            suggestion=(
                                "Reasoning events should declare a visibility "
                                "policy (e.g. PRESERVE, DROP, SUMMARIZE)."
                            ),
                        )
                    )

    # ------------------------------------------------------------------
    # Strict-mode checks (only when ctx.strict=True)
    # ------------------------------------------------------------------

    def _check_strict(
        self,
        record: AgentIRRecord,
        artifact_ids: set[str],
        diagnostics: list[Diagnostic],
    ) -> None:
        for episode in record.episodes:
            tool_call_ids: set[str] = set()
            for event in episode.events:
                if (
                    event.event_type == EventType.TOOL_CALL
                    and event.action
                    and event.action.tool_call_id
                ):
                    tool_call_ids.add(event.action.tool_call_id)

            for event in episode.events:
                # --- Missing provenance for parsed events ---
                if event.provenance is None or event.provenance.parser is None:
                    # The record was parsed (level is PARSED) but this event
                    # lacks provenance indicating which parser produced it.
                    if record.level.value == "PARSED":
                        diagnostics.append(
                            make_diagnostic(
                                DiagnosticCodes.VERIFY002,
                                event_id=event.event_id,
                                field="provenance",
                                suggestion=(
                                    "Parsed events should carry provenance with parser information."
                                ),
                            )
                        )

                # --- Unknown tool result pairing ---
                if event.event_type == EventType.TOOL_RESULT and event.action is not None:
                    call_id = event.action.tool_call_id
                    if call_id and call_id not in tool_call_ids:
                        diagnostics.append(
                            make_diagnostic(
                                DiagnosticCodes.VERIFY002,
                                event_id=event.event_id,
                                field="action.tool_call_id",
                                suggestion=(
                                    f"Tool result references tool_call_id "
                                    f"'{call_id}' with no matching TOOL_CALL "
                                    f"in episode '{episode.episode_id}'."
                                ),
                            )
                        )

                # --- Malformed patch artifact ---
                if event.event_type == EventType.FILE_PATCH and event.artifacts:
                    for artifact_ref in event.artifacts:
                        for artifact in record.artifacts:
                            if artifact.artifact_id == artifact_ref:
                                if artifact.kind.value == "PATCH" and not artifact.content:
                                    diagnostics.append(
                                        make_diagnostic(
                                            DiagnosticCodes.VERIFY003,
                                            event_id=event.event_id,
                                            field="artifacts",
                                            suggestion=(
                                                f"Patch artifact "
                                                f"'{artifact_ref}' has no "
                                                f"content (malformed patch)."
                                            ),
                                        )
                                    )

                # --- Empty assistant message without explicit incomplete
                #     diagnostic ---
                if event.event_type == EventType.ASSISTANT_MESSAGE:
                    has_content = any(
                        cb.text and cb.text.strip()
                        for cb in event.content
                        if hasattr(cb, "text") and cb.text is not None
                    )
                    if not has_content:
                        # Check if an incomplete diagnostic already exists for
                        # this event in the record-level diagnostics.
                        has_incomplete_diag = any(
                            d.get("event_id") == event.event_id
                            and "incomplete" in d.get("message", "").lower()
                            for d in record.diagnostics
                        )
                        if not has_incomplete_diag:
                            diagnostics.append(
                                make_diagnostic(
                                    DiagnosticCodes.VERIFY004,
                                    event_id=event.event_id,
                                    field="content",
                                    suggestion=(
                                        "Empty assistant message without an "
                                        "explicit incomplete diagnostic."
                                    ),
                                )
                            )


register_pass(VerifyPass())

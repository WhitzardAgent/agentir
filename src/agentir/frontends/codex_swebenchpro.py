"""Frontend for the Codex SWE-bench Pro dataset (Inferact/codex_swebenchpro_traces)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.frontends.base import BaseFrontend, FrontendContext, FrontendResult
from agentir.frontends.registry import register_frontend
from agentir.frontends.sharegpt import get_conversation_role, get_conversation_text
from agentir.ir import (
    AgentIRRecord,
    ContentBlock,
    ContentType,
    Episode,
    Event,
    EventType,
    IRLevel,
    MessageRole,
    Outcome,
    OutcomeStatus,
    Provenance,
    SourceRef,
    TaskSpec,
    Visibility,
)
from agentir.ir.base import DiagnosticSeverity

# Mapping from normalised role strings to (EventType, MessageRole) pairs.
_ROLE_TO_EVENT: dict[str, tuple[EventType, MessageRole]] = {
    "system": (EventType.SYSTEM_MESSAGE, MessageRole.SYSTEM),
    "user": (EventType.USER_MESSAGE, MessageRole.USER),
    "assistant": (EventType.ASSISTANT_MESSAGE, MessageRole.ASSISTANT),
    "tool": (EventType.TOOL_MESSAGE, MessageRole.TOOL),
    "developer": (EventType.SYSTEM_MESSAGE, MessageRole.DEVELOPER),
}


class CodexSWEBenchProFrontend(BaseFrontend):
    """Frontend for Codex SWE-bench Pro traces."""

    name = "codex-swebenchpro"

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self, sample: Mapping[str, Any]) -> float:
        """Return a 0-1 confidence score that *sample* comes from this dataset.

        We look for a ``conversations`` field containing a list of turns where
        each turn has ``from`` and ``value`` keys -- the hallmark of the
        ShareGPT-derived format used by Codex SWE-bench Pro.
        """
        conversations = sample.get("conversations")
        if not isinstance(conversations, list) or len(conversations) == 0:
            return 0.0

        # Check that at least the first few turns look like {from, value} dicts.
        checked = 0
        matches = 0
        for turn in conversations[:10]:
            if not isinstance(turn, dict):
                continue
            checked += 1
            if "from" in turn and "value" in turn:
                matches += 1

        if checked == 0:
            return 0.0

        # Strong signal: most turns have from/value.  We also give a small
        # bonus for Codex-specific metadata fields that commonly appear.
        score = matches / checked
        codex_fields = {
            "repo",
            "issue_id",
            "base_commit",
            "instance_id",
            "pass",
            "fail",
            "verifier",
            "model_name_or_path",
        }
        present = sum(1 for f in codex_fields if f in sample)
        if present > 0:
            score = min(1.0, score + 0.1 * present / len(codex_fields))

        return score

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_record(self, sample: Mapping[str, Any], ctx: FrontendContext) -> FrontendResult:
        """Parse a Codex SWE-bench Pro row into an :class:`AgentIRRecord`."""

        diagnostics: list[Diagnostic] = []

        # ---- Record identity ----
        record_id = (
            sample.get("instance_id")
            or sample.get("id")
            or (f"row-{ctx.row_index}" if ctx.row_index is not None else "unknown")
        )

        # ---- Source reference ----
        source = SourceRef(
            dataset=ctx.dataset or "Inferact/codex_swebenchpro_traces",
            dataset_url=ctx.dataset_url,
            config=ctx.config,
            split=ctx.split,
            row_id=str(record_id),
            row_index=ctx.row_index,
            framework="codex-swebenchpro",
            format="sharegpt-variant",
        )

        # ---- Provenance helper ----
        def _provenance(source_field: str) -> Provenance:
            return Provenance(
                dataset=source.dataset,
                config=source.config,
                split=source.split,
                row_id=source.row_id,
                row_index=source.row_index,
                source_field=source_field,
                parser=self.name,
            )

        # ---- Parse conversations into events ----
        conversations = sample.get("conversations", [])
        events: list[Event] = []

        for idx, turn in enumerate(conversations):
            if not isinstance(turn, dict):
                diagnostics.append(
                    Diagnostic(
                        code="DATA002",
                        severity=DiagnosticSeverity.WARNING,
                        message=f"Skipping non-dict conversation turn at index {idx}",
                    )
                )
                continue

            raw_role = get_conversation_role(turn)
            text = get_conversation_text(turn)

            event_type, message_role = _ROLE_TO_EVENT.get(
                raw_role, (EventType.UNPARSED_FRAGMENT, MessageRole.UNKNOWN)
            )

            # Build content blocks -- preserve full text, do NOT truncate.
            content_blocks: list[ContentBlock] = []
            if text:
                content_blocks.append(
                    ContentBlock(
                        type=ContentType.TEXT,
                        text=text,
                    )
                )

            # If the turn has a structured ``content`` list (OpenAI-style
            # multi-part), preserve each part as its own block.
            raw_content = turn.get("content")
            if isinstance(raw_content, list):
                for block in raw_content:
                    if isinstance(block, str):
                        content_blocks.append(ContentBlock(type=ContentType.TEXT, text=block))
                    elif isinstance(block, dict):
                        block_text = block.get("text")
                        block_type = block.get("type", "text")
                        if isinstance(block_text, str):
                            ct = (
                                ContentType.MARKDOWN
                                if block_type == "markdown"
                                else ContentType.TEXT
                            )
                            content_blocks.append(ContentBlock(type=ct, text=block_text))

            event_id = f"{record_id}-evt-{idx}"

            events.append(
                Event(
                    event_id=event_id,
                    idx=idx,
                    event_type=event_type,
                    role=message_role,
                    content=content_blocks,
                    provenance=_provenance(f"conversations[{idx}]"),
                    visibility=Visibility(),
                    raw=dict(turn),
                )
            )

        # ---- Episode ----
        episode_id = f"{record_id}-ep-0"
        episode = Episode(
            episode_id=episode_id,
            task_id=str(record_id),
            events=events,
        )

        # ---- Task spec ----
        task: TaskSpec | None = None
        has_task_fields = any(
            sample.get(k) is not None
            for k in ("repo", "issue_id", "base_commit", "instance_id", "problem_statement")
        )
        if has_task_fields:
            task = TaskSpec(
                task_id=str(sample.get("instance_id") or record_id),
                instruction=sample.get("problem_statement"),
                benchmark="swebench-pro",
                repo=sample.get("repo"),
                base_commit=sample.get("base_commit"),
                issue_id=sample.get("issue_id"),
            )

        # ---- Outcome ----
        outcome: Outcome | None = None
        has_outcome = any(
            sample.get(k) is not None for k in ("pass", "fail", "resolved", "verifier")
        )
        if has_outcome:
            passed = sample.get("pass") or sample.get("resolved")
            failed = sample.get("fail")

            if passed is not None:
                passed_bool = bool(passed)
            elif failed is not None:
                passed_bool = not bool(failed)
            else:
                passed_bool = None

            if passed_bool is True:
                status = OutcomeStatus.SUCCESS
            elif passed_bool is False:
                status = OutcomeStatus.FAILURE
            else:
                status = OutcomeStatus.UNKNOWN

            verifier_data = sample.get("verifier")
            verifier_result = None
            if verifier_data is not None:
                if isinstance(verifier_data, dict):
                    verifier_result = _build_verifier(verifier_data)
                elif isinstance(verifier_data, (str, bool)):
                    verifier_result = _build_verifier(
                        {"output": str(verifier_data), "passed": passed_bool}
                    )

            outcome = Outcome(
                status=status,
                passed=passed_bool,
                verifier=verifier_result,
            )

        # ---- Metadata -- store unsupported trial metrics under codex.* ----
        codex_meta: dict[str, Any] = {}
        known_keys = {
            "conversations",
            "instance_id",
            "id",
            "repo",
            "issue_id",
            "base_commit",
            "problem_statement",
            "pass",
            "fail",
            "resolved",
            "verifier",
            "model_name_or_path",
        }
        for key, value in sample.items():
            if key not in known_keys and value is not None:
                codex_meta[key] = value

        metadata: dict[str, Any] = {}
        if codex_meta:
            metadata["codex"] = codex_meta
        if sample.get("model_name_or_path"):
            metadata.setdefault("codex", {})["model_name_or_path"] = sample["model_name_or_path"]

        # ---- Assemble record ----
        record = AgentIRRecord(
            record_id=str(record_id),
            level=IRLevel.PARSED,
            source=source,
            task=task,
            episodes=[episode],
            outcome=outcome,
            raw={"record": dict(sample)},
            metadata=metadata,
        )

        return FrontendResult(record=record, diagnostics=diagnostics)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _build_verifier(data: dict[str, Any]) -> VerifierResult:
    """Build a VerifierResult from raw verifier data."""
    from agentir.ir.outcome import VerifierResult

    return VerifierResult(
        type=data.get("type"),
        command=data.get("command"),
        output=data.get("output"),
        passed=data.get("passed"),
        score=data.get("score"),
    )


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------

register_frontend(CodexSWEBenchProFrontend())

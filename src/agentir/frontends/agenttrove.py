"""Frontend for the open-thoughts/AgentTrove dataset."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.frontends.base import BaseFrontend, FrontendContext, FrontendResult
from agentir.frontends.registry import register_frontend
from agentir.frontends.sharegpt import get_conversation_role, get_conversation_text
from agentir.ir import (
    ActorKind,
    ActorSpec,
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

# Mapping from normalized sharegpt role to (EventType, MessageRole)
_ROLE_TO_EVENT: dict[str, tuple[EventType, MessageRole]] = {
    "user": (EventType.USER_MESSAGE, MessageRole.USER),
    "assistant": (EventType.ASSISTANT_MESSAGE, MessageRole.ASSISTANT),
    "system": (EventType.SYSTEM_MESSAGE, MessageRole.SYSTEM),
    "tool": (EventType.TOOL_MESSAGE, MessageRole.TOOL),
    "developer": (EventType.SYSTEM_MESSAGE, MessageRole.DEVELOPER),
}

# Fields that signal an AgentTrove-formatted record
_DETECT_FIELDS = (
    "messages",
    "conversations",
    "conversation",
    "original_source",
    "original_teacher",
    "reward",
)


class AgentTroveFrontend(BaseFrontend):
    """Frontend for open-thoughts/AgentTrove datasets."""

    name = "agenttrove"

    def detect(self, sample: Mapping[str, Any]) -> float:
        """Return a 0-1 confidence score that *sample* comes from AgentTrove."""
        hits = 0
        total = len(_DETECT_FIELDS)

        for field in _DETECT_FIELDS:
            if field in sample and sample[field] is not None:
                hits += 1

        # Must have at least one conversation-style field to be viable
        has_conversation = any(
            sample.get(k) is not None for k in ("messages", "conversations", "conversation")
        )

        if not has_conversation:
            return 0.0

        # Presence of AgentTrove-specific fields boosts confidence
        has_trove_marker = any(
            sample.get(k) is not None for k in ("original_source", "original_teacher", "reward")
        )

        base_score = hits / total
        if has_trove_marker:
            # Strong indicator: boost score significantly
            score = min(1.0, base_score + 0.4)
        else:
            # Generic conversation data without AgentTrove markers: lower confidence
            score = base_score * 0.6

        return round(score, 3)

    def parse_record(self, sample: Mapping[str, Any], ctx: FrontendContext) -> FrontendResult:
        """Parse an AgentTrove record into an AgentIRRecord."""
        # --- Identify the conversation field ---
        conversation: list[Mapping[str, Any]] | None = None
        conv_field: str | None = None
        for key in ("messages", "conversations", "conversation"):
            val = sample.get(key)
            if isinstance(val, list) and len(val) > 0:
                conversation = val
                conv_field = key
                break

        if conversation is None:
            return FrontendResult(
                record=None,
                diagnostics=[_diag("No conversation field found", "error")],
            )

        # --- Build events from conversation turns ---
        events: list[Event] = []
        for idx, turn in enumerate(conversation):
            raw_role = get_conversation_role(turn) if isinstance(turn, Mapping) else "unknown"
            text = get_conversation_text(turn) if isinstance(turn, Mapping) else ""

            event_type, message_role = _ROLE_TO_EVENT.get(
                raw_role, (EventType.UNPARSED_FRAGMENT, MessageRole.UNKNOWN)
            )

            content_blocks: list[ContentBlock] = []
            if text:
                content_blocks.append(ContentBlock(type=ContentType.TEXT, text=text))
            # Handle structured content lists (e.g. OpenAI-style content arrays)
            raw_content = turn.get("content") if isinstance(turn, Mapping) else None
            if isinstance(raw_content, list) and len(raw_content) > 0:
                for block in raw_content:
                    if isinstance(block, dict):
                        if block.get("type") == "text" and isinstance(block.get("text"), str):
                            # Already handled via get_conversation_text above; skip duplicate
                            continue
                        elif block.get("type") == "image_url":
                            content_blocks.append(
                                ContentBlock(
                                    type=ContentType.IMAGE,
                                    metadata={"url": block.get("image_url", {}).get("url", "")},
                                )
                            )
                        elif isinstance(block.get("text"), str):
                            # Non-text-typed block with text field
                            content_blocks.append(
                                ContentBlock(type=ContentType.TEXT, text=block["text"])
                            )

            event_id = f"evt_{idx:04d}"
            event = Event(
                event_id=event_id,
                idx=idx,
                event_type=event_type,
                role=message_role,
                content=content_blocks,
                provenance=Provenance(
                    dataset=ctx.dataset,
                    config=ctx.config,
                    split=ctx.split,
                    row_index=ctx.row_index,
                    source_field=conv_field,
                    parser=self.name,
                ),
                visibility=Visibility(),
            )
            events.append(event)

        # --- Build source reference ---
        source = SourceRef(
            dataset="open-thoughts/AgentTrove"
            if ctx.dataset and "agenttrove" in ctx.dataset.lower()
            else ctx.dataset,
            dataset_url=ctx.dataset_url,
            config=ctx.config,
            split=ctx.split,
            row_index=ctx.row_index,
            framework="agenttrove",
            format=conv_field,
            original_source=sample.get("original_source"),
            original_teacher=sample.get("original_teacher"),
        )

        # --- Build task spec ---
        task: TaskSpec | None = None
        task_id = sample.get("task_id")
        if task_id is not None:
            task = TaskSpec(task_id=str(task_id))

        # --- Build actor spec ---
        actors: list[ActorSpec] = []
        model = sample.get("model")
        if model is not None:
            actors.append(
                ActorSpec(
                    actor_id="actor_0",
                    kind=ActorKind.ASSISTANT,
                    model=str(model),
                )
            )

        # --- Build outcome ---
        outcome: Outcome | None = None
        reward = sample.get("reward")
        if reward is not None:
            try:
                reward_val = float(reward)
            except (TypeError, ValueError):
                reward_val = None
            if reward_val is not None:
                outcome = Outcome(
                    status=OutcomeStatus.UNKNOWN,
                    reward=reward_val,
                )

        # --- Build episode ---
        episode = Episode(
            episode_id="ep_0",
            task_id=task_id if isinstance(task_id, str) else None,
            events=events,
            outcome=outcome,
        )

        # --- Assemble record ---
        record = AgentIRRecord(
            record_id=f"rec_{ctx.row_index:06d}" if ctx.row_index is not None else "rec_000000",
            level=IRLevel.PARSED,
            source=source,
            task=task,
            actors=actors,
            episodes=[episode],
            outcome=outcome,
            raw={"record": dict(sample)},
        )

        return FrontendResult(record=record)


def _diag(message: str, severity: str = "warning") -> Diagnostic:
    from agentir.ir.base import DiagnosticSeverity

    sev = DiagnosticSeverity.ERROR if severity == "error" else DiagnosticSeverity.WARNING
    return Diagnostic(code="DATA002", severity=sev, message=message)


# Register the frontend
register_frontend(AgentTroveFrontend())

"""Frontend for the Hermes Agent dataset (lambda/hermes-agent-reasoning-traces).

Detects and parses records that follow the Hermes conversation format with
tool definitions.  The frontend emits conversations as message events;
XML parsing of tool calls / reasoning within assistant turns is deferred
to the ``parse-hermes-xml`` pass.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from agentir.frontends.base import BaseFrontend, FrontendContext, FrontendResult
from agentir.frontends.registry import register_frontend
from agentir.frontends.sharegpt import (
    get_conversation_role,
    get_conversation_text,
)
from agentir.ir import (
    AgentIRRecord,
    ContentBlock,
    ContentType,
    Episode,
    Event,
    EventType,
    IRLevel,
    MessageRole,
    Provenance,
    SourceRef,
    TaskSpec,
    ToolSpec,
    Visibility,
)
from agentir.ir.base import DiagnosticSeverity, ReasoningPolicy, RedactionStatus

# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

_ROLE_TO_EVENT_TYPE: dict[str, tuple[EventType, MessageRole]] = {
    "system": (EventType.SYSTEM_MESSAGE, MessageRole.SYSTEM),
    "user": (EventType.USER_MESSAGE, MessageRole.USER),
    "assistant": (EventType.ASSISTANT_MESSAGE, MessageRole.ASSISTANT),
    "tool": (EventType.TOOL_MESSAGE, MessageRole.TOOL),
    "developer": (EventType.SYSTEM_MESSAGE, MessageRole.DEVELOPER),
}


def _parse_tools_field(tools: Any) -> list[dict[str, Any]]:
    """Normalise the ``tools`` field to a list of dicts.

    The field may be a JSON string, a list of dicts, or a single dict.
    """
    if tools is None:
        return []
    if isinstance(tools, str):
        try:
            tools = json.loads(tools)
        except json.JSONDecodeError:
            return []
    if isinstance(tools, dict):
        # Some datasets wrap the list under a key like "tools" or "functions".
        for key in ("tools", "functions", "definitions"):
            if key in tools and isinstance(tools[key], list):
                return tools[key]
        return [tools]
    if isinstance(tools, list):
        return tools
    return []


def _build_tool_spec(raw_tool: dict[str, Any], idx: int) -> ToolSpec:
    """Build a :class:`ToolSpec` from a raw tool definition."""
    name = raw_tool.get("name") or raw_tool.get("function", {}).get("name") or f"tool_{idx}"
    description = raw_tool.get("description") or raw_tool.get("function", {}).get("description")
    schema = raw_tool.get("parameters") or raw_tool.get("function", {}).get("parameters") or {}
    if not isinstance(schema, dict):
        schema = {}

    return ToolSpec(
        tool_id=f"tool_{idx}",
        name=name,
        description=description,
        input_schema=schema,
    )


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------


class HermesAgentFrontend(BaseFrontend):
    """Frontend for Hermes Agent reasoning traces."""

    name = "hermes-agent"

    # -- detection -----------------------------------------------------------

    def detect(self, sample: Mapping[str, Any]) -> float:
        """Return a 0-1 confidence score that *sample* is a Hermes Agent record.

        Checks for:
        * ``conversations`` list whose entries have ``from`` and ``value``
        * ``tools`` field (JSON string or object)
        * ``category``, ``subcategory``, ``task`` metadata fields
        """
        score = 0.0

        # --- conversations structure ---
        convs = sample.get("conversations")
        if isinstance(convs, list) and len(convs) > 0:
            score += 0.3
            first = convs[0]
            if isinstance(first, dict) and "from" in first and "value" in first:
                score += 0.3
                # Check multiple turns for stronger signal
                matching = 0
                for turn in convs[:10]:
                    if isinstance(turn, dict) and "from" in turn and "value" in turn:
                        matching += 1
                if matching >= 3:
                    score += 0.1

        # --- tools field ---
        tools = sample.get("tools")
        if tools is not None:
            score += 0.15
            parsed = _parse_tools_field(tools)
            if parsed and isinstance(parsed, list) and len(parsed) > 0:
                score += 0.05

        # --- metadata fields ---
        if sample.get("category"):
            score += 0.03
        if sample.get("subcategory"):
            score += 0.02
        if sample.get("task"):
            score += 0.05

        return min(score, 1.0)

    # -- parsing -------------------------------------------------------------

    def parse_record(
        self,
        sample: Mapping[str, Any],
        ctx: FrontendContext,
    ) -> FrontendResult:
        """Parse a Hermes Agent row into an :class:`AgentIRRecord`."""
        from agentir.diagnostics.diagnostic import Diagnostic

        diagnostics: list[Diagnostic] = []
        events: list[Event] = []

        # --- Source reference ---
        row_id = str(sample.get("id", "")) or None
        source = SourceRef(
            dataset=ctx.dataset,
            dataset_url=ctx.dataset_url,
            config=ctx.config,
            split=ctx.split,
            row_id=row_id,
            row_index=ctx.row_index,
            framework="hermes-agent",
            format="hermes-conversation",
        )

        # --- Tool registry ---
        raw_tools = _parse_tools_field(sample.get("tools"))
        tool_registry = [_build_tool_spec(t, i) for i, t in enumerate(raw_tools)]

        # --- Task spec ---
        task = TaskSpec(
            task_id=row_id,
            instruction=sample.get("task") or None,
            category=sample.get("category") or None,
            subcategory=sample.get("subcategory") or None,
            metadata={
                k: v
                for k, v in {
                    "source": sample.get("source"),
                    "model_name": sample.get("model_name"),
                }.items()
                if v is not None
            },
        )

        # --- Conversations -> events ---
        conversations = sample.get("conversations", [])
        if not isinstance(conversations, list):
            conversations = []

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

            event_type, message_role = _ROLE_TO_EVENT_TYPE.get(
                raw_role, (EventType.UNPARSED_FRAGMENT, MessageRole.UNKNOWN)
            )

            # Detect reasoning content marked with ༄
            visibility = Visibility()
            if raw_role == "assistant" and text.startswith("༄"):
                event_type = EventType.REASONING
                visibility = Visibility(
                    contains_reasoning=True,
                    redaction_status=RedactionStatus.METADATA_ONLY,
                    policy=ReasoningPolicy.METADATA_ONLY,
                )

            content_blocks: list[ContentBlock] = []
            if text:
                content_blocks.append(ContentBlock(type=ContentType.TEXT, text=text))

            provenance = Provenance(
                dataset=ctx.dataset,
                config=ctx.config,
                split=ctx.split,
                row_id=row_id,
                source_field=f"conversations[{idx}]",
                row_index=ctx.row_index,
            )

            event = Event(
                event_id=f"evt_{idx}",
                idx=idx,
                event_type=event_type,
                role=message_role,
                content=content_blocks,
                provenance=provenance,
                visibility=visibility,
                raw=dict(turn),
            )
            events.append(event)

        # --- Episode ---
        episode = Episode(
            episode_id="ep_0",
            events=events,
        )

        # --- Record ---
        record_id = row_id or f"row_{ctx.row_index}"
        record = AgentIRRecord(
            record_id=record_id,
            level=IRLevel.PARSED,
            source=source,
            task=task,
            tool_registry=tool_registry,
            episodes=[episode],
            raw={"record": dict(sample)},
        )

        return FrontendResult(record=record, diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_frontend(HermesAgentFrontend())

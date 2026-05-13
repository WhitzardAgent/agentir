"""Hermes XML backend.

Produces conversations in the Hermes/Shield format with XML tool-call
representations inside ༄ markers.
"""

from __future__ import annotations

import json
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from agentir.backends.base import BackendContext
from agentir.backends.loss import LossItem, LossReport, LoweringResult
from agentir.backends.registry import register_backend
from agentir.ir.base import (
    DiagnosticSeverity,
    EventType,
    LoweringStatus,
)
from agentir.ir.record import AgentIRRecord


def _content_text(event) -> str:
    parts: list[str] = []
    for block in event.content:
        if block.text is not None:
            parts.append(block.text)
        elif block.json_value is not None:
            parts.append(json.dumps(block.json_value, ensure_ascii=False))
    return "\n".join(parts)


def _obs_text(obs) -> str | None:
    if obs is None:
        return None
    parts: list[str] = []
    if obs.stdout:
        parts.append(obs.stdout)
    if obs.stderr:
        parts.append(obs.stderr)
    for block in obs.content:
        if block.text is not None:
            parts.append(block.text)
        elif block.json_value is not None:
            parts.append(json.dumps(block.json_value, ensure_ascii=False))
    return "\n".join(parts) if parts else None


def _should_include_reasoning(ctx: BackendContext) -> bool:
    """Check whether reasoning should be included based on context policy."""
    if ctx.include_reasoning:
        return True
    policy = ctx.reasoning_policy
    if policy in ("preserve", "summarize", "metadata_only"):
        return True
    return False


def _role_to_from(role) -> str:
    """Map MessageRole / event type to Hermes 'from' field."""
    from agentir.ir.base import MessageRole

    mapping = {
        MessageRole.SYSTEM: "system",
        MessageRole.USER: "human",
        MessageRole.ASSISTANT: "gpt",
        MessageRole.TOOL: "tool",
        MessageRole.DEVELOPER: "system",
        MessageRole.ENVIRONMENT: "tool",
    }
    return mapping.get(role, "gpt")


# Events that produce assistant-side tool calls
_TOOL_CALL_EVENTS = {
    EventType.TOOL_CALL,
    EventType.TERMINAL_COMMAND,
    EventType.FILE_WRITE,
    EventType.FILE_PATCH,
    EventType.BROWSER_ACTION,
}


class HermesXMLBackend:
    """Lower AgentIR to Hermes/Shield XML conversation format."""

    name: str = "hermes-xml"

    def lower_record(self, record: AgentIRRecord, ctx: BackendContext) -> LoweringResult:
        losses: list[LossItem] = []
        conversations: list[dict[str, str]] = []

        all_events: list[Any] = []
        for episode in record.episodes:
            all_events.extend(episode.events)

        # Build tool_call_id -> result text map
        tool_call_id_to_result: dict[str, str] = {}
        for event in all_events:
            if (
                event.event_type == EventType.TOOL_RESULT
                and event.action
                and event.action.tool_call_id
            ):
                text = _obs_text(event.observation) or ""
                tool_call_id_to_result[event.action.tool_call_id] = text

        include_reasoning = _should_include_reasoning(ctx)

        for event in all_events:
            # Reasoning
            if event.event_type == EventType.REASONING:
                if not include_reasoning:
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.WARNING,
                            code="LOWER003",
                            field="reasoning",
                            message="Reasoning event dropped; Hermes XML cannot represent private reasoning by default.",
                            event_id=event.event_id,
                            suggestion="Use --include-reasoning or --reasoning-policy preserve.",
                        )
                    )
                    continue
                text = _content_text(event)
                if text:
                    conversations.append(
                        {"from": "gpt", "value": f"\n{xml_escape(text)}\n</think>"}
                    )
                continue

            # Plan
            if event.event_type == EventType.PLAN:
                if not include_reasoning:
                    continue
                text = _content_text(event)
                if text:
                    conversations.append(
                        {"from": "gpt", "value": f"<plan>\n{xml_escape(text)}\n</plan>"}
                    )
                continue

            # System message
            if event.event_type == EventType.SYSTEM_MESSAGE:
                text = _content_text(event)
                if text:
                    conversations.append({"from": "system", "value": xml_escape(text)})
                continue

            # User message
            if event.event_type == EventType.USER_MESSAGE:
                text = _content_text(event)
                if text:
                    conversations.append({"from": "human", "value": xml_escape(text)})
                continue

            # Assistant message
            if event.event_type == EventType.ASSISTANT_MESSAGE:
                text = _content_text(event)
                if text:
                    conversations.append({"from": "gpt", "value": xml_escape(text)})
                continue

            # Tool call events
            if event.event_type in _TOOL_CALL_EVENTS:
                action = event.action
                if action is None:
                    continue

                tool_name = action.tool_name or event.event_type.value
                args_json = json.dumps(action.arguments, ensure_ascii=False)

                # Build the ༄-wrapped tool call
                tool_call_text = f"༄{tool_name}({args_json})༄"

                text = _content_text(event)
                value_parts: list[str] = []
                if text:
                    value_parts.append(xml_escape(text))
                value_parts.append(tool_call_text)

                conversations.append({"from": "gpt", "value": "\n".join(value_parts)})

                # Tool result
                tc_id = action.tool_call_id
                if tc_id and tc_id in tool_call_id_to_result:
                    result_text = tool_call_id_to_result[tc_id]
                    conversations.append({"from": "tool", "value": xml_escape(result_text)})
                elif event.observation:
                    obs_text = _obs_text(event.observation)
                    if obs_text:
                        conversations.append({"from": "tool", "value": xml_escape(obs_text)})
                continue

            # Tool result events not already consumed
            if event.event_type == EventType.TOOL_RESULT:
                action = event.action
                obs_text = _obs_text(event.observation) or ""
                conversations.append({"from": "tool", "value": xml_escape(obs_text)})
                continue

            # Finish
            if event.event_type == EventType.FINISH:
                text = _content_text(event)
                if text:
                    conversations.append({"from": "gpt", "value": xml_escape(text)})
                continue

            # Check for multi-artifact observations that can't be represented
            if event.event_type in (EventType.BROWSER_OBSERVATION, EventType.TERMINAL_OUTPUT):
                if event.observation and len(event.observation.artifact_ids) > 1:
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.WARNING,
                            code="LOWER006",
                            field="observation",
                            message="Multi-artifact observation cannot be fully represented in Hermes XML.",
                            event_id=event.event_id,
                            suggestion="Flatten multi-artifact observations before lowering.",
                        )
                    )
                continue

            # Unhandled
            if event.event_type in (
                EventType.TODO_UPDATE,
                EventType.STATE_SNAPSHOT,
                EventType.VERIFICATION,
                EventType.REWARD,
                EventType.ERROR,
                EventType.UNPARSED_FRAGMENT,
                EventType.MEMORY_READ,
                EventType.MEMORY_WRITE,
                EventType.AGENT_HANDOFF,
                EventType.SUBTASK_SPAWN,
                EventType.SUBTASK_RESULT,
                EventType.FILE_READ,
            ):
                losses.append(
                    LossItem(
                        severity=DiagnosticSeverity.INFO,
                        code="LOWER005",
                        field=event.event_type.value,
                        message=f"Event type {event.event_type.value} not represented in hermes-xml output.",
                        event_id=event.event_id,
                    )
                )
                continue

        # Build tools spec
        tools_spec: list[dict[str, Any]] = []
        for tool in record.tool_registry:
            spec: dict[str, Any] = {
                "name": tool.name,
            }
            if tool.description:
                spec["description"] = tool.description
            if tool.input_schema:
                spec["parameters"] = tool.input_schema
            tools_spec.append(spec)

        # Determine status
        if any(l.severity in (DiagnosticSeverity.ERROR, DiagnosticSeverity.FATAL) for l in losses):
            status = LoweringStatus.UNSUPPORTED
        elif any(l.severity == DiagnosticSeverity.WARNING for l in losses):
            status = LoweringStatus.LOSSY
        elif losses:
            status = LoweringStatus.PARTIAL
        else:
            status = LoweringStatus.EXACT

        output = {
            "conversations": conversations,
            "tools": json.dumps(tools_spec, ensure_ascii=False),
        }

        return LoweringResult(
            output=output,
            report=LossReport(
                target=self.name,
                status=status,
                losses=losses,
                metrics={"conversation_turns": len(conversations), "tools_count": len(tools_spec)},
            ),
        )


register_backend(HermesXMLBackend())

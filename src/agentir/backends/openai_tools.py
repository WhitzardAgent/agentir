"""OpenAI tools backend.

Produces chat messages in OpenAI's native tool_calls format
with role=tool messages carrying tool_call_id.
"""

from __future__ import annotations

import json
from typing import Any

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


# Events that produce assistant-side tool_calls
_TOOL_CALL_EVENTS = {
    EventType.TOOL_CALL,
    EventType.TERMINAL_COMMAND,
    EventType.FILE_WRITE,
    EventType.FILE_PATCH,
    EventType.BROWSER_ACTION,
}


class OpenAIToolsBackend:
    """Lower AgentIR to OpenAI chat + tool_calls format."""

    name: str = "openai-tools"

    def lower_record(self, record: AgentIRRecord, ctx: BackendContext) -> LoweringResult:
        losses: list[LossItem] = []
        messages: list[dict[str, Any]] = []

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

        # Track which tool_call_ids we've emitted results for
        emitted_results: set[str] = set()

        for event in all_events:
            # Drop reasoning
            if event.event_type == EventType.REASONING:
                losses.append(
                    LossItem(
                        severity=DiagnosticSeverity.INFO,
                        code="LOWER003",
                        field="reasoning",
                        message="Reasoning event dropped in openai-tools backend.",
                        event_id=event.event_id,
                    )
                )
                continue

            if event.event_type == EventType.PLAN:
                losses.append(
                    LossItem(
                        severity=DiagnosticSeverity.INFO,
                        code="LOWER004",
                        field="plan",
                        message="Plan event dropped in openai-tools backend.",
                        event_id=event.event_id,
                    )
                )
                continue

            # System message
            if event.event_type == EventType.SYSTEM_MESSAGE:
                text = _content_text(event)
                if text:
                    messages.append({"role": "system", "content": text})
                continue

            # User message
            if event.event_type == EventType.USER_MESSAGE:
                text = _content_text(event)
                if text:
                    messages.append({"role": "user", "content": text})
                continue

            # Assistant message (no tool calls)
            if event.event_type == EventType.ASSISTANT_MESSAGE:
                text = _content_text(event)
                if text:
                    messages.append({"role": "assistant", "content": text})
                continue

            # Tool call events
            if event.event_type in _TOOL_CALL_EVENTS:
                action = event.action
                if action is None:
                    continue

                tool_call_id = action.tool_call_id
                generated_id = False
                if not tool_call_id:
                    tool_call_id = f"call_{event.event_id}"
                    generated_id = True
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.WARNING,
                            code="LOWER001",
                            field="tool_call_id",
                            message="Tool call lacks ID; generated stable ID call_<event_id>.",
                            event_id=event.event_id,
                            suggestion="Ensure source provides tool_call_id.",
                        )
                    )

                text = _content_text(event) or None

                # Determine tool name
                tool_name = action.tool_name
                if tool_name is None:
                    if event.event_type == EventType.TERMINAL_COMMAND:
                        tool_name = "terminal"
                    elif event.event_type == EventType.FILE_WRITE:
                        tool_name = "file_write"
                    elif event.event_type == EventType.FILE_PATCH:
                        tool_name = "file_patch"
                    elif event.event_type == EventType.BROWSER_ACTION:
                        tool_name = "browser_action"
                    else:
                        tool_name = "unknown"

                tool_call_obj = {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(action.arguments, ensure_ascii=False),
                    },
                }

                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": text,
                    "tool_calls": [tool_call_obj],
                }
                messages.append(msg)

                # Attach tool result
                if tool_call_id in tool_call_id_to_result:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": tool_call_id_to_result[tool_call_id],
                        }
                    )
                    emitted_results.add(tool_call_id)
                elif event.observation:
                    obs_text = _obs_text(event.observation)
                    if obs_text:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": obs_text,
                            }
                        )
                        emitted_results.add(tool_call_id)
                continue

            # Tool result events that were not consumed by a tool call
            if event.event_type == EventType.TOOL_RESULT:
                action = event.action
                tc_id = action.tool_call_id if action else None
                if tc_id and tc_id not in emitted_results:
                    obs_text = _obs_text(event.observation) or ""
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": obs_text,
                        }
                    )
                    emitted_results.add(tc_id)
                continue

            # Finish
            if event.event_type == EventType.FINISH:
                text = _content_text(event)
                if text:
                    messages.append({"role": "assistant", "content": text})
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
                EventType.TERMINAL_OUTPUT,
                EventType.BROWSER_OBSERVATION,
            ):
                losses.append(
                    LossItem(
                        severity=DiagnosticSeverity.INFO,
                        code="LOWER005",
                        field=event.event_type.value,
                        message=f"Event type {event.event_type.value} not represented in openai-tools output.",
                        event_id=event.event_id,
                    )
                )
                continue

        # Determine status
        if any(l.severity in (DiagnosticSeverity.ERROR, DiagnosticSeverity.FATAL) for l in losses):
            status = LoweringStatus.UNSUPPORTED
        elif any(l.severity == DiagnosticSeverity.WARNING for l in losses):
            status = LoweringStatus.LOSSY
        elif losses:
            status = LoweringStatus.PARTIAL
        else:
            status = LoweringStatus.EXACT

        return LoweringResult(
            output={"messages": messages},
            report=LossReport(
                target=self.name,
                status=status,
                losses=losses,
                metrics={"message_count": len(messages)},
            ),
        )


register_backend(OpenAIToolsBackend())

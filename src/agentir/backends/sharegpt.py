"""ShareGPT backend.

Produces conversation pairs in ShareGPT format (human/gpt).
Inherently lossy for structured tool calls.
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


_TOOL_CALL_EVENTS = {
    EventType.TOOL_CALL,
    EventType.TERMINAL_COMMAND,
    EventType.FILE_WRITE,
    EventType.FILE_PATCH,
    EventType.BROWSER_ACTION,
}


def _inline_tool_call(action, event) -> str:
    """Serialize a tool call inline as text."""
    tool_name = action.tool_name or event.event_type.value
    args_json = json.dumps(action.arguments, ensure_ascii=False)
    return f"[Tool Call: {tool_name}({args_json})]"


class ShareGPTBackend:
    """Lower AgentIR to ShareGPT conversation format."""

    name: str = "sharegpt"

    def lower_record(self, record: AgentIRRecord, ctx: BackendContext) -> LoweringResult:
        losses: list[LossItem] = []
        conversations: list[dict[str, str]] = []
        has_tool_calls = False

        all_events: list[Any] = []
        for episode in record.episodes:
            all_events.extend(episode.events)

        include_reasoning = ctx.include_reasoning

        for event in all_events:
            # Reasoning
            if event.event_type == EventType.REASONING:
                if not include_reasoning:
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.INFO,
                            code="LOWER003",
                            field="reasoning",
                            message="Reasoning event dropped in sharegpt backend.",
                            event_id=event.event_id,
                        )
                    )
                    continue
                text = _content_text(event)
                if text:
                    conversations.append({"from": "gpt", "value": text})
                continue

            if event.event_type == EventType.PLAN:
                if not include_reasoning:
                    continue
                text = _content_text(event)
                if text:
                    conversations.append({"from": "gpt", "value": text})
                continue

            # System message -> map to human (ShareGPT doesn't have a system role)
            if event.event_type == EventType.SYSTEM_MESSAGE:
                text = _content_text(event)
                if text:
                    conversations.append({"from": "human", "value": text})
                continue

            # User message
            if event.event_type == EventType.USER_MESSAGE:
                text = _content_text(event)
                if text:
                    conversations.append({"from": "human", "value": text})
                continue

            # Assistant message
            if event.event_type == EventType.ASSISTANT_MESSAGE:
                text = _content_text(event)
                if text:
                    conversations.append({"from": "gpt", "value": text})
                continue

            # Tool call events
            if event.event_type in _TOOL_CALL_EVENTS:
                has_tool_calls = True
                action = event.action
                if action is None:
                    continue

                if ctx.tool_policy == "inline":
                    # Serialize tool call inline
                    inline_text = _inline_tool_call(action, event)
                    text = _content_text(event)
                    value = f"{text}\n{inline_text}" if text else inline_text
                    conversations.append({"from": "gpt", "value": value})

                    # Tool result inline
                    obs_text = _obs_text(event.observation) if event.observation else None
                    if obs_text:
                        conversations.append(
                            {"from": "human", "value": f"[Tool Result]: {obs_text}"}
                        )
                else:
                    # Drop tool calls entirely (structured or drop policy)
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.WARNING,
                            code="LOWER007",
                            field="tool_calls",
                            message="Tool calls cannot be represented in ShareGPT format and were dropped.",
                            event_id=event.event_id,
                            suggestion="Use --tool-policy inline to serialize tool calls as text.",
                        )
                    )
                continue

            # Tool result events
            if event.event_type == EventType.TOOL_RESULT:
                # Already handled if inline policy, otherwise drop
                if ctx.tool_policy != "inline":
                    if event.action and event.action.tool_call_id:
                        losses.append(
                            LossItem(
                                severity=DiagnosticSeverity.INFO,
                                code="LOWER007",
                                field="tool_result",
                                message="Tool result dropped in ShareGPT format.",
                                event_id=event.event_id,
                            )
                        )
                continue

            # Finish
            if event.event_type == EventType.FINISH:
                text = _content_text(event)
                if text:
                    conversations.append({"from": "gpt", "value": text})
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
                        message=f"Event type {event.event_type.value} not represented in sharegpt output.",
                        event_id=event.event_id,
                    )
                )
                continue

        # Determine status
        # ShareGPT is inherently lossy when tool calls exist
        if has_tool_calls and ctx.tool_policy != "inline":
            # Default: lossy because tool calls can't be represented
            status = LoweringStatus.LOSSY
        elif has_tool_calls and ctx.tool_policy == "inline":
            # Even inline is partial since it's not native
            status = LoweringStatus.PARTIAL
        elif any(
            l.severity in (DiagnosticSeverity.ERROR, DiagnosticSeverity.FATAL) for l in losses
        ):
            status = LoweringStatus.UNSUPPORTED
        elif any(l.severity == DiagnosticSeverity.WARNING for l in losses):
            status = LoweringStatus.LOSSY
        elif losses:
            status = LoweringStatus.PARTIAL
        else:
            status = LoweringStatus.EXACT

        # Build metadata
        metadata: dict[str, Any] = {
            "trajectory_id": record.record_id,
        }
        if record.source:
            if record.source.dataset:
                metadata["source_dataset"] = record.source.dataset
            if record.source.framework:
                metadata["source_framework"] = record.source.framework
        if record.outcome:
            metadata["reward"] = record.outcome.reward
            metadata["passed"] = record.outcome.passed

        output = {
            "conversations": conversations,
            "metadata": metadata,
        }

        return LoweringResult(
            output=output,
            report=LossReport(
                target=self.name,
                status=status,
                losses=losses,
                metrics={"conversation_turns": len(conversations)},
            ),
        )


register_backend(ShareGPTBackend())

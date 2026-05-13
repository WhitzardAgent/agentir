"""SFT (Supervised Fine-Tuning) backend.

Produces chat-style messages suitable for SFT training with tool-call support.
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
    """Extract plain-text content from an event."""
    parts: list[str] = []
    for block in event.content:
        if block.text is not None:
            parts.append(block.text)
        elif block.json_value is not None:
            parts.append(json.dumps(block.json_value, ensure_ascii=False))
    return "\n".join(parts)


def _obs_text(obs) -> str | None:
    """Extract text from an observation."""
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


class SFTBackend:
    """Lower AgentIR to SFT chat-message format."""

    name: str = "sft"

    def lower_record(self, record: AgentIRRecord, ctx: BackendContext) -> LoweringResult:
        losses: list[LossItem] = []
        messages: list[dict[str, Any]] = []
        has_assistant_output = False

        # Build a lookup for events by id so we can match tool results
        all_events: list[Any] = []
        for episode in record.episodes:
            all_events.extend(episode.events)

        event_by_id: dict[str, Any] = {e.event_id: e for e in all_events}

        # Collect tool_call_id -> tool result observation text
        tool_call_id_to_result: dict[str, str] = {}
        for event in all_events:
            if (
                event.event_type == EventType.TOOL_RESULT
                and event.action
                and event.action.tool_call_id
            ):
                text = _obs_text(event.observation) or ""
                tool_call_id_to_result[event.action.tool_call_id] = text

        for event in all_events:
            # Drop reasoning unless include_reasoning
            if event.event_type == EventType.REASONING:
                if not ctx.include_reasoning:
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.WARNING,
                            code="LOWER003",
                            field="reasoning",
                            message="Reasoning event dropped; target format cannot represent private reasoning blocks.",
                            event_id=event.event_id,
                            suggestion="Use --include-reasoning or --reasoning-policy metadata_only.",
                        )
                    )
                    continue
                # If included, emit as assistant message
                text = _content_text(event)
                if text:
                    messages.append({"role": "assistant", "content": text})
                continue

            # Plan events: treat like reasoning
            if event.event_type == EventType.PLAN:
                if not ctx.include_reasoning:
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.INFO,
                            code="LOWER004",
                            field="plan",
                            message="Plan event dropped.",
                            event_id=event.event_id,
                        )
                    )
                    continue
                text = _content_text(event)
                if text:
                    messages.append({"role": "assistant", "content": text})
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

            # Assistant message (plain, no tool calls)
            if event.event_type == EventType.ASSISTANT_MESSAGE:
                has_assistant_output = True
                text = _content_text(event)
                if text:
                    messages.append({"role": "assistant", "content": text})
                continue

            # Tool call
            if event.event_type == EventType.TOOL_CALL:
                has_assistant_output = True
                action = event.action
                if action is None:
                    continue

                tool_call_id = action.tool_call_id or f"call_{event.event_id}"
                if action.tool_call_id is None:
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.WARNING,
                            code="LOWER001",
                            field="tool_call_id",
                            message="Tool call lacks ID; generated stable ID.",
                            event_id=event.event_id,
                            suggestion="Ensure source provides tool_call_id.",
                        )
                    )

                # Any assistant text content alongside the tool call
                text = _content_text(event) or None

                tool_call_obj = {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": action.tool_name or "unknown",
                        "arguments": json.dumps(action.arguments, ensure_ascii=False),
                    },
                }

                msg: dict[str, Any] = {"role": "assistant"}
                if text:
                    msg["content"] = text
                else:
                    msg["content"] = None
                msg["tool_calls"] = [tool_call_obj]
                messages.append(msg)

                # Attach tool result
                result_text = tool_call_id_to_result.get(tool_call_id)
                if result_text is not None:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": result_text,
                        }
                    )
                continue

            # Tool result not already consumed
            if event.event_type == EventType.TOOL_RESULT:
                # Already handled above in the tool_call_id_to_result lookup
                # If orphan (no matching tool call), emit as tool message with best ID
                action = event.action
                obs_text = _obs_text(event.observation) or ""
                tc_id = action.tool_call_id if action else None
                if tc_id and tc_id not in tool_call_id_to_result:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": obs_text,
                        }
                    )
                continue

            # Terminal command -> treat as tool call
            if event.event_type == EventType.TERMINAL_COMMAND:
                has_assistant_output = True
                action = event.action
                command = action.arguments.get("command", "") if action else ""
                tc_id = (
                    action.tool_call_id
                    if action and action.tool_call_id
                    else f"call_{event.event_id}"
                )
                tool_call_obj = {
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": json.dumps({"command": command}, ensure_ascii=False),
                    },
                }
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tool_call_obj],
                    }
                )
                # Attach nearest terminal output
                obs_text = _obs_text(event.observation) if event.observation else ""
                if obs_text:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": obs_text,
                        }
                    )
                continue

            # Other action events as tool calls if they have an action
            if event.event_type in (
                EventType.FILE_WRITE,
                EventType.FILE_PATCH,
                EventType.BROWSER_ACTION,
            ):
                has_assistant_output = True
                action = event.action
                if action is None:
                    continue
                tc_id = action.tool_call_id or f"call_{event.event_id}"
                tool_call_obj = {
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": action.tool_name or event.event_type.value,
                        "arguments": json.dumps(action.arguments, ensure_ascii=False),
                    },
                }
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tool_call_obj],
                    }
                )
                obs_text = _obs_text(event.observation) if event.observation else ""
                if obs_text:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": obs_text,
                        }
                    )
                continue

            # Finish event
            if event.event_type == EventType.FINISH:
                text = _content_text(event)
                if text:
                    has_assistant_output = True
                    messages.append({"role": "assistant", "content": text})
                continue

            # Unhandled event types
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
                        message=f"Event type {event.event_type.value} not represented in SFT output.",
                        event_id=event.event_id,
                    )
                )
                continue

        if not has_assistant_output:
            losses.append(
                LossItem(
                    severity=DiagnosticSeverity.WARNING,
                    code="LOWER003",
                    field="messages",
                    message="SFT record has no assistant output.",
                    suggestion="Check source data for missing assistant turns.",
                )
            )

        # Determine status
        if any(l.severity in (DiagnosticSeverity.ERROR, DiagnosticSeverity.FATAL) for l in losses):
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
            "messages": messages,
            "metadata": metadata,
        }

        return LoweringResult(
            output=output,
            report=LossReport(
                target=self.name,
                status=status,
                losses=losses,
                metrics={"message_count": len(messages)},
            ),
        )


register_backend(SFTBackend())

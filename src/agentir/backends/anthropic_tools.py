"""Anthropic tools backend.

Produces messages in the Anthropic Messages API format with typed content
blocks: text, tool_use, and tool_result.
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


def _content_blocks(event) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in event.content:
        if block.text is not None:
            blocks.append({"type": "text", "text": block.text})
        elif block.json_value is not None:
            blocks.append(
                {"type": "text", "text": json.dumps(block.json_value, ensure_ascii=False)}
            )
    return blocks


def _obs_content_blocks(obs) -> list[dict[str, Any]]:
    if obs is None:
        return []
    blocks: list[dict[str, Any]] = []
    if obs.stdout:
        blocks.append({"type": "text", "text": obs.stdout})
    if obs.stderr:
        blocks.append({"type": "text", "text": obs.stderr})
    for block in obs.content:
        if block.text is not None:
            blocks.append({"type": "text", "text": block.text})
        elif block.json_value is not None:
            blocks.append(
                {"type": "text", "text": json.dumps(block.json_value, ensure_ascii=False)}
            )
    if obs.exit_code is not None:
        blocks.append({"type": "text", "text": f"Exit code: {obs.exit_code}"})
    return blocks


_TOOL_CALL_EVENTS = {
    EventType.TOOL_CALL,
    EventType.TERMINAL_COMMAND,
    EventType.FILE_WRITE,
    EventType.FILE_PATCH,
    EventType.BROWSER_ACTION,
}


class AnthropicToolsBackend:
    """Lower AgentIR to Anthropic Messages API format with tool_use/tool_result."""

    name: str = "anthropic-tools"

    def lower_record(self, record: AgentIRRecord, ctx: BackendContext) -> LoweringResult:
        losses: list[LossItem] = []
        messages: list[dict[str, Any]] = []

        all_events: list[Any] = []
        for episode in record.episodes:
            all_events.extend(episode.events)

        tool_call_id_to_result: dict[str, list[dict[str, Any]]] = {}
        for event in all_events:
            if (
                event.event_type == EventType.TOOL_RESULT
                and event.action
                and event.action.tool_call_id
            ):
                blocks = _obs_content_blocks(event.observation)
                tool_call_id_to_result[event.action.tool_call_id] = blocks

        emitted_results: set[str] = set()

        for event in all_events:
            if event.event_type == EventType.REASONING:
                if not ctx.include_reasoning:
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.INFO,
                            code="LOWER003",
                            field="reasoning",
                            message="Reasoning event dropped in anthropic-tools backend.",
                            event_id=event.event_id,
                        )
                    )
                    continue
                blocks = _content_blocks(event)
                if blocks:
                    messages.append({"role": "assistant", "content": blocks})
                continue

            if event.event_type == EventType.PLAN:
                if not ctx.include_reasoning:
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.INFO,
                            code="LOWER004",
                            field="plan",
                            message="Plan event dropped in anthropic-tools backend.",
                            event_id=event.event_id,
                        )
                    )
                    continue
                blocks = _content_blocks(event)
                if blocks:
                    messages.append({"role": "assistant", "content": blocks})
                continue

            if event.event_type == EventType.SYSTEM_MESSAGE:
                blocks = _content_blocks(event)
                if blocks:
                    messages.append({"role": "user", "content": blocks})
                continue

            if event.event_type == EventType.USER_MESSAGE:
                blocks = _content_blocks(event)
                if blocks:
                    messages.append({"role": "user", "content": blocks})
                continue

            if event.event_type == EventType.ASSISTANT_MESSAGE:
                blocks = _content_blocks(event)
                if blocks:
                    messages.append({"role": "assistant", "content": blocks})
                continue

            if event.event_type in _TOOL_CALL_EVENTS:
                action = event.action
                if action is None:
                    continue

                tool_call_id = action.tool_call_id
                if not tool_call_id:
                    tool_call_id = f"toolu_{event.event_id}"
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.WARNING,
                            code="LOWER001",
                            field="tool_call_id",
                            message="Tool call lacks ID; generated stable ID toolu_<event_id>.",
                            event_id=event.event_id,
                            suggestion="Ensure source provides tool_call_id.",
                        )
                    )

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

                tool_use_block: dict[str, Any] = {
                    "type": "tool_use",
                    "id": tool_call_id,
                    "name": tool_name,
                    "input": action.arguments,
                }

                content_blocks = _content_blocks(event)
                content_blocks.append(tool_use_block)

                messages.append({"role": "assistant", "content": content_blocks})

                if tool_call_id in tool_call_id_to_result:
                    result_blocks = tool_call_id_to_result[tool_call_id]
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_call_id,
                                    "content": result_blocks,
                                }
                            ],
                        }
                    )
                    emitted_results.add(tool_call_id)
                elif event.observation:
                    result_blocks = _obs_content_blocks(event.observation)
                    if result_blocks:
                        messages.append(
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": tool_call_id,
                                        "content": result_blocks,
                                    }
                                ],
                            }
                        )
                        emitted_results.add(tool_call_id)
                continue

            if event.event_type == EventType.TOOL_RESULT:
                action = event.action
                tc_id = action.tool_call_id if action else None
                if tc_id and tc_id not in emitted_results:
                    result_blocks = _obs_content_blocks(event.observation)
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tc_id,
                                    "content": result_blocks,
                                }
                            ],
                        }
                    )
                    emitted_results.add(tc_id)
                continue

            if event.event_type == EventType.FINISH:
                blocks = _content_blocks(event)
                if blocks:
                    messages.append({"role": "assistant", "content": blocks})
                continue

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
                        message=(
                            f"Event type {event.event_type.value} not represented "
                            "in anthropic-tools output."
                        ),
                        event_id=event.event_id,
                    )
                )
                continue

        tools_spec: list[dict[str, Any]] = []
        for tool in record.tool_registry:
            spec: dict[str, Any] = {"name": tool.name}
            if tool.description:
                spec["description"] = tool.description
            if tool.input_schema:
                spec["input_schema"] = tool.input_schema
            tools_spec.append(spec)

        if any(
            item.severity in (DiagnosticSeverity.ERROR, DiagnosticSeverity.FATAL)
            for item in losses
        ):
            status = LoweringStatus.UNSUPPORTED
        elif any(item.severity == DiagnosticSeverity.WARNING for item in losses):
            status = LoweringStatus.LOSSY
        elif losses:
            status = LoweringStatus.PARTIAL
        else:
            status = LoweringStatus.EXACT

        output: dict[str, Any] = {"messages": messages}
        if tools_spec:
            output["tools"] = tools_spec

        return LoweringResult(
            output=output,
            report=LossReport(
                target=self.name,
                status=status,
                losses=losses,
                metrics={"message_count": len(messages), "tools_count": len(tools_spec)},
            ),
        )


register_backend(AnthropicToolsBackend())

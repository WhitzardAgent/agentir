"""OpenHands backend.

Produces trajectory data in the OpenHands format with native tool_calls
and model_patch extraction from patch artifacts.
"""

from __future__ import annotations

import json
from typing import Any

from agentir.backends.base import BackendContext
from agentir.backends.loss import LossItem, LossReport, LoweringResult
from agentir.backends.registry import register_backend
from agentir.ir.base import (
    ArtifactKind,
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


class OpenHandsBackend:
    """Lower AgentIR to OpenHands trajectory format."""

    name: str = "openhands"

    def lower_record(self, record: AgentIRRecord, ctx: BackendContext) -> LoweringResult:
        losses: list[LossItem] = []
        trajectory: list[dict[str, Any]] = []

        all_events: list[Any] = []
        for episode in record.episodes:
            all_events.extend(episode.events)

        # Build artifact lookup
        artifacts_by_id: dict[str, Any] = {}
        for artifact in record.artifacts:
            artifacts_by_id[artifact.artifact_id] = artifact

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

        emitted_results: set[str] = set()

        # Extract model_patch from patch artifacts
        model_patch = ""
        for artifact in record.artifacts:
            if artifact.kind == ArtifactKind.PATCH and artifact.content:
                model_patch = artifact.content
                break
        # Also check outcome's final_patch_artifact_id
        if not model_patch and record.outcome and record.outcome.final_patch_artifact_id:
            patch_art = artifacts_by_id.get(record.outcome.final_patch_artifact_id)
            if patch_art and patch_art.content:
                model_patch = patch_art.content

        # Report lossy for non-coding artifacts that can't be represented
        non_coding_kinds = {
            ArtifactKind.SCREENSHOT,
            ArtifactKind.WEBPAGE,
            ArtifactKind.BINARY,
            ArtifactKind.DATASET_ROW,
        }
        for artifact in record.artifacts:
            if artifact.kind in non_coding_kinds:
                losses.append(
                    LossItem(
                        severity=DiagnosticSeverity.WARNING,
                        code="LOWER006",
                        field="artifact",
                        message=f"Non-coding artifact of kind {artifact.kind.value} cannot be represented in OpenHands format.",
                        event_id=artifact.created_by_event_id,
                        suggestion="Consider pre-processing non-coding artifacts before lowering.",
                    )
                )

        for event in all_events:
            # Drop reasoning
            if event.event_type == EventType.REASONING:
                losses.append(
                    LossItem(
                        severity=DiagnosticSeverity.INFO,
                        code="LOWER003",
                        field="reasoning",
                        message="Reasoning event dropped in openhands backend.",
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
                        message="Plan event dropped in openhands backend.",
                        event_id=event.event_id,
                    )
                )
                continue

            # System message
            if event.event_type == EventType.SYSTEM_MESSAGE:
                text = _content_text(event)
                if text:
                    trajectory.append({"role": "user", "content": text})
                continue

            # User message
            if event.event_type == EventType.USER_MESSAGE:
                text = _content_text(event)
                if text:
                    trajectory.append({"role": "user", "content": text})
                continue

            # Assistant message (no tool calls)
            if event.event_type == EventType.ASSISTANT_MESSAGE:
                text = _content_text(event)
                if text:
                    trajectory.append({"role": "assistant", "content": text})
                continue

            # Tool call events
            if event.event_type in _TOOL_CALL_EVENTS:
                action = event.action
                if action is None:
                    continue

                tool_call_id = action.tool_call_id or f"call_{event.event_id}"
                if not action.tool_call_id:
                    losses.append(
                        LossItem(
                            severity=DiagnosticSeverity.WARNING,
                            code="LOWER001",
                            field="tool_call_id",
                            message="Tool call lacks ID; generated stable ID.",
                            event_id=event.event_id,
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

                text = _content_text(event) or None

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
                trajectory.append(msg)

                # Tool result
                if tool_call_id in tool_call_id_to_result:
                    trajectory.append(
                        {
                            "role": "tool",
                            "content": tool_call_id_to_result[tool_call_id],
                            "tool_call_id": tool_call_id,
                        }
                    )
                    emitted_results.add(tool_call_id)
                elif event.observation:
                    obs_text = _obs_text(event.observation)
                    if obs_text:
                        trajectory.append(
                            {
                                "role": "tool",
                                "content": obs_text,
                                "tool_call_id": tool_call_id,
                            }
                        )
                        emitted_results.add(tool_call_id)
                continue

            # Tool result events not consumed
            if event.event_type == EventType.TOOL_RESULT:
                action = event.action
                tc_id = action.tool_call_id if action else None
                if tc_id and tc_id not in emitted_results:
                    obs_text = _obs_text(event.observation) or ""
                    trajectory.append(
                        {
                            "role": "tool",
                            "content": obs_text,
                            "tool_call_id": tc_id,
                        }
                    )
                    emitted_results.add(tc_id)
                continue

            # Finish
            if event.event_type == EventType.FINISH:
                text = _content_text(event)
                if text:
                    trajectory.append({"role": "assistant", "content": text})
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
                        message=f"Event type {event.event_type.value} not represented in openhands output.",
                        event_id=event.event_id,
                    )
                )
                continue

        # Determine repo from metadata or source
        repo = record.metadata.get("repo", "")
        if not repo and record.source:
            repo = record.source.dataset or ""

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
            "trajectory_id": record.record_id,
            "repo": repo,
            "trajectory": trajectory,
            "model_patch": model_patch,
        }

        return LoweringResult(
            output=output,
            report=LossReport(
                target=self.name,
                status=status,
                losses=losses,
                metrics={"trajectory_turns": len(trajectory)},
            ),
        )


register_backend(OpenHandsBackend())

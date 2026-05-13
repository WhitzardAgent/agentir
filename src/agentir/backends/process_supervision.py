"""Process-supervision backend.

Produces step-level trajectory data with per-step label placeholders
for process reward model training.
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

# Event types that become steps
_STEP_EVENT_TYPES = {
    EventType.TOOL_CALL,
    EventType.TERMINAL_COMMAND,
    EventType.FILE_WRITE,
    EventType.FILE_PATCH,
    EventType.BROWSER_ACTION,
}


def _content_text(event) -> str:
    parts: list[str] = []
    for block in event.content:
        if block.text is not None:
            parts.append(block.text)
        elif block.json_value is not None:
            parts.append(json.dumps(block.json_value, ensure_ascii=False))
    return "\n".join(parts)


def _obs_dict(obs) -> dict[str, Any] | None:
    """Convert an Observation to a plain dict."""
    if obs is None:
        return None
    result: dict[str, Any] = {"kind": obs.kind.value}
    if obs.stdout:
        result["stdout"] = obs.stdout
    if obs.stderr:
        result["stderr"] = obs.stderr
    if obs.exit_code is not None:
        result["exit_code"] = obs.exit_code
    if obs.truncated:
        result["truncated"] = True
    for block in obs.content:
        if block.text is not None:
            result.setdefault("content_parts", []).append({"type": "text", "text": block.text})
        elif block.json_value is not None:
            result.setdefault("content_parts", []).append(
                {"type": "json", "value": block.json_value}
            )
    return result


def _find_nearest_observation(events: list, start_idx: int) -> dict[str, Any] | None:
    """Find the nearest following observation/tool_result event."""
    for j in range(start_idx + 1, len(events)):
        evt = events[j]
        if evt.event_type in (
            EventType.TOOL_RESULT,
            EventType.TERMINAL_OUTPUT,
            EventType.BROWSER_OBSERVATION,
        ):
            return _obs_dict(evt.observation)
        # If we hit another action event, stop looking
        if evt.event_type in _STEP_EVENT_TYPES or evt.event_type == EventType.TOOL_CALL:
            break
    return None


class ProcessSupervisionBackend:
    """Lower AgentIR to process-supervision step format."""

    name: str = "process-supervision"

    def lower_record(self, record: AgentIRRecord, ctx: BackendContext) -> LoweringResult:
        losses: list[LossItem] = []
        steps: list[dict[str, Any]] = []

        for episode in record.episodes:
            events = list(episode.events)

            for i, event in enumerate(events):
                if event.event_type not in _STEP_EVENT_TYPES:
                    continue

                action = event.action
                action_dict: dict[str, Any] = {"event_type": event.event_type.value}
                if action:
                    action_dict["tool_name"] = action.tool_name
                    action_dict["tool_call_id"] = action.tool_call_id
                    action_dict["arguments"] = action.arguments
                else:
                    # Try to infer from content
                    action_dict["raw_content"] = _content_text(event)

                # State: content from the event itself
                state: dict[str, Any] = {}
                text = _content_text(event)
                if text:
                    state["text"] = text
                if event.observation:
                    state["observation"] = _obs_dict(event.observation)

                # Observation: nearest following observation
                obs = _find_nearest_observation(events, i)

                step = {
                    "step_id": event.event_id,
                    "state": state,
                    "action": action_dict,
                    "observation": obs,
                    "label": {
                        "is_progress": None,
                        "failure_type": None,
                    },
                }
                steps.append(step)

        # Outcome
        outcome_dict: dict[str, Any] | None = None
        if record.outcome:
            outcome_dict = {
                "status": record.outcome.status.value,
            }
            if record.outcome.reward is not None:
                outcome_dict["reward"] = record.outcome.reward
            if record.outcome.passed is not None:
                outcome_dict["passed"] = record.outcome.passed
            if record.outcome.failure_reason is not None:
                outcome_dict["failure_reason"] = record.outcome.failure_reason.value

        # Metadata
        metadata: dict[str, Any] = {
            "ir_version": record.ir_version,
            "step_count": len(steps),
        }
        if record.source and record.source.dataset:
            metadata["source_dataset"] = record.source.dataset
        if record.source and record.source.framework:
            metadata["source_framework"] = record.source.framework

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
            "steps": steps,
            "outcome": outcome_dict,
            "metadata": metadata,
        }

        return LoweringResult(
            output=output,
            report=LossReport(
                target=self.name,
                status=status,
                losses=losses,
                metrics={"step_count": len(steps)},
            ),
        )


register_backend(ProcessSupervisionBackend())

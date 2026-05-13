"""Frontend for the OpenHands dataset (nvidia/SWE-Hero-openhands-trajectories)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.frontends.base import BaseFrontend, FrontendContext, FrontendResult
from agentir.frontends.registry import register_frontend
from agentir.ir import (
    AgentIRRecord,
    Artifact,
    ArtifactKind,
    CallStyle,
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
    SideEffectLevel,
    SourceRef,
    TaskSpec,
)
from agentir.ir.action import Action
from agentir.ir.base import ActionKind, DiagnosticSeverity

_ROLE_MAP: dict[str, MessageRole] = {
    "system": MessageRole.SYSTEM,
    "user": MessageRole.USER,
    "assistant": MessageRole.ASSISTANT,
    "tool": MessageRole.TOOL,
    "developer": MessageRole.DEVELOPER,
}

_ROLE_EVENT_TYPE_MAP: dict[MessageRole, EventType] = {
    MessageRole.SYSTEM: EventType.SYSTEM_MESSAGE,
    MessageRole.USER: EventType.USER_MESSAGE,
    MessageRole.ASSISTANT: EventType.ASSISTANT_MESSAGE,
    MessageRole.DEVELOPER: EventType.SYSTEM_MESSAGE,
}


def _resolve_role(raw_role: str) -> MessageRole:
    return _ROLE_MAP.get(raw_role.lower().strip(), MessageRole.UNKNOWN)


def _extract_text_content(message: Mapping[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return ""


class OpenHandsFrontend(BaseFrontend):
    name = "openhands"

    def detect(self, sample: Mapping[str, Any]) -> float:
        hits = 0
        total = 4
        if "trajectory" in sample and isinstance(sample.get("trajectory"), list):
            hits += 1
        if "trajectory_id" in sample and sample["trajectory_id"] is not None:
            hits += 1
        if "model_patch" in sample and sample["model_patch"] is not None:
            hits += 1
        if "repo" in sample and sample["repo"] is not None:
            hits += 1
        return hits / total

    def parse_record(self, sample: Mapping[str, Any], ctx: FrontendContext) -> FrontendResult:
        diagnostics: list[Diagnostic] = []
        events: list[Event] = []
        artifacts: list[Artifact] = []

        trajectory_id = sample.get("trajectory_id")
        record_id = (
            str(trajectory_id)
            if trajectory_id is not None
            else (f"openhands-row-{ctx.row_index}" if ctx.row_index is not None else "unknown")
        )

        source = SourceRef(
            dataset=ctx.dataset,
            dataset_url=ctx.dataset_url,
            config=ctx.config,
            split=ctx.split,
            row_id=str(trajectory_id) if trajectory_id is not None else None,
            row_index=ctx.row_index,
            framework="openhands",
            format="openhands-trajectory",
            license=sample.get("license"),
        )

        task = TaskSpec(repo=sample.get("repo"))

        trajectory = sample.get("trajectory", [])
        if not isinstance(trajectory, list):
            trajectory = []
            diagnostics.append(
                Diagnostic(
                    code="DATA002",
                    severity=DiagnosticSeverity.WARNING,
                    message="trajectory field is not a list",
                )
            )

        event_idx = 0
        for msg in trajectory:
            if not isinstance(msg, dict):
                continue

            raw_role = msg.get("role", "")
            role = _resolve_role(raw_role)
            text = _extract_text_content(msg)
            tool_calls = msg.get("tool_calls")

            if role == MessageRole.TOOL:
                tool_call_id = msg.get("tool_call_id")
                event = Event(
                    event_id=f"{record_id}-evt-{event_idx}",
                    idx=event_idx,
                    event_type=EventType.TOOL_RESULT,
                    role=role,
                    content=[ContentBlock(type=ContentType.TEXT, text=text)] if text else [],
                    provenance=Provenance(
                        parser="openhands",
                        source_field="trajectory",
                        confidence=1.0,
                    ),
                    raw=dict(msg),
                )
                if tool_call_id is not None:
                    event.action = Action(
                        kind=ActionKind.GENERIC_TOOL,
                        tool_call_id=str(tool_call_id),
                        call_style=CallStyle.NATIVE_TOOL_CALL,
                    )
                events.append(event)
                event_idx += 1
                continue

            if role == MessageRole.ASSISTANT and tool_calls and isinstance(tool_calls, list):
                if text:
                    events.append(
                        Event(
                            event_id=f"{record_id}-evt-{event_idx}",
                            idx=event_idx,
                            event_type=EventType.ASSISTANT_MESSAGE,
                            role=role,
                            content=[ContentBlock(type=ContentType.TEXT, text=text)],
                            provenance=Provenance(
                                parser="openhands",
                                source_field="trajectory",
                                confidence=1.0,
                            ),
                            raw=dict(msg),
                        )
                    )
                    event_idx += 1

                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    func = tc.get("function", {})
                    tool_name = func.get("name") if isinstance(func, dict) else None
                    arguments_raw = func.get("arguments") if isinstance(func, dict) else None
                    arguments: dict[str, Any] = {}
                    if isinstance(arguments_raw, str):
                        try:
                            arguments = json.loads(arguments_raw)
                        except json.JSONDecodeError:
                            arguments = {"_raw": arguments_raw}
                    elif isinstance(arguments_raw, dict):
                        arguments = arguments_raw

                    tc_id = tc.get("id")
                    events.append(
                        Event(
                            event_id=f"{record_id}-evt-{event_idx}",
                            idx=event_idx,
                            event_type=EventType.TOOL_CALL,
                            role=role,
                            action=Action(
                                kind=ActionKind.GENERIC_TOOL,
                                tool_name=tool_name,
                                tool_call_id=str(tc_id) if tc_id is not None else None,
                                arguments=arguments,
                                call_style=CallStyle.NATIVE_TOOL_CALL,
                                side_effect_level=SideEffectLevel.UNKNOWN,
                            ),
                            provenance=Provenance(
                                parser="openhands",
                                source_field="trajectory.tool_calls",
                                confidence=1.0,
                            ),
                            raw=dict(tc),
                        )
                    )
                    event_idx += 1
                continue

            event_type = _ROLE_EVENT_TYPE_MAP.get(role, EventType.UNPARSED_FRAGMENT)
            events.append(
                Event(
                    event_id=f"{record_id}-evt-{event_idx}",
                    idx=event_idx,
                    event_type=event_type,
                    role=role,
                    content=[ContentBlock(type=ContentType.TEXT, text=text)] if text else [],
                    provenance=Provenance(
                        parser="openhands",
                        source_field="trajectory",
                        confidence=1.0,
                    ),
                    raw=dict(msg),
                )
            )
            event_idx += 1

        model_patch = sample.get("model_patch")
        patch_artifact_id: str | None = None
        if model_patch is not None:
            patch_artifact_id = f"{record_id}-patch"
            artifacts.append(
                Artifact(
                    artifact_id=patch_artifact_id,
                    kind=ArtifactKind.PATCH,
                    content=str(model_patch),
                )
            )

        outcome = Outcome(
            status=OutcomeStatus.UNKNOWN,
            final_patch_artifact_id=patch_artifact_id,
        )

        episode = Episode(
            episode_id=f"{record_id}-ep-0",
            events=events,
            outcome=outcome,
        )

        record = AgentIRRecord(
            record_id=record_id,
            level=IRLevel.PARSED,
            source=source,
            task=task,
            episodes=[episode],
            artifacts=artifacts,
            outcome=outcome,
            raw={"record": dict(sample)},
        )

        return FrontendResult(record=record, diagnostics=diagnostics)


register_frontend(OpenHandsFrontend())

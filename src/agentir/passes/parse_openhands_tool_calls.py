"""Pass that processes OpenHands structured tool_calls from trajectory messages."""

from __future__ import annotations

import json
from typing import Any

from agentir.diagnostics.codes import DiagnosticCodes, make_diagnostic
from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.action import Action
from agentir.ir.artifact import Artifact
from agentir.ir.base import (
    ActionKind,
    ArtifactKind,
    CallStyle,
    ContentType,
    EventType,
    IRLevel,
    MessageRole,
    PassKind,
    SideEffectLevel,
)
from agentir.ir.content import ContentBlock
from agentir.ir.episode import Episode
from agentir.ir.event import Event
from agentir.ir.outcome import Outcome
from agentir.ir.provenance import Provenance
from agentir.ir.record import AgentIRRecord
from agentir.ir.visibility import Visibility
from agentir.passes.base import AgentIRPass, PassContext, PassResult
from agentir.passes.registry import register_pass


def _infer_action_kind(tool_name: str) -> ActionKind:
    """Map an OpenHands tool name to an ActionKind."""
    mapping: dict[str, ActionKind] = {
        "run": ActionKind.TERMINAL,
        "run_ipython": ActionKind.TERMINAL,
        "execute_bash": ActionKind.TERMINAL,
        "str_replace_editor": ActionKind.FILE_WRITE,
        "file_editor": ActionKind.FILE_WRITE,
        "browser": ActionKind.BROWSER,
        "browse": ActionKind.BROWSER,
        "think": ActionKind.PLANNER,
        "finish": ActionKind.FINISH,
    }
    return mapping.get(tool_name, ActionKind.GENERIC_TOOL)


def _infer_side_effect(tool_name: str) -> SideEffectLevel:
    """Heuristic side-effect level from the tool name."""
    read_tools = {"read", "view", "cat", "ls", "glob", "grep", "find", "head", "tail"}
    if tool_name.lower() in read_tools:
        return SideEffectLevel.READ_ONLY
    if tool_name.lower() in ("think", "plan", "finish"):
        return SideEffectLevel.NONE
    if tool_name.lower() in ("browser", "browse"):
        return SideEffectLevel.NETWORK
    return SideEffectLevel.WORKSPACE_WRITE


class ParseOpenHandsToolCallsPass(AgentIRPass):
    """Parse structured tool_calls from OpenHands trajectory messages.

    OpenHands trajectories store tool invocations as ``tool_calls`` lists on
    assistant messages (ChatML-style).  Each entry has ``id``, ``function.name``,
    and ``function.arguments``.  The corresponding tool-role message carries the
    result.  This pass converts those structures into proper TOOL_CALL and
    TOOL_RESULT events.
    """

    name = "parse-openhands-tool-calls"
    kind = PassKind.PARSE

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult:
        diagnostics: list[Diagnostic] = []
        raw_messages = record.raw.get("messages", [])
        if not isinstance(raw_messages, list) or not raw_messages:
            return PassResult(record=record, diagnostics=diagnostics)

        # Collect existing events and track IDs to avoid collisions.
        events: list[Event] = []
        for ep in record.episodes:
            events.extend(ep.events)
        existing_ids = {e.event_id for e in events}
        idx = len(events)

        # Build a lookup from tool_call_id -> tool_call Event so we can link
        # tool_result events to their parent tool_call.
        call_id_to_event_id: dict[str, str] = {}

        for msg_idx, msg in enumerate(raw_messages):
            if not isinstance(msg, dict):
                continue

            role = msg.get("role", "")
            tool_calls_raw = msg.get("tool_calls")

            # --- Assistant message with structured tool_calls ---
            if role == "assistant" and isinstance(tool_calls_raw, list):
                # First emit the assistant text content (if any) as an
                # ASSISTANT_MESSAGE event so we preserve the original message.
                text_content = msg.get("content")
                if text_content:
                    if isinstance(text_content, list):
                        # Content may be a list of parts
                        text_parts = []
                        for part in text_content:
                            if isinstance(part, dict):
                                text_parts.append(part.get("text", ""))
                            else:
                                text_parts.append(str(part))
                        text_content = "\n".join(text_parts)
                    if isinstance(text_content, str) and text_content.strip():
                        evt_id = f"evt_{idx:04d}"
                        while evt_id in existing_ids:
                            idx += 1
                            evt_id = f"evt_{idx:04d}"
                        events.append(
                            Event(
                                event_id=evt_id,
                                idx=idx,
                                event_type=EventType.ASSISTANT_MESSAGE,
                                role=MessageRole.ASSISTANT,
                                content=[
                                    ContentBlock(
                                        type=ContentType.TEXT,
                                        text=text_content,
                                    )
                                ],
                                provenance=Provenance(
                                    source_field=f"messages[{msg_idx}].content",
                                    confidence=1.0,
                                    parser=self.name,
                                ),
                                visibility=Visibility(),
                                raw={"original_message_index": msg_idx},
                            )
                        )
                        existing_ids.add(evt_id)
                        idx += 1

                # Emit a TOOL_CALL event for each structured tool_call.
                for tc_idx, tc in enumerate(tool_calls_raw):
                    if not isinstance(tc, dict):
                        continue

                    tc_id = tc.get("id") or f"tc_{msg_idx}_{tc_idx}"
                    func = tc.get("function", {})
                    tool_name = func.get("name", "unknown") if isinstance(func, dict) else "unknown"
                    raw_args = func.get("arguments", "{}") if isinstance(func, dict) else "{}"

                    # Parse arguments – they are typically a JSON string.
                    parsed_args: dict[str, Any] = {}
                    if isinstance(raw_args, str):
                        try:
                            parsed_args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            parsed_args = {"_raw": raw_args}
                            diagnostics.append(
                                make_diagnostic(
                                    DiagnosticCodes.PARSE003,
                                    event_id=tc_id,
                                    field=f"messages[{msg_idx}].tool_calls[{tc_idx}].function.arguments",
                                    suggestion="Fix malformed JSON in tool call arguments",
                                )
                            )
                    elif isinstance(raw_args, dict):
                        parsed_args = raw_args

                    evt_id = f"evt_{idx:04d}"
                    while evt_id in existing_ids:
                        idx += 1
                        evt_id = f"evt_{idx:04d}"

                    action_kind = _infer_action_kind(tool_name)
                    side_effect = _infer_side_effect(tool_name)

                    events.append(
                        Event(
                            event_id=evt_id,
                            idx=idx,
                            event_type=EventType.TOOL_CALL,
                            role=MessageRole.ASSISTANT,
                            action=Action(
                                kind=action_kind,
                                tool_name=tool_name,
                                tool_call_id=tc_id,
                                arguments=parsed_args,
                                normalized_arguments=parsed_args,
                                call_style=CallStyle.NATIVE_TOOL_CALL,
                                side_effect_level=side_effect,
                            ),
                            provenance=Provenance(
                                source_field=f"messages[{msg_idx}].tool_calls[{tc_idx}]",
                                confidence=1.0,
                                parser=self.name,
                            ),
                            visibility=Visibility(),
                            raw={
                                "original_message_index": msg_idx,
                                "tool_call_index": tc_idx,
                            },
                        )
                    )
                    existing_ids.add(evt_id)
                    call_id_to_event_id[tc_id] = evt_id
                    idx += 1

            # --- Tool role message (tool result) ---
            elif role == "tool":
                tc_id = msg.get("tool_call_id", "")
                result_text = msg.get("content", "")
                if isinstance(result_text, list):
                    result_text = "\n".join(
                        p.get("text", "") if isinstance(p, dict) else str(p) for p in result_text
                    )
                if not isinstance(result_text, str):
                    result_text = str(result_text)

                parent_event_id = call_id_to_event_id.get(tc_id)

                evt_id = f"evt_{idx:04d}"
                while evt_id in existing_ids:
                    idx += 1
                    evt_id = f"evt_{idx:04d}"

                evt = Event(
                    event_id=evt_id,
                    idx=idx,
                    event_type=EventType.TOOL_RESULT,
                    role=MessageRole.TOOL,
                    content=[
                        ContentBlock(
                            type=ContentType.TEXT,
                            text=result_text,
                        )
                    ],
                    provenance=Provenance(
                        source_field=f"messages[{msg_idx}]",
                        confidence=1.0,
                        parser=self.name,
                    ),
                    visibility=Visibility(),
                    raw={"original_message_index": msg_idx, "tool_call_id": tc_id},
                )
                if parent_event_id:
                    evt.parent_event_ids = [parent_event_id]
                events.append(evt)
                existing_ids.add(evt_id)

                # Link parent -> child.
                if parent_event_id:
                    for e in events:
                        if e.event_id == parent_event_id:
                            e.child_event_ids.append(evt_id)
                            break

                idx += 1

            # --- Other roles (system, user) ---
            elif role in ("system", "user", "developer"):
                text_content = msg.get("content", "")
                if isinstance(text_content, list):
                    text_parts = []
                    for part in text_content:
                        if isinstance(part, dict):
                            text_parts.append(part.get("text", ""))
                        else:
                            text_parts.append(str(part))
                    text_content = "\n".join(text_parts)
                if not isinstance(text_content, str):
                    text_content = str(text_content)

                event_type = {
                    "system": EventType.SYSTEM_MESSAGE,
                    "user": EventType.USER_MESSAGE,
                    "developer": EventType.SYSTEM_MESSAGE,
                }.get(role, EventType.UNPARSED_FRAGMENT)
                msg_role = {
                    "system": MessageRole.SYSTEM,
                    "user": MessageRole.USER,
                    "developer": MessageRole.DEVELOPER,
                }.get(role, MessageRole.UNKNOWN)

                evt_id = f"evt_{idx:04d}"
                while evt_id in existing_ids:
                    idx += 1
                    evt_id = f"evt_{idx:04d}"

                events.append(
                    Event(
                        event_id=evt_id,
                        idx=idx,
                        event_type=event_type,
                        role=msg_role,
                        content=[ContentBlock(type=ContentType.TEXT, text=text_content)],
                        provenance=Provenance(
                            source_field=f"messages[{msg_idx}]",
                            confidence=1.0,
                            parser=self.name,
                        ),
                        visibility=Visibility(),
                        raw={"original_message_index": msg_idx},
                    )
                )
                existing_ids.add(evt_id)
                idx += 1

        # --- Handle model_patch as a final patch artifact ---
        model_patch = record.raw.get("model_patch") or record.raw.get("patch")
        if model_patch and isinstance(model_patch, str) and model_patch.strip():
            artifact_id = "artifact_model_patch"
            patch_artifact = Artifact(
                artifact_id=artifact_id,
                kind=ArtifactKind.PATCH,
                content=model_patch,
                created_by_event_id=events[-1].event_id if events else None,
                metadata={"source": "model_patch"},
            )

            # Attach artifact to the record.
            existing_artifacts = list(record.artifacts)
            existing_artifact_ids = {a.artifact_id for a in existing_artifacts}
            if artifact_id not in existing_artifact_ids:
                existing_artifacts.append(patch_artifact)

            # Update the outcome to reference the patch.
            outcome = record.outcome or Outcome()
            if not outcome.final_patch_artifact_id:
                outcome = Outcome(
                    status=outcome.status,
                    reward=outcome.reward,
                    passed=outcome.passed,
                    verifier=outcome.verifier,
                    final_answer=outcome.final_answer,
                    final_patch_artifact_id=artifact_id,
                    failure_reason=outcome.failure_reason,
                    metrics=outcome.metrics,
                    metadata=outcome.metadata,
                )

            record = record.model_copy(
                update={
                    "artifacts": existing_artifacts,
                    "outcome": outcome,
                }
            )

        # --- Rebuild episodes with new events ---
        new_episodes = list(record.episodes)
        if not new_episodes:
            new_episodes.append(Episode(episode_id="ep_0001", events=events))
        else:
            first = new_episodes[0]
            new_episodes[0] = Episode(
                episode_id=first.episode_id,
                task_id=first.task_id,
                attempt_id=first.attempt_id,
                parent_episode_id=first.parent_episode_id,
                segments=first.segments,
                events=events,
                state_timeline=first.state_timeline,
                outcome=first.outcome,
                metadata=first.metadata,
            )

        updated = record.model_copy(
            update={
                "episodes": new_episodes,
                "level": IRLevel.PARSED,
            }
        )
        return PassResult(record=updated, diagnostics=diagnostics)


register_pass(ParseOpenHandsToolCallsPass())

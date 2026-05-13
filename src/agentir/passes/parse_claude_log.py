"""Parse pass for Claude Code specific log fields.

Processes messages_json, tools_json, assistant_response, and gitdiff
fields found in raw.record and produces canonical AgentIR events,
artifacts, tool specs, and diagnostics.
"""

from __future__ import annotations

import hashlib
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
    ObservationKind,
    PassKind,
    SideEffectLevel,
)
from agentir.ir.content import ContentBlock
from agentir.ir.episode import Episode
from agentir.ir.event import Event
from agentir.ir.observation import Observation
from agentir.ir.provenance import Provenance
from agentir.ir.record import AgentIRRecord
from agentir.ir.tool import ToolSpec
from agentir.ir.visibility import Visibility
from agentir.passes.base import AgentIRPass, PassContext, PassResult
from agentir.passes.registry import register_pass

# Map Claude message role strings to MessageRole / EventType
_ROLE_MAP: dict[str, tuple[MessageRole, EventType]] = {
    "user": (MessageRole.USER, EventType.USER_MESSAGE),
    "assistant": (MessageRole.ASSISTANT, EventType.ASSISTANT_MESSAGE),
    "system": (MessageRole.SYSTEM, EventType.SYSTEM_MESSAGE),
    "tool": (MessageRole.TOOL, EventType.TOOL_RESULT),
    "tool_result": (MessageRole.TOOL, EventType.TOOL_RESULT),
}


def _parse_messages_json(
    messages: list[dict[str, Any]],
    *,
    start_idx: int,
    existing_ids: set[str],
    parser_name: str,
) -> tuple[list[Event], list[Diagnostic]]:
    """Parse a *messages_json* list into Event objects.

    Tool calls embedded inside assistant content blocks are marked with
    ``call_style=INFERRED`` and ``confidence <= 0.7`` per the spec.
    """
    events: list[Event] = []
    diagnostics: list[Diagnostic] = []
    idx = start_idx

    for i, msg in enumerate(messages):
        raw_role = msg.get("role", "unknown")
        role, event_type = _ROLE_MAP.get(
            raw_role, (MessageRole.UNKNOWN, EventType.UNPARSED_FRAGMENT)
        )

        # Build content blocks ------------------------------------------------
        content_blocks: list[ContentBlock] = []
        action: Action | None = None
        observation: Observation | None = None
        parent_ids: list[str] = []

        # Standard text / content field
        text = msg.get("content", "")
        if isinstance(text, str):
            if text:
                content_blocks.append(ContentBlock(type=ContentType.TEXT, text=text))
        elif isinstance(text, list):
            # Claude format: content is a list of content-block dicts
            for block in text:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "text":
                    block_text = block.get("text", "")
                    if block_text:
                        content_blocks.append(ContentBlock(type=ContentType.TEXT, text=block_text))
                elif btype == "tool_use":
                    # Native tool call within assistant message
                    tool_name = block.get("name", "unknown")
                    tool_call_id = block.get("id")
                    tool_input = block.get("input", {})
                    action = Action(
                        kind=ActionKind.GENERIC_TOOL,
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        arguments=tool_input if isinstance(tool_input, dict) else {},
                        call_style=CallStyle.NATIVE_TOOL_CALL,
                        side_effect_level=SideEffectLevel.UNKNOWN,
                    )
                elif btype == "tool_result":
                    # Tool result content block
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        result_content = [ContentBlock(type=ContentType.TEXT, text=result_content)]
                    elif isinstance(result_content, list):
                        result_content = [
                            ContentBlock(
                                type=ContentType.TEXT,
                                text=b.get("text", str(b)) if isinstance(b, dict) else str(b),
                            )
                            for b in result_content
                        ]
                    else:
                        result_content = []
                    observation = Observation(
                        kind=ObservationKind.TOOL_JSON,
                        content=result_content,
                    )
                elif btype == "thinking":
                    block_text = block.get("thinking", "")
                    if block_text:
                        content_blocks.append(ContentBlock(type=ContentType.TEXT, text=block_text))
                else:
                    # Unknown block type -- store as raw JSON
                    content_blocks.append(ContentBlock(type=ContentType.JSON, json_value=block))

        # Handle top-level tool_calls (OpenAI-style) as INFERRED ----------------
        tool_calls = msg.get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                func = tc.get("function", {})
                action = Action(
                    kind=ActionKind.GENERIC_TOOL,
                    tool_name=func.get("name", "unknown"),
                    tool_call_id=tc.get("id"),
                    arguments=func.get("arguments", {}),
                    call_style=CallStyle.INFERRED,
                    side_effect_level=SideEffectLevel.UNKNOWN,
                    metadata={"confidence": 0.7},
                )

        # If assistant message has tool-use-like content in plain text,
        # treat it as INFERRED.  We detect heuristics: the text contains
        # something that looks like a tool invocation (e.g. XML-style tags
        # or function-call patterns) but was not structured as a
        # native tool_use block.
        if role == MessageRole.ASSISTANT and action is None and content_blocks:
            combined = " ".join(cb.text for cb in content_blocks if cb.text)
            if _looks_like_tool_call(combined):
                action = Action(
                    kind=ActionKind.GENERIC_TOOL,
                    tool_name="unknown",
                    call_style=CallStyle.INFERRED,
                    side_effect_level=SideEffectLevel.UNKNOWN,
                    metadata={"confidence": 0.7},
                )

        # Empty assistant response diagnostic ----------------------------------
        if role == MessageRole.ASSISTANT and not content_blocks and action is None:
            diagnostics.append(
                make_diagnostic(
                    DiagnosticCodes.DATA001,
                    field="assistant_response",
                    suggestion="Assistant response is empty; check for truncated log.",
                )
            )

        # Generate unique event id ---------------------------------------------
        event_id = f"evt_{idx:04d}"
        while event_id in existing_ids:
            idx += 1
            event_id = f"evt_{idx:04d}"

        prov = Provenance(
            source_field=f"messages_json[{i}]",
            parser=parser_name,
            confidence=0.7 if (action and action.call_style == CallStyle.INFERRED) else 0.9,
        )

        events.append(
            Event(
                event_id=event_id,
                idx=idx,
                event_type=event_type,
                role=role,
                content=content_blocks,
                action=action,
                observation=observation,
                parent_event_ids=parent_ids,
                provenance=prov,
                visibility=Visibility(),
                raw=msg,
            )
        )
        existing_ids.add(event_id)
        idx += 1

    return events, diagnostics


def _looks_like_tool_call(text: str) -> bool:
    """Heuristic: does *text* resemble a tool invocation embedded in prose?"""
    # Simple heuristic: contains XML-ish tags or function_call markers
    # that suggest a tool invocation without being a native tool_use block.
    for marker in ("<tool_call>", "<function", "<invoke", "<arg_value><tool_call>", "```tool"):
        if marker in text:
            return True
    return False


def _parse_tools_json(
    tools: list[dict[str, Any]],
    existing_names: set[str],
    parser_name: str,
) -> list[ToolSpec]:
    """Parse a *tools_json* list into ToolSpec entries, skipping duplicates."""
    specs: list[ToolSpec] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        name = t.get("name", "")
        if not name or name in existing_names:
            continue
        specs.append(
            ToolSpec(
                tool_id=f"tool_{name}",
                name=name,
                description=t.get("description"),
                input_schema=t.get("input_schema", t.get("parameters", {})),
                output_schema=t.get("output_schema", {}),
                source=parser_name,
                metadata=t.get("metadata", {}),
            )
        )
        existing_names.add(name)
    return specs


def _handle_gitdiff(
    gitdiff: str,
    *,
    start_idx: int,
    existing_ids: set[str],
    parser_name: str,
) -> tuple[Artifact, Event]:
    """Create a PATCH artifact and a FILE_PATCH event for a gitdiff string."""
    sha = hashlib.sha256(gitdiff.encode()).hexdigest()[:16]
    artifact_id = f"patch_{sha}"
    event_id = f"evt_{start_idx:04d}"
    while event_id in existing_ids:
        start_idx += 1
        event_id = f"evt_{start_idx:04d}"

    artifact = Artifact(
        artifact_id=artifact_id,
        kind=ArtifactKind.PATCH,
        content=gitdiff,
        encoding="utf-8",
        mime_type="text/x-diff",
    )
    event = Event(
        event_id=event_id,
        idx=start_idx,
        event_type=EventType.FILE_PATCH,
        role=MessageRole.ASSISTANT,
        content=[ContentBlock(type=ContentType.DIFF, text=gitdiff)],
        action=Action(
            kind=ActionKind.FILE_PATCH,
            call_style=CallStyle.NONE,
            side_effect_level=SideEffectLevel.WORKSPACE_WRITE,
        ),
        artifacts=[artifact_id],
        provenance=Provenance(
            source_field="gitdiff",
            parser=parser_name,
            confidence=0.95,
        ),
        visibility=Visibility(),
    )
    return artifact, event


class ParseClaudeLogPass(AgentIRPass):
    """Parse Claude Code specific log fields into AgentIR events."""

    name = "parse-claude-log"
    kind = PassKind.PARSE

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult:
        diagnostics: list[Diagnostic] = []
        raw_rec = record.raw.get("record", {})

        # Collect existing events / ids ----------------------------------------
        events: list[Event] = []
        for ep in record.episodes:
            events.extend(ep.events)
        existing_ids: set[str] = {e.event_id for e in events}
        idx = len(events)

        # Existing tool names to avoid duplicates --------------------------------
        existing_tool_names: set[str] = {t.name for t in record.tool_registry}

        new_artifacts: list[Artifact] = list(record.artifacts)

        # 1. Parse messages_json ------------------------------------------------
        messages_json = raw_rec.get("messages_json")
        if messages_json and isinstance(messages_json, str):
            try:
                messages_json = json.loads(messages_json)
            except json.JSONDecodeError:
                messages_json = None
                diagnostics.append(
                    make_diagnostic(
                        DiagnosticCodes.PARSE003,
                        field="messages_json",
                        suggestion="messages_json is not valid JSON.",
                    )
                )

        if messages_json and isinstance(messages_json, list):
            msg_events, msg_diags = _parse_messages_json(
                messages_json,
                start_idx=idx,
                existing_ids=existing_ids,
                parser_name=self.name,
            )
            events.extend(msg_events)
            diagnostics.extend(msg_diags)
            idx = len(events)

        # 2. Parse tools_json ---------------------------------------------------
        tools_json = raw_rec.get("tools_json")
        if tools_json and isinstance(tools_json, str):
            try:
                tools_json = json.loads(tools_json)
            except json.JSONDecodeError:
                tools_json = None
                diagnostics.append(
                    make_diagnostic(
                        DiagnosticCodes.PARSE003,
                        field="tools_json",
                        suggestion="tools_json is not valid JSON.",
                    )
                )

        new_tool_specs: list[ToolSpec] = list(record.tool_registry)
        if tools_json and isinstance(tools_json, list):
            parsed_specs = _parse_tools_json(
                tools_json,
                existing_names=existing_tool_names,
                parser_name=self.name,
            )
            new_tool_specs.extend(parsed_specs)

        # 3. Handle assistant_response ------------------------------------------
        assistant_response = raw_rec.get("assistant_response", "")
        if isinstance(assistant_response, str):
            assistant_response = assistant_response.strip()
        if not assistant_response:
            diagnostics.append(
                make_diagnostic(
                    DiagnosticCodes.DATA001,
                    field="assistant_response",
                    suggestion="Assistant response is empty; check for truncated log.",
                )
            )
        else:
            # Only create a separate event if messages_json didn't already cover
            # this content (i.e. no assistant events from messages_json).
            has_assistant_from_messages = any(e.role == MessageRole.ASSISTANT for e in events)
            if not has_assistant_from_messages:
                event_id = f"evt_{idx:04d}"
                while event_id in existing_ids:
                    idx += 1
                    event_id = f"evt_{idx:04d}"

                # Check for inferred tool calls in freeform text
                action: Action | None = None
                confidence = 0.9
                if _looks_like_tool_call(assistant_response):
                    action = Action(
                        kind=ActionKind.GENERIC_TOOL,
                        tool_name="unknown",
                        call_style=CallStyle.INFERRED,
                        side_effect_level=SideEffectLevel.UNKNOWN,
                        metadata={"confidence": 0.7},
                    )
                    confidence = 0.7

                events.append(
                    Event(
                        event_id=event_id,
                        idx=idx,
                        event_type=EventType.ASSISTANT_MESSAGE,
                        role=MessageRole.ASSISTANT,
                        content=[ContentBlock(type=ContentType.TEXT, text=assistant_response)],
                        action=action,
                        provenance=Provenance(
                            source_field="assistant_response",
                            parser=self.name,
                            confidence=confidence,
                        ),
                        visibility=Visibility(),
                    )
                )
                existing_ids.add(event_id)
                idx += 1

        # 4. Handle gitdiff -----------------------------------------------------
        gitdiff = raw_rec.get("gitdiff")
        if gitdiff and isinstance(gitdiff, str) and gitdiff.strip():
            artifact, patch_event = _handle_gitdiff(
                gitdiff,
                start_idx=idx,
                existing_ids=existing_ids,
                parser_name=self.name,
            )
            new_artifacts.append(artifact)
            events.append(patch_event)
            existing_ids.add(patch_event.event_id)
            idx += 1

        # Rebuild episodes ------------------------------------------------------
        new_episodes: list[Episode] = list(record.episodes)
        if not new_episodes:
            new_episodes.append(Episode(episode_id="ep_0001", events=events))
        else:
            first = new_episodes[0]
            merged_events = list(first.events) + events
            new_episodes[0] = Episode(
                episode_id=first.episode_id,
                task_id=first.task_id,
                attempt_id=first.attempt_id,
                parent_episode_id=first.parent_episode_id,
                segments=first.segments,
                events=merged_events,
                state_timeline=first.state_timeline,
                outcome=first.outcome,
                metadata=first.metadata,
            )

        # Set provenance.parser on all newly created events ----------------------
        for ev in events:
            if ev.provenance is None:
                ev.provenance = Provenance(parser=self.name)
            elif ev.provenance.parser is None:
                ev.provenance.parser = self.name

        updated = record.model_copy(
            update={
                "episodes": new_episodes,
                "tool_registry": new_tool_specs,
                "artifacts": new_artifacts,
                "level": IRLevel.PARSED,
            }
        )
        return PassResult(record=updated, diagnostics=diagnostics)


register_pass(ParseClaudeLogPass())

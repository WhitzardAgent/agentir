"""Frontend for the Claude Code dataset (nlile/misc-merged-claude-code-traces-v1)."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any

from agentir.diagnostics.codes import DiagnosticCodes, make_diagnostic
from agentir.diagnostics.diagnostic import Diagnostic
from agentir.frontends.base import BaseFrontend, FrontendContext, FrontendResult
from agentir.frontends.registry import register_frontend
from agentir.ir import (
    Action,
    ActionKind,
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
    Observation,
    ObservationKind,
    Provenance,
    SourceRef,
    ToolSpec,
    Visibility,
)

# Minimum character length for claude_log to be stored as an Artifact
# rather than just metadata.
_LOG_ARTIFACT_THRESHOLD = 64

# Fields that detect() looks for to identify this dataset.
_DETECT_FIELDS = ("messages_json", "tools_json", "gitdiff", "claude_log", "assistant_response")


class ClaudeCodeFrontend(BaseFrontend):
    """Frontend for the Claude Code dataset."""

    name = "claude-code"

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self, sample: Mapping[str, Any]) -> float:
        """Return a 0-1 confidence score that *sample* came from the Claude Code dataset.

        The score is the fraction of the five signature fields that are present
        and non-empty.  A score of 0.4 (2/5) is enough for the registry to
        consider this a candidate.
        """
        hits = 0
        for field in _DETECT_FIELDS:
            val = sample.get(field)
            if val is not None and val != "" and val != []:
                hits += 1
        return hits / len(_DETECT_FIELDS)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_record(self, sample: Mapping[str, Any], ctx: FrontendContext) -> FrontendResult:
        """Parse a Claude Code dataset row into an AgentIRRecord."""
        diagnostics: list[Diagnostic] = []
        events: list[Event] = []
        artifacts: list[Artifact] = []
        tool_registry: list[ToolSpec] = []

        # -- Record identity ------------------------------------------------
        record_id = str(ctx.row_index) if ctx.row_index is not None else uuid.uuid4().hex[:12]

        source = SourceRef(
            dataset=ctx.dataset or "nlile/misc-merged-claude-code-traces-v1",
            dataset_url=ctx.dataset_url,
            config=ctx.config,
            split=ctx.split,
            row_index=ctx.row_index,
            framework="claude-code",
            format="claude-code-trace",
        )

        # -- Parse tool registry --------------------------------------------
        tools_json = _safe_str(sample.get("tools_json"))
        if tools_json:
            tool_registry = _parse_tools_json(tools_json, diagnostics)

        # -- Parse messages --------------------------------------------------
        messages = _parse_messages(sample, diagnostics)
        idx = 0
        for msg in messages:
            role_str = msg.get("role", "unknown")
            content = msg.get("content", "")

            event_type, message_role = _role_to_event_type(role_str)
            content_blocks = _content_to_blocks(content)

            action: Action | None = None
            observation: Observation | None = None
            provenance: Provenance | None = None
            visibility = Visibility()

            # Detect embedded tool use in assistant messages
            if message_role == MessageRole.ASSISTANT:
                text_val = _blocks_to_text(content_blocks)
                if not text_val.strip():
                    diagnostics.append(make_diagnostic(DiagnosticCodes.DATA001))
                # Check for embedded tool-use markers (e.g. tool_call blocks,
                # XML-like invocations) in the raw content.
                if _has_embedded_tool_use(content):
                    action = Action(
                        kind=ActionKind.GENERIC_TOOL,
                        call_style=CallStyle.INFERRED,
                        metadata={"confidence": 0.7},
                    )
                    provenance = Provenance(
                        parser=self.name,
                        confidence=0.7,
                    )
                    visibility = Visibility(trainable=True)

            # For tool-result messages, create an observation
            if message_role == MessageRole.TOOL:
                observation = Observation(
                    kind=ObservationKind.TOOL_JSON,
                    content=content_blocks,
                )

            event_id = f"evt-{record_id}-{idx}"
            event = Event(
                event_id=event_id,
                idx=idx,
                event_type=event_type,
                role=message_role,
                content=content_blocks,
                action=action,
                observation=observation,
                provenance=provenance,
                visibility=visibility,
            )
            events.append(event)
            idx += 1

        # -- Git diff artifact -----------------------------------------------
        gitdiff = _safe_str(sample.get("gitdiff"))
        if gitdiff:
            diff_artifact_id = f"art-{record_id}-gitdiff"
            diff_artifact = Artifact(
                artifact_id=diff_artifact_id,
                kind=ArtifactKind.PATCH,
                content=gitdiff,
                encoding="utf-8",
                mime_type="text/x-diff",
                size_bytes=len(gitdiff.encode("utf-8")),
                sha256=hashlib.sha256(gitdiff.encode("utf-8")).hexdigest(),
            )
            artifacts.append(diff_artifact)
            # Create a file_patch event referencing this artifact
            patch_event_id = f"evt-{record_id}-{idx}"
            patch_event = Event(
                event_id=patch_event_id,
                idx=idx,
                event_type=EventType.FILE_PATCH,
                artifacts=[diff_artifact_id],
                action=Action(
                    kind=ActionKind.FILE_PATCH,
                    call_style=CallStyle.NONE,
                ),
                visibility=Visibility(),
            )
            events.append(patch_event)
            diff_artifact.created_by_event_id = patch_event_id
            idx += 1

        # -- Claude log artifact / metadata -----------------------------------
        claude_log = _safe_str(sample.get("claude_log"))
        log_metadata: dict[str, Any] = {}
        if claude_log:
            if len(claude_log) >= _LOG_ARTIFACT_THRESHOLD:
                log_artifact_id = f"art-{record_id}-claude-log"
                log_artifact = Artifact(
                    artifact_id=log_artifact_id,
                    kind=ArtifactKind.TERMINAL_LOG,
                    content=claude_log,
                    encoding="utf-8",
                    mime_type="text/plain",
                    size_bytes=len(claude_log.encode("utf-8")),
                    sha256=hashlib.sha256(claude_log.encode("utf-8")).hexdigest(),
                )
                artifacts.append(log_artifact)
            else:
                log_metadata["claude_log"] = claude_log

        # -- Assemble record -------------------------------------------------
        episode = Episode(
            episode_id=f"ep-{record_id}",
            events=events,
            metadata=log_metadata,
        )

        record = AgentIRRecord(
            record_id=record_id,
            level=IRLevel.PARSED,
            source=source,
            tool_registry=tool_registry,
            episodes=[episode],
            artifacts=artifacts,
            raw={"record": dict(sample)},
        )

        return FrontendResult(record=record, diagnostics=diagnostics)


# ======================================================================
# Helper functions (module-private)
# ======================================================================


def _safe_str(val: Any) -> str:
    """Return *val* as a string, or empty string if None/empty."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    # Could be a list or dict already loaded; serialise back.
    try:
        return json.dumps(val)
    except (TypeError, ValueError):
        return str(val)


def _parse_messages(sample: Mapping[str, Any], diagnostics: list) -> list[dict[str, Any]]:
    """Extract the conversation messages from the row.

    Prefers ``messages_json`` (parsed via json.loads).  Falls back to
    ``system_prompt`` / ``user_prompt`` / ``assistant_response`` fields.
    """
    messages_json_raw = _safe_str(sample.get("messages_json"))
    if messages_json_raw:
        try:
            msgs = json.loads(messages_json_raw)
            if isinstance(msgs, list) and len(msgs) > 0:
                return msgs
        except (json.JSONDecodeError, TypeError):
            diagnostics.append(
                make_diagnostic(
                    DiagnosticCodes.PARSE003,
                    field="messages_json",
                    suggestion="messages_json could not be parsed as JSON; falling back to flat fields",
                )
            )

    # Fallback: construct from flat fields
    fallback: list[dict[str, Any]] = []
    system_prompt = _safe_str(sample.get("system_prompt"))
    if system_prompt:
        fallback.append({"role": "system", "content": system_prompt})
    user_prompt = _safe_str(sample.get("user_prompt"))
    if user_prompt:
        fallback.append({"role": "user", "content": user_prompt})
    assistant_response = _safe_str(sample.get("assistant_response"))
    if assistant_response:
        fallback.append({"role": "assistant", "content": assistant_response})
    return fallback


def _parse_tools_json(tools_json_str: str, diagnostics: list) -> list[ToolSpec]:
    """Parse a JSON string describing available tools into ToolSpec entries."""
    tool_specs: list[ToolSpec] = []
    try:
        tools = json.loads(tools_json_str)
    except (json.JSONDecodeError, TypeError):
        diagnostics.append(
            make_diagnostic(
                DiagnosticCodes.PARSE003,
                field="tools_json",
                suggestion="tools_json could not be parsed as JSON",
            )
        )
        return tool_specs

    if not isinstance(tools, list):
        # Might be a single tool dict; normalise.
        tools = [tools]

    for i, tool_def in enumerate(tools):
        if not isinstance(tool_def, dict):
            continue
        name = tool_def.get("name") or tool_def.get("function", {}).get("name") or f"tool-{i}"
        description = tool_def.get("description") or tool_def.get("function", {}).get("description")
        input_schema = (
            tool_def.get("input_schema")
            or tool_def.get("parameters")
            or tool_def.get("function", {}).get("parameters")
            or {}
        )
        tool_specs.append(
            ToolSpec(
                tool_id=f"tool-{name}",
                name=name,
                description=description,
                input_schema=input_schema if isinstance(input_schema, dict) else {},
                source="claude-code",
            )
        )
    return tool_specs


def _role_to_event_type(role_str: str) -> tuple[EventType, MessageRole]:
    """Map a raw role string to (EventType, MessageRole)."""
    role_lower = role_str.lower().strip()
    mapping: dict[str, tuple[EventType, MessageRole]] = {
        "system": (EventType.SYSTEM_MESSAGE, MessageRole.SYSTEM),
        "user": (EventType.USER_MESSAGE, MessageRole.USER),
        "human": (EventType.USER_MESSAGE, MessageRole.USER),
        "assistant": (EventType.ASSISTANT_MESSAGE, MessageRole.ASSISTANT),
        "tool": (EventType.TOOL_MESSAGE, MessageRole.TOOL),
        "developer": (EventType.SYSTEM_MESSAGE, MessageRole.DEVELOPER),
    }
    return mapping.get(role_lower, (EventType.UNPARSED_FRAGMENT, MessageRole.UNKNOWN))


def _content_to_blocks(content: Any) -> list[ContentBlock]:
    """Convert raw message content to a list of ContentBlock instances."""
    if content is None:
        return []
    if isinstance(content, str):
        if not content:
            return []
        return [ContentBlock(type=ContentType.TEXT, text=content)]
    if isinstance(content, list):
        blocks: list[ContentBlock] = []
        for item in content:
            if isinstance(item, str):
                blocks.append(ContentBlock(type=ContentType.TEXT, text=item))
            elif isinstance(item, dict):
                item_type = item.get("type", "text")
                if item_type == "text":
                    blocks.append(
                        ContentBlock(
                            type=ContentType.TEXT,
                            text=item.get("text", ""),
                        )
                    )
                elif item_type == "tool_use":
                    blocks.append(
                        ContentBlock(
                            type=ContentType.JSON,
                            json_value=item,
                            metadata={"tool_use": True, "tool_name": item.get("name")},
                        )
                    )
                elif item_type == "tool_result":
                    blocks.append(
                        ContentBlock(
                            type=ContentType.JSON,
                            json_value=item,
                            metadata={"tool_result": True, "tool_use_id": item.get("tool_use_id")},
                        )
                    )
                else:
                    blocks.append(
                        ContentBlock(
                            type=ContentType.JSON,
                            json_value=item,
                        )
                    )
        return blocks
    # Fallback: serialise anything else as text
    return [ContentBlock(type=ContentType.TEXT, text=str(content))]


def _blocks_to_text(blocks: list[ContentBlock]) -> str:
    """Concatenate text from a list of ContentBlock instances."""
    parts: list[str] = []
    for b in blocks:
        if b.text:
            parts.append(b.text)
    return "\n".join(parts)


def _has_embedded_tool_use(content: Any) -> bool:
    """Return True if *content* contains structured tool-use blocks.

    In the Claude Code dataset, assistant messages may include tool_use
    content blocks alongside text.  These are *embedded* rather than
    native separate tool-call messages, so we mark them as inferred.
    """
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") in ("tool_use", "tool_result"):
                return True
    return False


# -- Register with the frontend registry ------------------------------------

register_frontend(ClaudeCodeFrontend())

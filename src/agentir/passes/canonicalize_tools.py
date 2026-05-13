"""Canonicalize tool calls into Action objects with normalized kinds."""

from __future__ import annotations

from agentir.ir.action import Action
from agentir.ir.base import (
    ActionKind,
    CallStyle,
    EventType,
    IRLevel,
    PassKind,
    SideEffectLevel,
)
from agentir.ir.episode import Episode
from agentir.ir.event import Event
from agentir.ir.record import AgentIRRecord
from agentir.passes.base import AgentIRPass, PassContext, PassResult
from agentir.passes.registry import register_pass

# ---------------------------------------------------------------------------
# Tool-name classification tables
# ---------------------------------------------------------------------------

_TERMINAL_TOOLS: frozenset[str] = frozenset(
    {
        "execute_bash",
        "run_command",
        "bash",
        "shell",
        "terminal",
        "execute_command",
        "run_bash",
        "exec_bash",
        "execute_shell",
        "run_shell",
        "command",
        "cmd",
        "subprocess",
        "os_exec",
    }
)

_FILE_WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "write_file",
        "edit_file",
        "str_replace_editor",
        "create_file",
        "write",
        "save_file",
        "create_or_update_file",
        "apply_patch",
        "insert_content",
        "replace_in_file",
        "patch_file",
        "modify_file",
        "overwrite_file",
        "append_file",
    }
)

_FILE_PATCH_TOOLS: frozenset[str] = frozenset(
    {
        "apply_diff",
        "diff_edit",
        "str_replace",
        "insert",
        "replace",
        "patch",
        "edit_file_diff",
        "sed_edit",
    }
)

_FILE_READ_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "cat",
        "view_file",
        "open_file",
        "get_file",
        "read",
        "head_file",
        "tail_file",
        "view",
        "show_file",
        "less",
        "more",
        "type",
    }
)

_BROWSER_TOOLS: frozenset[str] = frozenset(
    {
        "browser_click",
        "browser_type",
        "browser_scroll",
        "browser_hover",
        "browser_navigate",
        "browser_screenshot",
        "browser_search",
        "browser_back",
        "browser_forward",
        "browser_reload",
        "browser_select_option",
        "browser_drag",
        "browser_tab_new",
        "browser_tab_close",
        "browser_tab_switch",
        "browser_wait",
        "browser",
        "web_search",
        "web_navigate",
        "web_click",
        "web_type",
        "web_scroll",
        "browse",
        "navigate",
    }
)

# Build a single lookup: raw_name -> (ActionKind, SideEffectLevel)
_TOOL_MAP: dict[str, tuple[ActionKind, SideEffectLevel]] = {}
for _name in _TERMINAL_TOOLS:
    _TOOL_MAP[_name] = (ActionKind.TERMINAL, SideEffectLevel.WORKSPACE_WRITE)
for _name in _FILE_WRITE_TOOLS:
    _TOOL_MAP[_name] = (ActionKind.FILE_WRITE, SideEffectLevel.WORKSPACE_WRITE)
for _name in _FILE_PATCH_TOOLS:
    _TOOL_MAP[_name] = (ActionKind.FILE_PATCH, SideEffectLevel.WORKSPACE_WRITE)
for _name in _FILE_READ_TOOLS:
    _TOOL_MAP[_name] = (ActionKind.FILE_READ, SideEffectLevel.READ_ONLY)
for _name in _BROWSER_TOOLS:
    _TOOL_MAP[_name] = (ActionKind.BROWSER, SideEffectLevel.NETWORK)


def _classify_tool(raw_name: str) -> tuple[ActionKind, SideEffectLevel, str]:
    """Return (action_kind, side_effect_level, normalized_name) for a tool name.

    Falls back to GENERIC_TOOL / UNKNOWN when no specific mapping exists.
    The normalized name is the lowercased, whitespace-stripped name.
    """
    normalized = raw_name.strip().lower()
    if normalized in _TOOL_MAP:
        kind, level = _TOOL_MAP[normalized]
        return kind, level, normalized

    # Prefix-based heuristic for browser tools (e.g. "browser_*")
    if normalized.startswith("browser_"):
        return ActionKind.BROWSER, SideEffectLevel.NETWORK, normalized

    # Generic fallback
    return ActionKind.GENERIC_TOOL, SideEffectLevel.UNKNOWN, normalized


class CanonicalizeToolsPass(AgentIRPass):
    """Normalize TOOL_CALL events into well-typed Action objects."""

    name = "canonicalize-tools"
    kind = PassKind.CANONICALIZE

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult:
        any_changed = False

        updated_episodes: list[Episode] = []
        for episode in record.episodes:
            updated_events: list[Event] = []
            for event in episode.events:
                if event.event_type != EventType.TOOL_CALL:
                    updated_events.append(event)
                    continue

                # If the event already has a properly classified action, skip.
                if event.action is not None and event.action.kind != ActionKind.GENERIC_TOOL:
                    updated_events.append(event)
                    continue

                # Determine the raw tool name from the existing action or metadata.
                raw_name = ""
                if event.action is not None and event.action.tool_name:
                    raw_name = event.action.tool_name
                elif "tool_name" in event.metadata:
                    raw_name = str(event.metadata["tool_name"])
                elif "tool.name" in event.metadata:
                    raw_name = str(event.metadata["tool.name"])

                if not raw_name:
                    # Cannot classify without a tool name; keep as-is.
                    updated_events.append(event)
                    continue

                kind, level, normalized = _classify_tool(raw_name)

                # Preserve existing action fields that should not be overwritten.
                existing = event.action
                existing_args = existing.arguments if existing else {}
                existing_norm_args = existing.normalized_arguments if existing else {}
                existing_call_style = existing.call_style if existing else CallStyle.UNKNOWN
                existing_timeout = existing.timeout_seconds if existing else None
                existing_call_id = existing.tool_call_id if existing else None
                existing_meta = dict(existing.metadata) if existing and existing.metadata else {}

                # Merge in canonicalization metadata.
                existing_meta["tool.name.raw"] = raw_name
                existing_meta["normalized_name"] = normalized

                new_action = Action(
                    kind=kind,
                    tool_name=normalized,
                    tool_call_id=existing_call_id,
                    arguments=existing_args,
                    normalized_arguments=existing_norm_args,
                    call_style=existing_call_style,
                    side_effect_level=level,
                    timeout_seconds=existing_timeout,
                    metadata=existing_meta,
                )

                updated_event = event.model_copy(update={"action": new_action})
                updated_events.append(updated_event)
                any_changed = True

            updated_episodes.append(
                Episode(
                    episode_id=episode.episode_id,
                    task_id=episode.task_id,
                    attempt_id=episode.attempt_id,
                    parent_episode_id=episode.parent_episode_id,
                    segments=episode.segments,
                    events=updated_events,
                    state_timeline=episode.state_timeline,
                    outcome=episode.outcome,
                    metadata=episode.metadata,
                )
            )

        if any_changed:
            updated_record = record.model_copy(
                update={
                    "episodes": updated_episodes,
                    "level": IRLevel.CANONICAL,
                }
            )
        else:
            updated_record = record

        return PassResult(record=updated_record)


register_pass(CanonicalizeToolsPass())

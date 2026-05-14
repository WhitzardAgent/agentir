"""DSL compiler: turns a TrajectoryFormat spec into a runtime frontend.

The ``RuntimeDSLFrontend`` implements :class:`BaseFrontend` using the
declarative mapping rules from a ``*.agentir.yaml`` file.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from agentir.backends.loss import LoweringResult
from agentir.diagnostics.diagnostic import Diagnostic
from agentir.dsl.models import TrajectoryFormat
from agentir.frontends.base import BaseFrontend, FrontendContext, FrontendResult
from agentir.ir import (
    AgentIRRecord,
    Artifact,
    ArtifactKind,
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
    SourceRef,
    TaskSpec,
    ToolSpec,
)
from agentir.ir.action import Action
from agentir.ir.base import (
    ActionKind,
    CallStyle,
    DiagnosticSeverity,
    SideEffectLevel,
)
from agentir.ir.observation import Observation, ObservationKind


# ---------------------------------------------------------------------------
# Built-in transform maps
# ---------------------------------------------------------------------------

_ROLE_EVENT_TYPE_MAP: dict[str, EventType] = {
    "system": EventType.SYSTEM_MESSAGE,
    "user": EventType.USER_MESSAGE,
    "assistant": EventType.ASSISTANT_MESSAGE,
    "tool": EventType.TOOL_MESSAGE,
    "developer": EventType.SYSTEM_MESSAGE,
}

_ROLE_IR_MAP: dict[str, MessageRole] = {
    "system": MessageRole.SYSTEM,
    "user": MessageRole.USER,
    "assistant": MessageRole.ASSISTANT,
    "tool": MessageRole.TOOL,
    "developer": MessageRole.DEVELOPER,
}


# ---------------------------------------------------------------------------
# Path resolver
# ---------------------------------------------------------------------------


def _resolve_path(root: Any, path: str, vars_: dict[str, Any] | None = None) -> Any:
    """Evaluate a restricted JSONPath-like expression against *root*.

    Supported syntax:
        ``$``              whole row
        ``$.field``        object field
        ``$.a.b``          nested field
        ``$.items[0]``     list index
        ``$.items[*]``     list wildcard (returns the list itself for iteration)
    """
    if path == "$":
        return root

    if not path.startswith("$"):
        # Relative path -- try root first, then vars_
        current = root
        segments = path.split(".")
        for seg in segments:
            if isinstance(current, dict):
                current = current.get(seg)
            else:
                current = None
                break
        if current is not None:
            return current
        # Try resolving against vars_ (full dot chain walk)
        if vars_ is not None:
            vcur = vars_
            for seg in segments:
                if isinstance(vcur, dict):
                    vcur = vcur.get(seg)
                else:
                    vcur = None
                    break
            if vcur is not None:
                return vcur
        return None

    # Tokenise the path: $.a.b[0].c  ->  ["a", "b", "0", "c"]
    rest = path[1:]  # drop the leading "$"
    segments: list[str] = []

    while rest:
        if rest.startswith("."):
            rest = rest[1:]
            continue
        if rest.startswith("["):
            rbracket = rest.index("]")
            segment = rest[1:rbracket]
            segments.append(segment)
            rest = rest[rbracket + 1:]
            continue
        # Field name -- scan until a special char or end of string
        end = 0
        for i, ch in enumerate(rest):
            if ch in (".", "["):
                end = i
                break
        else:
            end = len(rest)
        segments.append(rest[:end])
        rest = rest[end:]

    current: Any = root
    for seg in segments:
        if seg == "*":
            # wildcard on a list -- return the list itself for iteration
            if isinstance(current, list):
                return current
            return None
        if isinstance(current, list):
            try:
                current = current[int(seg)]
            except (IndexError, ValueError):
                return None
        elif isinstance(current, dict):
            current = current.get(seg)
        else:
            return None

    return current


# ---------------------------------------------------------------------------
# Built-in transforms
# ---------------------------------------------------------------------------


def _builtin_transform(name: str, input_val: Any, fallback: Any = None) -> Any:
    """Apply a named built-in transform.

    Supported transforms
    --------------------
    ``role_to_event_type``
        Map a role string (system/user/assistant/tool/developer) to an
        :class:`EventType` enum.
    ``role_to_message_role``
        Map a role string to a :class:`MessageRole` enum.
    ``parse_json``
        ``json.loads`` if the input is a string; otherwise pass through
        if it is already a list/dict.
    ``extract_text``
        Extract plain text from a string or a list of content items.
    ``to_string`` / ``to_integer`` / ``to_float`` / ``to_boolean``
        Type-coercion helpers.
    """
    lower = name.lower().replace("-", "_")

    if lower == "role_to_event_type":
        return _ROLE_EVENT_TYPE_MAP.get(
            str(input_val).lower(), EventType.UNPARSED_FRAGMENT
        )

    if lower == "role_to_message_role":
        return _ROLE_IR_MAP.get(
            str(input_val).lower(), MessageRole.UNKNOWN
        )

    if lower == "parse_json":
        if isinstance(input_val, str):
            try:
                return json.loads(input_val)
            except json.JSONDecodeError:
                return fallback
        if isinstance(input_val, (list, dict)):
            return input_val
        return fallback

    if lower == "extract_text":
        if isinstance(input_val, str):
            return input_val
        if isinstance(input_val, list):
            parts: list[str] = []
            for item in input_val:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(str(item.get("text", item)))
                elif item is not None:
                    parts.append(str(item))
            return "\n".join(parts)
        if input_val is not None:
            return str(input_val)
        return fallback

    if lower == "to_string":
        return str(input_val) if input_val is not None else fallback

    if lower == "to_integer":
        try:
            return int(input_val)
        except (TypeError, ValueError):
            return fallback

    if lower == "to_float":
        try:
            return float(input_val)
        except (TypeError, ValueError):
            return fallback

    if lower == "to_boolean":
        if isinstance(input_val, bool):
            return input_val
        if isinstance(input_val, str):
            return input_val.lower() in ("true", "yes", "1")
        if isinstance(input_val, (int, float)):
            return bool(input_val)
        return fallback

    # Unknown transform -- return fallback
    return fallback


# ---------------------------------------------------------------------------
# Value expression evaluator
# ---------------------------------------------------------------------------


def _eval_value(
    expr: Any,
    root: Any,
    vars_: dict[str, Any],
    context: dict[str, Any],
) -> Any:
    """Evaluate a value expression.

    Expression forms
    ----------------
    * ``None`` -> ``None``
    * plain ``str``, ``int``, ``float``, ``bool`` -> returned as-is
    * ``{"const": value}`` -> *value* returned literally
    * ``{"var": "name"}`` -> looked up in *vars_*
    * ``{"path": "$.field"}`` -> dispatched to :func:`_resolve_path`
    * ``{"template": "..."}`` -> ``str.format(**{**context, **vars_})``
    * ``{"transform": "name", "input": expr, "fallback": val}``
    * ``{"first_of": [expr, ...]}`` -> first non-``None`` result
    * plain ``list`` / ``dict`` -> recursively evaluated
    """
    # --- None ---
    if expr is None:
        return None

    # --- atomic literals ---
    if isinstance(expr, (int, float, bool)):
        return expr

    if isinstance(expr, str):
        if expr.startswith('$'):
            return _resolve_path(root, expr, vars_)
        if '.' in expr and not expr.startswith(('{', 'http', 'ftp')):
            if vars_:
                parts = expr.split('.')
                current = vars_.get(parts[0])
                rest = parts[1:]
                if current is not None and rest:
                    for segment in rest:
                        if isinstance(current, dict):
                            current = current.get(segment)
                        else:
                            current = None
                            break
                if current is not None:
                    return current
            return _resolve_path(root, expr, vars_)
        return expr

    # --- structured expressions (must be dict) ---
    if not isinstance(expr, dict):
        # pass through lists (will be recursed below)
        if isinstance(expr, list):
            return [_eval_value(item, root, vars_, context) for item in expr]
        return expr

    # dict-based expr forms
    if "var" in expr:
        return vars_.get(expr["var"])

    if "const" in expr:
        return expr["const"]

    if "template" in expr:
        tmpl: str = expr["template"]
        env = {**context, **vars_}
        env.setdefault("root", root)
        try:
            return tmpl.format(**env)
        except (KeyError, ValueError):
            return tmpl

    if "path" in expr:
        return _resolve_path(root, expr["path"], vars_)

    if "transform" in expr:
        input_expr = expr.get("input")
        input_val = _eval_value(input_expr, root, vars_, context)
        fb = expr.get("fallback")
        return _builtin_transform(expr["transform"], input_val, fb)

    if "first_of" in expr:
        for candidate in expr["first_of"]:
            val = _eval_value(candidate, root, vars_, context)
            if val is not None:
                return val
        return None

    # Generic dict -- recurse into values
    return {k: _eval_value(v, root, vars_, context) for k, v in expr.items()}


# ---------------------------------------------------------------------------
# Runtime DSL frontend
# ---------------------------------------------------------------------------


class RuntimeDSLFrontend(BaseFrontend):
    """A :class:`BaseFrontend` driven by a ``*.agentir.yaml`` specification.

    The spec is evaluated at runtime against each sample row, so no
    code-generation step is required.
    """

    name: str = "runtime-dsl"

    def __init__(self, spec: TrajectoryFormat, dsl_path: str = "") -> None:
        self.spec = spec
        self._name = spec.metadata.name
        self._dsl_path = dsl_path

    @property
    def frontend_name(self) -> str:
        return self._name

    # ------------------------------------------------------------------
    # detect
    # ------------------------------------------------------------------

    def detect(self, sample: Mapping[str, Any]) -> float:
        """Evaluate detection rules to produce a confidence score in [0, 1]."""
        rules = self.spec.detect.rules
        if not rules:
            return 1.0

        total = 0.0
        sample_dict = dict(sample)

        for rule in rules:
            score = rule.score

            if rule.field_exists is not None:
                if _resolve_path(sample_dict, rule.field_exists) is not None:
                    total += score

            if rule.field_missing is not None:
                if _resolve_path(sample_dict, rule.field_missing) is None:
                    total += score

            if rule.field_is_list is not None:
                if isinstance(
                    _resolve_path(sample_dict, rule.field_is_list), list
                ):
                    total += score

            if rule.field_is_dict is not None:
                if isinstance(
                    _resolve_path(sample_dict, rule.field_is_dict), dict
                ):
                    total += score

            if rule.field_is_string is not None:
                if isinstance(
                    _resolve_path(sample_dict, rule.field_is_string), str
                ):
                    total += score

            if rule.any_field_exists:
                for field in rule.any_field_exists:
                    if _resolve_path(sample_dict, field) is not None:
                        total += score
                        break

            if rule.all_fields_exist:
                if all(
                    _resolve_path(sample_dict, f) is not None
                    for f in rule.all_fields_exist
                ):
                    total += score

            if rule.text_contains:
                path = rule.text_contains.get("path", "$")
                texts: list[str] = rule.text_contains.get("any", [])
                resolved = _resolve_path(sample_dict, path)
                if isinstance(resolved, list):
                    resolved = "\n".join(str(r) for r in resolved)
                if isinstance(resolved, str):
                    for t in texts:
                        if t in resolved:
                            total += score
                            break

        return min(total, 1.0)

    # ------------------------------------------------------------------
    # parse_record
    # ------------------------------------------------------------------

    def parse_record(
        self, sample: Mapping[str, Any], ctx: FrontendContext
    ) -> FrontendResult:
        """Convert a single source row into an :class:`AgentIRRecord`."""
        diagnostics: list[Diagnostic] = []
        sample_dict = dict(sample)

        # ---- build template evaluation context ----
        eval_context = {
            "dataset": ctx.dataset,
            "config": ctx.config,
            "split": ctx.split,
            "row_index": ctx.row_index,
        }

        # ---- evaluate vars block ----
        vars_: dict[str, Any] = {}
        for var_name, var_expr in self.spec.vars.items():
            vars_[var_name] = _eval_value(var_expr, sample_dict, vars_, eval_context)

        # ---- row id ----
        src_overrides = self.spec.source_overrides
        default_row_id_expr = {
            "first_of": [
                {"path": "$.id"},
                {"path": "$.instance_id"},
                {"path": "$.trajectory_id"},
                {"template": "dsl-row-{row_index}"},
            ]
        }
        row_id_expr = src_overrides.get("row_id") if src_overrides else None
        if row_id_expr is None:
            row_id_expr = default_row_id_expr
        record_id = str(
            _eval_value(row_id_expr, sample_dict, vars_, eval_context) or "unknown"
        )

        # ---- source reference ----
        source = SourceRef(
            dataset=self.spec.source.default_dataset or ctx.dataset,
            dataset_url=ctx.dataset_url,
            config=self.spec.source.default_config or ctx.config,
            split=self.spec.source.default_split or ctx.split,
            row_id=_eval_value(
                src_overrides.get("row_id"), sample_dict, vars_, eval_context
            ) if (src_overrides and src_overrides.get("row_id")) else None,
            row_index=ctx.row_index,
            framework=self.spec.source.framework,
            format=self.spec.source.format,
            license=self.spec.source.license,
        )

        # ---- task spec ----
        task: TaskSpec | None = None
        task_mapping = self.spec.task
        if task_mapping:
            task = TaskSpec(
                task_id=str(
                    _eval_value(
                        task_mapping.get("task_id") or task_mapping.get("id"),
                        sample_dict,
                        vars_,
                        eval_context,
                    )
                    or record_id
                ),
                instruction=_eval_value(
                    task_mapping.get("instruction") or task_mapping.get("task"),
                    sample_dict,
                    vars_,
                    eval_context,
                ),
                category=_eval_value(
                    task_mapping.get("category"), sample_dict, vars_, eval_context
                ),
                subcategory=_eval_value(
                    task_mapping.get("subcategory"), sample_dict, vars_, eval_context
                ),
            )

        # ---- tool registry ----
        tool_registry: list[ToolSpec] = []
        tr_def = self.spec.tool_registry
        if tr_def:
            from_val = _eval_value(tr_def.from_, sample_dict, vars_, eval_context)
            if isinstance(from_val, list):
                item_map = tr_def.item or {}
                for i, raw_tool in enumerate(from_val):
                    tool_vars = {**vars_, "item": raw_tool}
                    name = _eval_value(
                        item_map.get("name", {"path": "$.item.name"}),
                        sample_dict,
                        tool_vars,
                        eval_context,
                    )
                    description = _eval_value(
                        item_map.get("description"),
                        sample_dict,
                        tool_vars,
                        eval_context,
                    )
                    input_schema_raw = _eval_value(
                        item_map.get("input_schema"), sample_dict, tool_vars, eval_context
                    ) or {}
                    tool_registry.append(
                        ToolSpec(
                            tool_id=f"tool_{i}",
                            name=str(name or f"tool_{i}"),
                            description=description,
                            input_schema=(
                                input_schema_raw
                                if isinstance(input_schema_raw, dict)
                                else {}
                            ),
                        )
                    )

        # ---- episodes ----
        episodes: list[Episode] = []
        for ep_spec in self.spec.episodes:
            ep_id = str(
                _eval_value(ep_spec.episode_id, sample_dict, vars_, eval_context)
                or f"{record_id}-ep-0"
            )
            ep_task_id = str(
                _eval_value(ep_spec.task_id, sample_dict, vars_, eval_context)
                or record_id
            )

            episode_events: list[Event] = []
            for event_mapping in ep_spec.events:
                # -- foreach iteration --
                items = _eval_value(
                    event_mapping.foreach, sample_dict, vars_, eval_context
                )
                if items is None:
                    continue
                if not isinstance(items, list):
                    items = [items]

                emit_spec = event_mapping.emit
                if emit_spec is None:
                    continue

                for iter_idx, item in enumerate(items):
                    loop_vars = dict(vars_)
                    as_name = event_mapping.as_ or "item"
                    loop_vars[as_name] = item
                    if event_mapping.index_as:
                        loop_vars[event_mapping.index_as] = iter_idx
                    loop_vars["turn"] = item if isinstance(item, dict) else {}

                    # event_id
                    evt_id = str(
                        _eval_value(emit_spec.event_id, sample_dict, loop_vars, eval_context)
                        or f"{record_id}-evt-{iter_idx:04d}"
                    )

                    # idx
                    idx_raw = _eval_value(emit_spec.idx, sample_dict, loop_vars, eval_context)
                    idx = idx_raw if isinstance(idx_raw, int) else iter_idx

                    # event_type
                    raw_event_type = _eval_value(
                        emit_spec.event_type, sample_dict, loop_vars, eval_context
                    )
                    if isinstance(raw_event_type, EventType):
                        event_type = raw_event_type
                    elif isinstance(raw_event_type, str):
                        event_type = _ROLE_EVENT_TYPE_MAP.get(
                            raw_event_type.lower(), EventType.UNPARSED_FRAGMENT
                        )
                    else:
                        event_type = EventType.UNPARSED_FRAGMENT

                    # role
                    raw_role = _eval_value(
                        emit_spec.role, sample_dict, loop_vars, eval_context
                    )
                    if isinstance(raw_role, MessageRole):
                        role = raw_role
                    elif isinstance(raw_role, str):
                        role = _ROLE_IR_MAP.get(
                            raw_role.lower(), MessageRole.UNKNOWN
                        )
                    else:
                        role = MessageRole.UNKNOWN

                    # content
                    content_raw = _eval_value(
                        emit_spec.content, sample_dict, loop_vars, eval_context
                    )
                    content_blocks: list[ContentBlock] = []
                    if isinstance(content_raw, str):
                        content_blocks.append(
                            ContentBlock(type=ContentType.TEXT, text=content_raw)
                        )
                    elif isinstance(content_raw, list):
                        for cb in content_raw:
                            if isinstance(cb, str):
                                content_blocks.append(
                                    ContentBlock(type=ContentType.TEXT, text=cb)
                                )
                            elif isinstance(cb, ContentBlock):
                                content_blocks.append(cb)
                            elif isinstance(cb, dict):
                                content_blocks.append(
                                    ContentBlock(
                                        type=ContentType(cb.get("type", "text")),
                                        text=cb.get("text"),
                                    )
                                )

                    # action
                    action_raw = _eval_value(
                        emit_spec.action, sample_dict, loop_vars, eval_context
                    )
                    action: Action | None = None
                    if isinstance(action_raw, dict):
                        action = Action(
                            kind=ActionKind(
                                action_raw.get("kind", "generic_tool")
                            ),
                            tool_name=action_raw.get("tool_name"),
                            tool_call_id=action_raw.get("tool_call_id"),
                            call_style=CallStyle(
                                action_raw.get("call_style", "native_tool_call")
                            ),
                        )
                    elif isinstance(action_raw, Action):
                        action = action_raw

                    episode_events.append(
                        Event(
                            event_id=evt_id,
                            idx=idx,
                            event_type=event_type,
                            role=role,
                            content=content_blocks,
                            action=action,
                            provenance=Provenance(
                                parser=f"dsl:{self._name}",
                                source_field=f"conversations[{iter_idx}]",
                                confidence=1.0,
                            ),
                        )
                    )

            episodes.append(
                Episode(
                    episode_id=ep_id,
                    task_id=ep_task_id,
                    events=episode_events,
                )
            )

        # ---- outcome ----
        outcome: Outcome | None = None
        if self.spec.outcome:
            om = self.spec.outcome
            raw_status = _eval_value(om.status, sample_dict, vars_, eval_context)
            if isinstance(raw_status, str):
                try:
                    status = OutcomeStatus(raw_status.lower())
                except ValueError:
                    status = OutcomeStatus.UNKNOWN
            else:
                status = OutcomeStatus.UNKNOWN

            raw_passed = _eval_value(om.passed, sample_dict, vars_, eval_context)
            if isinstance(raw_passed, str):
                raw_passed = raw_passed.lower() in ("true", "yes", "1", "success")
            elif isinstance(raw_passed, (int, float)):
                raw_passed = bool(raw_passed)

            outcome = Outcome(
                status=status,
                passed=bool(raw_passed) if raw_passed is not None else None,
            )

        # ---- assemble record ----
        record = AgentIRRecord(
            record_id=record_id,
            level=IRLevel.PARSED,
            source=source,
            task=task,
            tool_registry=tool_registry,
            episodes=episodes,
            outcome=outcome,
            raw={"record": sample_dict},
        )

        return FrontendResult(record=record, diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compile_dsl_frontend(
    spec: TrajectoryFormat, dsl_path: str = ""
) -> RuntimeDSLFrontend:
    """Create a :class:`RuntimeDSLFrontend` from a validated DSL spec.

    Args:
        spec: A validated :class:`TrajectoryFormat`.
        dsl_path: Path to the source ``.agentir.yaml`` file (for provenance).

    Returns:
        A configured runtime frontend implementing :class:`BaseFrontend`.
    """
    return RuntimeDSLFrontend(spec, dsl_path)

"""Pydantic v2 models for the AgentIR Format DSL v0.1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Value Expressions
# ---------------------------------------------------------------------------

class PathExpr(BaseModel):
    """Reference a value by JSON path."""

    model_config = ConfigDict(extra="forbid")
    path: str


class ConstExpr(BaseModel):
    """A literal constant value."""

    model_config = ConfigDict(extra="forbid")
    const: Any


class TemplateExpr(BaseModel):
    """A Python string template expression."""

    model_config = ConfigDict(extra="forbid")
    template: str


class TransformExpr(BaseModel):
    """A transformation applied to an input value."""

    model_config = ConfigDict(extra="forbid")
    transform: str
    input: Any = None
    on_error: str | None = None
    fallback: Any = None


class FirstOfExpr(BaseModel):
    """Return the first non-None / non-empty value from a list of expressions."""

    model_config = ConfigDict(extra="forbid")
    first_of: list[Any]


class VarRef(BaseModel):
    """Reference a variable defined in the top-level `vars` block."""

    model_config = ConfigDict(extra="forbid")
    var: str


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

class DetectRule(BaseModel):
    """A single detection rule that contributes a score."""

    model_config = ConfigDict(extra="allow")
    field_exists: str | None = None
    field_missing: str | None = None
    field_is_list: str | None = None
    field_is_dict: str | None = None
    field_is_string: str | None = None
    any_field_exists: list[str] | None = None
    all_fields_exist: list[str] | None = None
    text_contains: dict[str, Any] | None = None
    regex_match: dict[str, Any] | None = None
    json_parseable: str | None = None
    sample_predicate: str | None = None
    score: float = 0.10


class DetectDef(BaseModel):
    """Auto-detection configuration for inferring format/source parameters."""

    model_config = ConfigDict(extra="forbid")
    min_score: float = 0.70
    rules: list[DetectRule] = []


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------

class SourceDef(BaseModel):
    """Describes the origin and shape of the trajectory data."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["json", "jsonl", "parquet", "hf", "unknown"] = "jsonl"
    record_mode: Literal["row", "array", "auto"] = "row"
    default_dataset: str | None = None
    default_config: str | None = None
    default_split: str | None = None
    format: str | None = None
    framework: str | None = None
    license: str | None = None
    raw_policy: Literal["full", "external_ref", "hash_only", "none_for_tests_only"] = "full"


# ---------------------------------------------------------------------------
# Actors / Tools
# ---------------------------------------------------------------------------

class ActorDef(BaseModel):
    """An actor (agent, environment, human) participating in the trajectory."""

    model_config = ConfigDict(extra="forbid")
    actor_id: str
    kind: str
    name: str | None = None
    model: str | None = None


class ToolRegistryDef(BaseModel):
    """Registry of tools available to actors."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    from_: Any = Field(default=None, alias="from")
    item: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Episodes / Events
# ---------------------------------------------------------------------------

class EmitSpec(BaseModel):
    """Specification for how to emit a single event field."""

    model_config = ConfigDict(extra="forbid")
    event_id: Any = None
    idx: Any = None
    event_type: Any = None
    role: Any = None
    content: Any = None
    action: Any = None
    observation: Any = None
    actor_id: Any = None
    provenance: Any = None
    timestamp: Any = None
    metadata: Any = None


class EventMapping(BaseModel):
    """Maps source records to structured trajectory events."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    foreach: Any = None
    as_: str | None = Field(default=None, alias="as")
    index_as: str | None = None
    emit: EmitSpec | None = None
    emit_once: Any = None
    expand_tool_calls: Any = None


class EpisodeMapping(BaseModel):
    """Maps a source dataset row (or group of rows) to a single episode."""

    model_config = ConfigDict(extra="forbid")
    episode_id: Any = None
    task_id: Any = None
    events: list[EventMapping] = []


# ---------------------------------------------------------------------------
# Outcome
# ---------------------------------------------------------------------------

class OutcomeMapping(BaseModel):
    """Describes how to derive the outcome / pass-fail from the data."""

    model_config = ConfigDict(extra="forbid")
    status: Any = None
    passed: Any = None
    reward: Any = None
    final_patch_artifact_id: Any = None
    final_answer: Any = None
    failure_reason: Any = None


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

class Metadata(BaseModel):
    """Human-readable metadata for the trajectory format definition."""

    model_config = ConfigDict(extra="forbid")
    name: str
    title: str | None = None
    version: str = "0.1.0"
    description: str | None = None
    owners: list[str] = []
    tags: list[str] = []


# ---------------------------------------------------------------------------
# Top-level TrajectoryFormat
# ---------------------------------------------------------------------------

class TrajectoryFormat(BaseModel):
    """Root model for an AgentIR Format DSL v0.1 definition."""

    model_config = ConfigDict(extra="forbid")
    apiVersion: Literal["agentir.qitor.ai/v0.1"] = "agentir.qitor.ai/v0.1"
    kind: Literal["TrajectoryFormat"] = "TrajectoryFormat"
    metadata: Metadata
    source: SourceDef
    detect: DetectDef = Field(default_factory=DetectDef)
    vars: dict[str, Any] = {}
    source_overrides: dict[str, Any] = {}
    actors: list[ActorDef] = []
    tool_registry: ToolRegistryDef | None = None
    task: dict[str, Any] = {}
    artifacts: list[dict[str, Any]] = []
    episodes: list[EpisodeMapping] = []
    outcome: OutcomeMapping | None = None
    passes: Any = []
    quality: dict[str, Any] = {}
    performance: dict[str, Any] = {}


# Rebuild all models to resolve forward references.
# This is required for Pydantic v2.13+ when models reference each other
# or use typing.Literal in class bodies.
SourceDef.model_rebuild()
DetectRule.model_rebuild()
DetectDef.model_rebuild()
EmitSpec.model_rebuild()
EventMapping.model_rebuild()
EpisodeMapping.model_rebuild()
OutcomeMapping.model_rebuild()
ActorDef.model_rebuild()
ToolRegistryDef.model_rebuild()
Metadata.model_rebuild()
TrajectoryFormat.model_rebuild()
PathExpr.model_rebuild()
ConstExpr.model_rebuild()
TemplateExpr.model_rebuild()
TransformExpr.model_rebuild()
FirstOfExpr.model_rebuild()
VarRef.model_rebuild()

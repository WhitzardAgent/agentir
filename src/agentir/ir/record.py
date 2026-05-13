"""Top-level AgentIR record model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.actor import ActorSpec
from agentir.ir.artifact import Artifact
from agentir.ir.base import IRLevel
from agentir.ir.episode import Episode
from agentir.ir.outcome import Outcome
from agentir.ir.source import SourceRef
from agentir.ir.task import TaskSpec
from agentir.ir.tool import ToolSpec


class AgentIRRecord(BaseModel):
    """Top-level record in the AgentIR intermediate representation."""

    model_config = ConfigDict(extra="allow")

    ir_version: Literal["0.1.0"] = "0.1.0"
    record_id: str
    level: IRLevel
    source: SourceRef
    task: TaskSpec | None = None
    tool_registry: list[ToolSpec] = Field(default_factory=list)
    actors: list[ActorSpec] = Field(default_factory=list)
    episodes: list[Episode] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    outcome: Outcome | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

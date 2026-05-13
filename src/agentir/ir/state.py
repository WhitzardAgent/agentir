"""State snapshot and delta models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StateSnapshot(BaseModel):
    """Snapshot of the environment state at a point in time."""

    state_id: str
    after_event_id: str | None = None
    cwd: str | None = None
    repo: str | None = None
    commit: str | None = None
    files_modified: list[str] = Field(default_factory=list)
    patch_artifact_id: str | None = None
    memory: dict = Field(default_factory=dict)
    todos: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class StateDelta(BaseModel):
    """Delta of state changes between events."""

    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    creates: list[str] = Field(default_factory=list)
    deletes: list[str] = Field(default_factory=list)
    cwd_before: str | None = None
    cwd_after: str | None = None
    patch_artifact_id: str | None = None
    metadata: dict = Field(default_factory=dict)

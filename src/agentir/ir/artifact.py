"""Artifact model for files, patches, and other produced assets."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentir.ir.base import ArtifactKind


class Artifact(BaseModel):
    """An artifact produced or referenced during a trajectory."""

    artifact_id: str
    kind: ArtifactKind
    uri: str | None = None
    path: str | None = None
    content: str | None = None
    encoding: str | None = None
    mime_type: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    created_by_event_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

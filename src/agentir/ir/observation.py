"""Observation model for tool outputs and environment responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentir.ir.base import ObservationKind
from agentir.ir.content import ContentBlock


class Observation(BaseModel):
    """An observation returned from the environment or a tool."""

    kind: ObservationKind
    content: list[ContentBlock] = Field(default_factory=list)
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    error_type: str | None = None
    truncated: bool = False
    artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

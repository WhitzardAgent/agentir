"""Content block model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentir.ir.base import ContentType


class ContentBlock(BaseModel):
    """A block of content within an event."""

    type: ContentType
    text: str | None = None
    json_value: Any | None = None
    artifact_id: str | None = None
    mime_type: str | None = None
    metadata: dict = Field(default_factory=dict)

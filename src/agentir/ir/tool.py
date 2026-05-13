"""Tool specification model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    """Specification of an available tool."""

    tool_id: str
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    normalized_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

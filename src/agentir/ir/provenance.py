"""Provenance tracking model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Provenance information tracking the source of a field."""

    dataset: str | None = None
    config: str | None = None
    split: str | None = None
    row_id: str | None = None
    source_field: str | None = None
    row_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    parser: str | None = None
    confidence: float = 1.0
    metadata: dict = Field(default_factory=dict)

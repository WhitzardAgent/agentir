"""Source reference model for tracking dataset provenance."""

from __future__ import annotations

from pydantic import BaseModel


class SourceRef(BaseModel):
    """Reference to the original data source."""

    dataset: str | None = None
    dataset_url: str | None = None
    config: str | None = None
    split: str | None = None
    row_id: str | None = None
    row_index: int | None = None
    framework: str | None = None
    framework_version: str | None = None
    format: str | None = None
    license: str | None = None
    original_source: str | None = None
    original_teacher: str | None = None

"""Task specification models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EnvironmentSpec(BaseModel):
    """Specification of the execution environment."""

    kind: str | None = None
    cwd: str | None = None
    network: Literal["enabled", "disabled", "unknown"] = "unknown"
    sandbox: str | None = None
    image: str | None = None
    metadata: dict = Field(default_factory=dict)


class TaskSpec(BaseModel):
    """Specification of the task to be solved."""

    task_id: str | None = None
    instruction: str | None = None
    category: str | None = None
    subcategory: str | None = None
    benchmark: str | None = None
    repo: str | None = None
    base_commit: str | None = None
    issue_id: str | None = None
    environment: EnvironmentSpec | None = None
    metadata: dict = Field(default_factory=dict)
